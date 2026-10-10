import { ApiRequestError } from '../../api/client';
import { getCurrentMockUser, listAllUsers } from '../auth/mockUsers';
import { computeCashMovementLast30Days } from '../finance/financeLedgerEngine';
import { getMockEvent, listMockEvents } from '../events/mockEventsStore';
import { countsForMockEvent, revenueForMockEvent } from '../tickets/mockTicketsStore';
import { mockVolunteering } from '../volunteering/mockVolunteeringStore';
import type { ClubHealth, HealthComponent, SimulatorInputs, SimulatorResult } from './types';

const SIMULATOR_ROLES = ['president', 'treasurer', 'event_manager'];
const HEALTH_ROLES = ['president'];

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

function requireRole(roles: string[], message: string) {
  const user = requireUser();
  if (!user.roles.some((r) => roles.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message });
  }
  return user;
}

export function simulate(inputs: SimulatorInputs): SimulatorResult {
  requireRole(SIMULATOR_ROLES, 'Only the event manager, treasurer or president can use the simulator.');

  if (inputs.ticketPrice <= inputs.variableCostPerHead) {
    throw new ApiRequestError({ code: 'validation_error', message: 'Ticket price must be greater than the variable cost per head.', field: 'ticket_price', errors: [{ field: 'ticket_price', code: 'no_break_even', message: 'Ticket price must be greater than the variable cost per head.' }] });
  }

  const marginPerHead = inputs.ticketPrice - inputs.variableCostPerHead;
  const breakEvenAttendance = Math.ceil(inputs.fixedCosts / marginPerHead);
  const revenue = inputs.ticketPrice * inputs.expectedAttendance;
  const costs = inputs.fixedCosts + inputs.variableCostPerHead * inputs.expectedAttendance;
  const profit = revenue - costs;
  const breaksEven = inputs.expectedAttendance >= breakEvenAttendance;

  let event: { id: number; title: string } | null = null;
  let forecastVsActual: SimulatorResult['forecastVsActual'] = null;

  if (inputs.event !== undefined) {
    const mockEvent = getMockEvent(inputs.event);
    if (!mockEvent) throw new ApiRequestError({ code: 'validation_error', message: 'No such event.', field: 'event' });
    event = { id: mockEvent.id, title: mockEvent.title };

    const isOver = new Date(mockEvent.endsAt) < new Date();
    if (isOver) {
      const counts = countsForMockEvent(mockEvent.id);
      const actualRevenue = revenueForMockEvent(mockEvent.id);
      // The mock doesn't separately track an event's realized costs outside
      // the finance ledger's expense entries — approximate actual costs as
      // fixed + variable-per-checked-in-head, same formula as the forecast.
      const actualCosts = inputs.fixedCosts + inputs.variableCostPerHead * counts.checkedIn;
      const actualProfit = actualRevenue - actualCosts;
      const forecast = { attendance: inputs.expectedAttendance, revenue, costs, profit };
      const actual = { attendance: counts.checkedIn, ticketsSold: counts.sold, revenue: actualRevenue, costs: actualCosts, profit: actualProfit };
      forecastVsActual = {
        forecast,
        actual,
        difference: { attendance: actual.attendance - forecast.attendance, revenue: actual.revenue - forecast.revenue, costs: actual.costs - forecast.costs, profit: actual.profit - forecast.profit },
      };
    }
  }

  return { inputs, marginPerHead, breakEvenAttendance, revenue, costs, profit, breaksEven, event, forecastVsActual };
}

export function health(): ClubHealth {
  requireRole(HEALTH_ROLES, 'Only the president can view Club Health.');

  const components: HealthComponent[] = [];

  // Membership: active share of everyone who has ever joined (active or
  // lapsed). No renewal history is modeled in the mock, so this uses the
  // active-share-alone fallback the contract itself describes for a club
  // with no lapsed memberships yet.
  const users = listAllUsers();
  const everJoined = users.filter((u) => u.membershipStatus === 'active' || u.membershipStatus === 'lapsed');
  const activeNow = users.filter((u) => u.membershipStatus === 'active');
  const membershipScore = everJoined.length === 0 ? null : Math.round((activeNow.length / everJoined.length) * 1000) / 10;
  components.push({
    key: 'membership',
    label: 'Membership',
    score: membershipScore,
    weight: 30,
    contribution: membershipScore === null ? 0 : Math.round(((membershipScore * 30) / 100) * 10) / 10,
    reason:
      everJoined.length === 0
        ? 'No one has joined yet.'
        : `${activeNow.length} of ${everJoined.length} people who joined are active members (${Math.round((activeNow.length / everJoined.length) * 100)}%).`,
  });

  // Attendance: checked in vs sold, across closed events only.
  const closedEvents = listMockEvents().filter((e) => e.status === 'closed');
  let sold = 0;
  let checkedIn = 0;
  for (const e of closedEvents) {
    const counts = countsForMockEvent(e.id);
    sold += counts.sold;
    checkedIn += counts.checkedIn;
  }
  const attendanceScore = sold === 0 ? null : Math.round((checkedIn / sold) * 1000) / 10;
  components.push({
    key: 'attendance',
    label: 'Event attendance',
    score: attendanceScore,
    weight: 25,
    contribution: attendanceScore === null ? 0 : Math.round(((attendanceScore * 25) / 100) * 10) / 10,
    reason: sold === 0 ? 'No closed events with ticket sales yet.' : `${checkedIn} of ${sold} tickets were checked in across ${closedEvents.length} closed event(s).`,
  });

  // Volunteering: tasks done vs all tasks, across every fundraiser.
  const allTasks = mockVolunteering.listFundraisers().flatMap((f) => f.tasks);
  const doneTasks = allTasks.filter((t) => t.status === 'done');
  const volunteeringScore = allTasks.length === 0 ? null : Math.round((doneTasks.length / allTasks.length) * 1000) / 10;
  components.push({
    key: 'volunteering',
    label: 'Volunteering',
    score: volunteeringScore,
    weight: 20,
    contribution: volunteeringScore === null ? 0 : Math.round(((volunteeringScore * 20) / 100) * 10) / 10,
    reason: allTasks.length === 0 ? 'No tasks yet.' : `${doneTasks.length} of ${allTasks.length} tasks are done.`,
  });

  // Money: share of cash moved in the last 30 days that was coming in.
  const { inAmount, outAmount } = computeCashMovementLast30Days();
  const moved = inAmount + outAmount;
  const moneyScore = moved === 0 ? null : Math.round((inAmount / moved) * 1000) / 10;
  components.push({
    key: 'money',
    label: 'Money',
    score: moneyScore,
    weight: 25,
    contribution: moneyScore === null ? 0 : Math.round(((moneyScore * 25) / 100) * 10) / 10,
    reason: moved === 0 ? 'No cash has moved in the last 30 days.' : `In the last 30 days ₹${(inAmount / 100).toFixed(2)} came in and ₹${(outAmount / 100).toFixed(2)} went out.`,
  });

  const withData = components.filter((c) => c.score !== null);
  const totalWeight = withData.reduce((s, c) => s + c.weight, 0);
  const score = withData.length === 0 ? null : Math.round(withData.reduce((s, c) => s + (c.score! * c.weight) / totalWeight, 0));

  return { score, components };
}
