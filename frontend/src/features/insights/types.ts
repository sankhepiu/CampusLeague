export interface SimulatorInputs {
  ticketPrice: number; // paise
  expectedAttendance: number;
  fixedCosts: number; // paise
  variableCostPerHead: number; // paise
  event?: number;
}

export interface SimulatorForecastActual {
  forecast: { attendance: number; revenue: number; costs: number; profit: number };
  actual: { attendance: number; ticketsSold: number; revenue: number; costs: number; profit: number };
  difference: { attendance: number; revenue: number; costs: number; profit: number };
}

export interface SimulatorResult {
  inputs: SimulatorInputs;
  marginPerHead: number;
  breakEvenAttendance: number;
  revenue: number;
  costs: number;
  profit: number;
  breaksEven: boolean;
  event: { id: number; title: string } | null;
  forecastVsActual: SimulatorForecastActual | null;
}

export interface HealthComponent {
  key: string;
  label: string;
  score: number | null; // 0-100
  weight: number;
  contribution: number;
  reason: string;
}

export interface ClubHealth {
  score: number | null; // 0-100
  components: HealthComponent[];
}

export interface SaveFile {
  id: number;
  event: { id: number; title: string };
  vendors: string;
  budgetNotes: string;
  whatWorked: string;
  whatDidnt: string;
  checklist: string[];
  updatedAt: string;
}

export interface SaveFileDraft {
  event: number;
  vendors?: string;
  budgetNotes?: string;
  whatWorked?: string;
  whatDidnt?: string;
  checklist?: string[];
}
