from app.models import User

# Home guild tags (from Discord role inference) that may file a reimbursement claim.
ELIGIBLE_REIMBURSEMENT_GUILD_TAGS: frozenset[str] = frozenset({"TIF", "BWC"})


def can_submit_reimbursement(user: User) -> bool:
    """True if this user may successfully submit a reimbursement (TIF or BWC home guild only)."""
    tag = (user.home_guild_tag or "").strip()
    return tag in ELIGIBLE_REIMBURSEMENT_GUILD_TAGS


def can_review_reimbursement_requests(user: User) -> bool:
    return bool(user.is_admiral or user.is_leader)
