from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit import services as audit

from . import roles, verification
from .models import RoleAssignment, RoleInvite
from .permissions import has_role
from .serializers import (
    LoginSerializer, ResendCodeSerializer, RoleAssignmentSerializer, RoleInviteCreateSerializer,
    RoleInviteSerializer, SignupSerializer, UserSerializer, VerifyEmailSerializer,
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


President = has_role('president')


class SelfAssignmentError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'You cannot nominate yourself for a role.'
    default_code = 'self_assignment'


class InvitePendingError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This person already has a pending invite for this role.'
    default_code = 'invite_pending'


class RoleAlreadyHeldError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This person already holds this role.'
    default_code = 'role_already_held'


class InviteNotPendingError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'invite_not_pending'


class NotTheNomineeError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Only the person invited can accept or decline.'
    default_code = 'not_the_nominee'


class LastPresidentError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'The club must keep at least one president. Hand the role over first.'
    default_code = 'last_president'


INVITES = RoleInvite.objects.select_related('user', 'invited_by')


def visible_invites(request):
    """A president sees every invite; everyone else sees their own."""
    if President().has_permission(request, None):
        return INVITES.all()
    return INVITES.filter(user=request.user)


class RoleListCreateView(ListAPIView):
    """GET /roles: the role assignments. POST /roles: nominate someone.
    President only (plan: "Assign roles, see audit log").

    ASSUMPTION (changes the plan's direct assignment): POST creates an
    invite. The role is granted when the nominee accepts it.
    """

    permission_classes = [President]
    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.order_by('-term_start', '-id')

    def post(self, request):
        serializer = RoleInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invite = roles.invite(inviter=request.user, **serializer.validated_data)
        except roles.SelfAssignment:
            raise SelfAssignmentError()
        except roles.InvitePending:
            raise InvitePendingError()
        except roles.RoleAlreadyHeld:
            raise RoleAlreadyHeldError()
        return Response(RoleInviteSerializer(invite).data, status=status.HTTP_201_CREATED)


class RoleEndView(APIView):
    """POST /roles/{id}/end. President only."""

    permission_classes = [President]

    def post(self, request, pk):
        get_object_or_404(RoleAssignment, pk=pk)
        try:
            assignment = roles.end_role(assignment_id=pk, actor=request.user)
        except roles.LastPresident:
            raise LastPresidentError()
        return Response({
            'ended': True,
            # null when the term had only just begun and the row was removed.
            'assignment': RoleAssignmentSerializer(assignment).data if assignment else None,
        })


class RoleInviteListView(ListAPIView):
    """GET /roles/invites. Any logged-in user: a president sees all
    invites, everyone else their own. ?status= filters.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RoleInviteSerializer

    def get_queryset(self):
        roles.expire_stale()
        invites = visible_invites(self.request)
        wanted = self.request.query_params.get('status')
        return invites.filter(status=wanted) if wanted else invites


class RoleInviteActionView(APIView):
    """POST /roles/invites/{id}/accept, /decline (the nominee) and /revoke
    (a president). An invite the caller may not see is a 404.
    """

    permission_classes = [IsAuthenticated]
    action = None

    def post(self, request, pk):
        get_object_or_404(visible_invites(request), pk=pk)
        try:
            if self.action == 'revoke':
                if not President().has_permission(request, self):
                    self.permission_denied(request)
                invite = roles.revoke(invite_id=pk, actor=request.user)
            else:
                invite = roles.respond(invite_id=pk, user=request.user, accept=self.action == 'accept')
        except roles.NotTheNominee:
            raise NotTheNomineeError()
        except roles.InviteNotPending as exc:
            raise InviteNotPendingError(f'This invite is {exc.status} and can no longer be changed.')
        return Response(RoleInviteSerializer(invite).data)
