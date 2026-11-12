#!/usr/bin/env python3
"""Split an AmigaDOS hunk load file, or a TOS PRG, into code, data, bss, and relocs.

Amiga relocations are the on-disk offsets (the loader adds the hunk base).
TOS relocations are the on-disk offsets into the text+data image.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HUNK_CODE = 1001
HUNK_DATA = 1002
HUNK_BSS = 1003
HUNK_RELOC32 = 1004
HUNK_END = 1010
HUNK_HEADER = 1011
NAMES = {
    HUNK_CODE: "code",
    HUNK_DATA: "data",
    HUNK_BSS: "bss",
    HUNK_RELOC32: "reloc32",
    HUNK_END: "end",
    HUNK_HEADER: "header",
}


def split_hunk(blob: bytes, out: Path) -> None:
    if struct.unpack_from(">I", blob, 0)[0] != HUNK_HEADER:
        raise SystemExit("not an AmigaDOS hunk file")
    off = 4
    while True:
        count = struct.unpack_from(">I", blob, off)[0]
        off += 4
        if count == 0:
            break
        off += count * 4
    table, first, last = struct.unpack_from(">III", blob, off)
    off += 12
    count = last - first + 1
    if count != table:
        raise SystemExit(f"hunk table {table} does not match {first}..{last}")
    sizes = struct.unpack_from(f">{count}I", blob, off)
    off += 4 * count
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"hunks {count} first {first} last {last}"]
    for index, size in enumerate(sizes):
        lines.append(f"hunk {index} mem {size >> 30} bytes {(size & 0x3FFFFFFF) * 4}")
    index = 0
    while off + 4 <= len(blob):
        raw = struct.unpack_from(">I", blob, off)[0]
        off += 4
        kind = raw & 0x1FFFFFFF
        if kind in (HUNK_CODE, HUNK_DATA):
            nlong = struct.unpack_from(">I", blob, off)[0]
            off += 4
            data = blob[off : off + nlong * 4]
            off += nlong * 4
            path = out / f"hunk{index}.{NAMES[kind]}.bin"
            path.write_bytes(data)
            lines.append(f"hunk {index} {NAMES[kind]} {len(data)} {path.name}")
        elif kind == HUNK_BSS:
            nlong = struct.unpack_from(">I", blob, off)[0]
            off += 4
            (out / f"hunk{index}.bss.txt").write_text(f"{nlong * 4}\n")
            lines.append(f"hunk {index} bss {nlong * 4}")
        elif kind == HUNK_RELOC32:
            relocs = []
            while True:
                n = struct.unpack_from(">I", blob, off)[0]
                off += 4
                if n == 0:
                    break
                hunk = struct.unpack_from(">I", blob, off)[0]
                off += 4
                offsets = struct.unpack_from(f">{n}I", blob, off)
                off += 4 * n
                relocs.extend(f"{hunk} {item:08x}" for item in offsets)
            (out / f"hunk{index}.reloc.txt").write_text("\n".join(relocs) + ("\n" if relocs else ""))
            lines.append(f"hunk {index} reloc32 {len(relocs)}")
        elif kind == HUNK_END:
            lines.append(f"hunk {index} end")
            index += 1
        else:
            raise SystemExit(f"unknown hunk type {kind:#x} at {off-4:#x}")
    if off != len(blob):
        lines.append(f"trailing {len(blob) - off} bytes at {off:#x}")
    (out / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def split_prg(blob: bytes, out: Path) -> None:
    if struct.unpack_from(">H", blob, 0)[0] != 0x601A:
        raise SystemExit("not a TOS PRG")
    text, data, bss, sym = struct.unpack_from(">4I", blob, 2)
    absflag = struct.unpack_from(">H", blob, 26)[0]
    off = 28
    text_bytes = blob[off : off + text]
    off += text
    data_bytes = blob[off : off + data]
    off += data
    off += sym
    out.mkdir(parents=True, exist_ok=True)
    (out / "text.bin").write_bytes(text_bytes)
    (out / "data.bin").write_bytes(data_bytes)
    (out / "bss.txt").write_text(f"{bss}\n")
    relocs = []
    if absflag == 0 and off < len(blob):
        first = struct.unpack_from(">I", blob, off)[0]
        off += 4
        if first:
            relocs.append(first)
            while off < len(blob):
                delta = blob[off]
                off += 1
                if delta == 0:
                    break
                if delta == 1:
                    relocs[-1] += 254
                    continue
                relocs.append(relocs[-1] + delta)
    (out / "reloc.txt").write_text("\n".join(f"{item:08x}" for item in relocs) + ("\n" if relocs else ""))
    lines = [
        f"text {text}",
        f"data {data}",
        f"bss {bss}",
        f"symbols {sym}",
        f"relocs {len(relocs)}",
        f"consumed {off} of {len(blob)}",
    ]
    (out / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--tos", action="store_true")
    args = ap.parse_args()
    blob = args.binary.read_bytes()
    if args.tos or blob[:2] == b"\x60\x1a":
        split_prg(blob, args.out)
    else:
        split_hunk(blob, args.out)


if __name__ == "__main__":
    sys.exit(main())
