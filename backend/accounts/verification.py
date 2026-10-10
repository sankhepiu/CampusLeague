"""Email verification by one-time code. ASSUMPTION: beyond the backend plan.

Rules:
  - 6 digits from the secrets module (a cryptographic random source).
  - Stored only as a keyed hash; the plain code exists in the email alone.
  - Expires 10 minutes after it was sent.
  - Void after 5 wrong attempts.
  - Single use: a successful verification deletes it.
  - A new code replaces the previous one; at most one is sent per 60 seconds.
"""
import logging
import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import EmailVerificationCode, User

logger = logging.getLogger('campusleague.verification')

CODE_DIGITS = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_INTERVAL = timedelta(seconds=60)

OK, INVALID, EXPIRED, LOCKED = 'ok', 'invalid', 'expired', 'locked'


def hash_code(user_id, code):
    """HMAC-SHA256 of the code, keyed with the server's SECRET_KEY and bound
    to the user. A copy of the database alone does not reveal the codes, and
    one user's hash is useless for another user.
    """
    return salted_hmac('campusleague.email-otp', f'{user_id}:{code}', algorithm='sha256').hexdigest()


def new_code():
    return f'{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}'


def issue_code(user, now=None):
    """Create (or replace) the user's code and return it in plain text, for
    the email only. Replacing the row voids any earlier code and resets the
    attempt counter.
    """
    now = now or timezone.now()
    code = new_code()
    EmailVerificationCode.objects.update_or_create(user=user, defaults={
        'code_hash': hash_code(user.pk, code), 'sent_at': now, 'expires_at': now + CODE_TTL, 'attempts': 0,
    })
    return code


def email_code(user, code):
    """Send the code. A mail failure is logged, not raised: the account
    exists, and the user can ask for another code.
    """
    try:
        send_mail(
            subject='Your Campus League verification code',
            message=(
                f'Hi {user.name},\n\n'
                f'Your Campus League verification code is {code}\n\n'
                f'It expires in {int(CODE_TTL.total_seconds() // 60)} minutes. '
                'If you did not sign up, you can ignore this email.\n'
            ),
            from_email=None,
            recipient_list=[user.email],
        )
        return True
    except Exception:
        logger.exception('Could not send the verification code to user %s', user.pk)
        return False


def resend(email, now=None):
    """Send a fresh code if this is an unverified account that has not been
    sent one in the last 60 seconds. Says nothing about which of those was
    true: the caller answers the same way every time.
    """
    now = now or timezone.now()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(
            email=email.strip().lower(), is_active=True, email_verified=False,
        ).first()
        if user is None:
            return
        existing = EmailVerificationCode.objects.filter(user=user).first()
        if existing and now - existing.sent_at < RESEND_INTERVAL:
            return
        code = issue_code(user, now)
    email_code(user, code)


def verify(email, code, now=None):
    """Check a code. Returns (outcome, user): OK with the user, or INVALID,
    EXPIRED or LOCKED with None.

    A wrong guess is committed (the attempt counter must survive), so this
    returns an outcome and never raises for one.
    """
    now = now or timezone.now()
    with transaction.atomic():
        # Row lock on the user: simultaneous guesses are counted one by one,
        # so parallel requests cannot get more than MAX_ATTEMPTS tries.
        user = User.objects.select_for_update().filter(
            email=email.strip().lower(), is_active=True, email_verified=False,
        ).first()
        record = user and EmailVerificationCode.objects.filter(user=user).first()
        if record is None:
            # Unknown email, already verified, or no code issued: all look
            # the same as a wrong code.
            return INVALID, None
        if record.attempts >= MAX_ATTEMPTS:
            return LOCKED, None
        if now >= record.expires_at:
            return EXPIRED, None
        if not constant_time_compare(record.code_hash, hash_code(user.pk, code)):
            record.attempts += 1
            record.save(update_fields=['attempts', 'updated_at'])
            return (LOCKED if record.attempts >= MAX_ATTEMPTS else INVALID), None

        user.email_verified = True
        user.save(update_fields=['email_verified', 'updated_at'])
        record.delete()        # single use
        return OK, user
