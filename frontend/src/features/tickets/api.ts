import { env } from '../../core/config/env';
import { mockTicketsApi } from './api.mock';
import { realTicketsApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const ticketsApi = env.useMockApi ? mockTicketsApi : realTicketsApi;

export type { PaymentTestOutcome, PurchaseTicketsRequest, PurchaseTicketsResult, Ticket, TicketStatus } from './types';
