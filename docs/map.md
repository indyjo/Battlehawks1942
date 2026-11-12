# Battlehawks 1942: Amiga and Atari ST

This is a map of the two images in `images/`, not a claim that either build boots. `make check` assembles the code sections with `m68k-atari-mintelf-as -m68000 --register-prefix-optional` and compares them to the original bytes.

The assembler accepts Motorola mnemonics (`move.l d0,26310(a4)`). It has no `.syntax motorola` directive. Where it would emit a different legal encoding than the original (for example `sub.l #9,d0` as `subi`, or `cmp.w #64,d4` as `cmpi`), the source keeps the Motorola line as a comment and emits `.word`.

## Images

Amiga, Lucasfilm, standard OFS ADFs, volumes `BHawk1` and `BHawk2`.

- `s/startup-sequence` runs `type FLTTEXT`, then `flt`, then `bh`.
- `bh` is a three-hunk load file. Hunk 0 is 116628 bytes of code with 3 relocations. Hunk 1 is 42596 bytes of data on disk (the header allocates 61932) with 2146 relocations. Hunk 2 is 4 bytes of BSS.
- `flt` is 6096 bytes of code. `type` is two small code hunks (316 and 1808 bytes).

Atari, Kixx, Pasti STX. Not the original Lucasfilm ST master. Both disks are ordinary GEMDOS FAT12 once the sector data offset is taken relative to the track image. Every track has Pasti flag bit 5 set; sampled sectors still have FDC status 0.

- Disk 1: 80 cylinders, 2 sides, 9 sectors of 512 bytes. Media id `$F9`. Root holds `BH.PRG` and directory `SDAT`.
- Disk 2: 80 cylinders, 1 side, 9 sectors. Media id `$F8`. Root holds directory `FDAT`.
- `BH.PRG` is a TOS executable (`$601A`), not a boot sector. Text 114306, data 45624, BSS 19738, 2219 relocations. The text section is the ST code image.

## What is shared

Matched by bytes, with relocation immediates zeroed, not by load address. Runs shorter than 48 bytes (code) or 64 bytes (data) are not counted.

The programs are laid out alike. The longest code run is 5761 bytes at Amiga code `0x18400` and ST text `0x18398`. Forty code runs cover 10362 bytes. Thirty-two data runs cover 41348 bytes, including two blocks of 12357 and 11027 bytes. The list is in `src/common/ranges.s`.

Both executables name the same vehicle files, Amiga with `/` and ST with `\`:

`fdat/zekev4.pac`, `wildv3`, `sbdv5nb`, `tbmv4`, `valv3`, `katev2`, `lex`, `tonev1`, `kagav3`, `ryujov1`, `stdv1`, `fxv1`, and the `s` forms of those names.

Amiga-only glue includes `intuition.library`, `graphics.library`, `dos.library`, and the strings `palettes`, `sound.rsc`, `sound2.rsc`. The ST program names `sdat\sfx.sfx` and the `sdat\*.pac` UI files instead.

## Roles

Offsets are into the Amiga `bh` code hunk unless noted. The ST text is 0x68 bytes earlier at the draw-list site (`0x1834e` holds the same `move.w #$C929` the Amiga has at `0x183b6`). `a4` is data-hunk base plus `$7FFE` (`lea` at code `0x1b15c`, relocated to hunk 1).

| Where | Length | Role |
| --- | --- | --- |
| code `0x39f6` | 172 bytes | Build a path and open a file. Failure falls through a retry. |
| code `0x37d2` | 376 bytes | Read a PAC. Each record runs until a `$FF` byte, which is stored. A call can skip leading records and keep a count of later ones. Pointers go in the BSS table at `a4+$4F00`; the bytes go to the pointer at `a4+$6100`. |
| code `0x394a` | 172 bytes | If the vehicle index at `a4+$61FC` changed, load that vehicle's PAC. The index is cached, so the file is not read again for the same vehicle. |
| code `0x245a` | one call | Recognition test. Always passes `fdat/zekev4.pac`, keeps one record, and picks the record number from the 15 bytes at data `0x11F0`: 14, 17, 20, 22, 24, 26, 29, 32, 35, 37, 40, 43, 45, 47, 49. |
| data `0x1414` | 16 pointers | Relocated pointers into the code hunk. First half: `fdat/wildv3.pac`, `sbdv5nb`, `tbmv4`, `zekev4`, `valv3`, `katev2`, `lex`, `tonev1`, `kagav3`, `ryujov1`. Second half: the `s` names, starting at `fdat/wildv3s.pac`. |
| code `0x161ec` | 142 bytes | Picture expander, also in the ST text (the `cmpi.b #-2,d3` is at ST `0x161d4`). `$FE` ends a row, `$FD` skips pixels, any other byte is a color `0..15` and the next byte plus one is the run length. Pixels are packed two per byte. |
| code `0x15c52` | 100 bytes | Build the row-offset table at `a4-$1222` from a width and height. Row stride is `width/2`. |
| code `0x162b6` | 428 bytes | Fold an angle into one quadrant. Flags land in the object at `a4-$0E22`. Sine values come from the table at `a4+$29E` (data `0x829C`): a quarter turn, about `sin(k/128 * 90°) * 32768`. |
| code `0x18360` | 280 bytes | Rebuild the draw list for the current angle, or return if the object's id word still matches the saved id at `a4+$1718`. One transformed list is cached, not one bitmap per angle. |
| code `0x16ff4` | 164 bytes | Masked CPU blit of a small image whose first two bytes are width and height. The pointer table at `a4+$1842` (data `0x9840`) holds those images; the records there are a few bytes each. |
| code `0x15982` | — | Point `a4+$70CC` at `$DFF096`, `$DFF09A`, and `$DFF0A0` (DMACON, INTENA, AUD0). |

