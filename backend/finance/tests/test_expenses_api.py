import os
import threading

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from accounts.models import User
from audit.models import AuditLog
from common.testing import ApiTestCase
from events.tests.helpers import make_event
from finance import expenses
from finance.models import Approval, ExpenseRequest, LedgerEntry
from finance.services import account_balance
from finance.tests.helpers import JPG, PDF, PNG, TempMediaMixin, receipt
from volunteering.models import Fundraiser

EXPENSES = '/api/expenses'


class ExpenseTestCase(TempMediaMixin, ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.volunteer = self.make_user()
        self.treasurer = self.make_role_user('treasurer')
        self.president = self.make_role_user('president')
        self.login_as(self.volunteer)

    def submit(self, **overrides):
        body = {
            'amount': 150000, 'category': 'event', 'event': self.event.id,
            'description': 'Catering deposit', 'receipt_file': receipt(),
        }
        body.update(overrides)
        body = {key: value for key, value in body.items() if value is not None}
        return self.client.post(EXPENSES, body, format='multipart')

    def submitted(self, **overrides):
        response = self.submit(**overrides)
        self.assertEqual(response.status_code, 201, response.content)
        return ExpenseRequest.objects.get(pk=response.json()['id'])

    def act(self, expense, action, user, **body):
        self.login_as(user)
        return self.client.post(f'{EXPENSES}/{expense.id}/{action}', body, format='json')

    def balances(self):
        return {code: account_balance(code) for code in ['1000', '2000', '5000', '5200']}

    NO_MONEY = {'1000': 0, '2000': 0, '5000': 0, '5200': 0}


class SubmitTests(ExpenseTestCase):
    def test_volunteer_submits_an_expense_with_a_receipt(self):
        response = self.submit()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        expense = ExpenseRequest.objects.get()
        self.assertEqual(body['status'], 'submitted')
        self.assertEqual(body['requester'], {'id': self.volunteer.id, 'name': 'Priya'})
        self.assertIsNone(body['approval'])
        # Relative, so the frontend's /media proxy serves it.
        self.assertTrue(body['receipt_url'].startswith('/media/receipts/'), body['receipt_url'])
        self.assertNotIn('://', body['receipt_url'])
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, expense.receipt_file.name)))
        # Submitting moves no money.
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_stored_file_name_is_random_not_the_uploaders(self):
        expense = self.submitted(receipt_file=receipt(name='../../etc/passwd.png'))
        self.assertRegex(expense.receipt_file.name, r'^receipts/[0-9a-f]{32}\.png$')

    def test_jpg_and_pdf_receipts_are_accepted(self):
        self.submitted(receipt_file=receipt('r.jpg', JPG, 'image/jpeg'))
        self.submitted(receipt_file=receipt('r.PDF', PDF, 'application/pdf'))
        self.assertEqual(ExpenseRequest.objects.count(), 2)

    def test_status_and_requester_from_the_client_are_ignored(self):
        expense = self.submitted(status='approved', requester=self.treasurer.id)
        self.assertEqual(expense.status, 'submitted')
        self.assertEqual(expense.requester, self.volunteer)
        self.assertEqual(Approval.objects.count(), 0)
        self.assertEqual(self.balances(), self.NO_MONEY)

    def test_bad_receipts_are_refused(self):
        cases = [
            (receipt('virus.exe', b'MZ' + b'\x00' * 40, 'application/octet-stream'), 'unsupported_file_type'),
            (receipt('page.html', b'<script>alert(1)</script>', 'text/html'), 'unsupported_file_type'),
            (receipt('noextension', PNG), 'unsupported_file_type'),
            (receipt('fake.png', b'<script>alert(1)</script>'), 'file_content_mismatch'),
            (receipt('fake.pdf', PNG, 'application/pdf'), 'file_content_mismatch'),
            (receipt('big.png', PNG + b'\x00' * (5 * 1024 * 1024)), 'file_too_large'),
            (None, 'required'),
        ]
        for upload, code in cases:
            with self.subTest(code=code, name=getattr(upload, 'name', None)):
                body = self.assert_error(self.submit(receipt_file=upload), 400, 'validation_error', field='receipt_file')
                self.assertIn(('receipt_file', code), self.field_codes(body))
        self.assertEqual(ExpenseRequest.objects.count(), 0)

    def test_invalid_amounts_and_tags_are_refused(self):
        fundraiser = Fundraiser.objects.create(title='Bake Sale', goal_amount=100000, starts_on='2026-10-01', ends_on='2026-10-31')
        cases = [
            ({'amount': 0}, 'amount'), ({'amount': -500}, 'amount'), ({'amount': 'lots'}, 'amount'), ({'amount': None}, 'amount'),
            ({'description': ''}, 'description'), ({'category': 'bribes'}, 'category'),
            ({'category': 'event', 'event': None}, 'event'),
            ({'category': 'fundraiser', 'event': None}, 'fundraiser'),
            ({'category': 'general'}, 'category'),                       # general, but names an event
            ({'category': 'event', 'fundraiser': fundraiser.id}, 'event'),
            ({'event': 999999}, 'event'),
        ]
        for overrides, field in cases:
            with self.subTest(overrides=overrides):
                self.assert_error(self.submit(**overrides), 400, 'validation_error', field=field)
        self.assertEqual(ExpenseRequest.objects.count(), 0)

    def test_requires_login(self):
        self.client.credentials()
        self.assert_error(self.submit(), 401, 'not_authenticated')


