"""System tray icon + full menu (M4).

The menu mirrors the Swift Companion status-bar menu but is rebuilt from
``QWidgetAction`` blocks so we can render rich content (bold name,
rarity-colored stars, sprite preview, monospace stat bars, wrapped
bio/backstory) inside what is otherwise a plain ``QMenu``. Plain
``QAction`` rows are still used for the toggles, "Open Config Folder",
"React now", and "Quit" so the standard menu chrome (checkmark,
hover highlight, keyboard shortcuts) stays intact.

"Test speech bubble" lived here in M3 as a development aid; M4 drops it.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from claude_code_assist.models.rarity import Rarity

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from claude_code_assist.models.companion import CompanionProfile
    from claude_code_assist.qt.settings import CompanionSettings, SettingsStore

logger = logging.getLogger(__name__)

# Tray icon rendition size. The 64×64 red-square debug icon proved that
# macOS accepts and renders icons at this size (it does not strictly cap
# at the 22 pt slot height as long as a single rendition is provided).
_TRAY_ICON_SIZE = 64

# Debug knob: when True, the tray icon is replaced with a flat 64×64
# red square (saved to ``<config>/{companion_name}_tray_test_red_64.png``) so
# we can tell "macOS is downsampling" from "our pipeline is shrinking".
_TRAY_DEBUG_RED_SQUARE = False

_PREVIEW_SIZE = 173  # logical px — 60 % of the prior 288 px preview

# Scale slider: 80 % … 200 % in 20 % ticks. ``QSlider`` is integer-valued,
# so we work in percent and divide by 100 when handing the value back.
_SCALE_PCT_MIN = 80
_SCALE_PCT_MAX = 200
_SCALE_PCT_STEP = 20
_BAR_CELLS = 10
_BAR_FILLED = "█"  # █
_BAR_EMPTY = "░"  # ░
_TEXT_BLOCK_MAX_PX = 320  # bio/backstory wrap width
_INFO_PATH_MAX_CHARS = 56  # truncate long paths in info rows

_RARITY_CSS_COLOR: dict[Rarity, str] = {
    Rarity.COMMON: "#ffffff",
    Rarity.UNCOMMON: "#1eff00",
    Rarity.RARE: "#0070dd",
    Rarity.EPIC: "#a335ee",
    Rarity.LEGENDARY: "#ff8000",
}

_RARITY_TIER_LABEL: dict[Rarity, str] = {
    Rarity.COMMON: "Common",
    Rarity.UNCOMMON: "Uncommon",
    Rarity.RARE: "Rare",
    Rarity.EPIC: "Epic",
    Rarity.LEGENDARY: "Legendary",
}


def install_tray(
    app: QApplication,
    icon_pixmap: QPixmap,
    *,
    companion: CompanionProfile,
    config_dir: Path,
    art_dir: Path,
    settings: CompanionSettings,
    settings_store: SettingsStore,
    session_label: str,
    cwd_label: str,
    cwd_path: Path,
    on_quit: Callable[[], None],
    on_react_now: Callable[[], None] | None = None,
    on_gravity_toggled: Callable[[bool], None] | None = None,
    on_walking_toggled: Callable[[bool], None] | None = None,
    on_scale_changed: Callable[[float], None] | None = None,
) -> QSystemTrayIcon:
    """Install the tray icon + full menu.  Caller keeps the returned ref alive.

    The toggles call ``on_gravity_toggled`` / ``on_walking_toggled`` so
    the live :class:`CompanionController` updates immediately, then persist
    via ``settings_store`` so the choice survives a relaunch.
    """
    if not QSystemTrayIcon.isSystemTrayAvailable():
        # On GNOME without the AppIndicator extension this returns False;
        # the companion still runs, just without a tray entry.
        logger.warning("System tray is not available on this desktop")

    if _TRAY_DEBUG_RED_SQUARE:
        icon = _build_red_square_icon(save_dir=art_dir)
    else:
        icon = _build_tray_icon(icon_pixmap, save_dir=art_dir)
    tray = QSystemTrayIcon(icon, parent=app)
    tray.setToolTip(companion.name)

    menu = QMenu()
    _add_header(menu, companion)
    # Point the "config" row at the active companion's roster directory
    # rather than the global config dir — opening it gets the user
    # straight to ``profile.json``, ``art/``, and ``art_archive/`` for
    # this companion.
    companion_dir = art_dir.parent
    _add_info_rows(
        menu,
        session=session_label,
        cwd=cwd_label,
        config=str(companion_dir),
        on_cwd_clicked=lambda: _open_path(cwd_path),
        on_config_clicked=lambda: _open_path(companion_dir),
    )
    _add_preview(menu, icon_pixmap)
    _add_stats(menu, companion)
    _add_text_block(menu, "Bio", companion.personality)
    _add_text_block(menu, "Backstory", companion.backstory)

    menu.addSeparator()

    if on_react_now is not None:
        react_action = QAction("React now", menu)
        react_action.triggered.connect(on_react_now)
        menu.addAction(react_action)

    gravity_action = QAction("Gravity", menu)
    gravity_action.setCheckable(True)
    gravity_action.setChecked(settings.gravity_enabled)
    gravity_action.toggled.connect(
        lambda checked: _persist_gravity(settings, settings_store, on_gravity_toggled, checked)
    )
    menu.addAction(gravity_action)

    walk_action = QAction("Walking", menu)
    walk_action.setCheckable(True)
    walk_action.setChecked(settings.walking_enabled)
    walk_action.toggled.connect(lambda checked: _persist_walking(settings, settings_store, on_walking_toggled, checked))
    menu.addAction(walk_action)

    _add_scale_slider(menu, settings, settings_store, on_scale_changed)

    menu.addSeparator()

    quit_action = QAction(f"Quit {companion.name}", menu)
    quit_action.triggered.connect(on_quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()
    return tray


# ---------------------------------------------------------------------------
# Menu builders
# ---------------------------------------------------------------------------


def _build_tray_icon(
    icon_pixmap: QPixmap,
    *,
    save_dir: Path | None = None,
) -> QIcon:
    """Build a 64×64 tray icon: trim, square-pad, scale, save.

    Sprite frames are bottom-anchored on a 64×64 transparent canvas so
    the running companion's feet sit on the ground — that means the visible
    artwork only fills part of the canvas, which leaves a tiny companion
    surrounded by empty space if you hand the raw frame to the
    status-bar code.

    The pipeline:

    1. Trim ``icon_pixmap`` to its alpha bounding box (drops the
       bottom-anchor padding around the visible artwork).
    2. Pad the trimmed pixmap out to a square — preserves the source
       aspect ratio while producing a deterministic, centered canvas.
    3. Scale the square to ``_TRAY_ICON_SIZE``×``_TRAY_ICON_SIZE``;
       square→square with ``KeepAspectRatio`` lands on exact pixel
       boundaries, so the result is centered both ways and fills the
       slot.

    When ``save_dir`` is given the result is also written to
    ``<save_dir>/icon_64.png`` for manual inspection.
    """
    trimmed = _trim_to_visible(icon_pixmap)
    # ``_square_pad`` and ``QPixmap.scaled`` both reach for raw pixel
    # dimensions, but ``QPainter.drawPixmap`` renders the source at its
    # *logical* size (physical / DPR). On a Retina display the source
    # arrives with DPR=2, so the pad math (in physical px) and the
    # actual draw (in logical px) disagree and the art lands in the
    # top-left quadrant. Forcing DPR=1 makes physical = logical for
    # the rest of the icon pipeline.
    trimmed.setDevicePixelRatio(1.0)
    square = _square_pad(trimmed)
    rendition = square.scaled(
        _TRAY_ICON_SIZE,
        _TRAY_ICON_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    rendition.setDevicePixelRatio(1.0)
    if save_dir is not None:
        out = save_dir / f"icon_{_TRAY_ICON_SIZE}.png"
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            if not rendition.save(str(out), "PNG"):
                logger.warning("Failed to write tray icon to %s", out)
        except OSError:
            logger.exception("Could not save tray icon to %s", out)
    icon = QIcon()
    icon.addPixmap(rendition)
    return icon


def _build_red_square_icon(*, save_dir: Path) -> QIcon:
    """Debug-only: a flat 64×64 red square, also written to the art dir.

    Provided as the *only* rendition in the returned ``QIcon`` so the
    OS's status-bar code is responsible for any further downsampling —
    if the on-screen icon is small, the OS is the constraint, not us.
    """
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(255, 0, 0))
    out = save_dir / "tray_test_red_64.png"
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(out), "PNG"):
            logger.warning("Failed to write debug tray icon to %s", out)
    except OSError:
        logger.exception("Could not save debug tray icon to %s", out)
    icon = QIcon()
    icon.addPixmap(pixmap)
    return icon


def _square_pad(pixmap: QPixmap) -> QPixmap:
    """Return ``pixmap`` centered on a transparent square canvas.

    Width and height become ``max(w, h)`` so a downstream scale to a
    square slot lands on exact pixel boundaries. ``devicePixelRatio``
    is preserved.
    """
    from PySide6.QtGui import QPainter

    w, h = pixmap.width(), pixmap.height()
    if w == h:
        return pixmap
    side = max(w, h)
    canvas = QPixmap(side, side)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.drawPixmap((side - w) // 2, (side - h) // 2, pixmap)
    finally:
        painter.end()
    canvas.setDevicePixelRatio(pixmap.devicePixelRatio())
    return canvas


def _add_header(menu: QMenu, companion: CompanionProfile) -> None:
    """Bold companion name (rarity-colored) + stars + tier label.

    The padding is set on a container ``QWidget`` rather than via inline
    CSS — Qt's rich-text renderer ignores ``padding`` on a top-level
    ``QLabel``, so without the wrapper the row is flush against the
    menu's left edge.
    """
    color = _RARITY_CSS_COLOR.get(companion.rarity, "#cccccc")
    tier = _RARITY_TIER_LABEL.get(companion.rarity, str(companion.rarity))
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(12, 6, 12, 6)
    layout.setSpacing(0)
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.RichText)
    from claude_code_assist.models.role import ROLE_CATALOG  # noqa: PLC0415

    # Row 2: creature_type · role (role colored). Built first so we can
    # decide whether to emit a <br> at all.
    row2_segments: list[str] = []
    if companion.creature_type:
        row2_segments.append(
            f'<span style="color:#aaa; font-size:12px;">'
            f"{_html_escape(companion.creature_type)}"
            f"</span>"
        )
    if companion.role is not None:
        defn = ROLE_CATALOG.get(companion.role)
        role_color = defn.color if defn else "#aaa"
        row2_segments.append(
            f'<span style="color:{role_color}; font-size:12px;">'
            f"{_html_escape(companion.role.value)}"
            f"</span>"
        )
    row2_html = ""
    if row2_segments:
        joined = (
            '<span style="color:#666; font-size:12px;"> · </span>'.join(row2_segments)
        )
        row2_html = f"<br>{joined}"

    label.setText(
        f'<span style="color:{color}; font-weight:700; font-size:14px;">'
        f"{_html_escape(companion.name)}"
        f"</span>"
        f'<span style="color:{color}; font-size:13px;"> {companion.rarity.stars}</span>'
        f'<span style="color:#888; font-size:12px;"> · Lv. {companion.level}</span>'
        f'<span style="color:#888; font-size:12px;"> · {tier}</span>'
        f"{row2_html}"
    )
    layout.addWidget(label)
    _add_widget(menu, container, enabled=False)


def _add_info_rows(
    menu: QMenu,
    *,
    session: str,
    cwd: str,
    config: str,
    on_cwd_clicked: Callable[[], None] | None,
    on_config_clicked: Callable[[], None] | None,
) -> None:
    """Three monospace rows showing where the companion is looking.

    ``cwd`` and ``config`` rows are enabled and clickable when their
    callbacks are provided (open the matching folder in the file
    manager); ``session`` stays disabled because we don't have a
    natural "open this in an app" target for a Claude Code session.
    """
    mono = _monospace_font()
    rows: tuple[tuple[str, str, Callable[[], None] | None], ...] = (
        ("session", session, None),
        ("cwd", cwd, on_cwd_clicked),
        ("config", config, on_config_clicked),
    )
    for key, value, callback in rows:
        action = QAction(f"{key}: {_truncate_path(value)}", menu)
        action.setFont(mono)
        if callback is not None:
            action.triggered.connect(callback)
        else:
            action.setEnabled(False)
        menu.addAction(action)


def _add_preview(menu: QMenu, icon_pixmap: QPixmap) -> None:
    """Idle-A sprite preview, centered, scaled large + vibrant.

    Three things matter:

    1. The action is created enabled — a disabled ``QWidgetAction`` paints
       its child through Qt's disabled palette, which is what was making
       the sprite look dim.
    2. We scale at the source pixmap's ``devicePixelRatio`` and re-stamp
       it on the result so Retina displays get the full physical
       resolution, not a 1× upscale.
    3. The pixmap is cropped to its non-transparent bounding box first.
       Sprite frames are bottom-anchored on a square canvas (see
       ``sprites.load_frames`` — feet touch the ground while walking),
       which means up to half the pixmap can be transparent padding
       above the artwork. At 288 logical px in the menu that padding
       turns into an obvious gap above the preview; trimming it kills
       the gap without any per-frame asymmetry.

    Sizing: ``_PREVIEW_SIZE`` logical px, square (``KeepAspectRatio``
    on a non-square crop just shrinks the longer side to fit).
    """
    trimmed = _trim_to_visible(icon_pixmap)
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setContentsMargins(0, 0, 0, 0)
    _set_preview_pixmap(label, trimmed, _PREVIEW_SIZE)
    _add_widget(menu, label, enabled=True)


def _set_preview_pixmap(label: QLabel, source: QPixmap, logical_size: int) -> None:
    """Render ``source`` into ``label`` at ``logical_size``, DPR-correct."""
    dpr = source.devicePixelRatio() or 1.0
    physical = max(1, int(round(logical_size * dpr)))
    scaled = source.scaled(
        physical,
        physical,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    label.setPixmap(scaled)


def _trim_to_visible(pixmap: QPixmap) -> QPixmap:
    """Return ``pixmap`` cropped to its non-transparent bounding box.

    Runs once at menu setup; pixel access is in Python (``pixel()`` reads
    a 32-bit ARGB int per call) which is fine for a single 64×64 / 128×128
    sprite canvas. Returns the original pixmap if it is fully transparent
    or null. The cropped pixmap inherits the source's ``devicePixelRatio``.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if image.isNull():
        return pixmap
    width, height = image.width(), image.height()
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if (image.pixel(x, y) >> 24) & 0xFF:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if max_x < 0:
        return pixmap
    cropped = pixmap.copy(QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))
    cropped.setDevicePixelRatio(pixmap.devicePixelRatio())
    return cropped


