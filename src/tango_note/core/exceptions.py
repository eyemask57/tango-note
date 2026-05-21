"""Core-layer exception types.

The display layers (``cli/``, ``gui/``) catch these and translate them
through ``i18n`` — core itself never emits user-facing strings.
"""

from __future__ import annotations


class TangoNoteError(Exception):
    """Base class for all tango-note core exceptions."""


class DeckNotFoundError(TangoNoteError):
    """Raised when a deck file cannot be located on disk."""


class InvalidDeckSchemaError(TangoNoteError):
    """Raised when a deck file fails schema validation.

    Conditions include: missing ``version`` field, unsupported major
    version, malformed JSON structure, or missing required fields.
    """


class CardNotFoundError(TangoNoteError):
    """Raised when a card with the given id is not present in the deck."""


class DuplicateCardError(TangoNoteError):
    """Raised when a card id collides with an already-existing card."""


class EmptyDeckError(TangoNoteError):
    """Raised when a quiz operation is attempted on a deck with no cards."""


class InvalidConfigError(TangoNoteError):
    """Raised when the user config file cannot be parsed or validated."""
