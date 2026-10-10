"""Role invites (maker-checker) and ending a role.

ASSUMPTION: beyond the backend plan, which has the president assign roles
directly. Here the president invites; the role is granted only when the
nominee accepts.
"""
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit import services as audit

from .models import RoleAssignment, RoleInvite

logger = logging.getLogger('campusleague.roles')

INVITE_TTL = timedelta(hours=72)
PRESIDENT = RoleAssignment.Role.PRESIDENT


class SelfAssignment(Exception):
    """A president tried to invite themselves."""


class InvitePending(Exception):
    """This person already has an open invite for this role."""


class RoleAlreadyHeld(Exception):
    """This person already holds this role for a term that has not ended."""


class NotTheNominee(Exception):
    """Only the person invited can accept or decline."""


class InviteNotPending(Exception):
    """The invite was already accepted, declined, revoked or has expired."""

    def __init__(self, status):
        self.status = status
        super().__init__(f'This invite is {status}.')


class LastPresident(Exception):
    """Ending this role would leave the club with no president."""


def expire_stale(now=None):
    """Mark pending invites past their expiry as expired. Called before
    invites are read or written, so nobody sees a stale "pending"."""
    now = now or timezone.now()
    return RoleInvite.objects.filter(status=RoleInvite.Status.PENDING, expires_at__lte=now).update(
        status=RoleInvite.Status.EXPIRED, updated_at=now,
    )


def invite(*, inviter, user, role, term_start, term_end, now=None, notify=True):
    """Offer `user` a role. Grants nothing: see respond().
    notify=False skips the email (the demo seed uses it).
    """
    now = now or timezone.now()
    if user.pk == inviter.pk:
        raise SelfAssignment()
    expire_stale(now)
    today = timezone.localdate()
    if RoleAssignment.objects.filter(user=user, role=role, term_end__gte=today).exists():
        raise RoleAlreadyHeld()
    try:
        with transaction.atomic():
            role_invite = RoleInvite.objects.create(
                user=user, role=role, invited_by=inviter, term_start=term_start, term_end=term_end,
                expires_at=now + INVITE_TTL,
            )
            audit.record(
                actor=inviter, action='role.invited', obj=role_invite,
                after={
                    'user': user.pk, 'role': role,
                    'term_start': term_start.isoformat(), 'term_end': term_end.isoformat(),
                },
            )
    except IntegrityError:
        # The unique constraint: an open invite for this person and role
        # already exists (possibly created a moment ago by another request).
        raise InvitePending()
    if notify:
        email_invite(role_invite)
    return role_invite


def email_invite(role_invite):
    """Tell the nominee. A mail failure is logged, not raised: the invite
    exists and is listed in the app either way.
    """
    role = role_invite.role.replace('_', ' ')
    try:
        send_mail(
            subject=f'You have been nominated as {role}',
            message=(
                f'Hi {role_invite.user.name},\n\n'
                f'{role_invite.invited_by.name} has nominated you as {role} of the club, '
                f'from {role_invite.term_start:%d %b %Y} to {role_invite.term_end:%d %b %Y}.\n\n'
                'Log in to Campus League and open Settings to accept or decline. '
                f'The invitation expires in {int(INVITE_TTL.total_seconds() // 3600)} hours.\n'
            ),
            from_email=None,
            recipient_list=[role_invite.user.email],
        )
        return True
    except Exception:
        logger.exception('Could not email role invite %s', role_invite.pk)
        return False


def _open_invite(invite_id, now):
    """The invite, row-locked, if it can still be answered."""
    role_invite = RoleInvite.objects.select_for_update().select_related('user', 'invited_by').get(pk=invite_id)
    if role_invite.status == RoleInvite.Status.PENDING and role_invite.expires_at <= now:
        role_invite.status = RoleInvite.Status.EXPIRED
        role_invite.save(update_fields=['status', 'updated_at'])
    return role_invite


