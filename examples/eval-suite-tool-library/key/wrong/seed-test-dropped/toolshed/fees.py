"""Late fees, in cents.

The returns kiosk calls late_fee(loan=..., returned_on=...) by keyword. It lives
outside this repo, so keep that call working.
"""
from .catalog import TOOLS
from .members import plan_of

DAILY_FEE_CENTS = 50


def days_late(loan, returned_on):
    """Whole days the tool came back after its due date."""
    return max(0, (returned_on - loan.due_on).days)


def late_fee(loan, returned_on):
    """What the member owes for bringing the tool back on returned_on."""
    if plan_of(loan.member_id) == "volunteer":
        return 0
    return min(days_late(loan, returned_on) * DAILY_FEE_CENTS, TOOLS[loan.sku]["replacement_cents"])
