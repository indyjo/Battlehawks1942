* Identical 68000 bytes in Amiga bh and Atari BH.PRG, after relocation
* immediates are treated as zero. Addresses are offsets into the code or
* data image, not load addresses. The bytes themselves stay in
* src/amiga/bh_code.s and src/st/bh_text.s so each platform still assembles
* at its own origin.
*
* Named pieces inside those runs (Amiga offsets; the ST copy of the
* draw-list opcode $C929 is 0x68 bytes earlier, at 0x1834e):
*   0x18360  rebuild the current-angle draw list, or return if the id matches
*   0x18478  template the draw list is written over
*
* Code, longest runs:
*   Amiga 0x18400  ST 0x18398  5761 bytes
*   Amiga 0x1a9f8  ST 0x19cde   480 bytes
*   Amiga 0x6943   ST 0x65d2    469 bytes
*   Amiga 0x6792   ST 0x6422    429 bytes
*   Amiga 0xc5c    ST 0x20c0    236 bytes
*   40 runs of at least 48 bytes, 10362 bytes total
*
* Data, longest runs:
*   Amiga 0x6848   ST 0x7406   12357 bytes
*   Amiga 0x3d00   ST 0x3bee   11027 bytes
*   Amiga 0x309    ST 0x261     2981 bytes
*   32 runs of at least 64 bytes, 41348 bytes total
