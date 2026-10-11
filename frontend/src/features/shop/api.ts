import { env } from '../../core/config/env';
import { mockShopApi } from './api.mock';
import { realShopApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const shopApi = env.useMockApi ? mockShopApi : realShopApi;

export type { PaymentTestOutcome, PlaceOrderRequest, PlaceOrderResult, Product, ProductCategory, ProductDraft, ProductSize, RestockRequest, ShopOrder, SizeLabel } from './types';
