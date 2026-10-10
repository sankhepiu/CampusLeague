from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

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
        # Membership does not exist yet (next step). Until then every user is
        # "none"; the plan's values are active, lapsed, none.
        return 'none'


class SignupSerializer(serializers.Serializer):
    # Only these fields are read. Anything else the client sends (is_staff,
    # roles, id) is ignored, so signup can never grant privileges.
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    name = serializers.CharField(max_length=150)
    college_id = serializers.CharField(max_length=50)
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


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()
