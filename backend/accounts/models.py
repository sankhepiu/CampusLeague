from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('An email address is required.')
        # ASSUMPTION (plan says only "email (unique)"): emails are stored in
        # lowercase so Priya@x.com and priya@x.com cannot be two accounts.
        email = email.strip().lower()
        user = self.model(email=email, **extra_fields)
        # set_password hashes with Django's default hasher; the raw password
        # is never stored. None gives an unusable password (login impossible).
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        # Created by an operator at the command line, not by public signup.
        extra_fields.setdefault('email_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """Plan, data model: "User: email (unique), password, name, college_id,
    phone. One account per person."

    Club roles (president, treasurer, ...) are NOT stored here; they come
    from RoleAssignment. is_staff and is_superuser only control access to the
    Django admin, which the plan keeps as a fallback for demo data.
    """

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    college_id = models.CharField(max_length=50)
    # ASSUMPTION (plan is silent on which fields are required): phone is
    # optional; name and college_id are required, as R1 lists them for signup.
    phone = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # ASSUMPTION (beyond the plan): an account must prove it controls its
    # email address, with a one-time code, before it can log in.
    email_verified = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    # Extra prompts for `manage.py createsuperuser` (email and password are
    # always asked).
    REQUIRED_FIELDS = ['name', 'college_id']

    def __str__(self):
        return self.email

    def current_roles(self):
        """Plan: '"current role" = term includes today'. Sorted, no repeats."""
        today = timezone.localdate()
        return sorted(set(
            self.role_assignments
            .filter(term_start__lte=today, term_end__gte=today)
            .values_list('role', flat=True)
        ))


class RoleAssignment(TimeStampedModel):
    """Plan, data model: "RoleAssignment: user FK, role, term_start,
    term_end. Leadership changes yearly; a user can hold several roles."

    Access changes automatically when a term starts or ends: nothing is
    edited, the date simply moves past term_end.
    """

    class Role(models.TextChoices):
        PRESIDENT = 'president'
        TREASURER = 'treasurer'
        EVENT_MANAGER = 'event_manager'
        VOLUNTEER_COORDINATOR = 'volunteer_coordinator'
        # Kept as the plan lists it. Membership checks read from Membership,
        # never from this role.
        MEMBER = 'member'

    # PROTECT: a user with leadership history cannot be deleted out from
    # under it.
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='role_assignments')
    role = models.CharField(max_length=30, choices=Role.choices)
    # ASSUMPTION (plan says only "term includes today"): both dates are
    # inclusive calendar days in the club's time zone.
    term_start = models.DateField()
    term_end = models.DateField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(term_end__gte=models.F('term_start')),
                name='role_term_end_not_before_start',
            ),
            # choices are only checked by forms and serializers; this makes
            # the database refuse an unknown role too.
            models.CheckConstraint(
                condition=models.Q(role__in=[
                    'president', 'treasurer', 'event_manager',
                    'volunteer_coordinator', 'member',
                ]),
                name='role_is_known',
            ),
        ]

    def __str__(self):
        return f'{self.user} {self.role} {self.term_start} to {self.term_end}'


class EmailVerificationCode(TimeStampedModel):
    """The one-time code most recently emailed to a user (ASSUMPTION: beyond
    the plan). One row per user: sending a new code overwrites the old one,
    which is what makes a resend void the previous code.

    The code itself is never stored, only a keyed hash of it. See
    accounts.verification.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification_code')
    code_hash = models.CharField(max_length=64)
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    # Wrong guesses against this code.
    attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f'Verification code for {self.user}'
