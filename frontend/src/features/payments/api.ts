import { env } from '../../core/config/env';
import { mockPaymentsApi } from './api.mock';
import { realPaymentsApi } from './api.real';

export const paymentsApi = env.useMockApi ? mockPaymentsApi : realPaymentsApi;

export type { PaymentGateway, PaymentsConfig, RazorpayOrderInfo, RazorpayVerifyFields } from './types';
