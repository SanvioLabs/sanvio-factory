"""Lending a tool to a member."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .catalog import TOOLS
from .members import MEMBERS

LOAN_DAYS = 7


class LoanRefused(Exception):
    """The tool can't be lent. The message says why, and the front desk shows it."""


@dataclass
class Loan:
    member_id: str
    sku: str
    out_on: date
    due_on: date
    returned_on: Optional[date] = None


def checkout(member_id, sku, today, loans):
    """A new loan of sku to member_id from today. loans is every loan on record, returned or not."""
    if member_id not in MEMBERS:
        raise LoanRefused("not a member")
    if sku not in TOOLS:
        raise LoanRefused("no such tool")
    if any(loan.sku == sku and loan.returned_on is None for loan in loans):
        raise LoanRefused("that tool is out")
    return Loan(member_id, sku, today, today + timedelta(days=LOAN_DAYS))
