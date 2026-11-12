#!/usr/bin/env python3
"""Extract decoded sectors from a Pasti STX (RSY) disk image.

Track record (16 bytes): size, fuzzy-mask size, sector count, flags,
MFM size, track number (bit 7 is the side), record type. Flag bit 0 marks
sector descriptors, bit 5 a protected track, bit 6 a track image.
Each descriptor's data offset is relative to the first byte after the
descriptor list and the fuzzy mask (the track image). Size code 2 is a
512-byte sector. This does not reconstruct flux timing.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

TRACK_HEADER = 16
SECTOR_DESC = 16
PAYLOAD = 512


def parse(data: bytes) -> list[dict]:
    if data[:4] != b"RSY\x00":
        raise SystemExit("not a Pasti STX image")
    version = struct.unpack_from("<H", data, 4)[0]
    if version != 3:
        raise SystemExit(f"unsupported STX version {version}")
    track_count = data[10]
    pos = 16
    tracks = []
    for index in range(track_count):
        if pos + TRACK_HEADER > len(data):
            raise SystemExit(f"truncated track header at {pos}")
        size, fuzzy = struct.unpack_from("<II", data, pos)
        sector_count, flags, _mfm = struct.unpack_from("<HHH", data, pos + 8)
        track_byte = data[pos + 14]
        if size < TRACK_HEADER or pos + size > len(data):
            raise SystemExit(f"bad track size {size} at {pos}")
        rec = data[pos : pos + size]
        desc_at = TRACK_HEADER
        if flags & 1:
            desc_end = desc_at + sector_count * SECTOR_DESC
        else:
            desc_end = desc_at
        if desc_end > len(rec):
            raise SystemExit(f"truncated sector descriptors on track {index}")
        image_at = desc_end + fuzzy
        sectors = []
        for s in range(sector_count):
            desc = rec[desc_at + s * SECTOR_DESC : desc_at + (s + 1) * SECTOR_DESC]
            data_off = struct.unpack_from("<I", desc, 0)[0]
            id_track, id_head, id_sector, size_code = desc[8], desc[9], desc[10], desc[11]
            fdc = desc[14]
            nbytes = 128 << size_code if size_code < 8 else 0
            src = image_at + data_off
            if size_code != 2 or src + nbytes > len(rec):
                payload = b""
            else:
                payload = rec[src : src + nbytes]
            sectors.append(
                {
                    "id_track": id_track,
                    "id_head": id_head,
                    "id_sector": id_sector,
                    "size_code": size_code,
                    "fdc": fdc,
                    "payload": payload,
                }
            )
        tracks.append(
            {
                "index": index,
                "fuzzy": fuzzy,
                "flags": flags,
                "track_word": track_byte,
                "sectors": sectors,
            }
        )
        pos += size
    if pos != len(data):
        raise SystemExit(f"track records end at {pos}, file is {len(data)}")
    return tracks


def fill_kind(payload: bytes) -> str | None:
    if not payload:
        return "missing"
    if payload == bytes([payload[0]]) * len(payload):
        return f"fill {payload[0]:02X}"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stx", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    data = args.stx.read_bytes()
    tracks = parse(data)
    args.out.mkdir(parents=True, exist_ok=True)
    notes = [
        f"source {args.stx}",
        f"tracks {len(tracks)}",
        f"revision_byte {data[11]}",
    ]
    written = 0
    fill_counts: dict[str, int] = {}
    protected = 0
    odd_lines = []
    for tr in tracks:
        side = (tr["track_word"] >> 7) & 1
        cyl = tr["track_word"] & 0x7F
        if tr["flags"] & 0x20:
            protected += 1
        for sec in tr["sectors"]:
            kind = fill_kind(sec["payload"])
            name = f"c{cyl:02d}h{side}s{sec['id_sector']:02d}.bin"
            path = args.out / name
            if sec["payload"]:
                path.write_bytes(sec["payload"])
                written += 1
            if kind:
                fill_counts[kind] = fill_counts.get(kind, 0) + 1
            problems = []
            if tr["fuzzy"]:
                problems.append(f"fuzzy {tr['fuzzy']}")
            if sec["fdc"]:
                problems.append(f"fdc {sec['fdc']:02X}")
            if sec["size_code"] != 2 or not sec["payload"]:
                problems.append(f"size_code {sec['size_code']}")
            if kind and not kind.startswith("fill E5") and not kind.startswith("fill 00"):
                problems.append(kind)
            if problems:
                odd_lines.append(
                    f"c{cyl:02d}h{side} id {sec['id_track']}/{sec['id_head']}/{sec['id_sector']} "
                    + ", ".join(problems)
                )
    notes.append(f"protected_tracks {protected}")
    notes.append("fill_counts " + ", ".join(f"{k}={v}" for k, v in sorted(fill_counts.items())))
    notes.append(f"odd_sectors {len(odd_lines)}")
    notes.extend(odd_lines[:80])
    (args.out / "NOTES.txt").write_text("\n".join(notes) + "\n")
    print(f"wrote {written} sectors -> {args.out}")
    odd = [n for n in notes if n.startswith("c")]
    print(f"flagged sectors {len(odd)}")


if __name__ == "__main__":
    sys.exit(main())
