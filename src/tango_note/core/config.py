"""User configuration for tango-note.

Stored at ``~/.tango-note/config.json`` by default. The
``TANGO_NOTE_HOME`` environment variable overrides the home directory —
useful for tests (set to a ``tmp_path``) and for users who want a
custom location.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from tango_note.core.exceptions import InvalidConfigError

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"
DECKS_SUBDIR = "decks"
DEFAULT_LANG = "ja"

# Allowed values for ``AppConfig.export_default`` — how the GUI decides
# whether to strip learning statistics when exporting a deck.
EXPORT_DEFAULT_ASK = "ask"          # prompt the user every time
EXPORT_DEFAULT_STRIP = "strip"      # always export without stats
EXPORT_DEFAULT_INCLUDE = "include"  # always export with stats
EXPORT_DEFAULT_CHOICES = (
    EXPORT_DEFAULT_ASK,
    EXPORT_DEFAULT_STRIP,
    EXPORT_DEFAULT_INCLUDE,
)

# Allowed values for ``AppConfig.quiz_mode`` — how the quiz picks cards.
QUIZ_MODE_RANDOM = "random"            # uniformly random
QUIZ_MODE_WEAK = "weak"                # low-accuracy cards first
QUIZ_MODE_UNREVIEWED = "unreviewed"    # long-unreviewed cards first
QUIZ_MODE_CHOICES = (
    QUIZ_MODE_RANDOM,
    QUIZ_MODE_WEAK,
    QUIZ_MODE_UNREVIEWED,
)

# Fallback defaults for the quiz-tuning fields.
DEFAULT_WEAK_THRESHOLD = 0.7
DEFAULT_UNREVIEWED_DAYS = 30


@dataclass
class AppConfig:
    """User-level application config.

    Attributes:
        lang: ISO 639-1 UI language code (e.g. ``"ja"``, ``"en"``).
            Defaults to ``"ja"`` per the project i18n requirements.
        current_deck: Filesystem path of the active deck, or ``None``
            when no deck has been chosen yet.
        export_default: Default deck-export behavior. One of
            ``"ask"`` (prompt each time, the default), ``"strip"``
            (always drop learning stats), or ``"include"`` (always keep
            them).
        quiz_mode: Default quiz card-selection mode. One of
            ``"random"`` (the default), ``"weak"``, or ``"unreviewed"``.
        weak_threshold: Accuracy below which a reviewed card counts as
            "weak", in [0.0, 1.0]. Default 0.7.
        unreviewed_days: A card not reviewed for at least this many days
            counts as "long unreviewed". Positive integer, default 30.
    """

    lang: str = DEFAULT_LANG
    current_deck: Optional[str] = None
    export_default: str = EXPORT_DEFAULT_ASK
    quiz_mode: str = QUIZ_MODE_RANDOM
    weak_threshold: float = DEFAULT_WEAK_THRESHOLD
    unreviewed_days: int = DEFAULT_UNREVIEWED_DAYS


def home_dir() -> Path:
    """Resolve the application home directory.

    Honors the ``TANGO_NOTE_HOME`` environment variable so tests and
    custom layouts can redirect everything (config and deck storage)
    to an arbitrary path.

    Returns:
        ``Path(TANGO_NOTE_HOME)`` if set, else ``~/.tango-note``.
    """
    env = os.environ.get("TANGO_NOTE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".tango-note"


def config_path() -> Path:
    """Filesystem path of the user config file."""
    return home_dir() / CONFIG_FILENAME


def decks_dir() -> Path:
    """Default directory under which deck JSON files are stored."""
    return home_dir() / DECKS_SUBDIR


def _coerce_export_default(value: object) -> str:
    """Validate a raw ``export_default`` value from the config file.

    Returns:
        The value unchanged if it is one of ``EXPORT_DEFAULT_CHOICES``.
        ``"ask"`` if the field was absent (``value is None``) — a silent
        default. ``"ask"`` with a logged warning if the field was
        present but holds an unrecognized value, so a hand-edited config
        with a typo still lets the app start.
    """
    if value is None:
        return EXPORT_DEFAULT_ASK
    if value in EXPORT_DEFAULT_CHOICES:
        return value  # type: ignore[return-value]
    logger.warning(
        "Invalid export_default value: %s, falling back to 'ask'", value
    )
    return EXPORT_DEFAULT_ASK


def _coerce_quiz_mode(value: object) -> str:
    """Validate a raw ``quiz_mode`` value; fall back to ``"random"``.

    An absent field (``None``) defaults silently; a present but
    unrecognized value logs a warning before falling back.
    """
    if value is None:
        return QUIZ_MODE_RANDOM
    if value in QUIZ_MODE_CHOICES:
        return value  # type: ignore[return-value]
    logger.warning(
        "Invalid quiz_mode value: %s, falling back to 'random'", value
    )
    return QUIZ_MODE_RANDOM


def _coerce_weak_threshold(value: object) -> float:
    """Validate ``weak_threshold``; fall back to ``DEFAULT_WEAK_THRESHOLD``.

    Must be a real number in [0.0, 1.0]. An absent field defaults
    silently; an out-of-range or wrong-typed value logs a warning.
    """
    if value is None:
        return DEFAULT_WEAK_THRESHOLD
    # bool is a subclass of int — reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        logger.warning(
            "Invalid weak_threshold value: %s, falling back to %s",
            value,
            DEFAULT_WEAK_THRESHOLD,
        )
        return DEFAULT_WEAK_THRESHOLD
    if not 0.0 <= value <= 1.0:
        logger.warning(
            "Invalid weak_threshold value: %s (out of [0.0, 1.0]), "
            "falling back to %s",
            value,
            DEFAULT_WEAK_THRESHOLD,
        )
        return DEFAULT_WEAK_THRESHOLD
    return float(value)


def _coerce_unreviewed_days(value: object) -> int:
    """Validate ``unreviewed_days``; fall back to ``DEFAULT_UNREVIEWED_DAYS``.

    Must be an integer >= 1. An absent field defaults silently; a
    wrong-typed or non-positive value logs a warning.
    """
    if value is None:
        return DEFAULT_UNREVIEWED_DAYS
    # bool is a subclass of int — reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        logger.warning(
            "Invalid unreviewed_days value: %s, falling back to %s",
            value,
            DEFAULT_UNREVIEWED_DAYS,
        )
        return DEFAULT_UNREVIEWED_DAYS
    return value


def load_config() -> AppConfig:
    """Load the user config, returning defaults if the file is absent.

    Returns:
        An ``AppConfig`` populated from ``config_path()``, or a default
        instance if the file does not exist.

    Raises:
        InvalidConfigError: If the file exists but is not valid JSON,
            or is not a JSON object.
    """
    path = config_path()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidConfigError(f"Invalid JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise InvalidConfigError(
            f"Config must be a JSON object, got {type(data).__name__}: {path}"
        )
    return AppConfig(
        lang=data.get("lang", DEFAULT_LANG),
        current_deck=data.get("current_deck"),
        export_default=_coerce_export_default(data.get("export_default")),
        quiz_mode=_coerce_quiz_mode(data.get("quiz_mode")),
        weak_threshold=_coerce_weak_threshold(data.get("weak_threshold")),
        unreviewed_days=_coerce_unreviewed_days(data.get("unreviewed_days")),
    )


def save_config(cfg: AppConfig) -> None:
    """Atomically write the user config to ``config_path()``.

    Writes to a sibling ``*.tmp`` file first, then ``replace``s it onto
    the target. The parent directory is created if missing.

    Args:
        cfg: The config to persist.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)
