import unittest

from shop import order_total


class OrderTotal(unittest.TestCase):
    def test_no_tax(self):
        self.assertEqual(order_total(100, 0), 100)


if __name__ == "__main__":
    unittest.main()
