import type { PaymentsConfig } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockPaymentsApi = {
  /** Mock mode never has a real gateway behind it — always the familiar
   * Test Mode screen, regardless of what a real backend might report. */
  async getConfig(): Promise<PaymentsConfig> {
    await delay(100);
    return { gateway: 'mock' };
  },
};