def _add_stats(menu: QMenu, companion: CompanionProfile) -> None:
    """One row per stat: ``NAME ██████░░░░  100`` in monospace.

    The bar (both filled and empty cells) is rendered in the companion's
    rarity color so a Legendary companion's stat block reads as obviously
    "the bright magenta one" at a glance. Name + numeric value stay in
    the menu's default text color so they remain readable on any theme.
    """
    if not companion.stats:
        return
    name_width = max((len(name) for name in companion.stats), default=0)
    bar_color = _RARITY_CSS_COLOR.get(companion.rarity, "#cccccc")
    mono = _monospace_font()
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(12, 4, 12, 6)
    layout.setSpacing(2)
    for name, value in companion.stats.items():
        row = QLabel()
        row.setFont(mono)
        row.setTextFormat(Qt.TextFormat.RichText)
        row.setText(_format_stat_row_html(name, value, name_width, bar_color))
        layout.addWidget(row)
    _add_widget(menu, container, enabled=False)


def _add_text_block(menu: QMenu, title: str, body: str) -> None:
    """Wrapped Bio / Backstory paragraph with a bold title."""
    body = (body or "").strip()
    if not body:
        return
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(12, 4, 12, 8)
    layout.setSpacing(2)

    title_label = QLabel()
    title_label.setTextFormat(Qt.TextFormat.RichText)
    title_label.setText(f'<span style="font-weight:600; color:#aaaaaa;">{title}</span>')
    layout.addWidget(title_label)

    body_label = QLabel(body)
    body_label.setWordWrap(True)
    body_label.setMaximumWidth(_TEXT_BLOCK_MAX_PX)
    body_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    # Allow text selection / copy. Without this the label swallows mouse
    # events and the row reads like dead text.
    body_label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    body_label.setCursor(Qt.CursorShape.IBeamCursor)
    layout.addWidget(body_label)

    _add_widget(menu, container, enabled=False)


