from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from comms import services
from comms.models import Announcement, AnnouncementDelivery
from common.testing import ApiTestCase
from events.tests.helpers import make_member

ANNOUNCEMENTS = '/api/announcements'
BODY = {'title': 'Gala tickets on sale', 'body': 'Doors open at 7. Members get a discount.'}


def broken(*args, **kwargs):
    raise ConnectionRefusedError('smtp server unreachable')


class AnnouncementTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.president = self.make_role_user('president')
        self.asha = self.make_user(email='asha@example.com', name='Asha', college_id='SSA-A')
        self.ravi = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-R')
        self.login_as(self.president)

    def post(self, **overrides):
        return self.client.post(ANNOUNCEMENTS, {**BODY, **overrides}, format='json')

    def statuses(self):
        return sorted(AnnouncementDelivery.objects.values_list('recipient__email', 'status', 'attempts'))


class PostAnnouncementTests(AnnouncementTestCase):
    def test_one_post_is_saved_and_emailed_to_everyone(self):
        response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['author'], {'id': self.president.id, 'name': self.president.name})
        self.assertEqual(body['deliveries'], {'recipients': 3, 'queued': 0, 'sent': 3, 'failed': 0})
        self.assertEqual(sorted(m.to[0] for m in mail.outbox),
                         ['asha@example.com', 'president@example.com', 'ravi@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Gala tickets on sale')
        self.assertIn('Doors open at 7', mail.outbox[0].body)
        self.assertTrue(all(len(m.to) == 1 for m in mail.outbox))   # nobody sees another's address

    def test_author_and_time_come_from_the_server(self):
        self.post(author=self.asha.id, published_at='2001-01-01T00:00:00Z')
        announcement = Announcement.objects.get()
        self.assertEqual(announcement.author, self.president)
        self.assertLess(timezone.now() - announcement.published_at, timedelta(minutes=1))

    def test_members_audience_reaches_only_current_members(self):
        make_member(self.asha)
        make_member(self.ravi, days_left=-1)     # lapsed
        self.post(audience='members')
        self.assertEqual([m.to[0] for m in mail.outbox], ['asha@example.com'])

    def test_inactive_accounts_are_not_emailed(self):
        self.ravi.is_active = False
        self.ravi.save()
        self.post()
        self.assertNotIn('ravi@example.com', [m.to[0] for m in mail.outbox])

    def test_invalid_posts_are_refused_and_send_nothing(self):
        for overrides, field in [({'title': ''}, 'title'), ({'body': '  '}, 'body'),
                                 ({'title': 'x' * 201}, 'title'), ({'audience': 'everyone'}, 'audience')]:
            with self.subTest(field=field):
                self.assert_error(self.post(**overrides), 400, 'validation_error', field=field)
        self.assertEqual(Announcement.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_only_president_event_manager_and_volunteer_coordinator_may_post(self):
        for role, allowed in [('event_manager', True), ('volunteer_coordinator', True), ('treasurer', False), ('member', False)]:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                response = self.post(title=f'From {role}')
                if allowed:
                    self.assertEqual(response.status_code, 201, response.content)
                else:
                    self.assert_error(response, 403, 'permission_denied')
        self.login_as(self.asha)
        self.assert_error(self.post(), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.post(), 401, 'not_authenticated')
        self.assertEqual(Announcement.objects.count(), 2)


class EmailFailureTests(AnnouncementTestCase):
    """Plan: "Break the email backend; announcement is still saved and shows
    failed deliveries."
    """

    def test_broken_email_still_saves_the_announcement_and_records_failures(self):
        with mock.patch('comms.services.send_mail', side_effect=broken):
            with self.assertLogs('campusleague.comms', level='WARNING'):
                response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['deliveries'], {'recipients': 3, 'queued': 0, 'sent': 0, 'failed': 3})
        self.assertEqual(Announcement.objects.get().title, 'Gala tickets on sale')
        for delivery in AnnouncementDelivery.objects.all():
            self.assertEqual((delivery.status, delivery.attempts), ('failed', 1))
            self.assertEqual(delivery.last_error, 'ConnectionRefusedError: smtp server unreachable')
        # ...and it is in the public archive regardless.
        self.client.credentials()
        self.assertEqual(self.client.get(ANNOUNCEMENTS).json()['results'][0]['title'], 'Gala tickets on sale')

    def test_one_bad_address_does_not_stop_the_others(self):
        def flaky(subject, message, from_email, recipient_list):
            if recipient_list == ['asha@example.com']:
                raise ValueError('mailbox does not exist')

        with mock.patch('comms.services.send_mail', side_effect=flaky):
            with self.assertLogs('campusleague.comms', level='WARNING'):
                body = self.post().json()

        self.assertEqual(body['deliveries'], {'recipients': 3, 'queued': 0, 'sent': 2, 'failed': 1})
        self.assertEqual(self.statuses(), [
            ('asha@example.com', 'failed', 1), ('president@example.com', 'sent', 1), ('ravi@example.com', 'sent', 1),
        ])

    def test_retry_sends_only_the_failed_ones_once_email_works_again(self):
        with mock.patch('comms.services.send_mail', side_effect=broken), self.assertLogs('campusleague.comms', level='WARNING'):
            self.post()
        self.assertEqual(mail.outbox, [])

        with mock.patch('sys.stdout.write') as write:
            call_command('send_announcements')

        self.assertIn('Sent: 3  Failed: 0', write.call_args_list[0][0][0])
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual({(status, attempts) for _, status, attempts in self.statuses()}, {('sent', 2)})

        call_command('send_announcements', stdout=mock.Mock())     # nothing left to do
        self.assertEqual(len(mail.outbox), 3)                       # nobody emailed twice

    def test_gives_up_after_three_attempts(self):
        with mock.patch('comms.services.send_mail', side_effect=broken) as send, self.assertLogs('campusleague.comms', level='WARNING'):
            self.post()
            for _ in range(5):
                services.send_pending()

        self.assertEqual(send.call_count, 9)        # 3 recipients x 3 attempts, then no more
        self.assertEqual({(status, attempts) for _, status, attempts in self.statuses()}, {('failed', 3)})

    def test_database_allows_one_delivery_per_recipient(self):
        self.post()
        announcement = Announcement.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnnouncementDelivery.objects.create(announcement=announcement, recipient=self.asha)


class ArchiveTests(AnnouncementTestCase):
    def setUp(self):
        super().setUp()
        self.post(title='First')
        self.post(title='Second')
        self.first, self.second = Announcement.objects.order_by('id')

    def test_public_archive_is_newest_first_with_author_and_time(self):
        self.client.credentials()
        body = self.client.get(ANNOUNCEMENTS).json()

        self.assertEqual([a['title'] for a in body['results']], ['Second', 'First'])
        item = body['results'][0]
        self.assertEqual(item['author']['name'], self.president.name)
        self.assertTrue(item['published_at'])
        self.assertIsNone(item['deliveries'])                      # not for the public
        self.assertNotIn('example.com', str(body))                 # no email addresses

    def test_public_detail(self):
        self.client.credentials()
        response = self.client.get(f'{ANNOUNCEMENTS}/{self.first.id}')
        self.assertEqual(response.json()['title'], 'First')
        self.assert_error(self.client.get(f'{ANNOUNCEMENTS}/999999'), 404, 'not_found')

    def test_comms_staff_see_delivery_counts_and_the_log(self):
        detail = self.client.get(f'{ANNOUNCEMENTS}/{self.first.id}').json()
        self.assertEqual(detail['deliveries']['sent'], 3)

        log = self.client.get(f'{ANNOUNCEMENTS}/{self.first.id}/deliveries').json()
        self.assertEqual(log['count'], 3)
        self.assertEqual(log['results'][0]['status'], 'sent')
        self.assertIn('email', log['results'][0]['recipient'])

    def test_delivery_log_is_not_for_members_or_the_public(self):
        url = f'{ANNOUNCEMENTS}/{self.first.id}/deliveries'
        self.login_as(self.asha)
        self.assert_error(self.client.get(url), 403, 'permission_denied')
        self.login_as(self.make_role_user('treasurer'))
        self.assert_error(self.client.get(url), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.get(url), 401, 'not_authenticated')

    def test_announcements_cannot_be_edited_or_deleted_through_the_api(self):
        url = f'{ANNOUNCEMENTS}/{self.first.id}'
        self.assert_error(self.client.patch(url, {'title': 'Rewritten'}, format='json'), 405, 'method_not_allowed')
        self.assert_error(self.client.delete(url), 405, 'method_not_allowed')
        self.first.refresh_from_db()
        self.assertEqual(self.first.title, 'First')