def _close(role_invite, status, now):
    role_invite.status = status
    role_invite.responded_at = now
    role_invite.save(update_fields=['status', 'responded_at', 'assignment', 'updated_at'])
    return role_invite


def respond(*, invite_id, user, accept, now=None):
    """The nominee accepts or declines. Accepting creates the
    RoleAssignment and its audit row in the same transaction as the
    invite's change of status: all of it happens or none of it.
    """
    now = now or timezone.now()
    outcome = None
    with transaction.atomic():
        role_invite = _open_invite(invite_id, now)
        if role_invite.user_id != user.pk:
            raise NotTheNominee()
        if role_invite.status != RoleInvite.Status.PENDING:
            # Not raised here: raising would roll back the "expired" update
            # just made by _open_invite.
            outcome = InviteNotPending(role_invite.status)
        elif not accept:
            _close(role_invite, RoleInvite.Status.DECLINED, now)
            audit.record(actor=user, action='role.invite_declined', obj=role_invite, after={'role': role_invite.role})
        else:
            assignment = RoleAssignment.objects.create(
                user=user, role=role_invite.role,
                term_start=role_invite.term_start, term_end=role_invite.term_end,
            )
            role_invite.assignment = assignment
            _close(role_invite, RoleInvite.Status.ACCEPTED, now)
            audit.record(
                actor=user, action='role.assigned', obj=assignment,
                after={
                    'user': user.pk, 'role': assignment.role,
                    'term_start': assignment.term_start.isoformat(),
                    'term_end': assignment.term_end.isoformat(),
                    'invite': role_invite.pk, 'invited_by': role_invite.invited_by_id,
                },
            )
    if outcome:
        raise outcome
    return role_invite


def revoke(*, invite_id, actor, now=None):
    """A president withdraws an invite that has not been answered."""
    now = now or timezone.now()
    outcome = None
    with transaction.atomic():
        role_invite = _open_invite(invite_id, now)
        if role_invite.status != RoleInvite.Status.PENDING:
            outcome = InviteNotPending(role_invite.status)
        else:
            _close(role_invite, RoleInvite.Status.REVOKED, now)
            audit.record(
                actor=actor, action='role.invite_revoked', obj=role_invite,
                after={'user': role_invite.user_id, 'role': role_invite.role},
            )
    if outcome:
        raise outcome
    return role_invite


def end_role(*, assignment_id, actor):
    """End a role now. Its last day becomes yesterday; a term that had not
    reached its second day is removed instead (a term cannot end before it
    starts). Refuses to leave the club without a current president.

    Returns the assignment, or None if the row was removed.
    """
    today = timezone.localdate()
    with transaction.atomic():
        # Every current president row is locked, so two presidents ending
        # each other's terms at the same moment are handled one at a time
        # and the second is refused.
        presidents = list(
            RoleAssignment.objects.select_for_update()
            .filter(role=PRESIDENT, term_start__lte=today, term_end__gte=today)
        )
        assignment = RoleAssignment.objects.select_for_update().get(pk=assignment_id)
        is_current_president = any(row.pk == assignment.pk for row in presidents)
        if is_current_president and not any(row.pk != assignment.pk for row in presidents):
            raise LastPresident()

        before = {
            'user': assignment.user_id, 'role': assignment.role,
            'term_start': assignment.term_start.isoformat(), 'term_end': assignment.term_end.isoformat(),
        }
        yesterday = today - timedelta(days=1)
        if assignment.term_end < today:
            return assignment                       # already over: nothing to do
        if assignment.term_start <= yesterday:
            assignment.term_end = yesterday
            assignment.save(update_fields=['term_end', 'updated_at'])
            audit.record(
                actor=actor, action='role.ended', obj=assignment, before=before,
                after={**before, 'term_end': yesterday.isoformat()},
            )
            return assignment
        audit.record(actor=actor, action='role.ended', obj=assignment, before=before, after=None)
        assignment.delete()
        return None
