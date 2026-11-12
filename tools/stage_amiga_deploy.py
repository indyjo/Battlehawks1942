#!/usr/bin/env python3
"""Stage deploy/amiga from the two extracted Amiga volumes.

Disk 1 is copied first, then any file that exists only on disk 2. When the
same path is on both disks and the bytes differ, the disk 1 copy stays.
The result is one directory an emulator can mount as the game volume.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISK1 = ROOT / "extracted" / "amiga" / "BHawk1"
DISK2 = ROOT / "extracted" / "amiga" / "BHawk2"
OUT = ROOT / "deploy" / "amiga"
SKIP = {"LISTING.txt"}


def take(source: Path, origin: str, seen: dict[str, str], lines: list[str]) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name in SKIP:
            continue
        rel = path.relative_to(source).as_posix()
        target = OUT / rel
        if rel in seen:
            if target.read_bytes() != path.read_bytes():
                lines.append(f"{rel} kept {seen[rel]}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        seen[rel] = origin
        lines.append(f"{rel} {path.stat().st_size} {origin}")


def main() -> None:
    missing = [path for path in (DISK1, DISK2) if not path.is_dir()]
    if missing:
        raise SystemExit("run tools/prepare_workspace.py first; missing " + ", ".join(str(path) for path in missing))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    seen: dict[str, str] = {}
    lines: list[str] = []
    take(DISK1, "disk1", seen, lines)
    take(DISK2, "disk2", seen, lines)
    (OUT / "FILES.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
