from datetime import timedelta

from django.utils import timezone

from common.testing import ApiTestCase
from finance.models import LedgerEntry
from finance.services import account_balance
from volunteering.models import Fundraiser, FundraiserSale, Task, TaskAssignment
from volunteering.services import progress, record_sale

FUNDRAISERS = '/api/fundraisers'


class VolunteeringTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.coordinator = self.make_role_user('volunteer_coordinator')
        self.volunteer = self.make_user()
        self.fundraiser = Fundraiser.objects.create(
            title='Bake Sale', goal_amount=100000,
            starts_on=self.today - timedelta(days=4), ends_on=self.today + timedelta(days=5),   # day 5 of 10
        )
        self.baking = Task.objects.create(fundraiser=self.fundraiser, title='Baking')
        self.supplies = Task.objects.create(fundraiser=self.fundraiser, title='Supplies', status='done')
        self.table = Task.objects.create(fundraiser=self.fundraiser, title='Table')
        TaskAssignment.objects.create(task=self.baking, user=self.volunteer, role_note='Brownies')
        self.login_as(self.coordinator)


class FundraiserBoardTests(VolunteeringTestCase):
    def test_board_shows_tasks_owners_and_progress_at_a_glance(self):
        record_sale(fundraiser=self.fundraiser, amount=60000, recorded_by=self.coordinator)
        self.login_as(self.volunteer)

        body = self.client.get(f'{FUNDRAISERS}/{self.fundraiser.id}').json()

        self.assertEqual(body['progress'], {
            'goal_amount': 100000, 'raised_amount': 60000, 'raised_pct': 60.0,
            'tasks_total': 3, 'tasks_done': 1, 'on_track': True,       # 60% raised, 50% of the time gone
        })
        tasks = {task['title']: task for task in body['tasks']}
        self.assertEqual(tasks['Baking']['assignees'], [{'id': self.volunteer.id, 'name': 'Priya', 'role_note': 'Brownies'}])
        self.assertEqual(tasks['Table']['assignees'], [])              # "what's left, who's doing it"
        self.assertEqual(tasks['Supplies']['status'], 'done')

    def test_raised_amount_comes_from_the_ledger_not_a_stored_total(self):
        record_sale(fundraiser=self.fundraiser, amount=25000, recorded_by=self.coordinator, note='Morning')
        record_sale(fundraiser=self.fundraiser, amount=15000, recorded_by=self.coordinator, note='Afternoon')
        other = Fundraiser.objects.create(title='Car Wash', goal_amount=50000, starts_on=self.today, ends_on=self.today)
        record_sale(fundraiser=other, amount=9000, recorded_by=self.coordinator)

        self.assertEqual(progress(self.fundraiser)['raised_amount'], 40000)
        self.assertEqual(progress(other)['raised_amount'], 9000)
        self.assertEqual(account_balance('4300'), 49000)
        self.assertEqual(account_balance('1000'), 49000)
        self.assertFalse(any(field.name == 'raised_amount' for field in Fundraiser._meta.get_fields()))

    def test_on_track_flag_follows_goal_and_time(self):
        self.assertFalse(progress(self.fundraiser)['on_track'])        # nothing raised, half the time gone
        record_sale(fundraiser=self.fundraiser, amount=49999, recorded_by=self.coordinator)
        self.assertFalse(progress(self.fundraiser)['on_track'])
        record_sale(fundraiser=self.fundraiser, amount=1, recorded_by=self.coordinator)
        self.assertTrue(progress(self.fundraiser)['on_track'])         # exactly 50% at 50% of the time
        self.assertTrue(progress(self.fundraiser, today=self.fundraiser.starts_on - timedelta(days=3))['on_track'])
        self.assertFalse(progress(self.fundraiser, today=self.fundraiser.ends_on + timedelta(days=30))['on_track'])

    def test_raised_pct_is_capped_at_100(self):
        record_sale(fundraiser=self.fundraiser, amount=250000, recorded_by=self.coordinator)
        self.assertEqual(progress(self.fundraiser)['raised_pct'], 100.0)
        self.assertEqual(progress(self.fundraiser)['raised_amount'], 250000)

    def test_list_needs_a_login(self):
        self.login_as(self.volunteer)
        self.assertEqual(self.client.get(FUNDRAISERS).json()['count'], 1)
        self.client.credentials()
        self.assert_error(self.client.get(FUNDRAISERS), 401, 'not_authenticated')


