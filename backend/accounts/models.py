from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

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

    objects = UserManager()

    USERNAME_FIELD = 'email'
    # Extra prompts for `manage.py createsuperuser` (email and password are
    # always asked).
    REQUIRED_FIELDS = ['name', 'college_id']

    def __str__(self):
        return self.email
