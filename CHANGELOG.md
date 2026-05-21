# Changelog

All notable changes to this project are documented in this file.

## [1.1.1] - 2026-05-21

### Changed

- Improved tab visibility: larger font (11pt bold), wider padding for
  easier clicks, and a distinct color for the selected tab

## [1.1.0] - 2026-05-21

### Added

- Deck deletion from the GUI deck list and the CLI (`delete-deck`), each
  with a confirmation prompt that defaults to "No"
- Cards found via search can now be deleted directly (the Delete button
  was previously disabled while a search filter was active)
- Clear button (×) for the card search bar
- ESC key shortcut to clear the search bar

### Changed

- The "Add Card" button moved to the top bar next to the search field,
  with prominent navy, bold styling
- The notes field in the card editor is larger (6 lines by default) and
  the dialog is now resizable

## [1.0.0] - 2026-05-21

### Initial release

- Local JSON-based vocabulary deck management
- CLI (`tango-note` / `tn`) and GUI (`tango-note-gui` / `tn-gui`) interfaces
- Random / weak-first / long-unreviewed quiz modes
- Card search and duplicate detection
- Review statistics (accuracy, freshness distribution)
- Import / export with optional stats stripping
- Settings dialog for export defaults and quiz thresholds
- Multi-line notes support
- Continuous card entry mode
- Save button visual feedback (color and asterisk)
- Custom logo (TN with underline)
- Inno Setup installer for Windows
- Internationalization (Japanese, extensible via `.po` files)
