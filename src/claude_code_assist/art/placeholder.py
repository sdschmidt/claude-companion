"""Copy bundled placeholder PNGs into a companion's art dir."""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

from claude_code_assist.art.meta import ArtMeta, write_meta

logger = logging.getLogger(__name__)

PLACEHOLDER_PACKAGE = "claude_code_assist.assets.placeholder_frames"
FRAME_COUNT = 10


def prefill_placeholder_frames(art_dir: Path) -> list[Path]:
    """Copy bundled ``frame_0.png … frame_9.png`` (and ``icon.png``) into ``art_dir``.

    Returns the destination frame paths so callers can report a count.
    Also writes a ``meta.json`` marking the set as a placeholder so
    ``companion art`` can label it correctly in the restore picker.
    """
    art_dir.mkdir(parents=True, exist_ok=True)

    package = resources.files(PLACEHOLDER_PACKAGE)
    out_paths: list[Path] = []
    for i in range(FRAME_COUNT):
        name = f"frame_{i}.png"
        source = package.joinpath(name)
        dest = art_dir / name
        dest.write_bytes(source.read_bytes())
        out_paths.append(dest)

    icon_source = package.joinpath("icon.png")
    if icon_source.is_file():
        (art_dir / "icon.png").write_bytes(icon_source.read_bytes())

    write_meta(art_dir, ArtMeta(model="placeholder", prompt=""))
    return out_paths
