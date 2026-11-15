import unittest
from datetime import date

from toolshed.loans import Loan, LoanRefused, checkout

TODAY = date(2026, 3, 3)


class Checkout(unittest.TestCase):
    def test_a_loan_is_due_a_week_later(self):
        self.assertEqual(checkout("m1", "drill", TODAY, []).due_on, date(2026, 3, 10))

    def test_a_tool_that_is_out_is_refused(self):
        out = Loan("m3", "drill", date(2026, 3, 1), date(2026, 3, 8))
        with self.assertRaises(LoanRefused):
            checkout("m1", "drill", TODAY, [out])

    def test_a_returned_tool_can_go_out_again(self):
        back = Loan("m3", "drill", date(2026, 2, 1), date(2026, 2, 8), date(2026, 2, 7))
        self.assertEqual(checkout("m1", "drill", TODAY, [back]).sku, "drill")

    def test_strangers_are_refused(self):
        with self.assertRaises(LoanRefused):
            checkout("nobody", "drill", TODAY, [])