class ApprovalTests(ExpenseTestCase):
    """R18: "Volunteer uploads a receipt; committee approves; ledger entry
    created."
    """

    def test_a_different_user_approves_and_the_ledger_entry_appears(self):
        expense = self.submitted()

        response = self.act(expense, 'approve', self.treasurer, reason='Looks right')

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'approved')
        self.assertEqual(body['approval']['approver'], {'id': self.treasurer.id, 'name': self.treasurer.name})
        self.assertEqual((body['approval']['decision'], body['approval']['reason']), ('approved', 'Looks right'))

        entry = LedgerEntry.objects.get()
        self.assertEqual((entry.source_type, entry.source_id, entry.kind), ('expense_request', expense.id, 'expense_approved'))
        self.assertEqual(entry.event, self.event)
        self.assertEqual(entry.created_by, self.treasurer)
        self.assertEqual(sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
                         [('2000', 0, 150000), ('5000', 150000, 0)])
        # Owed but not yet paid: cash has not moved.
        self.assertEqual(self.balances(), {'1000': 0, '2000': 150000, '5000': 150000, '5200': 0})

    def test_general_expense_posts_to_the_general_account_untagged(self):
        expense = self.submitted(category='general', event=None)
        self.act(expense, 'approve', self.president)
        self.assertEqual(account_balance('5200'), 150000)
        self.assertIsNone(LedgerEntry.objects.get().event)

    def test_requester_cannot_approve_their_own_request_even_as_treasurer(self):
        self.login_as(self.treasurer)
        expense = self.submitted()                      # the treasurer's own expense

        for action in ['approve', 'reject', 'mark-paid']:
            with self.subTest(action=action):
                response = self.act(expense, action, self.treasurer, reason='trust me')
                self.assert_error(response, 403, 'self_approval')

        expense.refresh_from_db()
        self.assertEqual(expense.status, 'submitted')
        self.assertEqual(Approval.objects.count(), 0)
        self.assertEqual(self.balances(), self.NO_MONEY)
        # ...but the other approver can.
        self.assertEqual(self.act(expense, 'approve', self.president).status_code, 200)

    def test_requester_cannot_pay_out_their_own_approved_request(self):
        self.login_as(self.treasurer)
        expense = self.submitted()
        self.act(expense, 'approve', self.president)
        self.assert_error(self.act(expense, 'mark-paid', self.treasurer), 403, 'self_approval')
        self.assertEqual(account_balance('1000'), 0)

    def test_only_president_and_treasurer_may_decide(self):
        expense = self.submitted()
        refused = [self.make_role_user(role) for role in ['event_manager', 'volunteer_coordinator', 'member']]
        refused.append(self.make_user(email='nobody@example.com', name='Nobody', college_id='SSA-N'))
        for user in refused:
            for action in ['approve', 'reject', 'mark-paid']:
                with self.subTest(user=user.email, action=action):
                    self.assert_error(self.act(expense, action, user, reason='x'), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.post(f'{EXPENSES}/{expense.id}/approve'), 401, 'not_authenticated')
        expense.refresh_from_db()
        self.assertEqual(expense.status, 'submitted')
        self.assertEqual(self.balances(), self.NO_MONEY)

    def test_treasurer_whose_term_ended_cannot_approve(self):
        expense = self.submitted()
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-F')
        self.give_role(former, 'treasurer', start_offset=-400, end_offset=-1)
        self.assert_error(self.act(expense, 'approve', former), 403, 'permission_denied')

    def test_rejection_needs_a_reason_and_posts_nothing(self):
        expense = self.submitted()
        self.assert_error(self.act(expense, 'reject', self.treasurer), 400, 'validation_error', field='reason')

        response = self.act(expense, 'reject', self.treasurer, reason='No itemised receipt')

        self.assertEqual(response.json()['status'], 'rejected')
        self.assertEqual(response.json()['approval']['reason'], 'No itemised receipt')
        self.assertEqual(self.balances(), self.NO_MONEY)

    def test_paying_out_clears_the_payable_and_reduces_cash(self):
        expense = self.submitted()
        self.act(expense, 'approve', self.treasurer)

        response = self.act(expense, 'mark-paid', self.president)

        self.assertEqual(response.json()['status'], 'paid')
        self.assertEqual(self.balances(), {'1000': -150000, '2000': 0, '5000': 150000, '5200': 0})
        kinds = sorted(LedgerEntry.objects.filter(source_id=expense.id).values_list('kind', flat=True))
        self.assertEqual(kinds, ['expense_approved', 'expense_paid'])    # two entries, kept separate

    def test_only_valid_transitions_are_allowed(self):
        cases = [
            ([], 'mark-paid', 'submitted'),                       # cannot pay before approval
            (['approve'], 'approve', 'approved'),                 # cannot approve twice
            (['approve'], 'reject', 'approved'),                  # cannot reject after approving
            (['reject'], 'approve', 'rejected'),                  # cannot approve after rejecting
            (['reject'], 'mark-paid', 'rejected'),                # cannot pay a rejected request
            (['approve', 'mark-paid'], 'mark-paid', 'paid'),      # cannot pay twice
            (['approve', 'mark-paid'], 'approve', 'paid'),
        ]
        for done, attempt, status in cases:
            with self.subTest(done=done, attempt=attempt):
                self.login_as(self.volunteer)
                expense = self.submitted()
                for action in done:
                    self.assertEqual(self.act(expense, action, self.treasurer, reason='r').status_code, 200)
                entries = LedgerEntry.objects.count()

                response = self.act(expense, attempt, self.president, reason='r')

                self.assert_error(response, 409, 'invalid_status')
                expense.refresh_from_db()
                self.assertEqual(expense.status, status)
                self.assertEqual(LedgerEntry.objects.count(), entries)

    def test_status_cannot_be_changed_by_editing_the_record(self):
        # Plan: "Status can't become approved by editing the record directly."
        expense = self.submitted()
        for user in [self.volunteer, self.treasurer]:
            self.login_as(user)
            for method in ['patch', 'put', 'delete']:
                with self.subTest(user=user.email, method=method):
                    response = getattr(self.client, method)(f'{EXPENSES}/{expense.id}', {'status': 'approved'}, format='json')
                    self.assertEqual(response.status_code, 404)      # there is no such endpoint
        expense.refresh_from_db()
        self.assertEqual(expense.status, 'submitted')
        self.assertEqual(self.balances(), self.NO_MONEY)

    def test_every_decision_is_audited(self):
        expense = self.submitted()
        self.act(expense, 'approve', self.treasurer)
        self.act(expense, 'mark-paid', self.president)
        rejected = self.submitted_as_volunteer()
        self.act(rejected, 'reject', self.treasurer, reason='duplicate')

        logs = list(AuditLog.objects.order_by('id').values_list('action', 'actor__email', 'object_id', 'before', 'after'))
        self.assertEqual(logs, [
            ('expense.approved', 'treasurer@example.com', expense.id, {'status': 'submitted'}, {'status': 'approved'}),
            ('expense.paid', 'president@example.com', expense.id, {'status': 'approved'}, {'status': 'paid'}),
            ('expense.rejected', 'treasurer@example.com', rejected.id, {'status': 'submitted'}, {'status': 'rejected'}),
        ])

    def submitted_as_volunteer(self):
        self.login_as(self.volunteer)
        return self.submitted()

    def test_unknown_expense_is_404(self):
        self.login_as(self.treasurer)
        self.assert_error(self.client.post(f'{EXPENSES}/999999/approve'), 404, 'not_found')


class ExpenseListTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.mine = self.submitted()
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-R')
        self.login_as(other)
        self.theirs = self.submitted(description='Decorations')
        self.act(self.theirs, 'approve', self.treasurer)

    def test_my_expenses_shows_only_mine(self):
        self.login_as(self.volunteer)
        body = self.client.get(f'{EXPENSES}/me').json()
        self.assertEqual([item['id'] for item in body['results']], [self.mine.id])

    def test_receipt_url_is_relative_in_every_expense_endpoint(self):
        self.login_as(self.volunteer)
        mine = self.client.get(f'{EXPENSES}/me').json()['results']
        self.login_as(self.treasurer)
        queue = self.client.get(EXPENSES).json()['results']
        decided = self.act(self.mine, 'approve', self.treasurer).json()
        urls = [item['receipt_url'] for item in mine + queue] + [decided['receipt_url']]
        self.assertEqual(len(urls), 4)
        for url in urls:
            self.assertTrue(url.startswith('/media/'), url)

    def test_expense_and_trace_give_the_same_receipt_url(self):
        decided = self.act(self.mine, 'approve', self.treasurer).json()
        trace = self.client.get('/api/finance/trace', {'figure': 'payable'}).json()
        traced = {e['source']['id']: e['source']['details']['receipt_url'] for e in trace['entries']}
        self.assertEqual(traced[self.mine.id], decided['receipt_url'])

    def test_queue_is_for_president_and_treasurer_and_can_be_filtered(self):
        self.login_as(self.treasurer)
        self.assertEqual(self.client.get(EXPENSES).json()['count'], 2)
        queue = self.client.get(EXPENSES, {'status': 'submitted'}).json()
        self.assertEqual([item['id'] for item in queue['results']], [self.mine.id])
        self.assert_error(self.client.get(EXPENSES, {'status': 'bogus'}), 400, 'validation_error', field='status')

    def test_members_cannot_read_the_queue(self):
        self.login_as(self.volunteer)
        self.assert_error(self.client.get(EXPENSES), 403, 'permission_denied')
        self.login_as(self.make_role_user('event_manager'))
        self.assert_error(self.client.get(EXPENSES), 403, 'permission_denied')


class ConcurrentDecisionTests(TempMediaMixin, TransactionTestCase):
    serialized_rollback = True

    def test_simultaneous_approvals_post_one_ledger_entry(self):
        event = make_event()
        requester = User.objects.create_user(email='v@example.com', name='V', college_id='V1')
        approvers = [User.objects.create_user(email=f'a{n}@example.com', name=f'A{n}', college_id=f'A{n}') for n in range(6)]
        expense = ExpenseRequest.objects.create(
            requester=requester, amount=90000, category='event', event=event,
            description='Sound system', receipt_file='receipts/seeded.png',
        )
        barrier = threading.Barrier(len(approvers))
        results = []

        def worker(approver):
            try:
                barrier.wait(timeout=10)
                expenses.approve(expense.pk, approver)
                results.append('approved')
            except expenses.InvalidTransition:
                results.append('refused')
            except Exception as exc:
                results.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(approver,)) for approver in approvers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(sorted(results, key=str), ['approved'] + ['refused'] * 5)
        self.assertEqual(Approval.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('2000'), 90000)
