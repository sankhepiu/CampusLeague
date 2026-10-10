import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { listMockOrdersForUser } from './mockOrdersStore';
import type { Order } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

export const mockOrdersApi = {
  async listMine(page = 1): Promise<Paginated<Order>> {
    await delay(300);
    const user = getCurrentMockUser();
    if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
    const all = listMockOrdersForUser(user.email);
    const start = (page - 1) * PAGE_SIZE;
    const results = all.slice(start, start + PAGE_SIZE);
    return { count: all.length, next: start + PAGE_SIZE < all.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
  },
};
