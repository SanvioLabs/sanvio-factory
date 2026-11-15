import unittest
from datetime import date

from toolshed.fees import late_fee
from toolshed.loans import Loan


def loan(member_id="m1", sku="drill"):
    return Loan(member_id, sku, date(2026, 3, 3), date(2026, 3, 10))


class LateFees(unittest.TestCase):
    def test_returned_early_costs_nothing(self):
        self.assertEqual(late_fee(loan(), date(2026, 3, 8)), 0)

    def test_each_extra_day_adds_the_daily_fee(self):
        self.assertEqual(late_fee(loan(), date(2026, 3, 14)) - late_fee(loan(), date(2026, 3, 13)), 50)
