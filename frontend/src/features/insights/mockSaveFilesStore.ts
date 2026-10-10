import { ApiRequestError } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { getMockEvent } from '../events/mockEventsStore';
import type { SaveFile, SaveFileDraft } from './types';

interface MockSaveFile {
  id: number;
  eventId: number;
  vendors: string;
  budgetNotes: string;
  whatWorked: string;
  whatDidnt: string;
  checklist: string[];
  updatedAt: string;
}

const STORE_KEY = 'campusleague.mock.savefiles';
const SAVEFILE_ROLES = ['event_manager', 'president'];

function seed(): MockSaveFile[] {
  return [
    {
      id: 1,
      eventId: 1,
      vendors: 'Sound: Beatbox Audio (reliable, book 3 weeks ahead).',
      budgetNotes: 'Sound hire was the biggest cost.',
      whatWorked: 'QR check-in kept the queue short.',
      whatDidnt: 'Snacks ran out by 9 pm; order 20% more next time.',
      checklist: ['Book venue', 'Confirm sound vendor', 'Open ticket sales'],
      updatedAt: new Date(Date.now() - 5 * 86_400_000).toISOString(),
    },
  ];
}

function loadStore(): MockSaveFile[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockSaveFile[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seed();
  saveStore(seeded);
  return seeded;
}

function saveStore(items: MockSaveFile[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

function requireSaveFileRole() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  if (!user.roles.some((r) => SAVEFILE_ROLES.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the event manager or president can use Save Files.' });
  }
}

function toPublic(f: MockSaveFile): SaveFile {
  const event = getMockEvent(f.eventId);
  return {
    id: f.id,
    event: { id: f.eventId, title: event?.title ?? `Event #${f.eventId}` },
    vendors: f.vendors,
    budgetNotes: f.budgetNotes,
    whatWorked: f.whatWorked,
    whatDidnt: f.whatDidnt,
    checklist: f.checklist,
    updatedAt: f.updatedAt,
  };
}

export const mockSaveFiles = {
  list(eventId?: number): SaveFile[] {
    requireSaveFileRole();
    const items = loadStore()
      .filter((f) => eventId === undefined || f.eventId === eventId)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    return items.map(toPublic);
  },

  save(draft: SaveFileDraft): SaveFile {
    requireSaveFileRole();
    if (!getMockEvent(draft.event)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'No such event.', field: 'event' });
    }
    const items = loadStore();
    const existing = items.find((f) => f.eventId === draft.event);
    const now = new Date().toISOString();
    if (existing) {
      if (draft.vendors !== undefined) existing.vendors = draft.vendors;
      if (draft.budgetNotes !== undefined) existing.budgetNotes = draft.budgetNotes;
      if (draft.whatWorked !== undefined) existing.whatWorked = draft.whatWorked;
      if (draft.whatDidnt !== undefined) existing.whatDidnt = draft.whatDidnt;
      if (draft.checklist !== undefined) existing.checklist = draft.checklist;
      existing.updatedAt = now;
      saveStore(items);
      return toPublic(existing);
    }
    const created: MockSaveFile = {
      id: items.reduce((max, f) => Math.max(max, f.id), 0) + 1,
      eventId: draft.event,
      vendors: draft.vendors ?? '',
      budgetNotes: draft.budgetNotes ?? '',
      whatWorked: draft.whatWorked ?? '',
      whatDidnt: draft.whatDidnt ?? '',
      checklist: draft.checklist ?? [],
      updatedAt: now,
    };
    items.push(created);
    saveStore(items);
    return toPublic(created);
  },
};