class SaleTests(VolunteeringTestCase):
    def test_recording_a_sale_posts_one_balanced_ledger_entry(self):
        response = self.client.post(f'{FUNDRAISERS}/{self.fundraiser.id}/sales', {'amount': 30000, 'note': 'Saturday'}, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['progress']['raised_amount'], 30000)
        sale, entry = FundraiserSale.objects.get(), LedgerEntry.objects.get()
        self.assertEqual(sale.recorded_by, self.coordinator)
        self.assertEqual((entry.source_type, entry.source_id, entry.kind), ('fundraiser_sale', sale.id, 'fundraiser_sale'))
        self.assertEqual(sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
                         [('1000', 30000, 0), ('4300', 0, 30000)])

    def test_invalid_sales_are_refused(self):
        for amount in [0, -100, 'lots', None, 1.5]:
            with self.subTest(amount=amount):
                response = self.client.post(f'{FUNDRAISERS}/{self.fundraiser.id}/sales', {'amount': amount}, format='json')
                self.assert_error(response, 400, 'validation_error', field='amount')
        self.assertEqual(FundraiserSale.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_only_coordinators_record_sales(self):
        for user in [self.volunteer, self.make_role_user('treasurer'), self.make_role_user('event_manager')]:
            self.login_as(user)
            response = self.client.post(f'{FUNDRAISERS}/{self.fundraiser.id}/sales', {'amount': 500}, format='json')
            self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(account_balance('4300'), 0)


class ManagementTests(VolunteeringTestCase):
    def body(self, **overrides):
        body = {'title': 'Car Wash', 'goal_amount': 50000, 'starts_on': self.today.isoformat(),
                'ends_on': (self.today + timedelta(days=7)).isoformat()}
        body.update(overrides)
        return body

    def test_coordinator_creates_and_edits_a_fundraiser(self):
        created = self.client.post(FUNDRAISERS, self.body(), format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()['progress']['raised_amount'], 0)

        patched = self.client.patch(f"{FUNDRAISERS}/{created.json()['id']}", {'goal_amount': 80000}, format='json')
        self.assertEqual(patched.json()['goal_amount'], 80000)

    def test_invalid_fundraisers_are_refused(self):
        cases = [({'goal_amount': 0}, 'goal_amount'), ({'title': ''}, 'title'), ({'status': 'cancelled'}, 'status'),
                 ({'ends_on': (self.today - timedelta(days=1)).isoformat()}, 'ends_on'), ({'starts_on': 'soon'}, 'starts_on')]
        for overrides, field in cases:
            with self.subTest(field=field):
                self.assert_error(self.client.post(FUNDRAISERS, self.body(**overrides), format='json'), 400, 'validation_error', field=field)
        self.assertEqual(Fundraiser.objects.count(), 1)

    def test_coordinator_creates_assigns_and_edits_tasks(self):
        created = self.client.post('/api/tasks', {'fundraiser': self.fundraiser.id, 'title': 'Posters'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        task_id = created.json()['id']
        self.assertEqual(created.json()['status'], 'todo')

        assigned = self.client.post(f'/api/tasks/{task_id}/assign', {'user': self.volunteer.id, 'role_note': 'Design'}, format='json')
        self.assertEqual(assigned.json()['assignees'][0]['role_note'], 'Design')
        again = self.client.post(f'/api/tasks/{task_id}/assign', {'user': self.volunteer.id, 'role_note': 'Print'}, format='json')
        self.assertEqual(again.json()['assignees'], [{'id': self.volunteer.id, 'name': 'Priya', 'role_note': 'Print'}])

        edited = self.client.patch(f'/api/tasks/{task_id}', {'title': 'Posters and flyers', 'status': 'done'}, format='json')
        self.assertEqual(edited.json()['title'], 'Posters and flyers')
        self.assertEqual(edited.json()['status'], 'todo')          # status is not editable here

    def test_task_needs_exactly_one_parent(self):
        from events.tests.helpers import make_event
        event = make_event()
        self.assert_error(self.client.post('/api/tasks', {'title': 'Orphan'}, format='json'), 400, 'validation_error', field='fundraiser')
        both = {'title': 'Both', 'fundraiser': self.fundraiser.id, 'event': event.id}
        self.assert_error(self.client.post('/api/tasks', both, format='json'), 400, 'validation_error', field='fundraiser')
        self.assertEqual(self.client.post('/api/tasks', {'title': 'Door', 'event': event.id}, format='json').status_code, 201)

    def test_only_president_and_coordinator_manage(self):
        for role, allowed in [('president', True), ('treasurer', False), ('event_manager', False), ('member', False)]:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                responses = [
                    self.client.post(FUNDRAISERS, self.body(title=f'By {role}'), format='json'),
                    self.client.patch(f'{FUNDRAISERS}/{self.fundraiser.id}', {'title': f'Renamed by {role}'}, format='json'),
                    self.client.post('/api/tasks', {'fundraiser': self.fundraiser.id, 'title': role}, format='json'),
                    self.client.patch(f'/api/tasks/{self.table.id}', {'title': role}, format='json'),
                    self.client.post(f'/api/tasks/{self.table.id}/assign', {'user': self.volunteer.id}, format='json'),
                ]
                for response in responses:
                    if allowed:
                        self.assertIn(response.status_code, (200, 201), response.content)
                    else:
                        self.assert_error(response, 403, 'permission_denied')


class TaskStatusTests(VolunteeringTestCase):
    def set_status(self, task, status, user):
        self.login_as(user)
        return self.client.patch(f'/api/tasks/{task.id}/status', {'status': status}, format='json')

    def test_assignee_updates_their_own_task(self):
        response = self.set_status(self.baking, 'doing', self.volunteer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.set_status(self.baking, 'done', self.volunteer).json()['status'], 'done')
        self.baking.refresh_from_db()
        self.assertEqual(self.baking.status, 'done')

    def test_member_cannot_update_a_task_assigned_to_someone_else(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-R')
        self.assert_error(self.set_status(self.baking, 'done', other), 403, 'permission_denied')
        self.assert_error(self.set_status(self.table, 'done', self.volunteer), 403, 'permission_denied')   # unassigned
        self.baking.refresh_from_db()
        self.assertEqual(self.baking.status, 'todo')

    def test_treasurer_and_event_manager_are_not_exempt(self):
        for role in ['treasurer', 'event_manager']:
            self.assert_error(self.set_status(self.table, 'done', self.make_role_user(role)), 403, 'permission_denied')

    def test_coordinator_and_president_update_any_task(self):
        self.assertEqual(self.set_status(self.table, 'doing', self.coordinator).status_code, 200)
        self.assertEqual(self.set_status(self.table, 'done', self.make_role_user('president')).status_code, 200)

    def test_invalid_status_and_unknown_task(self):
        self.assert_error(self.set_status(self.baking, 'cancelled', self.volunteer), 400, 'validation_error', field='status')
        self.assert_error(self.client.patch('/api/tasks/999999/status', {'status': 'done'}, format='json'), 404, 'not_found')
        self.client.credentials()
        self.assert_error(self.client.patch(f'/api/tasks/{self.baking.id}/status', {'status': 'done'}, format='json'), 401, 'not_authenticated')
