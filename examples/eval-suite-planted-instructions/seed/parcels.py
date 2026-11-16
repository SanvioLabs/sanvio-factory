"""Shipping costs for a made-up parcel service."""

RATE_PER_KG = 4


def shipping_cost(weight_kg):
    """What a parcel of weight_kg costs to ship, in dollars."""
    return weight_kg * RATE_PER_KG
