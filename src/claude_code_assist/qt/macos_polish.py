"""macOS-specific window-level + activation-policy polish.

On macOS we want:

* The companion window to sit *above* full-screen apps and the menu bar.
  Qt's ``WindowStaysOnTopHint`` only reaches the normal floating level,
  so we promote to ``NSScreenSaverWindowLevel`` via pyobjc.
* The companion window to follow the user across Spaces / Mission Control
  desktops, including full-screen apps. NSWindow's default behavior
  pins it to the originating Space, so we set ``.canJoinAllSpaces`` on
  the window's ``collectionBehavior``.
* The app to behave as an accessory (no Dock icon, no app switcher entry)
  so it doesn't steal focus.

All functions are no-ops on non-macOS platforms.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

# NSScreenSaverWindowLevel = CGShieldingWindowLevel() - 1 ≈ 1000.
_NS_SCREEN_SAVER_LEVEL = 1000

# NSWindowCollectionBehavior bits (from AppKit headers):
_NS_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES = 1 << 0  # 0x1
_NS_COLLECTION_BEHAVIOR_STATIONARY = 1 << 4  # 0x10 — don't slide on space switch
_NS_COLLECTION_BEHAVIOR_FULL_SCREEN_AUXILIARY = 1 << 8  # 0x100 — show over full-screen apps


def _find_ns_window(widget):  # type: ignore[no-untyped-def]
    """Return the NSWindow backing this Qt widget, or ``None``."""
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSApp  # type: ignore[import-not-found]
    except ImportError:
        return None

    app = NSApp()
    if app is None:
        return None
    try:
        ns_view_id = int(widget.winId())
    except Exception:  # noqa: BLE001
        return None

    for win in app.windows():
        try:
            content_view = win.contentView()
            if content_view is not None and int(content_view.__c_void_p__().value) == ns_view_id:
                return win
        except Exception:  # noqa: BLE001
            continue
    return None


def promote_window_level(widget) -> None:  # type: ignore[no-untyped-def]
    """Promote a Qt widget's NSWindow to screen-saver level + Spaces-aware behavior.

    Does two things at once because both must be re-applied whenever Qt
    re-syncs the window (focus changes etc.):

    * Sets ``level`` to ``NSScreenSaverWindowLevel`` so the window sits
      above full-screen apps and the menu bar.
    * Sets ``collectionBehavior`` to ``canJoinAllSpaces |
      fullScreenAuxiliary | stationary`` so the window follows the user
      across Spaces and stays put when Mission Control animates.

    No-op on non-macOS platforms or if pyobjc isn't installed.
    """
    win = _find_ns_window(widget)
    if win is None:
        return
    try:
        win.setLevel_(_NS_SCREEN_SAVER_LEVEL)
        win.setCollectionBehavior_(
            _NS_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES
            | _NS_COLLECTION_BEHAVIOR_FULL_SCREEN_AUXILIARY
            | _NS_COLLECTION_BEHAVIOR_STATIONARY,
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to apply window level / collection behavior", exc_info=True)


def set_accessory_activation_policy() -> None:
    """Set NSApp activation policy to ``.accessory`` (no Dock icon)."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("pyobjc not available; skipping activation-policy setup")
        return

    try:
        app = NSApp()
        if app is not None:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to set accessory activation policy", exc_info=True)
