#!/usr/bin/env python3
"""Extract the disks, disassemble the programs, and install every source patch.

Patches live in patches/*.patch and are applied in filename order. Each file
is a unified diff. A hunk that only adds lines creates its target. Every other
hunk must match exactly once. The hooks include files kept in the repository,
and those files decide their own behavior with a compile-time flag.
Assembling without the flag emits the original bytes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "images"
AMIGA_A = IMAGES / "Battlehawks 1942 (Lucasfilm)" / "Battlehawks 1942 (Lucasfilm) A.adf"
AMIGA_B = IMAGES / "Battlehawks 1942 (Lucasfilm)" / "Battlehawks 1942 (Lucasfilm) B.adf"
ST_1 = IMAGES / "battlehawks_1942_kixx" / "Battlehawks 1942 (Disk 1 of 2) (Kixx).stx"
ST_2 = IMAGES / "battlehawks_1942_kixx" / "Battlehawks 1942 (Disk 2 of 2) (Kixx).stx"
PATCHES = ROOT / "patches"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def require_images() -> None:
    missing = [path for path in (AMIGA_A, AMIGA_B, ST_1, ST_2) if not path.is_file()]
    if missing:
        raise SystemExit("missing disk image:\n" + "\n".join(str(path) for path in missing))


def extract() -> None:
    run(["python3", "tools/extract_adf.py", str(AMIGA_A), "extracted/amiga/BHawk1", "--assets", "assets/amiga/BHawk1"])
    run(["python3", "tools/extract_adf.py", str(AMIGA_B), "extracted/amiga/BHawk2", "--assets", "assets/amiga/BHawk2"])
    run(["python3", "tools/extract_stx.py", str(ST_1), "extracted/st/disk1"])
    run(["python3", "tools/extract_stx.py", str(ST_2), "extracted/st/disk2"])
    run(["python3", "tools/extract_gemdos.py", "extracted/st/disk1", "extracted/st/disk1/files"])
    run(["python3", "tools/extract_gemdos.py", "extracted/st/disk2", "extracted/st/disk2/files"])
    copy_named_assets(ROOT / "extracted/st/disk1/files", ROOT / "assets/st/disk1")
    copy_named_assets(ROOT / "extracted/st/disk2/files", ROOT / "assets/st/disk2")


def copy_named_assets(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".pac", ".sfx"}:
            target = dest / path.name
            target.write_bytes(path.read_bytes())
            print(f"asset {target.relative_to(ROOT)}")


def split_and_disassemble() -> None:
    jobs = [
        (["python3", "tools/split_hunk.py", "extracted/amiga/BHawk1/bh", "extracted/amiga/hunks/bh"], None),
        (["python3", "tools/split_hunk.py", "extracted/amiga/BHawk1/flt", "extracted/amiga/hunks/flt"], None),
        (["python3", "tools/split_hunk.py", "extracted/amiga/BHawk1/type", "extracted/amiga/hunks/type"], None),
        (["python3", "tools/split_hunk.py", "--tos", "extracted/st/disk1/files/BH.PRG", "extracted/st/hunks/bh"], None),
    ]
    for cmd, _ in jobs:
        run(cmd)
    disasm = [
        ("extracted/amiga/hunks/bh/hunk0.code.bin", "src/amiga/bh_code.s", "Amiga bh code hunk", "bh"),
        ("extracted/amiga/hunks/flt/hunk0.code.bin", "src/amiga/flt_code.s", "Amiga flt code hunk", "flt"),
        ("extracted/amiga/hunks/type/hunk0.code.bin", "src/amiga/type_hunk0.s", "Amiga type hunk 0", "type0"),
        ("extracted/amiga/hunks/type/hunk1.code.bin", "src/amiga/type_hunk1.s", "Amiga type hunk 1", "type1"),
        ("extracted/st/hunks/bh/text.bin", "src/st/bh_text.s", "Atari ST BH.PRG text section", "st"),
    ]
    for binary, src, title, work in disasm:
        run(
            [
                "python3",
                "tools/disasm_motorola.py",
                binary,
                src,
                "--title",
                title,
                "--work",
                f"build/disasm/{work}",
            ]
        )


def replace_once(text: str, old: str, new: str, patch: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{patch.name} matched {count} times, expected 1:\n{old}")
    return text.replace(old, new, 1)


def parse_patch(path: Path) -> tuple[Path, list[tuple[str, str]]]:
    """Read one unified diff. Returns the target and each hunk as (old, new)."""
    target: Path | None = None
    hunks: list[tuple[str, str]] = []
    old: list[str] | None = None
    new: list[str] | None = None

    def close() -> None:
        nonlocal old, new
        if old is None:
            return
        hunks.append(("".join(old), "".join(new or [])))
        old = new = None

    for lineno, line in enumerate(path.read_text().splitlines(keepends=True), 1):
        if line.startswith("--- "):
            close()
            continue
        if line.startswith("+++ "):
            name = line[4:].strip().split("\t", 1)[0]
            if name.startswith("b/"):
                name = name[2:]
            if name in ("", "/dev/null"):
                raise SystemExit(f"{path.name}:{lineno}: patch has no target")
            target = ROOT / name
            continue
        if line.startswith("@@"):
            close()
            old, new = [], []
            continue
        if old is None or new is None:
            raise SystemExit(f"{path.name}:{lineno}: expected a hunk")
        if line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        elif line.startswith(" "):
            old.append(line[1:])
            new.append(line[1:])
        elif line.startswith("\\"):
            continue
        else:
            raise SystemExit(f"{path.name}:{lineno}: not a diff line")
    close()
    if target is None or not hunks:
        raise SystemExit(f"{path.name}: no hunks")
    return target, hunks


def install_patches() -> None:
    files = sorted(PATCHES.glob("*.patch"))
    if not files:
        raise SystemExit(f"no patches in {PATCHES}")
    for path in files:
        target, hunks = parse_patch(path)
        if all(old == "" for old, _ in hunks):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(new for _, new in hunks))
        else:
            text = target.read_text()
            for old, new in hunks:
                if old == "":
                    raise SystemExit(f"{path.name}: a new-file hunk is mixed with a replacement")
                text = replace_once(text, old, new, path)
            target.write_text(text)
        print(f"applied {path.name} -> {target.relative_to(ROOT)}")


def main() -> None:
    require_images()
    extract()
    split_and_disassemble()
    install_patches()


if __name__ == "__main__":
    sys.exit(main())
