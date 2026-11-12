#!/usr/bin/env python3
"""Read a GEMDOS FAT12 image made of cCChHsSS.bin sectors and extract files.

Logical sector order is the TOS order: for each cylinder, side 0 sectors
1..spt, then side 1, and so on. The boot sector supplies the BPB.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def load_sectors(directory: Path) -> dict[tuple[int, int, int], bytes]:
    sectors = {}
    for path in directory.glob("c*h*s*.bin"):
        name = path.name
        cyl = int(name[1:3])
        side = int(name[4])
        sec = int(name[6:8])
        sectors[(cyl, side, sec)] = path.read_bytes()
    if (0, 0, 1) not in sectors:
        raise SystemExit(f"no boot sector in {directory}")
    return sectors


def bpb(boot: bytes) -> dict:
    return {
        "bps": struct.unpack_from("<H", boot, 11)[0],
        "spc": boot[13],
        "res": struct.unpack_from("<H", boot, 14)[0],
        "nfats": boot[16],
        "ndir": struct.unpack_from("<H", boot, 17)[0],
        "spf": struct.unpack_from("<H", boot, 22)[0],
        "spt": struct.unpack_from("<H", boot, 24)[0],
        "sides": struct.unpack_from("<H", boot, 26)[0],
    }


class Image:
    def __init__(self, sectors: dict[tuple[int, int, int], bytes]) -> None:
        self.sectors = sectors
        self.bpb = bpb(sectors[(0, 0, 1)])
        if self.bpb["bps"] != 512:
            raise SystemExit(f"unexpected sector size {self.bpb['bps']}")
        self.fat = b"".join(self.logical(self.bpb["res"] + i) for i in range(self.bpb["spf"]))
        dir_secs = (self.bpb["ndir"] * 32 + 511) // 512
        self.dir_start = self.bpb["res"] + self.bpb["nfats"] * self.bpb["spf"]
        self.data_start = self.dir_start + dir_secs

    def logical(self, n: int) -> bytes:
        spt = self.bpb["spt"]
        sides = self.bpb["sides"]
        cyl, rem = divmod(n, spt * sides)
        side, sec = divmod(rem, spt)
        data = self.sectors.get((cyl, side, sec + 1))
        if data is None:
            raise SystemExit(f"missing logical sector {n} (c{cyl}h{side}s{sec+1})")
        return data

    def fat12(self, cluster: int) -> int:
        offset = cluster + cluster // 2
        val = self.fat[offset] | (self.fat[offset + 1] << 8)
        if cluster & 1:
            return val >> 4
        return val & 0xFFF

    def read_chain(self, cluster: int, size: int | None) -> bytes:
        blob = bytearray()
        seen: set[int] = set()
        spc = self.bpb["spc"]
        while 2 <= cluster < 0xFF0 and cluster not in seen:
            seen.add(cluster)
            logical_sec = self.data_start + (cluster - 2) * spc
            for step in range(spc):
                blob += self.logical(logical_sec + step)
            cluster = self.fat12(cluster)
        if size is None:
            return bytes(blob)
        return bytes(blob[:size])

    def entries(self, raw: bytes) -> list[tuple[str, int, int, int]]:
        found = []
        for index in range(0, len(raw), 32):
            entry = raw[index : index + 32]
            if not entry or entry[0] == 0:
                break
            if entry[0] == 0xE5:
                continue
            name = entry[:8].decode("latin1").rstrip(" ")
            ext = entry[8:11].decode("latin1").rstrip(" ")
            attr = entry[11]
            cluster = struct.unpack_from("<H", entry, 26)[0]
            size = struct.unpack_from("<I", entry, 28)[0]
            filename = f"{name}.{ext}" if ext else name
            found.append((filename, attr, cluster, size))
        return found

    def root(self) -> list[tuple[str, int, int, int]]:
        dir_secs = (self.bpb["ndir"] * 32 + 511) // 512
        raw = b"".join(self.logical(self.dir_start + i) for i in range(dir_secs))
        return self.entries(raw)


def write_tree(image: Image, entries: list[tuple[str, int, int, int]], dest: Path, lines: list[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, attr, cluster, size in entries:
        if name in (".", ".."):
            continue
        if attr & 0x08:
            lines.append(f"vol  {name}")
            continue
        if attr & 0x10:
            lines.append(f"dir  {dest.name}/{name}")
            raw = image.read_chain(cluster, None)
            write_tree(image, image.entries(raw), dest / name, lines)
            continue
        data = image.read_chain(cluster, size)
        (dest / name).write_bytes(data)
        lines.append(f"file {dest.name}/{name} {len(data)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sectors", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    image = Image(load_sectors(args.sectors))
    lines = [f"source {args.sectors}", f"bpb {image.bpb}"]
    write_tree(image, image.root(), args.out, lines)
    (args.out / "LISTING.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
