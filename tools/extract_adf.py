#!/usr/bin/env python3
"""Extract an AmigaDOS OFS floppy ADF (880 KiB, 80 cylinders, 2 sides, 11 sectors).

Root block is sector 880. File data is stored in OFS data blocks (type 8),
488 bytes of payload each. Writes the directory tree and a listing.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

SEC = 512
ROOT = 880
HT_SIZE = 72
ST_ROOT = 1
ST_USERDIR = 2
ST_FILE = -3

ASSET_SUFFIXES = {".pac", ".rsc", ".palettes"}
ASSET_NAMES = {"palettes"}


def bstr(block: bytes, offset: int) -> str:
    n = block[offset]
    return block[offset + 1 : offset + 1 + n].decode("latin1")


class Disk:
    def __init__(self, data: bytes) -> None:
        if len(data) != 80 * 2 * 11 * SEC:
            raise SystemExit(f"not an 880 KiB ADF ({len(data)} bytes)")
        if data[:3] != b"DOS":
            raise SystemExit("boot block is not DOS")
        self.data = data

    def block(self, n: int) -> bytes:
        off = n * SEC
        return self.data[off : off + SEC]


def read_file(disk: Disk, header: int) -> bytes:
    def pointers(block: bytes) -> tuple[list[int], int]:
        ptrs = struct.unpack(">72I", block[24 : 24 + 72 * 4])
        used = [p for p in ptrs if p]
        ext = struct.unpack(">I", block[504:508])[0]
        return list(reversed(used)), ext

    h = disk.block(header)
    if struct.unpack(">I", h[0:4])[0] != 2:
        raise SystemExit(f"block {header} is not a file header")
    size = struct.unpack(">I", h[324:328])[0]
    chunks, ext = pointers(h)
    seen = {header}
    while ext and ext not in seen:
        seen.add(ext)
        more, ext = pointers(disk.block(ext))
        chunks.extend(more)
    out = bytearray()
    for p in chunks:
        db = disk.block(p)
        typ = struct.unpack(">I", db[0:4])[0]
        if typ != 8:
            raise SystemExit(f"block {p} is not an OFS data block (type {typ})")
        dsz = struct.unpack(">I", db[12:16])[0]
        out += db[24 : 24 + dsz]
    if len(out) < size:
        raise SystemExit(f"short file at block {header}: got {len(out)} want {size}")
    return bytes(out[:size])


def walk(disk: Disk, block: int, rel: Path, out_dir: Path, lines: list[str]) -> None:
    h = disk.block(block)
    ht = struct.unpack(f">{HT_SIZE}I", h[24 : 24 + HT_SIZE * 4])
    stack = [x for x in ht if x]
    seen: set[int] = set()
    entries: list[tuple[str, int, int]] = []
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        hb = disk.block(b)
        name = bstr(hb, 432)
        stype = struct.unpack(">i", hb[508:512])[0]
        nxt = struct.unpack(">I", hb[496:500])[0]
        if nxt:
            stack.append(nxt)
        entries.append((name, stype, b))
    for name, stype, b in sorted(entries, key=lambda e: e[0].lower()):
        path = rel / name
        if stype == ST_USERDIR:
            lines.append(f"dir  {path}")
            walk(disk, b, path, out_dir, lines)
        elif stype == ST_FILE:
            data = read_file(disk, b)
            dest = out_dir / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            lines.append(f"file {path} {len(data)}")
        else:
            lines.append(f"skip {path} stype={stype} blk={b}")


def is_asset(path: Path) -> bool:
    name = path.name.lower()
    if name in ASSET_NAMES:
        return True
    return path.suffix.lower() in ASSET_SUFFIXES


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("adf", type=Path)
    ap.add_argument("out", type=Path, help="extracted directory for this volume")
    ap.add_argument("--assets", type=Path, help="copy PAC/RSC/PALETTES here")
    args = ap.parse_args()

    disk = Disk(args.adf.read_bytes())
    root = disk.block(ROOT)
    if struct.unpack(">I", root[0:4])[0] != 2:
        raise SystemExit("root block type is not 2")
    if struct.unpack(">i", root[508:512])[0] != ST_ROOT:
        raise SystemExit("sector 880 is not the root block")
    volume = bstr(root, 432)
    lines = [f"volume {volume}", f"source {args.adf}"]
    walk(disk, ROOT, Path("."), args.out, lines)
    listing = args.out / "LISTING.txt"
    listing.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    if args.assets:
        copied = 0
        for src in args.out.rglob("*"):
            if not src.is_file() or src.name == "LISTING.txt":
                continue
            if not is_asset(src):
                continue
            rel = src.relative_to(args.out)
            dest = args.assets / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            copied += 1
        print(f"assets {copied} -> {args.assets}")


if __name__ == "__main__":
    sys.exit(main())