## Sprites

`TM.PAC` is text, the gunnery lesson that starts "1) Gunnery Fundamentals". It is identical on both machines and is not a sprite.

Vehicle PACs are a sequence of records separated by `$FF`. `ZEKEV4.PAC` has 66 records, `ZEKEV4S.PAC` has 65, `WILDV3.PAC` has 209, `FXV1.PAC` has 104. A Zeke record begins with four signed bytes and a fifth byte that is 1. On 65 of the 66 Zeke frames the second and fourth bytes are the same, and the first and third are a negative and a positive x: frame 0 is -42, 13, 43, 13. The S frame is -21, 6, 19, 6. The S pack is a second authored set, about half the coordinate size and about half the file size, not a cache built at runtime. Both filenames are in the pointer table at data `0x1414`, and both programs reference `fdat/zekev4.pac` and `fdat/zekev4s.pac`.

The loaded records are kept in the BSS tail of the data hunk (allocated 61932 bytes, 42596 on disk). `0x394a` reloads a PAC only when the vehicle index changes.

Rotation is computed. `0x162b6` folds the angle with the sine table, and `0x18360` writes an 8-byte draw record per vertex into a template that lives in the code (`0x18478`, and a second template when the caller's flag is set). The template words are `$C929` / `$8529` or `$CB29` / `$8729`, and the routine fills in the coordinate. If the object's id word is unchanged it returns without rebuilding. That cache holds the current angle only. The same constants and the same early-out are in the ST text.

Screen pictures use a different coding. `LOGO.PAC` on the ST is rows of exactly 160 pixels for the first 133 rows: a run of color 15, length 16, ten times, then `$FE`. The expander at `0x161ec` is what reads that. Vehicle records contain no `$FE`, so they do not go through that row coder. `0x16ff4` blits a mask and a pixel rectangle with the CPU; the images it reaches from data `0x9840` are tiny (width and height bytes of 1 and 2), which fits instruments rather than an aircraft frame cache.

## Color

The picture expander stores colors `0..15`, two pixels per byte. That is a 16-color buffer on both machines, because the same `cmpi.b #-2,d3` decoder is in the ST text.

`PALETTES` on Amiga disk A is 835 bytes, not an IFF `CMAP`. The first big-endian long is 10. The rest is a stream of 12-bit `0RGB` words. `$0FFF` falls on a 16-word stride through the opening groups. Later groups are not all the same length. That table is not in the ST executable or in `SFX.SFX`. The vehicle PACs match byte for byte; the UI packs do not (`P.PAC` is 56232 bytes on the Amiga and 35250 on the ST). The ST buffer can hold 16 colors. Nothing in the ST image is a copy of the Amiga color words.

## Sound

Amiga `bh` opens `sound.rsc` and `sound2.rsc` (the names sit at code `0x409a`, passed from `0x405a`). `0x15982` aims Paula at `$DFF0A0`.

Both RSC files start with the same header shape. The first big-endian long is the file size minus 102 (`sound.rsc` 71355, `sound2.rsc` 50443). The next word is 102, the header length. The word after that is 33, then `$C000`, then zeros. At offset 24 both files have the word 2, at offset 28 the word 600, at offset 30 the word 127. From byte 4 through byte 7382 the two files are the same; the samples diverge after that. They are not `FORM`/`8SVX`. The 600 is in the header, not a confirmed playback rate.

The ST program opens `sdat\sfx.sfx` only. That file is 1907 bytes and is not a copy of either bank. It starts with the byte `$1E` and then a run of `$16` words. It cannot hold the Amiga samples.

## Faster Amiga hardware

No delay was patched. There is no read of `$DFF002` (blitter busy), no `$BFE001`, and no `$DFF006` raster read in the code hunk.

The custom-chip stores are:

- `0x44a`: `move.w #$8020,$DFF096` sets sprite DMA.
- `0x8c8`: `move.w #$0020,$DFF096` clears sprite DMA.
- `0xa38`: `move.w #$8100,$DFF096` sets bitplane DMA.
- `0x159a2`: absolute pointers to `$DFF096`, `$DFF09A`, and `$DFF0A0`.

The `dbf d1` sites branch back a short distance, so they are ordinary loops. The tightest are at `0x1b102` and `0x1b46a` (displacement -4). The others are `0x15c12`, `0x15d56`, `0x16076`, `0x16124`, `0x163f8`, `0x16408`, `0x16448`, `0x16458`, and `0x19b38`. `0x15d56` is the vertex loop that adds or subtracts a coordinate according to the quadrant flags.
