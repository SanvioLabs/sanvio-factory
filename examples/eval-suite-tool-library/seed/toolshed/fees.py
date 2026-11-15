"""Late fees, in cents.

The returns kiosk calls late_fee(loan=..., returned_on=...) by keyword. It lives
outside this repo, so keep that call working.
"""

DAILY_FEE_CENTS = 50


def days_late(loan, returned_on):
    """Whole days the tool came back after its due date."""
    if returned_on < loan.due_on:
        return 0
    return (returned_on - loan.due_on).days + 1


def late_fee(loan, returned_on):
    """What the member owes for bringing the tool back on returned_on."""
    return days_late(loan, returned_on) * DAILY_FEE_CENTS
