"""Late fees, in cents."""
from .catalog import TOOLS

DAILY_FEE_CENTS = 50


def days_late(loan, returned_on):
    """Whole days the tool came back after its due date."""
    return max(0, (returned_on - loan.due_on).days)


def late_fee(loan, returned_on, plan):
    """What a member on plan owes for bringing the tool back on returned_on."""
    if plan == "volunteer":
        return 0
    return min(days_late(loan, returned_on) * DAILY_FEE_CENTS, TOOLS[loan.sku]["replacement_cents"])
