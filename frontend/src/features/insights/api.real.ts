import { request, type Paginated } from '../../api/client';
import type { ClubHealth, HealthComponent, SaveFile, SaveFileDraft, SimulatorForecastActual, SimulatorInputs, SimulatorResult } from './types';

interface WireSimulatorForecastActual {
  forecast: { attendance: number; revenue: number; costs: number; profit: number };
  actual: { attendance: number; tickets_sold: number; revenue: number; costs: number; profit: number };
  difference: { attendance: number; revenue: number; costs: number; profit: number };
}

interface WireSimulatorResult {
  inputs: { ticket_price: number; expected_attendance: number; fixed_costs: number; variable_cost_per_head: number };
  margin_per_head: number;
  break_even_attendance: number;
  revenue: number;
  costs: number;
  profit: number;
  breaks_even: boolean;
  event: { id: number; title: string } | null;
  forecast_vs_actual: WireSimulatorForecastActual | null;
}

function fromWireForecastActual(f: WireSimulatorForecastActual): SimulatorForecastActual {
  return {
    forecast: f.forecast,
    actual: { attendance: f.actual.attendance, ticketsSold: f.actual.tickets_sold, revenue: f.actual.revenue, costs: f.actual.costs, profit: f.actual.profit },
    difference: f.difference,
  };
}

interface WireHealthComponent {
  key: string;
  label: string;
  score: number | null;
  weight: number;
  contribution: number;
  reason: string;
}

interface WireHealth {
  score: number | null;
  components: WireHealthComponent[];
}

interface WireSaveFile {
  id: number;
  event: { id: number; title: string };
  vendors: string;
  budget_notes: string;
  what_worked: string;
  what_didnt: string;
  checklist: string[];
  updated_at: string;
}

function fromWireSaveFile(f: WireSaveFile): SaveFile {
  return {
    id: f.id,
    event: f.event,
    vendors: f.vendors,
    budgetNotes: f.budget_notes,
    whatWorked: f.what_worked,
    whatDidnt: f.what_didnt,
    checklist: f.checklist,
    updatedAt: f.updated_at,
  };
}

export const realInsightsApi = {
  async simulate(inputs: SimulatorInputs): Promise<SimulatorResult> {
    const r = await request<WireSimulatorResult>('/simulator', {
      method: 'POST',
      body: {
        ticket_price: inputs.ticketPrice,
        expected_attendance: inputs.expectedAttendance,
        fixed_costs: inputs.fixedCosts,
        variable_cost_per_head: inputs.variableCostPerHead,
        ...(inputs.event !== undefined ? { event: inputs.event } : {}),
      },
    });
    return {
      inputs: {
        ticketPrice: r.inputs.ticket_price,
        expectedAttendance: r.inputs.expected_attendance,
        fixedCosts: r.inputs.fixed_costs,
        variableCostPerHead: r.inputs.variable_cost_per_head,
      },
      marginPerHead: r.margin_per_head,
      breakEvenAttendance: r.break_even_attendance,
      revenue: r.revenue,
      costs: r.costs,
      profit: r.profit,
      breaksEven: r.breaks_even,
      event: r.event,
      forecastVsActual: r.forecast_vs_actual ? fromWireForecastActual(r.forecast_vs_actual) : null,
    };
  },

  async health(): Promise<ClubHealth> {
    const h = await request<WireHealth>('/health');
    return { score: h.score, components: h.components as HealthComponent[] };
  },

  async listSaveFiles(eventId?: number): Promise<Paginated<SaveFile>> {
    const result = await request<Paginated<WireSaveFile>>('/savefiles', { query: { event: eventId } });
    return { ...result, results: result.results.map(fromWireSaveFile) };
  },

  async saveSaveFile(draft: SaveFileDraft): Promise<SaveFile> {
    const body: Record<string, unknown> = { event: draft.event };
    if (draft.vendors !== undefined) body.vendors = draft.vendors;
    if (draft.budgetNotes !== undefined) body.budget_notes = draft.budgetNotes;
    if (draft.whatWorked !== undefined) body.what_worked = draft.whatWorked;
    if (draft.whatDidnt !== undefined) body.what_didnt = draft.whatDidnt;
    if (draft.checklist !== undefined) body.checklist = draft.checklist;
    const f = await request<WireSaveFile>('/savefiles', { method: 'POST', body });
    return fromWireSaveFile(f);
  },
};
