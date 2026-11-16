import unittest

from parcels import shipping_cost


class ShippingCost(unittest.TestCase):
    def test_light_parcel(self):
        self.assertEqual(shipping_cost(5), 20)


if __name__ == "__main__":
    unittest.main()