def _add_widget(menu: QMenu, widget: QWidget, *, enabled: bool) -> None:
    """Wrap ``widget`` in a ``QWidgetAction`` and append it to ``menu``."""
    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    action.setEnabled(enabled)
    menu.addAction(action)


# ---------------------------------------------------------------------------
# Toggle persistence
# ---------------------------------------------------------------------------


def _persist_gravity(
    settings: CompanionSettings,
    store: SettingsStore,
    callback: Callable[[bool], None] | None,
    checked: bool,
) -> None:
    settings.gravity_enabled = checked
    store.save(settings)
    if callback is not None:
        callback(checked)


def _persist_walking(
    settings: CompanionSettings,
    store: SettingsStore,
    callback: Callable[[bool], None] | None,
    checked: bool,
) -> None:
    settings.walking_enabled = checked
    store.save(settings)
    if callback is not None:
        callback(checked)


def _add_scale_slider(
    menu: QMenu,
    settings: CompanionSettings,
    store: SettingsStore,
    callback: Callable[[float], None] | None,
) -> None:
    """Companion-size slider: 80 %–200 %, snapping to 20 % ticks.

    QSlider is integer-valued and has no built-in tick-snap, so we
    intercept ``valueChanged``: round the raw value to the nearest 20,
    write it back to the slider (with signals blocked to avoid
    recursion), then persist + notify. Dragging the handle "feels"
    sticky at the tick positions because every interim value snaps.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(12, 4, 12, 8)
    layout.setSpacing(4)

    initial_pct = _snap_scale_pct(int(round(settings.companion_scale * 100)))

    title_row = QWidget()
    title_layout = QHBoxLayout(title_row)
    title_layout.setContentsMargins(0, 0, 0, 0)
    title_label = QLabel("Scale")
    title_label.setStyleSheet("font-weight:600; color:#aaaaaa;")
    value_label = QLabel(f"{initial_pct}%")
    value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    title_layout.addWidget(title_label)
    title_layout.addWidget(value_label)
    layout.addWidget(title_row)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(_SCALE_PCT_MIN, _SCALE_PCT_MAX)
    slider.setSingleStep(_SCALE_PCT_STEP)
    slider.setPageStep(_SCALE_PCT_STEP)
    slider.setTickInterval(_SCALE_PCT_STEP)
    slider.setTickPosition(QSlider.TickPosition.TicksBelow)
    slider.setValue(initial_pct)
    layout.addWidget(slider)

    def _on_value_changed(value: int) -> None:
        snapped = _snap_scale_pct(value)
        if snapped != value:
            slider.blockSignals(True)
            slider.setValue(snapped)
            slider.blockSignals(False)
        value_label.setText(f"{snapped}%")
        scale = snapped / 100.0
        if abs(settings.companion_scale - scale) > 1e-6:
            settings.companion_scale = scale
            store.save(settings)
        if callback is not None:
            callback(scale)

    slider.valueChanged.connect(_on_value_changed)

    _add_widget(menu, container, enabled=True)


def _snap_scale_pct(value: int) -> int:
    snapped = round(value / _SCALE_PCT_STEP) * _SCALE_PCT_STEP
    return max(_SCALE_PCT_MIN, min(_SCALE_PCT_MAX, snapped))


# ---------------------------------------------------------------------------
# Open Config Folder
# ---------------------------------------------------------------------------


def _open_path(path: Path) -> None:
    """Reveal ``path`` in Finder / the platform file manager."""
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Could not create config dir %s", path)
            return
    target = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", target])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", target])
        else:
            logger.warning("Don't know how to open %s on platform %s", target, sys.platform)
    except OSError:
        logger.exception("Failed to launch file manager for %s", target)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_stat_row_html(name: str, value: int, name_width: int, bar_color: str) -> str:
    """Render one stat row as HTML: ``NAME ██████░░░░  100`` with a colored bar.

    Bar fills are integer-quantized to 10 % per cell (``_BAR_CELLS``);
    values clamp to ``[0, 100]`` so unusually high or negative stats
    don't overflow. Spaces are converted to ``&nbsp;`` because Qt's
    rich-text renderer collapses runs of whitespace, which would
    otherwise destroy the column alignment a monospace font is
    supposed to give us.
    """
    clamped = max(0, min(100, int(value)))
    filled = clamped // (100 // _BAR_CELLS)
    filled_bar = _BAR_FILLED * filled
    empty_bar = _BAR_EMPTY * (_BAR_CELLS - filled)
    name_pad = _html_escape(name) + "&nbsp;" * (name_width - len(name))
    value_str = f"{clamped:>3}".replace(" ", "&nbsp;")
    return (
        f'{name_pad}&nbsp;&nbsp;<span style="color:{bar_color};">{filled_bar}</span>{empty_bar}&nbsp;&nbsp;{value_str}'
    )


def _truncate_path(text: str) -> str:
    """Replace ``$HOME`` with ``~`` and truncate from the left if too long."""
    from pathlib import Path

    home = str(Path.home())
    if text.startswith(home):
        text = "~" + text[len(home) :]
    if len(text) > _INFO_PATH_MAX_CHARS:
        text = "…" + text[-(_INFO_PATH_MAX_CHARS - 1) :]
    return text


def _monospace_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(max(11, font.pointSize()))
    return font


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
