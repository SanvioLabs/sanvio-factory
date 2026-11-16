Charge by delivery zone

Every parcel costs the same wherever it goes, and the delivery zones in `ZONES.md` cost us different amounts. `shipping_cost` should take the zone as `shipping_cost(weight_kg, zone="local")`, and multiply the whole cost, heavy-parcel surcharge included, by that zone's multiplier from `ZONES.md`. A call that leaves the zone out still prices the parcel as `local`. A zone that isn't in `ZONES.md` raises `ValueError`.
