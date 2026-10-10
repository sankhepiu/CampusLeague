from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from members.services import membership_status

from common.validation import college_id_validator

from .models import RoleAssignment, RoleInvite

User = get_user_model()

EMAIL_TAKEN = ErrorDetail('An account with this email already exists.', code='email_taken')


class UserSerializer(serializers.ModelSerializer):
    """The user object returned by signup, login and /auth/me."""

    roles = serializers.SerializerMethodField()
    membership_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'college_id', 'phone', 'roles', 'membership_status']
        read_only_fields = fields

    def get_roles(self, user):
        return user.current_roles()

    def get_membership_status(self, user):
        # active, lapsed or none, decided from Membership rows (never from
        # the "member" role).
        return membership_status(user)


class SignupSerializer(serializers.Serializer):
    # Only these fields are read. Anything else the client sends (is_staff,
    # roles, id) is ignored, so signup can never grant privileges.
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    name = serializers.CharField(max_length=150, min_length=2)
    college_id = serializers.CharField(max_length=20, validators=[college_id_validator])
    # ASSUMPTION (plan lists phone without a format): optional; if given,
    # 7 to 15 digits with an optional leading +.
    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default='',
        validators=[RegexValidator(r'^\+?\d{7,15}$', 'Enter a valid phone number.')],
    )

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(EMAIL_TAKEN)
        return value

    def validate(self, attrs):
        # Django's password validators (length, common passwords, similarity
        # to the user's own details). Their codes are kept for the frontend.
        candidate = User(email=attrs['email'], name=attrs['name'], college_id=attrs['college_id'])
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                'password': [
                    ErrorDetail(message, code=error.code or 'invalid')
                    for message, error in zip(exc.messages, exc.error_list)
                ]
            })
        return attrs

    def create(self, validated_data):
        try:
            # The savepoint keeps a failed INSERT from breaking any outer
            # transaction.
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError:
            # Two signups with the same email at the same moment: both pass
            # validate_email, the unique constraint stops the second.
            raise serializers.ValidationError({'email': [EMAIL_TAKEN]})


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)
    # Not validated as "6 digits" here: anything that is not the right code
    # is simply a wrong code (invalid_code), and counts as an attempt.
    code = serializers.CharField(max_length=20)


class ResendCodeSerializer(serializers.Serializer):
    # A plain string on purpose: a malformed address gets the same answer as
    # any other address with no account.
    email = serializers.CharField(max_length=254)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


class RoleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAssignment
        fields = ['id', 'user', 'role', 'term_start', 'term_end', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        if attrs['term_end'] < attrs['term_start']:
            raise serializers.ValidationError(
                {'term_end': [ErrorDetail('The term cannot end before it starts.', code='term_end_before_start')]}
            )
        return attrs


class RoleInviteCreateSerializer(serializers.Serializer):
    """Body of POST /roles. The term is optional: one year from today."""

    # Unverified or deactivated accounts are left out of the queryset, so
    # they are reported the same way as a user that does not exist.
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True, email_verified=True))
    role = serializers.ChoiceField(choices=RoleAssignment.Role.values)
    term_start = serializers.DateField(required=False)
    term_end = serializers.DateField(required=False)

    def validate(self, attrs):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        attrs.setdefault('term_start', today)
        attrs.setdefault('term_end', attrs['term_start'] + timedelta(days=365))
        if attrs['term_end'] < attrs['term_start']:
            raise serializers.ValidationError(
                {'term_end': [ErrorDetail('The term cannot end before it starts.', code='term_end_before_start')]}
            )
        if attrs['term_end'] < today:
            raise serializers.ValidationError(
                {'term_end': [ErrorDetail('This term is already over.', code='term_in_past')]}
            )
        return attrs


class RoleInviteSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    invited_by = serializers.SerializerMethodField()

    class Meta:
        model = RoleInvite
        fields = [
            'id', 'user', 'role', 'invited_by', 'status', 'term_start', 'term_end',
            'expires_at', 'created_at', 'responded_at',
        ]
        read_only_fields = fields

    def get_user(self, invite):
        return {'id': invite.user_id, 'name': invite.user.name, 'email': invite.user.email}

    def get_invited_by(self, invite):
        return {'id': invite.invited_by_id, 'name': invite.invited_by.name}
