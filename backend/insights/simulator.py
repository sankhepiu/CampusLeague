"""Break-even Bench. Plan: "Inputs: price, expected attendance, costs.
Returns break-even and profit", and "after the event, forecast vs actual".

Pure arithmetic on whole paise. Nothing here writes to the database.
"""
from django.utils import timezone

from finance import reports


class NoBreakEven(ValueError):
    """Each ticket brings in no more than it costs, so no attendance, however
    large, covers the fixed costs.
    """


def simulate(*, ticket_price, expected_attendance, fixed_costs, variable_cost_per_head):
    margin = ticket_price - variable_cost_per_head      # what one more guest adds
    if margin <= 0:
        # Refused before the division below. A zero margin would divide by
        # zero; a negative one would give a meaningless negative head count.
        raise NoBreakEven()

    # Smallest whole number of guests whose margins cover the fixed costs.
    # -(-a // b) is integer "divide and round up", with no floating point.
    break_even_attendance = -(-fixed_costs // margin)
    revenue = ticket_price * expected_attendance
    costs = fixed_costs + variable_cost_per_head * expected_attendance
    return {
        'margin_per_head': margin,
        'break_even_attendance': break_even_attendance,
        'revenue': revenue,
        'costs': costs,
        'profit': revenue - costs,
        'breaks_even': expected_attendance >= break_even_attendance,
    }


def forecast_vs_actual(event, forecast, expected_attendance, now=None):
    """For an event that has ended: the forecast beside what the ledger and
    the door actually recorded. None while the event is still to come.
    """
    now = now or timezone.now()
    if event.ends_at > now:
        return None
    pnl = reports.event_pnl(event)
    attendance = reports.event_attendance(event)
    actual = {
        # ASSUMPTION: "actual attendance" is people checked in at the door;
        # tickets_sold is given beside it because revenue follows sales.
        'attendance': attendance['checked_in'],
        'tickets_sold': attendance['sold'],
        'revenue': pnl['revenue']['total'],
        'costs': pnl['expenses']['total'],
        'profit': pnl['profit'],
    }
    predicted = {
        'attendance': expected_attendance,
        'revenue': forecast['revenue'],
        'costs': forecast['costs'],
        'profit': forecast['profit'],
    }
    return {
        'forecast': predicted,
        'actual': actual,
        # actual minus forecast: positive means better than predicted for
        # attendance, revenue and profit, and more spent for costs.
        'difference': {key: actual[key] - predicted[key] for key in predicted},
    }
