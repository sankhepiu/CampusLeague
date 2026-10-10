from django.db import IntegrityError, transaction

from audit.models import AuditLog
from common.testing import ApiTestCase
from events.tests.helpers import make_event
from insights.models import SaveFile

SAVEFILES = '/api/savefiles'


class SaveFileTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.manager = self.make_role_user('event_manager')
        self.event = make_event(title='Freshers Night')
        self.login_as(self.manager)

    def post(self, **overrides):
        body = {
            'event': self.event.id, 'vendors': 'Beatbox Audio', 'budget_notes': 'Sound was half the budget',
            'what_worked': 'QR check-in', 'what_didnt': 'Snacks ran out', 'checklist': ['Book venue', 'Order snacks'],
        }
        body.update(overrides)
        return self.client.post(SAVEFILES, {k: v for k, v in body.items() if v != 'OMIT'}, format='json')


class SaveFileTests(SaveFileTestCase):
    def test_create_a_save_file_for_an_event(self):
        response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        save_file = SaveFile.objects.get()
        self.assertEqual(body['event'], {'id': self.event.id, 'title': 'Freshers Night'})
        self.assertEqual((body['vendors'], body['what_didnt'], body['checklist']),
                         ('Beatbox Audio', 'Snacks ran out', ['Book venue', 'Order snacks']))
        self.assertEqual(body['id'], save_file.id)
        self.assertEqual(set(body), {'id', 'event', 'vendors', 'budget_notes', 'what_worked', 'what_didnt', 'checklist', 'updated_at'})

    def test_creating_is_audited_with_the_author(self):
        self.post()
        log = AuditLog.objects.get()
        self.assertEqual((log.actor, log.action, log.object_type, log.object_id),
                         (self.manager, 'savefile.created', 'insights.savefile', SaveFile.objects.get().id))
        self.assertIsNone(log.before)
        self.assertEqual(log.after['vendors'], 'Beatbox Audio')
        self.assertEqual(log.after['checklist'], ['Book venue', 'Order snacks'])

    def test_posting_again_for_the_same_event_edits_the_one_file(self):
        first = self.post().json()
        president = self.make_role_user('president')
        self.login_as(president)

        response = self.client.post(SAVEFILES, {'event': self.event.id, 'what_didnt': 'Snacks ran out by 9 pm'}, format='json')

        self.assertEqual(response.status_code, 200, response.content)      # updated, not created
        body = response.json()
        self.assertEqual(SaveFile.objects.count(), 1)
        self.assertEqual(body['id'], first['id'])
        self.assertEqual(body['what_didnt'], 'Snacks ran out by 9 pm')
        self.assertEqual(body['vendors'], 'Beatbox Audio')                 # fields not sent are kept

    def test_each_edit_is_audited_with_before_and_after_of_what_changed(self):
        self.post()
        president = self.make_role_user('president')
        self.login_as(president)
        self.client.post(SAVEFILES, {'event': self.event.id, 'what_didnt': 'Too few bins',
                                     'vendors': 'Beatbox Audio', 'checklist': ['Book venue']}, format='json')

        created, updated = AuditLog.objects.order_by('id')
        self.assertEqual((updated.actor, updated.action), (president, 'savefile.updated'))
        # vendors was re-sent unchanged, so it is not in the diff.
        self.assertEqual(updated.before, {'what_didnt': 'Snacks ran out', 'checklist': ['Book venue', 'Order snacks']})
        self.assertEqual(updated.after, {'what_didnt': 'Too few bins', 'checklist': ['Book venue']})

    def test_saving_with_no_changes_writes_no_audit_row(self):
        self.post()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_fields_can_be_cleared(self):
        self.post()
        body = self.client.post(SAVEFILES, {'event': self.event.id, 'vendors': '', 'checklist': []}, format='json').json()
        self.assertEqual((body['vendors'], body['checklist']), ('', []))

    def test_only_the_event_is_required(self):
        response = self.client.post(SAVEFILES, {'event': self.event.id}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()['vendors'], response.json()['checklist']), ('', []))

    def test_database_allows_one_save_file_per_event(self):
        self.post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaveFile.objects.create(event=self.event)
        self.assertEqual(SaveFile.objects.count(), 1)

    def test_invalid_input_is_refused_and_not_audited(self):
        cases = [
            ('event', 'OMIT'), ('event', 999999), ('event', 'gala'),
            ('vendors', 'x' * 5001), ('vendors', ['a', 'list']),
            ('checklist', 'not a list'), ('checklist', ['ok', 'y' * 201]), ('checklist', ['item'] * 51), ('checklist', [{'a': 1}]),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=str(value)[:20]):
                response = self.post(**{field: value})
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()['code'], 'validation_error')
                self.assertTrue(response.json()['field'].startswith(field))
        self.assertEqual(SaveFile.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_list_and_filter_by_event(self):
        other = make_event(title='Meetup')
        self.post()
        self.post(event=other.id, vendors='Board game cafe')

        everything = self.client.get(SAVEFILES).json()
        only = self.client.get(SAVEFILES, {'event': other.id}).json()

        self.assertEqual(everything['count'], 2)
        self.assertEqual([item['vendors'] for item in only['results']], ['Board game cafe'])
        self.assertEqual(self.client.get(SAVEFILES, {'event': 999999}).json()['count'], 0)
        self.assert_error(self.client.get(SAVEFILES, {'event': 'gala'}), 400, 'validation_error', field='event')


class SaveFilePermissionTests(SaveFileTestCase):
    def test_event_manager_and_president_may_read_and_write(self):
        self.login_as(self.make_role_user('president'))
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.client.get(SAVEFILES).status_code, 200)
        self.login_as(self.manager)
        self.assertEqual(self.post(vendors='Changed').status_code, 200)
        self.assertEqual(self.client.get(SAVEFILES).status_code, 200)

    def test_everyone_else_is_refused_for_both_reading_and_writing(self):
        refused = [self.make_role_user(role) for role in ['treasurer', 'volunteer_coordinator', 'member']] + [self.make_user()]
        for user in refused:
            with self.subTest(user=user.email):
                self.login_as(user)
                self.assert_error(self.post(), 403, 'permission_denied')
                self.assert_error(self.client.get(SAVEFILES), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.post(), 401, 'not_authenticated')
        self.assert_error(self.client.get(SAVEFILES), 401, 'not_authenticated')
        self.assertEqual(SaveFile.objects.count(), 0)

    def test_next_years_event_manager_can_read_what_last_years_wrote(self):
        self.post()
        successor = self.make_user(email='next@example.com', name='Next Manager', college_id='SSA-NEXT')
        self.give_role(successor, 'event_manager')
        # ...and last year's manager has stepped down.
        from accounts.models import RoleAssignment
        RoleAssignment.objects.filter(user=self.manager).delete()
        self.give_role(self.manager, 'event_manager', start_offset=-400, end_offset=-1)

        self.login_as(successor)
        self.assertEqual(self.client.get(SAVEFILES).json()['results'][0]['vendors'], 'Beatbox Audio')
        self.login_as(self.manager)
        self.assert_error(self.client.get(SAVEFILES), 403, 'permission_denied')
