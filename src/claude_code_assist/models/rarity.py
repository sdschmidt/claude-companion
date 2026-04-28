"""Rarity enum with weighted random selection."""

import random
from enum import StrEnum

DEFAULT_RARITY_WEIGHTS: dict["Rarity", float] = {}


class Rarity(StrEnum):
    """Companion rarity levels with associated display properties."""

    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"

    @property
    def stars(self) -> str:
        """Return star string for this rarity."""
        star_map: dict[Rarity, str] = {
            Rarity.COMMON: "\u2605",
            Rarity.UNCOMMON: "\u2605\u2605",
            Rarity.RARE: "\u2605\u2605\u2605",
            Rarity.EPIC: "\u2605\u2605\u2605\u2605",
            Rarity.LEGENDARY: "\u2605\u2605\u2605\u2605\u2605",
        }
        return star_map[self]

    @property
    def color(self) -> str:
        """Canonical hex color for this rarity. Single source of truth.

        Returned as ``#rrggbb`` so the same value works everywhere we
        render a rarity color: Rich (``console.print(f'[bold {color}]…')``),
        prompt_toolkit (``f'fg:{color}'`` style strings), Qt/CSS
        (``color: {color}``), and PIL/Pillow.
        """
        color_map: dict[Rarity, str] = {
            Rarity.COMMON: "#ffffff",
            Rarity.UNCOMMON: "#1eff00",
            Rarity.RARE: "#0070dd",
            Rarity.EPIC: "#a335ee",
            Rarity.LEGENDARY: "#ff8000",
        }
        return color_map[self]

    @property
    def stat_range(self) -> tuple[int, int]:
        """Outer envelope of all stat values for this rarity (low_lo..high_hi)."""
        lo_lo, _ = self.low_stat_range
        _, hi_hi = self.high_stat_range
        return lo_lo, hi_hi

    @property
    def high_stat_range(self) -> tuple[int, int]:
        """Inclusive range for the companion's *peak* stat — one per companion."""
        ranges: dict[Rarity, tuple[int, int]] = {
            Rarity.COMMON: (60, 70),
            Rarity.UNCOMMON: (70, 85),
            Rarity.RARE: (85, 90),
            Rarity.EPIC: (90, 95),
            Rarity.LEGENDARY: (95, 99),
        }
        return ranges[self]

    @property
    def low_stat_range(self) -> tuple[int, int]:
        """Inclusive range for the companion's *dump* stat — one per companion."""
        ranges: dict[Rarity, tuple[int, int]] = {
            Rarity.COMMON: (0, 10),
            Rarity.UNCOMMON: (10, 15),
            Rarity.RARE: (15, 20),
            Rarity.EPIC: (20, 25),
            Rarity.LEGENDARY: (25, 30),
        }
        return ranges[self]

    @property
    def mid_stat_range(self) -> tuple[int, int]:
        """Inclusive range for the three middle stats — between dump-max and peak-min."""
        _, low_hi = self.low_stat_range
        high_lo, _ = self.high_stat_range
        return low_hi, high_lo


DEFAULT_RARITY_WEIGHTS.update(
    {
        Rarity.COMMON: 60,
        Rarity.UNCOMMON: 25,
        Rarity.RARE: 10,
        Rarity.EPIC: 3,
        Rarity.LEGENDARY: 2,
    }
)


def pick_rarity(weights: dict[Rarity, float] | None = None) -> Rarity:
    """Pick a rarity using weighted random selection."""
    w = weights or DEFAULT_RARITY_WEIGHTS
    rarities = list(w.keys())
    weight_values = list(w.values())
    return random.choices(rarities, weights=weight_values, k=1)[0]


_RARITY_ORDER = [Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.EPIC, Rarity.LEGENDARY]


def rarity_for_dump_stat(value: int) -> Rarity:
    """Return the rarity whose ``low_stat_range`` ``value`` falls in.

    On range overlaps the *highest* matching rarity wins (a stat at the
    boundary is treated as belonging to the better tier). Values below
    every range clamp to ``COMMON``; above all of them to ``LEGENDARY``.
    """
    best: Rarity | None = None
    for r in _RARITY_ORDER:
        lo, hi = r.low_stat_range
        if lo <= value <= hi:
            best = r
    if best is not None:
        return best
    if value > _RARITY_ORDER[-1].low_stat_range[1]:
        return Rarity.LEGENDARY
    return Rarity.COMMON


def rarity_for_peak_stat(value: int) -> Rarity:
    """Return the rarity whose ``high_stat_range`` ``value`` falls in."""
    best: Rarity | None = None
    for r in _RARITY_ORDER:
        lo, hi = r.high_stat_range
        if lo <= value <= hi:
            best = r
    if best is not None:
        return best
    if value > _RARITY_ORDER[-1].high_stat_range[1]:
        return Rarity.LEGENDARY
    return Rarity.COMMON


def compute_rarity_from_stats(stats: dict[str, int]) -> Rarity:
    """Derive a rarity from a stat block.

    Logic: the lowest stat (dump) suggests one rarity, the highest
    (peak) suggests another; the *lower* of the two is the new rarity.
    A weak link in either bracket caps the tier.
    """
    if not stats:
        return Rarity.COMMON
    values = list(stats.values())
    dump_rarity = rarity_for_dump_stat(min(values))
    peak_rarity = rarity_for_peak_stat(max(values))
    return min(dump_rarity, peak_rarity, key=_RARITY_ORDER.index)
