import { env } from '../../core/config/env';
import { mockOrdersApi } from './api.mock';
import { realOrdersApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const ordersApi = env.useMockApi ? mockOrdersApi : realOrdersApi;

export type { Order, OrderKind, OrderLine, OrderStatus } from './types';
