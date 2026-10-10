import { env } from '../../core/config/env';
import { mockCheckinApi } from './api.mock';
import { realCheckinApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const checkinApi = env.useMockApi ? mockCheckinApi : realCheckinApi;

export type { CheckinRequest, CheckinResponse, CheckinResult } from './types';
