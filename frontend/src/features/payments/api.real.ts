import { request } from '../../api/client';
import type { PaymentsConfig } from './types';

interface WirePaymentsConfig {
  gateway: PaymentsConfig['gateway'];
}

export const realPaymentsApi = {
  // GAP: not yet in docs/API_CONTRACT.md — built against the exact shape
  // the demo-polish brief gave ({"gateway": "mock" | "razorpay"}).
  async getConfig(): Promise<PaymentsConfig> {
    const result = await request<WirePaymentsConfig>('/payments/config');
    return { gateway: result.gateway };
  },
};
