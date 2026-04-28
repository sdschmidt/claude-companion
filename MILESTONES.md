# Milestones

Status legend: ✅ done · 🚧 in progress · ⬜ pending.

## ✅ M1 — Skeleton
- Tray icon (`QSystemTrayIcon`) with sprite preview + Quit.
- Frameless transparent always-on-top window
  (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | …`,
  `WA_TranslucentBackground`). On macOS the level + collection
  behavior are pinned via pyobjc so the window stays above other apps
  and doesn't hide on focus loss.
- Loads 10 PNG frames from `--art-dir` matching `{companion}_frame_{N}.png`,
  rendered at the active screen's `devicePixelRatio` so the companion stays
  sharp on Retina.
- Idle animation at 30 Hz, mirroring the Swift port:
  * Idle swap every 30 frames between idleA (0) and idleB (1).
  * Blink every 90 frames for 6 frames: blinkA (2) for 3 frames,
    blinkB (3) for 3 frames.
- Standalone runnable: `python -m claude_code_assist.qt`.

## ✅ M2 — Movement and physics
- Walking: 1.6 px/frame, alternating walkA (6) / walkB (7) every
  6 frames, randomized facing direction (mirror flag flips horizontally
  on draw).
- Falling: gravity 1.6 px/frame² applied to vertical velocity.
- Landing: stun threshold 36 px/frame; if exceeded, enter `LANDED` for
  30 frames and mark `awake_until = now + 10s`.
- Dragging: mouse press starts drag, release transitions to `FALLING`
  (gravity on) or `IDLE`.
- Ground = active screen `availableGeometry().bottom()`.
- Random idle-exit behavior:
  * Awake (within 10s of landing/drag): 60 % walk, 40 % idle.
  * Otherwise: 15 % sleep, 85 % walk-or-idle.
- Walk frames flip facing every walk entry (random coin flip).

## 🚧 M3 — Speech bubble + in-process commentary backend
The Swift binary was an external process driven by `tpet` over a Unix
socket. The Qt port runs everything in one process: the session
watcher + LLM client live inside this app, so the speech-bubble feed
is just an in-process method call (no socket, no JSON framing, no
parent process required).

- Speech bubble: frameless translucent QWidget anchored above the companion.
  * Fade in to opacity 1.0 over 0.18 s.
  * Auto-hide after 10.0 s (cancelable; new `show_comment` resets timer).
  * Fade out to 0.0 over 0.18 s on hide.
  * Repositions every tick: bottom-left of bubble overlaps top-right of
    companion by 6 px; flips to top-left near right screen edge.
  * Text: max 200 px wide, max 6 lines, word-wrapped, 10/6 px padding.
  * Public API: `bubble.show_comment(text)` / `bubble.hide_comment()`.
- Backend (`qt/backend.py`): wraps the existing
  `commentary/` and `monitor/` packages.
  * SessionWatcher runs in its own watchdog thread.
  * Commentary calls go through a single-worker `ThreadPoolExecutor`
    so the 30 Hz tick never blocks on LLM I/O.
  * `app.py` polls completed futures each tick and forwards text to
    `bubble.show_comment()`; session events trigger the REACTING state.
- Tray "React now" item submits a fresh comment, bypassing the cooldown.

## ✅ M4 — Tray menu (full content + toggles)
- Header: companion name (bold, rarity-colored) + rarity stars + tier label.
- Info rows (monospaced, disabled): `session`, `cwd`, `config`.
- Sprite preview (idle-A scaled to 96×96).
- Stats table: `NAME ██████░░░░  100` — 10-cell bar (filled per 10 %).
- Bio + Backstory text blocks (wrapped).
- Gravity toggle (checkbox, persisted).
- Walk toggle (checkbox, persisted).
- Open Config Folder (`open` on macOS, `xdg-open` on Linux).
- Quit.
- Persistence: `<config_dir>/companion_settings.json`
  (`{"gravityEnabled": bool, "walkingEnabled": bool}`). Falls back to
  `QSettings` when no config dir is given.
- GNOME tray-extension caveat documented in README.

## ⬜ M5 — Window perching
- Cross-platform abstraction: `WindowSurfaces.current(excluding=…)`
  returning `[(rect, top_y)]`. Implementations:
  * macOS: `pyobjc` → `Quartz.CGWindowListCopyWindowInfo`.
  * Linux X11: `python-xlib` → walk `_NET_CLIENT_LIST`, query each
    window's geometry + `_NET_FRAME_EXTENTS`.
  * Linux Wayland: not implementable. Return empty list and document.
- Match the Swift perching algorithm: perch tolerance ≥ 80 × 20; track
  `current_surface_id`; drop and fall when the companion center leaves the
  surface's X bounds or rises above the surface; on falling, pick the
  highest valid surface the companion center is passing through.

## ⬜ M6 — Sprite seeding and bundled placeholder fallbacks
- Bundle a default placeholder companion sprite sheet inside `assets/`.
- On startup, if `--art-dir` is missing any frame, copy the bundled
  fallbacks in (one-time seeding, never overwrites user art).
- Optionally ship a small `companion new`-style flow inside this repo so the
  Qt app is fully self-sufficient (currently relies on the companion
  `tpet new` to generate a profile + sprite sheet).

## Constants (kept in sync with Swift `PetController.swift`)

| Setting              | Value                       |
|----------------------|-----------------------------|
| Tick rate            | 30 Hz (33.33 ms)            |
| Idle duration        | 30–120 frames (1–4 s)       |
| Walk duration        | 90–300 frames (3–10 s)      |
| Sleep duration       | 120–360 frames (4–12 s)     |
| Landed duration      | 30 frames (1 s)             |
| Reacting duration    | 120 frames (4 s)            |
| Walk speed           | 1.6 px/frame                |
| Gravity              | 1.6 px/frame²               |
| Stun threshold       | 36 px/frame                 |
| Perch min size       | 80 × 20 px                  |
| Awake window         | 10.0 s                      |
| Idle swap interval   | 30 frames                   |
| Blink period         | 90 frames                   |
| Blink length         | 6 frames                    |
| Blink half-length    | 3 frames                    |
| Walk frame interval  | 6 frames                    |
| Bubble fade          | 0.18 s                      |
| Bubble auto-hide     | 10.0 s                      |
| Bubble max width     | 200 px                      |
| Bubble max lines     | 6                           |
| Bubble padding       | 10 / 6 px                   |
| Bubble corner radius | 10 px                       |
| Bubble overlap       | 6 px                        |
| Sprite canvas        | 64 × 64 px                  |
| Tray icon size       | 22 / 44 px (1× / 2× DPR)    |
| Menu preview sprite  | 96 × 96 px                  |
