import type { Paginated } from '../../api/client';
import { mockVolunteering } from './mockVolunteeringStore';
import type { AssignRequest, Fundraiser, FundraiserDraft, SaleRequest, Task, TaskDraft, TaskStatus } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

function paginate<T>(items: T[], page: number): Paginated<T> {
  const start = (page - 1) * PAGE_SIZE;
  const results = items.slice(start, start + PAGE_SIZE);
  return { count: items.length, next: start + PAGE_SIZE < items.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
}

export const mockVolunteeringApi = {
  async listFundraisers(page = 1): Promise<Paginated<Fundraiser>> {
    await delay(300);
    return paginate(mockVolunteering.listFundraisers(), page);
  },

  async getFundraiser(id: number): Promise<Fundraiser> {
    await delay(250);
    return mockVolunteering.getFundraiser(id);
  },

  async createFundraiser(draft: FundraiserDraft): Promise<Fundraiser> {
    await delay(400);
    return mockVolunteering.createFundraiser(draft);
  },

  async updateFundraiser(id: number, draft: Partial<FundraiserDraft>): Promise<Fundraiser> {
    await delay(400);
    return mockVolunteering.updateFundraiser(id, draft);
  },

  async recordSale(fundraiserId: number, req: SaleRequest): Promise<Fundraiser> {
    await delay(350);
    return mockVolunteering.recordSale(fundraiserId, req);
  },

  async createTask(draft: TaskDraft): Promise<Task> {
    await delay(350);
    return mockVolunteering.createTask(draft);
  },

  async updateTask(id: number, draft: Partial<TaskDraft>): Promise<Task> {
    await delay(350);
    return mockVolunteering.updateTask(id, draft);
  },

  async assignTask(id: number, req: AssignRequest): Promise<Task> {
    await delay(350);
    return mockVolunteering.assignTask(id, req);
  },

  async setTaskStatus(id: number, status: TaskStatus): Promise<Task> {
    await delay(300);
    return mockVolunteering.setTaskStatus(id, status);
  },
};
