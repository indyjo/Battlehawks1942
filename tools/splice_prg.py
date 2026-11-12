#!/usr/bin/env python3
"""Splice assembled text and data into the original BH.PRG.

Text may be longer than the original. Bytes inserted at the end of text
shift the data, so relocation positions and data pointers move with it.
"""

import sys
from pathlib import Path

HEADER = 28


def parse_relocs(blob, start):
    if start + 4 > len(blob) or blob[start:start + 4] == b"\x00\x00\x00\x00":
        return [], start + 4
    offset = int.from_bytes(blob[start:start + 4], "big")
    positions = [offset]
    i = start + 4
    while i < len(blob):
        byte = blob[i]
        i += 1
        if byte == 0:
            break
        if byte == 1:
            offset += 254
            continue
        offset += byte
        positions.append(offset)
    return positions, i


def write_relocs(positions):
    if not positions:
        return b"\x00\x00\x00\x00"
    out = bytearray(positions[0].to_bytes(4, "big"))
    previous = positions[0]
    for position in positions[1:]:
        delta = position - previous
        if delta <= 0:
            raise SystemExit(f"relocation offsets went backwards at {position:#x}")
        while delta > 254:
            out.append(1)
            delta -= 254
        out.append(delta)
        previous = position
    out.append(0)
    return bytes(out)


def main():
    text_path, data_path, prg_path, out_path = sys.argv[1:5]
    text = Path(text_path).read_bytes()
    data = Path(data_path).read_bytes()
    prg = Path(prg_path).read_bytes()
    old_text = int.from_bytes(prg[2:6], "big")
    old_data = int.from_bytes(prg[6:10], "big")
    sym = int.from_bytes(prg[14:18], "big")
    if sym != 0 or len(data) != old_data or len(text) < old_text:
        raise SystemExit(
            f"unexpected sizes text {len(text):#x}/{old_text:#x} "
            f"data {len(data):#x}/{old_data:#x} sym {sym:#x}"
        )
    if len(text) & 1 or len(data) & 1:
        raise SystemExit(
            f"text and data must be even lengths, got text {len(text):#x} "
            f"data {len(data):#x}"
        )
    growth = len(text) - old_text
    reloc_at = HEADER + old_text + old_data
    positions, reloc_end = parse_relocs(prg, reloc_at)
    if reloc_end != len(prg):
        raise SystemExit(f"relocation table ended at {reloc_end:#x}, file is {len(prg):#x}")

    out = bytearray(prg[:HEADER])
    out[2:6] = len(text).to_bytes(4, "big")
    out += text
    out += data
    shifted = [p + growth if p >= old_text else p for p in positions]
    out += write_relocs(shifted)
    for position in shifted:
        at = HEADER + position
        value = int.from_bytes(out[at:at + 4], "big")
        if value >= old_text:
            out[at:at + 4] = (value + growth).to_bytes(4, "big")
    Path(out_path).write_bytes(out)


if __name__ == "__main__":
    main()
