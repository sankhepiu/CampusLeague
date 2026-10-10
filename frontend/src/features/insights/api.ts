import { env } from '../../core/config/env';
import { mockInsightsApi } from './api.mock';
import { realInsightsApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const insightsApi = env.useMockApi ? mockInsightsApi : realInsightsApi;

export type { ClubHealth, HealthComponent, SaveFile, SaveFileDraft, SimulatorForecastActual, SimulatorInputs, SimulatorResult } from './types';
