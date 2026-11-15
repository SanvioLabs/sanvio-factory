"""Members, by id. A member's plan is "standard" or "volunteer"."""

MEMBERS = {
    "m1": {"name": "Ada Brook", "plan": "standard"},
    "m2": {"name": "Jo Fenn", "plan": "volunteer"},
    "m3": {"name": "Sam Reyes", "plan": "standard"},
}


def plan_of(member_id):
    """The member's plan."""
    return MEMBERS[member_id]["plan"]
