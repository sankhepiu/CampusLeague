import type { Paginated } from '../../api/client';
import { health, simulate } from './insightsMock';
import { mockSaveFiles } from './mockSaveFilesStore';
import type { ClubHealth, SaveFile, SaveFileDraft, SimulatorInputs, SimulatorResult } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockInsightsApi = {
  async simulate(inputs: SimulatorInputs): Promise<SimulatorResult> {
    await delay(300);
    return simulate(inputs);
  },

  async health(): Promise<ClubHealth> {
    await delay(300);
    return health();
  },

  async listSaveFiles(eventId?: number): Promise<Paginated<SaveFile>> {
    await delay(300);
    const results = mockSaveFiles.list(eventId);
    return { count: results.length, next: null, previous: null, results };
  },

  async saveSaveFile(draft: SaveFileDraft): Promise<SaveFile> {
    await delay(350);
    return mockSaveFiles.save(draft);
  },
};
