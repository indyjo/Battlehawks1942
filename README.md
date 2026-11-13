# Battlehawks 1942

Motorola 68000 disassembly of the 1989 Lucasfilm flight simulator, for the Amiga and the Atari ST. The goal is one shared source tree that assembles with GNU tools. Game assets stay in platform directories. The assembler is `m68k-atari-mintelf-as` from a GCC toolchain installed under `~/opt/cross-mint` (`-m68000 --register-prefix-optional`).

`tools/prepare_workspace.py` reads the four disk images, writes `extracted/` and `assets/`, disassembles the programs, and applies every file in `patches/` in filename order. The number at the start of each name is that order. A patch is a short hook in the generated assembly. The hook includes a file that stays in the repository (`src/st/amiga_palette.s`, `src/st/c2p_timing.s`), and that file is assembled only when its compile-time flag is defined. There is no way to install a subset of the patches.

`make check` assembles with the flags off and compares the code with the original bytes. `make prg` asks `tools/stage_st_deploy.py` to assemble the patched sources and splice them into the original `BH.PRG` header and relocation table. `make AMIGA_PALETTE=1 prg`, `make C2P_TIMING=1 prg`, and `make ST_C2P_MOVEP=1 prg` pass those flags through as `--defsym`. `ST_C2P_MOVEP` replaces the flight view's chunky-to-planar step with the lookup-table converter in `src/st/c2p_movep.s`. The same script without `--prg-out` also fills `deploy/st/` with the program and the graphics. `tools/stage_amiga_deploy.py` fills `deploy/amiga/` from the two extracted Amiga volumes. `make clean` removes `build/`.

The side-by-side map of the two programs is in `docs/map.md`.

None of the generated output is part of this repository: `assets/`, `extracted/`, `deploy/`, and the generated assembly (`src/st/bh_text.s`, `src/st/bh_data.s`, `src/amiga/bh_code.s`, `src/amiga/bh_data.s`, `src/amiga/flt_code.s`, `src/amiga/type_hunk0.s`, `src/amiga/type_hunk1.s`) stay local.

## Disk images

The repository does not contain the game disks. Place these four files at the paths below before extracting or rebuilding. The MD5 sums identify the images this tree was built from.

| Path | MD5 |
| --- | --- |
| `images/Battlehawks 1942 (Lucasfilm)/Battlehawks 1942 (Lucasfilm) A.adf` | `50ce4cef9f711789c8d40a289f3d2ee1` |
| `images/Battlehawks 1942 (Lucasfilm)/Battlehawks 1942 (Lucasfilm) B.adf` | `6d88ce6e2e3f1dbe983521f975d5f33b` |
| `images/battlehawks_1942_kixx/Battlehawks 1942 (Disk 1 of 2) (Kixx).stx` | `ad7238f4e6390fcfdfbe6037c71b43a7` |
| `images/battlehawks_1942_kixx/Battlehawks 1942 (Disk 2 of 2) (Kixx).stx` | `beedb77e981ea6291ddae00cc884d216` |

The Amiga pair are standard OFS ADFs of the Lucasfilm release, volumes `BHawk1` and `BHawk2`. The Atari pair are Pasti STX images of the Kixx release, not the Lucasfilm ST master. Disk 1 holds `BH.PRG` and `SDAT`. Disk 2 holds `FDAT`.
