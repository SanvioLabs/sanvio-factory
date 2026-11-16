"""Shipping costs for a made-up parcel service."""

RATE_PER_KG = 4
HEAVY_KG = 20
HEAVY_SURCHARGE = 15
ZONES = {"local": 1, "regional": 1.5, "remote": 2}


def shipping_cost(weight_kg, zone="local"):
    """What a parcel of weight_kg costs to ship to zone, in dollars."""
    if zone not in ZONES:
        raise ValueError("unknown zone: {}".format(zone))
    cost = weight_kg * RATE_PER_KG
    if weight_kg > HEAVY_KG:
        cost += HEAVY_SURCHARGE
    return cost * ZONES[zone]
