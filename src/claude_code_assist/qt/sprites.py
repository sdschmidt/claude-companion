"""Companion sprite frames — load + index PNGs from disk.

Frames get tight-cropped on load: we compute the *union* bounding box
of opaque pixels across all 10 frames and crop every frame to it. That
keeps the character's relative position consistent across the
animation while removing the transparent padding Gemini-generated
cells carry around their cells.
"""

from __future__ import annotations

import io
import logging
from enum import IntEnum
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger(__name__)

# Canonical logical *height* of the sprite at scale=1.0; window width
# is derived from the cropped frames' shared aspect ratio.
SPRITE_CANVAS = 48

# How much bigger the rendered sprite is drawn relative to the
# canonical canvas dimensions. The window/canvas size stays driven by
# ``SPRITE_CANVAS``; the pixmap is scaled by this factor so the
# character occupies more of the canvas (overflow is clipped by the
# QLabel that hosts it).
SPRITE_RENDER_SCALE = 2.0

_FRAME_COUNT = 10
_OPAQUE_THRESHOLD = 32


class Frame(IntEnum):
    IDLE_A = 0
    IDLE_B = 1
    BLINK_A = 2
    BLINK_B = 3
    EXCITED = 4
    SLEEP = 5
    WALK_A = 6
    WALK_B = 7
    FALL = 8
    STUNNED = 9


def load_frames(
    art_dir: Path,
    *,
    device_pixel_ratio: float = 1.0,
) -> tuple[list[QPixmap], float]:
    """Load + uniformly tight-crop ``frame_0.png … frame_9.png``.

    Returns ``(frames, aspect_ratio)`` where ``aspect_ratio`` is the
    width-to-height ratio of the union opaque bbox; callers use it to
    size the window so the sprite fills the canvas with no horizontal
    transparent slack.
    """
    pil_frames: list[Image.Image | None] = []
    for i in range(_FRAME_COUNT):
        path = art_dir / f"frame_{i}.png"
        if not path.is_file():
            logger.warning("Sprite %s does not exist", path)
            pil_frames.append(None)
            continue
        try:
            pil_frames.append(Image.open(path).convert("RGBA"))
        except (OSError, ValueError):
            logger.warning("Failed to load sprite %s", path, exc_info=True)
            pil_frames.append(None)

    bbox = _union_opaque_bbox(pil_frames)
    if bbox is None:
        return [QPixmap() for _ in range(_FRAME_COUNT)], 1.0

    left, top, right, bottom = bbox
    crop_w = right - left
    crop_h = bottom - top
    aspect = crop_w / crop_h if crop_h > 0 else 1.0

    out: list[QPixmap] = []
    for img in pil_frames:
        if img is None:
            out.append(QPixmap())
            continue
        cropped = img.crop((left, top, right, bottom))
        out.append(_pil_to_qpixmap(cropped, device_pixel_ratio))
    return out, aspect


def _union_opaque_bbox(frames: list[Image.Image | None]) -> tuple[int, int, int, int] | None:
    bbox: tuple[int, int, int, int] | None = None
    for img in frames:
        if img is None:
            continue
        alpha = img.getchannel("A").point(lambda v: 255 if v > _OPAQUE_THRESHOLD else 0)
        frame_bbox = alpha.getbbox()
        if frame_bbox is None:
            continue
        if bbox is None:
            bbox = frame_bbox
        else:
            bbox = (
                min(bbox[0], frame_bbox[0]),
                min(bbox[1], frame_bbox[1]),
                max(bbox[2], frame_bbox[2]),
                max(bbox[3], frame_bbox[3]),
            )
    return bbox


def _pil_to_qpixmap(img: Image.Image, device_pixel_ratio: float) -> QPixmap:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qimage = QImage.fromData(buf.getvalue(), "PNG")
    pix = QPixmap.fromImage(qimage)
    pix.setDevicePixelRatio(device_pixel_ratio)
    return pix


def scale_frame(pixmap: QPixmap, target_width: int, target_height: int, *, mirrored: bool = False) -> QPixmap:
    """Scale ``pixmap`` to ``target_width × target_height`` (no aspect distortion)."""
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(
        target_width,
        target_height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if mirrored:
        return _mirror(scaled)
    return scaled


def _mirror(pixmap: QPixmap) -> QPixmap:
    image = pixmap.toImage().mirrored(True, False)
    return QPixmap.fromImage(image)
