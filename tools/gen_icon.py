#!/usr/bin/env python
"""Generate the tango-note application icon (ICO) from the source PNG.

Reads ``installer/tango-note_source.png`` and writes a multi-resolution
``installer/tango-note.ico`` used both for the built ``.exe`` and the
Inno Setup installer.

The logo's vector source is intentionally not kept in the repo: its
typography depends on Adobe Fonts, which cannot be reproduced on other
machines. To change the logo, edit the original in Adobe Illustrator
(or any editor), re-export it as ``installer/tango-note_source.png``,
and re-run this script.
"""

from pathlib import Path

from PIL import Image


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    source = repo_root / "installer" / "tango-note_source.png"
    out = repo_root / "installer" / "tango-note.ico"

    if not source.exists():
        raise SystemExit(
            f"Source image not found: {source}\n"
            "Place your logo as installer/tango-note_source.png "
            "(256x256 or larger, PNG format)."
        )

    src_img = Image.open(source).convert("RGBA")
    if src_img.width < 256 or src_img.height < 256:
        raise SystemExit(
            f"Source image is too small: {src_img.size}.\n"
            "It must be at least 256x256 so every ICO resolution can be "
            "generated cleanly. Re-export the logo at 256x256 or larger "
            "(1024x1024 recommended)."
        )

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    # Resize the source ONCE to 256x256 — the largest ICO frame — and
    # let Pillow downsample that base to every entry in ``sizes``.
    #
    # Pillow's ICO writer drops any requested size LARGER than the saved
    # base image (it never upscales). The earlier version handed it a
    # base pre-resized to 16x16, so all five larger frames were silently
    # discarded and the .ico held only 16x16. A 256x256 base covers all
    # six sizes.
    base = src_img.resize((256, 256), Image.Resampling.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, format="ICO", sizes=sizes)
    print(f"Generated: {out}")
    print(f"  Sizes: {sizes}")


if __name__ == "__main__":
    main()
