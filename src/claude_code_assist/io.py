"""JSON load/save helpers for pydantic models."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


def save_json(model: BaseModel, path: Path) -> None:
    """Serialize a pydantic model to ``path`` as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def load_json(path: Path, model_cls: type[M]) -> M | None:
    """Load a pydantic model from ``path``; return ``None`` if missing/invalid."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_cls.model_validate(data)
    except (json.JSONDecodeError, ValidationError, OSError) as e:
        logger.warning("Failed to load %s as %s: %s", path, model_cls.__name__, e)
        return None
