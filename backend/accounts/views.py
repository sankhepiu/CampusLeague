from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit import services as audit

from . import verification
from .models import RoleAssignment
from .permissions import has_role
from .serializers import (
    LoginSerializer, ResendCodeSerializer, RoleAssignmentSerializer, SignupSerializer, UserSerializer,
    VerifyEmailSerializer,
)


class InvalidCredentials(APIException):
    # One message for "no such email", "wrong password" and "inactive
    # account", so the response does not reveal which emails are registered.
    #
    # Not a subclass of AuthenticationFailed: DRF turns that into a 403 on
    # views with no authentication classes, and LoginView has none.
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Incorrect email or password.'
    default_code = 'invalid_credentials'
    # DRF's exception handler copies this into the WWW-Authenticate header,
    # which a 401 response is expected to carry.
    auth_header = 'Token'


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Verify your email address before logging in. Enter the code we emailed you.'
    default_code = 'email_not_verified'


class InvalidCode(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'That code is not correct.'
    default_code = 'invalid_code'


class CodeExpired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'That code has expired. Request a new one.'
    default_code = 'code_expired'


class TooManyAttempts(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = 'Too many wrong attempts. Request a new code.'
    default_code = 'too_many_attempts'


def session_payload(user, token):
    return {'token': token.key, 'user': UserSerializer(user).data}


class SignupView(APIView):
    # No authentication at all: a stale Authorization header must not turn
    # signup or login into a 401.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'signup'

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The account and its first code are saved together or not at all.
        # No token: the account cannot log in until the email is verified.
        with transaction.atomic():
            user = serializer.save()
            code = verification.issue_code(user)
        # Emailed only after the commit, so a code is never sent for an
        # account that was rolled back.
        verification.email_code(user, code)
        return Response({'verification_required': True, 'email': user.email}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    # Slows down password guessing.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            raise InvalidCredentials()
        # Checked only now, after the password matched. Someone who does not
        # know the password gets invalid_credentials whether or not the
        # account exists or is verified, so this reveals nothing to them.
        if not user.email_verified:
            raise EmailNotVerified()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(session_payload(user, token))


class VerifyEmailView(APIView):
    """POST /auth/verify-email. On success, the same body as login."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp'

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        outcome, user = verification.verify(**serializer.validated_data)
        if outcome == verification.LOCKED:
            raise TooManyAttempts()
        if outcome == verification.EXPIRED:
            raise CodeExpired()
        if outcome != verification.OK:
            raise InvalidCode()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(session_payload(user, token))


class ResendCodeView(APIView):
    """POST /auth/resend-code. Always answers {"sent": true}: whether the
    email belongs to an account, is already verified, or was sent a code a
    moment ago is not revealed.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp'

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification.resend(serializer.validated_data['email'])
        return Response({'sent': True})


class LogoutView(APIView):
    # The plan's table lists logout as Public, but the server can only end a
    # session it can identify, so a valid token is required.
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # request.auth is the Token that authenticated this request.
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # The user comes from the token, never from anything in the request
        # body or query string.
        return Response(UserSerializer(request.user).data)


class RoleListCreateView(ListCreateAPIView):
    """GET/POST /roles. President only (plan: "Assign roles, see audit log")."""

    permission_classes = [has_role('president')]
    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.order_by('-term_start', '-id')

    def perform_create(self, serializer):
        # The assignment and its audit row are saved together or not at all.
        with transaction.atomic():
            assignment = serializer.save()
            audit.record(
                actor=self.request.user,
                action='role.assigned',
                obj=assignment,
                after={
                    'user': assignment.user_id,
                    'role': assignment.role,
                    'term_start': assignment.term_start.isoformat(),
                    'term_end': assignment.term_end.isoformat(),
                },
            )
