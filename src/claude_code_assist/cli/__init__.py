"""``companion`` CLI dispatcher.

The top-level ``companion`` script peeks at ``sys.argv[1]``: if it's a
known subcommand (``new`` / ``art`` / ``roster``) we dispatch to the
matching module; otherwise we fall through to the Qt companion entry point
(``claude_code_assist.qt.app.main``) with the original argv. This
keeps existing flags (``--debug``, ``--config-dir``, ``--profile``,
…) working for the no-subcommand "just run the companion" path.

We don't use a real subparser here on purpose — the companion entry point has
its own argparse and adopting subparsers globally would force every flag
to be redeclared at the top level.
"""

from __future__ import annotations

import sys

_SUBCOMMANDS = ("new", "art", "roster", "levelup")


def _print_top_level_help() -> None:
    print(
        "companion — Claude Code desktop companion\n"
        "\n"
        "Usage:\n"
        "  companion              Run the companion (default).\n"
        "  companion new          Generate a new companion (archives the existing one).\n"
        "  companion art          Generate sprite art for the current companion.\n"
        "  companion roster       List + switch between archived companions.\n"
        "  companion levelup      Force a level-up + stat boost (debug; skips eligibility).\n"
        "\n"
        "Run 'companion <subcommand> --help' for subcommand-specific options.\n"
        "Run 'companion --help' (no subcommand) for companion-runtime flags.\n"
    )


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] in _SUBCOMMANDS:
        cmd, sub_argv = raw[0], raw[1:]
        if cmd == "new":
            from claude_code_assist.cli.new import run as run_new

            return run_new(sub_argv)
        if cmd == "art":
            from claude_code_assist.cli.art import run as run_art

            return run_art(sub_argv)
        if cmd == "roster":
            from claude_code_assist.cli.roster import run as run_roster

            return run_roster(sub_argv)
        if cmd == "levelup":
            from claude_code_assist.cli.levelup import run as run_levelup

            return run_levelup(sub_argv)

    if raw and raw[0] in ("help", "--commands"):
        _print_top_level_help()
        return 0

    from claude_code_assist.qt.app import main as run_companion

    return run_companion(raw)


if __name__ == "__main__":
    raise SystemExit(main())
