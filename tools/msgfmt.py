#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Minimal Python reimplementation of GNU msgfmt.
#
# Adapted from CPython's ``Tools/i18n/msgfmt.py``
#   https://github.com/python/cpython/blob/main/Tools/i18n/msgfmt.py
# distributed under the Python Software Foundation License Version 2
# (https://docs.python.org/3/license.html).
#
# This version drops support for msgid_plural / msgctxt / fuzzy-aware
# rebuilding, but is sufficient for the tango-note message catalog.
# ---------------------------------------------------------------------------
"""Compile a GNU .po file into a binary .mo catalog.

Usage::

    python tools/msgfmt.py FILE.po [-o OUTPUT.mo]

If ``-o`` is omitted, the output is written next to the input file with
the ``.mo`` extension.
"""

from __future__ import annotations

import ast
import struct
import sys
from pathlib import Path


def _compile_mo(messages: dict[bytes, bytes]) -> bytes:
    """Pack a {msgid: msgstr} mapping into GNU MO binary format.

    See the GNU gettext manual, "The Format of GNU MO Files":
    https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
    """
    keys = sorted(messages.keys())
    offsets: list[tuple[int, int, int, int]] = []
    ids = b""
    strs = b""
    for msgid in keys:
        msgstr = messages[msgid]
        offsets.append((len(ids), len(msgid), len(strs), len(msgstr)))
        ids += msgid + b"\0"
        strs += msgstr + b"\0"

    header_size = 7 * 4
    keytab_size = 8 * len(keys)
    valuetab_size = 8 * len(keys)
    keytab_start = header_size
    valuetab_start = keytab_start + keytab_size
    keys_start = valuetab_start + valuetab_size
    values_start = keys_start + len(ids)

    key_offsets: list[int] = []
    value_offsets: list[int] = []
    for raw_key_off, key_len, raw_val_off, val_len in offsets:
        key_offsets.extend([key_len, keys_start + raw_key_off])
        value_offsets.extend([val_len, values_start + raw_val_off])

    header = struct.pack(
        "<Iiiiiii",
        0x950412DE,        # magic
        0,                 # version
        len(keys),         # number of strings
        keytab_start,      # offset of key table
        valuetab_start,    # offset of value table
        0, 0,              # hash table size + offset (unused)
    )
    output = header
    if key_offsets:
        output += struct.pack(f"<{len(key_offsets)}i", *key_offsets)
        output += struct.pack(f"<{len(value_offsets)}i", *value_offsets)
    output += ids
    output += strs
    return output


def _parse_po(path: Path) -> dict[bytes, bytes]:
    """Parse a .po file into a {msgid: msgstr} dict of UTF-8 bytes."""
    messages: dict[bytes, bytes] = {}
    msgid = b""
    msgstr = b""
    state: str | None = None  # "id" | "str" | None
    fuzzy = False

    def commit() -> None:
        nonlocal msgid, msgstr, fuzzy
        if not fuzzy and msgstr:
            messages[msgid] = msgstr
        msgid = b""
        msgstr = b""
        fuzzy = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            if state == "str":
                commit()
            state = None
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        if line.startswith(("msgid_plural", "msgctxt", "msgstr[")):
            raise SystemExit(
                f"msgfmt: line {lineno}: msgid_plural/msgctxt/msgstr[] "
                "not supported by this minimal compiler"
            )
        if line.startswith("msgid"):
            if state == "str":
                commit()
            state = "id"
            msgid = b""
            msgstr = b""
            line = line[len("msgid"):].strip()
        elif line.startswith("msgstr"):
            state = "str"
            line = line[len("msgstr"):].strip()

        if not (line.startswith('"') and line.endswith('"')):
            continue

        try:
            decoded = ast.literal_eval(line)
        except (SyntaxError, ValueError) as exc:
            raise SystemExit(
                f"msgfmt: line {lineno}: invalid string literal: {exc}"
            ) from exc
        chunk = decoded.encode("utf-8") if isinstance(decoded, str) else bytes(decoded)

        if state == "id":
            msgid += chunk
        elif state == "str":
            msgstr += chunk

    if state == "str":
        commit()

    return messages


def make(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Read ``input_path`` (.po) and write ``output_path`` (.mo)."""
    in_path = Path(input_path)
    out_path = Path(output_path) if output_path else in_path.with_suffix(".mo")
    messages = _parse_po(in_path)
    out_path.write_bytes(_compile_mo(messages))
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    output: str | None = None
    if "-o" in args:
        idx = args.index("-o")
        if idx + 1 >= len(args):
            print("msgfmt: -o requires an argument", file=sys.stderr)
            return 2
        output = args[idx + 1]
        del args[idx : idx + 2]
    if len(args) != 1:
        print("Usage: msgfmt.py FILE.po [-o FILE.mo]", file=sys.stderr)
        return 2
    out = make(args[0], output)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
