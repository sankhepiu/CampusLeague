import { ApiRequestError } from '../../api/client';
import { getCurrentMockUser, updateUser } from '../auth/mockUsers';
import { addMockOrder } from '../orders/mockOrdersStore';
import { addDays, addMonths, today } from './dates';
import type { MembershipRecord, MyMembership, Order, Payment, Plan, PurchaseRequest, PurchaseResult } from './types';

/** Same two plans the contract's own GET /plans example uses, so numbers
 * line up when the real endpoint lands. */
export const MOCK_PLANS: Plan[] = [
  { id: 1, name: 'Basic', price: 50000, durationMonths: 12, ticketDiscountPct: 0, merchDiscountPct: 10 },
  { id: 2, name: 'Plus', price: 90000, durationMonths: 12, ticketDiscountPct: 5, merchDiscountPct: 20 },
];

interface IdempotencyRecord {
  userEmail: string;
  plan: number;
  result: PurchaseResult;
}

interface MockMembershipState {
  memberships: Record<string, MembershipRecord>; // keyed by user email
  idempotency: Record<string, IdempotencyRecord>;
}

const STORE_KEY = 'campusleague.mock.memberships';
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Matches the active/lapsed demo accounts seeded in auth/mockUsers.ts, so
 * their membershipStatus field (on the User object) and their actual
 * membership record agree from the very first load. */
function seedState(): MockMembershipState {
  const basic = MOCK_PLANS[0];
  return {
    memberships: {
      'active@campusleague.dev': {
        id: 1,
        plan: basic,
        status: 'active',
        startDate: addMonths(today(), -1),
        endDate: addMonths(today(), 11),
      },
      'lapsed@campusleague.dev': {
        id: 2,
        plan: basic,
        status: 'lapsed',
        startDate: addMonths(today(), -14),
        endDate: addMonths(today(), -2),
      },
    },
    idempotency: {},
  };
}

function loadState(): MockMembershipState {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockMembershipState;
  } catch {
    /* storage unavailable or corrupt — fall through to reseed */
  }
  const seeded = seedState();
  saveState(seeded);
  return seeded;
}

function saveState(state: MockMembershipState): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable */
  }
}

// Mock-only id generator — large enough never to collide with the seed data's
// small hand-assigned ids, no persisted counter needed since nothing here
// depends on strict sequential order.
const newId = () => Date.now() + Math.floor(Math.random() * 1000);
const mockGatewayRef = () => `mock_${newId().toString(16)}${Math.random().toString(16).slice(2, 10)}`;

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

/** Recomputes status the same way a real backend's scheduled job would: an
 * "active" membership whose end_date has passed is actually lapsed. */
function effectiveRecord(record: MembershipRecord): MembershipRecord {
  if (record.status === 'active' && record.endDate < today()) {
    return { ...record, status: 'lapsed' };
  }
  return record;
}

/** Synchronous lookup other mocks (shop) need to apply a plan-specific
 * discount percentage — the contract computes merch price from "their
 * plan's merch_discount_pct", not a flat rate, so the caller needs to know
 * which plan, not just whether membership is active. */
export function getActiveMembershipPlanForCurrentUser(): Plan | null {
  const user = getCurrentMockUser();
  if (!user) return null;
  const record = loadState().memberships[user.email];
  if (!record) return null;
  return effectiveRecord(record).status === 'active' ? record.plan : null;
}

/** Mock member-card token. The real one is signed by the server; this only
 * needs to be recognisable by the mock check-in scanner. */
export const MOCK_MEMBER_TOKEN_PREFIX = 'mock-member:';
export const mockMemberToken = (userId: number) => `${MOCK_MEMBER_TOKEN_PREFIX}${userId}`;

export const mockMembershipApi = {
  async listPlans(): Promise<Plan[]> {
    await delay(300);
    return MOCK_PLANS;
  },

  async getMyMembership(): Promise<MyMembership> {
    await delay(250);
    const user = requireUser();
    const state = loadState();
    const stored = state.memberships[user.email];
    if (!stored) return { status: 'none', membership: null, paidUntil: null, memberQrToken: null };

    const record = effectiveRecord(stored);
    if (record.status !== stored.status) {
      state.memberships[user.email] = record;
      saveState(state);
      updateUser(user.email, { membershipStatus: 'lapsed' });
    }

    const status = record.status === 'active' ? 'active' : record.status === 'lapsed' ? 'lapsed' : 'none';
    return { status, membership: record, paidUntil: record.endDate, memberQrToken: mockMemberToken(user.id) };
  },

  async purchase({ plan: planId, testOutcome = 'success' }: PurchaseRequest, idempotencyKey: string): Promise<PurchaseResult> {
    await delay(700);
    const user = requireUser();
    const state = loadState();

    const replay = state.idempotency[idempotencyKey];
    if (replay) {
      if (replay.userEmail !== user.email || replay.plan !== planId) {
        throw new ApiRequestError({
          code: 'idempotency_key_reused',
          message: 'This idempotency key already paid for a different plan, or belongs to another user.',
        });
      }
      return { ...replay.result, replayed: true };
    }

    const plan = MOCK_PLANS.find((p) => p.id === planId);
    if (!plan) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Unknown or inactive plan.', field: 'plan' });
    }

    if (testOutcome === 'failure') {
      throw new ApiRequestError({ code: 'payment_failed', message: 'The mock payment gateway declined this attempt.' });
    }

    const orderId = newId();
    const createdAt = new Date().toISOString();

    if (testOutcome === 'pending') {
      // The contract is explicit: a pending key is never remembered, so it
      // can be retried — nothing is written to the idempotency store here.
      const order: Order = {
        id: orderId,
        status: 'pending',
        subtotal: plan.price,
        discount: 0,
        total: plan.price,
        paymentRef: '',
        createdAt,
        lines: [{ id: orderId, kind: 'membership', plan: plan.id, qty: 1, unitPrice: plan.price }],
      };
      return { order, payment: null, membership: null, replayed: false };
    }

    const existing = state.memberships[user.email];
    const stillCovered = existing && effectiveRecord(existing).status === 'active';
    const startDate = stillCovered ? addDays(existing.endDate, 1) : today();
    const endDate = addMonths(startDate, plan.durationMonths);
    const gatewayRef = mockGatewayRef();

    const membership: MembershipRecord = {
      id: existing?.id ?? newId(),
      plan,
      status: 'active',
      startDate,
      endDate,
    };
    const order: Order = {
      id: orderId,
      status: 'paid',
      subtotal: plan.price,
      discount: 0,
      total: plan.price,
      paymentRef: gatewayRef,
      createdAt,
      lines: [{ id: orderId, kind: 'membership', plan: plan.id, qty: 1, unitPrice: plan.price }],
    };
    const payment: Payment = { id: newId(), amount: plan.price, status: 'succeeded', gatewayRef, createdAt };

    state.memberships[user.email] = membership;
    const result: PurchaseResult = { order, payment, membership, replayed: false };
    state.idempotency[idempotencyKey] = { userEmail: user.email, plan: plan.id, result };
    addMockOrder(user.email, {
      ...order,
      lines: order.lines.map((l) => ({ ...l, kind: 'membership' as const, label: `${plan.name} membership`, tier: null, productSize: null, discount: 0 })),
    });
    saveState(state);
    updateUser(user.email, { membershipStatus: 'active' });

    return result;
  },
};
