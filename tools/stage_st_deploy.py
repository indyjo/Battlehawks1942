#!/usr/bin/env python3
"""Assemble the ST sources and stage deploy/st.

The sources are already patched. --amiga-palette, --c2p-timing and
--c2p-movep are compile-time flags (--defsym AMIGA_PALETTE, C2P_TIMING
and ST_C2P_MOVEP), not a choice of which patches to install. With no
flag the assembled program matches the disk.

An Amiga PAC replaces the ST file only when the bytes are identical. The
full-screen packs are a different geometry, and the ST row decoder paints them
off the screen. Amiga packs with no ST counterpart are still copied into FDAT.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMIGA = ROOT / "extracted" / "amiga"
ST_FILES = ROOT / "extracted" / "st"
OUT = ROOT / "deploy" / "st"
ORIGINAL_PRG = ST_FILES / "disk1" / "files" / "BH.PRG"
BIN = Path.home() / "opt" / "cross-mint" / "bin"


def amiga_pacs() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in AMIGA.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".pac":
            found[path.name.upper()] = path
    return found


def st_palette_word(amiga: int) -> int:
    """Amiga 12-bit 0RGB to ST 9-bit 0RGB, dropping the low bit of each channel."""
    red = (amiga >> 8) & 0xF
    green = (amiga >> 4) & 0xF
    blue = amiga & 0xF
    return ((red >> 1) << 8) | ((green >> 1) << 4) | (blue >> 1)


def write_palette(source: Path, dest: Path) -> int:
    raw = source.read_bytes()
    count = len(raw) // 2
    words = [st_palette_word(struct.unpack_from(">H", raw, i)[0]) for i in range(0, count * 2, 2)]
    dest.write_bytes(struct.pack(f">{len(words)}H", *words))
    return len(words)


def stage_dir(names_from: Path, dest: Path, amiga: dict[str, Path]) -> list[str]:
    lines = []
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(names_from.iterdir()):
        if not src.is_file():
            continue
        other = amiga.get(src.name.upper())
        if other is not None and other.read_bytes() == src.read_bytes():
            chosen, origin = other, "amiga"
        else:
            chosen, origin = src, "st"
        shutil.copy2(chosen, dest / src.name.upper())
        lines.append(f"{dest.name}/{src.name.upper()} {chosen.stat().st_size} {origin}")
    return lines


def build_prg(palette: bool, timing: bool, movep: bool, dest: Path) -> None:
    """Assemble the patched ST sources and splice them into the original header."""
    tag = "st"
    if palette:
        tag += "-amiga"
    if timing:
        tag += "-c2p"
    if movep:
        tag += "-movep"
    work = ROOT / "build" / tag
    work.mkdir(parents=True, exist_ok=True)
    flags = ["-m68000", "--register-prefix-optional"]
    if palette:
        flags += ["--defsym", "AMIGA_PALETTE=1"]
    if timing:
        flags += ["--defsym", "C2P_TIMING=1"]
    if movep:
        flags += ["--defsym", "ST_C2P_MOVEP=1"]
    assembler = str(BIN / "m68k-atari-mintelf-as")
    copier = str(BIN / "m68k-atari-mintelf-objcopy")
    for name, section in (("bh_text", ".text"), ("bh_data", ".data")):
        obj = work / f"{name}.o"
        blob = work / f"{name}.bin"
        subprocess.check_call([assembler, *flags, "-o", str(obj), str(ROOT / "src" / "st" / f"{name}.s")])
        subprocess.check_call([copier, "-O", "binary", "-j", section, str(obj), str(blob)])
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "python3",
            str(ROOT / "tools" / "splice_prg.py"),
            str(work / "bh_text.bin"),
            str(work / "bh_data.bin"),
            str(ORIGINAL_PRG),
            str(dest),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amiga-palette", action="store_true", help="define AMIGA_PALETTE for this build")
    parser.add_argument("--c2p-timing", action="store_true", help="define C2P_TIMING for this build")
    parser.add_argument("--c2p-movep", action="store_true", help="define ST_C2P_MOVEP for this build")
    parser.add_argument("--prg-out", type=Path, help="write only BH.PRG, and do not restage the tree")
    args = parser.parse_args()
    if args.prg_out:
        build_prg(args.amiga_palette, args.c2p_timing, args.c2p_movep, args.prg_out)
        if OUT.is_dir():
            shutil.copy2(args.prg_out, OUT / "BH.PRG")
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    amiga = amiga_pacs()
    build_prg(args.amiga_palette, args.c2p_timing, args.c2p_movep, OUT / "BH.PRG")
    flags = []
    if args.amiga_palette:
        flags.append("AMIGA_PALETTE")
    if args.c2p_timing:
        flags.append("C2P_TIMING")
    if args.c2p_movep:
        flags.append("ST_C2P_MOVEP")
    prg_note = ",".join(flags) if flags else "original"
    lines = [f"BH.PRG {(OUT / 'BH.PRG').stat().st_size} {prg_note}"]
    lines += stage_dir(ST_FILES / "disk1" / "files" / "SDAT", OUT / "SDAT", amiga)
    lines += stage_dir(ST_FILES / "disk2" / "files" / "FDAT", OUT / "FDAT", amiga)
    placed = {line.split()[0].split("/", 1)[-1] for line in lines if "/" in line.split()[0] or line.startswith("FDAT")}
    # names already recorded as SDAT/NAME or FDAT/NAME
    used = set()
    for line in lines:
        name = line.split()[0]
        if "/" in name:
            used.add(name.split("/", 1)[1])
    extra = OUT / "FDAT"
    for name in sorted(amiga):
        if name in used:
            continue
        shutil.copy2(amiga[name], extra / name)
        lines.append(f"FDAT/{name} {amiga[name].stat().st_size} amiga-only")
    pal_src = AMIGA / "BHawk1" / "PALETTES"
    n = write_palette(pal_src, OUT / "PALETTES.ST")
    lines.append(f"PALETTES.ST {n} words from {pal_src.name}")
    (OUT / "FILES.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
