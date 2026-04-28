# CLAUDE.md

Project context for Claude Code working in this repo.

## What this is

A cross-platform PySide6 desktop **companion** that watches the user's
Claude Code sessions and reacts in-character. Originated as a
sub-package of [`term-pet`](https://github.com/paulrobello/tpet)
(Swift `Deskpet` + terminal renderers); the Qt frontend and the
modules needed for in-process commentary were extracted here.

The product was rebranded from "pet" to "companion" — code, config,
and docs all use "companion" now. The Swift parent binary keeps its
historical name (`Deskpet` / `PetController.swift`) since it lives in
the unchanged sibling repo.

## Layout

```
src/claude_code_assist/
    qt/             # Qt frontend: window, controller, bubble, tray, app entry
    cli/            # `companion` subcommand dispatcher (new / art / roster / archive)
    art/            # Gemini sprite-sheet pipeline + chroma key + frame split + placeholder copier
    commentary/     # LLM call pipeline (ThreadPoolExecutor, prompts)
    monitor/        # watchdog-based JSONL session watcher + text-file follower
    models/         # CompanionProfile, Rarity, StatConfig pydantic models
    profile/        # profile.json load / save + storage helpers + LLM-driven generator + leveling
    assets/         # bundled placeholder PNGs for `companion art -> Prefill`
    config.py       # CompanionConfig + multi-provider (Claude / Ollama / OpenAI / OpenRouter / Gemini)
    llm_client.py   # Shared OpenAI-compatible client factory
    io.py           # save_json / load_json helpers
```

The CLI entry point is `claude_code_assist.cli:main` (the `companion`
console script). With no arguments it runs the Qt companion (still
runnable via `python -m claude_code_assist.qt`); with a name it
switches active and runs; with a subcommand it dispatches.

## Commands

```bash
companion                     # run the active companion
companion <name>              # switch active to <name> and run
companion --debug             # mirror logs to <config>/debug.log

companion new                 # interactive generation (quiz / free / random)
companion art                 # generate / prefill / recrop / restore for active companion
companion roster              # list + switch between companions
companion archive             # clear active marker

make dev                      # alias for `uv run companion`
make checkall                 # fmt + lint + typecheck + tests
make sync                     # uv sync
```

## Config layout

```
~/.config/claude-code-assist/
├── config.json                  # LLM provider + cooldown / budget + active_companion + tray toggles
├── debug.log                    # written when --debug is passed
├── .env                         # API keys (OPENAI_API_KEY, GEMINI_API_KEY, …)
└── roster/<CompanionName>/
    ├── profile.json
    ├── art/                     # frame_{0..9}.png + sprite.png + meta.json + tray icon
    └── art_archive/<ts>/        # previous art sets after `companion art` regen
```

`profile.storage.migrate_legacy_layout()` is idempotent and brings
older layouts (flat `profile.yaml` + `art/` at the top of the config
dir, the mid-2026 `pet/` subdir, the late-2026 `companion/` subdir +
top-level `archive/`, `{name}_` art prefixes) into this layout on every
launch.

## Key behaviors / constants

See `MILESTONES.md` for the full table. The most important:

- 30 Hz tick. State machine: IDLE → WALKING / SLEEPING / DRAGGING /
  FALLING / LANDED / REACTING.
- Walk speed 1.6 px/frame, gravity 1.6 px/frame², stun threshold
  36 px/frame, awake window 10 s.
- Bubble fade 0.18 s, auto-hide 10 s.
- macOS: NSWindow level pinned to `NSScreenSaverWindowLevel` via
  pyobjc; activation policy `.accessory`. Re-promoted on every
  `applicationStateChanged` so Qt can't lower it.

## Sibling repo

`~/projects/term-pet` still hosts the terminal frontends, the Swift
`Deskpet` binary, and the AI-art generation pipeline. The shared
modules (`commentary`, `monitor`, `llm_client`) were **copied** here,
not symlinked — the two repos can drift independently. Locally
managed (rebranded / heavily refactored): `models`, `config`,
`profile`, `io`.
