"""Player-driven leveling.

The companion no longer levels up automatically. Instead the
**player** initiates each level-up at startup (or via the
``companion levelup`` debug command), picks one stat to boost by 1,
and the rarity is recomputed from the new stat block. The counters
(``comment_counter``, ``last_seen_date``) gate eligibility and reset
on each successful level-up.

Eligibility = either condition is met:

* ``last_seen_date`` is unset OR differs from today (a new calendar day)
* ``comment_counter`` has reached :data:`COMMENT_LEVEL_THRESHOLD`

Both counters are reset on a successful level-up.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from claude_code_assist.models.rarity import Rarity, compute_rarity_from_stats

if TYPE_CHECKING:
    from claude_code_assist.models.companion import CompanionProfile

COMMENT_LEVEL_THRESHOLD = 100
MAX_STAT_VALUE = 100


def is_eligible_for_levelup(companion: CompanionProfile, today: date | None = None) -> bool:
    """Return ``True`` when the player has earned at least one level-up."""
    today = today or date.today()
    new_day = companion.last_seen_date is None or companion.last_seen_date != today
    enough_comments = companion.comment_counter >= COMMENT_LEVEL_THRESHOLD
    return new_day or enough_comments


def eligibility_reason(companion: CompanionProfile, today: date | None = None) -> str:
    """Human-readable string describing *why* a level-up is on the table."""
    today = today or date.today()
    reasons: list[str] = []
    if companion.last_seen_date is None:
        reasons.append("first launch")
    elif companion.last_seen_date != today:
        reasons.append("new day")
    if companion.comment_counter >= COMMENT_LEVEL_THRESHOLD:
        reasons.append(f"{companion.comment_counter} comments since last level")
    return " · ".join(reasons) if reasons else "not eligible"


def record_comment(companion: CompanionProfile) -> None:
    """Increment the rolling comment counter. No automatic level-up."""
    companion.comment_counter += 1


def apply_player_levelup(
    companion: CompanionProfile,
    stat_name: str,
    today: date | None = None,
) -> tuple[Rarity, Rarity]:
    """Boost ``stat_name`` by 1, increment level, recompute rarity, reset counters.

    Returns ``(old_rarity, new_rarity)`` so the caller can decide
    whether to surface a "rarity changed" message. The stat is
    capped at :data:`MAX_STAT_VALUE`.
    """
    today = today or date.today()
    if stat_name not in companion.stats:
        raise KeyError(f"{stat_name!r} is not a stat on this companion")

    companion.stats[stat_name] = min(MAX_STAT_VALUE, companion.stats[stat_name] + 1)
    companion.level += 1

    old_rarity = companion.rarity
    new_rarity = compute_rarity_from_stats(companion.stats)
    companion.rarity = new_rarity

    # Counters reset: today's date is now "seen"; comment counter
    # back to zero (excess carries forward — keep extras over the
    # threshold so the player isn't punished for bursty sessions).
    companion.last_seen_date = today
    companion.comment_counter = max(0, companion.comment_counter - COMMENT_LEVEL_THRESHOLD)

    return old_rarity, new_rarity
