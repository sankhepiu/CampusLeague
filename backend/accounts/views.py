from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import LoginSerializer, SignupSerializer, UserSerializer


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
        # User and token are created together or not at all.
        with transaction.atomic():
            user = serializer.save()
            token = Token.objects.create(user=user)
        return Response(session_payload(user, token), status=status.HTTP_201_CREATED)


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
        token, _ = Token.objects.get_or_create(user=user)
        return Response(session_payload(user, token))


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
