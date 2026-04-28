"""Stat configuration and generation."""

import random

from pydantic import BaseModel, Field

from claude_code_assist.models.rarity import Rarity

DEFAULT_STAT_NAMES: list[str] = ["DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK"]

# Short, single-line definitions surfaced to the LLM so generated stats
# track the persona — used in the profile-generation system prompt and
# any future stat-tooltip UI. Keys must match ``DEFAULT_STAT_NAMES``.
STAT_DEFINITIONS: dict[str, str] = {
    "DEBUGGING": "Attentiveness to errors.",
    "PATIENCE": "Tolerance for repetitive tasks.",
    "CHAOS": "Unpredictability of reactions.",
    "WISDOM": "Overall knowledge/intelligence.",
    "SNARK": "Tendency for sarcastic responses.",
}


class StatConfig(BaseModel):
    """Configuration for companion stat generation."""

    names: list[str] = Field(
        default_factory=lambda: list(DEFAULT_STAT_NAMES),
        description=(
            "Ordered list of stat names used during random fallback generation. "
            "Default: DEBUGGING, PATIENCE, CHAOS, WISDOM, SNARK."
        ),
    )
    pool_size: int = Field(
        default=5,
        description="Number of stats to generate per companion during random fallback. Must be <= len(names).",
    )


def shape_stats(
    rarity: Rarity,
    llm_hints: dict[str, int] | None = None,
    *,
    names: list[str] | None = None,
) -> dict[str, int]:
    """Build a peak / dump / mid stat block within the rarity's ranges.

    The companion always has exactly one *peak* stat (highest range),
    one *dump* stat (lowest range), and three *mid* stats. Which stat
    is peak vs dump is decided by ``llm_hints`` if provided —
    highest-valued hint becomes peak, lowest becomes dump — otherwise
    they're picked at random. Numeric values are then re-rolled within
    the matching rarity range, so the LLM's exact numbers don't matter,
    only the relative *ordering* of the stats it cares about.

    Args:
        rarity: Determines the high/low/mid value windows.
        llm_hints: Optional ``{name: value}`` ordering hint from the
            generation LLM. Unknown names are ignored.
        names: Stat name list to populate. Defaults to
            :data:`DEFAULT_STAT_NAMES`. Must have at least 2 entries.
    """
    pool = list(names) if names is not None else list(DEFAULT_STAT_NAMES)
    if len(pool) < 2:
        raise ValueError("shape_stats needs at least two stat names")

    valid_hints: dict[str, int] = {}
    if llm_hints:
        for k, v in llm_hints.items():
            if k in pool and isinstance(v, int | float):
                valid_hints[k] = int(v)

    if len(valid_hints) >= 2:
        ordered = sorted(valid_hints.items(), key=lambda kv: kv[1])
        dump = ordered[0][0]
        peak = ordered[-1][0]
    elif len(valid_hints) == 1:
        peak = next(iter(valid_hints))
        dump = random.choice([n for n in pool if n != peak])
    else:
        peak, dump = random.sample(pool, 2)

    high_lo, high_hi = rarity.high_stat_range
    low_lo, low_hi = rarity.low_stat_range
    mid_lo, mid_hi = rarity.mid_stat_range

    out: dict[str, int] = {}
    for name in pool:
        if name == peak:
            out[name] = random.randint(high_lo, high_hi)
        elif name == dump:
            out[name] = random.randint(low_lo, low_hi)
        else:
            out[name] = random.randint(mid_lo, mid_hi)
    return out


def generate_stats(config: StatConfig, rarity: Rarity) -> dict[str, int]:
    """Random-fallback stat generator (no LLM hints). Calls :func:`shape_stats`."""
    count = min(config.pool_size, len(config.names))
    pool = config.names[:count] if count == len(config.names) else random.sample(config.names, count)
    return shape_stats(rarity, llm_hints=None, names=pool)
