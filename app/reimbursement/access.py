from app.models import User
from app.config import get_settings


def reimbursement_enabled_guild_tags() -> frozenset[str]:
    raw = (get_settings().reimbursement_enabled_guild_tags or "").strip()
    tags = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return frozenset(tags)


def can_submit_reimbursement(user: User) -> bool:
    """True if this user's home guild tag is enabled for reimbursement in settings."""
    tag = (user.home_guild_tag or "").strip().upper()
    return bool(tag and tag in reimbursement_enabled_guild_tags())


def can_review_reimbursement_requests(user: User) -> bool:
    return bool(user.is_admiral or user.is_leader or user.is_officer)


def can_review_reimbursement_request_for_tag(user: User, submitter_guild_tag: str | None) -> bool:
    """True if reviewer has command role and matches the request's submitter guild tag."""
    if not can_review_reimbursement_requests(user):
        return False
    reviewer_tag = (user.home_guild_tag or "").strip().upper()
    request_tag = (submitter_guild_tag or "").strip().upper()
    if not reviewer_tag or not request_tag:
        return False
    return reviewer_tag == request_tag
