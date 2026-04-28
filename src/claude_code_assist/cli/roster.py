"""``companion roster`` — list every companion and switch which is active.

With the roster layout there's no separate "archive" folder: every
companion lives at ``<config>/roster/<slot>/`` and the
``active_companion`` field of ``config.json`` names which one is
currently in use. Switching is a single config write — no file moves.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import questionary
from rich.console import Console

from claude_code_assist.profile.storage import (
    PROFILE_FILENAME,
    get_active_slot,
    list_roster,
    load_profile,
    migrate_legacy_layout,
    set_active_slot,
)

if TYPE_CHECKING:
    from claude_code_assist.models.rarity import Rarity
    from claude_code_assist.models.role import Role

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class _RosterEntry:
    slot: str
    """Folder name inside ``<config>/roster/`` (the addressing key)."""
    display_name: str
    """Companion name from ``profile.json`` (may differ from slot on collision)."""
    creature_type: str
    is_active: bool
    has_art: bool
    rarity: Rarity | None
    role: Role | None
    level: int
    created_at: datetime | None


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="companion roster",
        description="List every companion in your roster and switch which one is active.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Config directory override. Defaults to $XDG_CONFIG_HOME/claude-code-assist.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser.parse_args(argv)


def _resolve_config_dir(override: Path | None) -> Path:
    if override is not None:
        return override
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "claude-code-assist" if xdg else Path.home() / ".config" / "claude-code-assist"


# ---------------------------------------------------------------------------
# Roster scan
# ---------------------------------------------------------------------------


def _has_complete_art(slot_dir: Path) -> bool:
    art_dir = slot_dir / "art"
    if not art_dir.is_dir():
        return False
    return all((art_dir / f"frame_{i}.png").is_file() for i in range(10))


def _scan_roster(config_dir: Path) -> list[_RosterEntry]:
    """Return one entry per ``roster/<slot>/`` folder.

    The active slot (per ``config.json``) is sorted to the top; the rest
    follow in newest-first order by ``profile.created_at`` (the LLM
    write timestamp), with folders that lack a parseable profile
    falling back to filesystem mtime so they still show up.
    """
    active_slot = get_active_slot(config_dir)
    entries: list[_RosterEntry] = []
    for slot_dir in list_roster(config_dir):
        profile = load_profile(slot_dir / PROFILE_FILENAME)
        if profile is not None:
            display_name = profile.name
            creature_type = profile.creature_type
            rarity: Rarity | None = profile.rarity
            role: Role | None = profile.role
            level = profile.level
            created = profile.created_at
        else:
            display_name = slot_dir.name
            creature_type = ""
            rarity = None
            role = None
            level = 1
            created = datetime.fromtimestamp(slot_dir.stat().st_mtime).astimezone()
        entries.append(
            _RosterEntry(
                slot=slot_dir.name,
                display_name=display_name,
                creature_type=creature_type,
                is_active=slot_dir.name == active_slot,
                has_art=_has_complete_art(slot_dir),
                rarity=rarity,
                role=role,
                level=level,
                created_at=created,
            )
        )

    entries.sort(
        key=lambda e: (
            0 if e.is_active else 1,
            -(e.created_at.timestamp() if e.created_at is not None else 0),
        )
    )
    return entries


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def _format_choice_title(entry: _RosterEntry) -> list[tuple[str, str]]:
    """``Name ★★★★★ · creature_type · Lv. N (active|created…) ⚠ no art?``.

    Name is colored by rarity (canonical ``Rarity.color`` hex via
    ``fg:#rrggbb``); stars share the rarity color. Everything after
    the dot separator is dimmed so the name + tier read first.
    """
    # Same canonical hex Rarity.color uses everywhere; prompt_toolkit
    # accepts ``fg:#rrggbb`` style strings.
    name_style = f"fg:{entry.rarity.color}" if entry.rarity is not None else ""
    stars = entry.rarity.stars if entry.rarity is not None else ""

    if entry.is_active:
        suffix = "  (active)"
    elif entry.created_at is not None:
        suffix = f"  (created {entry.created_at.strftime('%Y-%m-%d %H:%M')})"
    else:
        suffix = ""

    from claude_code_assist.models.role import ROLE_CATALOG  # noqa: PLC0415

    parts: list[tuple[str, str]] = [(name_style, entry.display_name)]
    if stars:
        parts.append((name_style, f"  {stars}"))
    parts.append(("fg:ansibrightblack", f"  ·  Lv. {entry.level}"))
    if entry.creature_type:
        parts.append(("fg:ansibrightblack", f"  · {entry.creature_type}"))
    if entry.role is not None:
        defn = ROLE_CATALOG.get(entry.role)
        role_color = defn.color if defn else "#888"
        parts.append(("fg:ansibrightblack", "  ·  "))
        parts.append((f"fg:{role_color}", entry.role.value))
    if suffix:
        parts.append(("fg:ansibrightblack", suffix))
    if not entry.has_art:
        parts.append(("fg:ansiyellow", "  ⚠ no art"))
    return parts


def _pick_companion(entries: list[_RosterEntry]) -> _RosterEntry | None:
    choices = [questionary.Choice(title=_format_choice_title(e), value=e.slot) for e in entries]
    try:
        selected = questionary.select(
            "Choose a companion to activate:",
            choices=choices,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None
    if selected is None:
        return None
    return next((e for e in entries if e.slot == selected), None)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(argv: list[str]) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    config_dir = _resolve_config_dir(args.config_dir)
    migrate_legacy_layout(config_dir)

    entries = _scan_roster(config_dir)
    if not entries:
        console.print("[yellow]No companions in your roster.[/yellow]")
        console.print("Run [bold]companion new[/bold] to create one.")
        return 0

    chosen = _pick_companion(entries)
    if chosen is None:
        console.print("[yellow]Cancelled — no change.[/yellow]")
        return 0

    if chosen.is_active:
        console.print(f"[dim]'{chosen.display_name}' is already active. No change.[/dim]")
        return 0

    set_active_slot(config_dir, chosen.slot)
    console.print(f"[green]'{chosen.display_name}' is now the active companion.[/green]")
    return 0
