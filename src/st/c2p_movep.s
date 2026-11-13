* Flight-view chunky to planar, for the ST low-resolution screen.
* Assembled only when ST_C2P_MOVEP is defined. The workspace patch
* branches here from the original converters and leaves their bytes in
* place, so a build without the flag still matches the disk.
*
* The chunky view is two pixels per byte, high nibble on the left. A
* longword is eight pixels, B0 B1 B2 B3 in memory order. movep.l writes
* one register as the bytes at d, d+2, d+4 and d+6, which are plane 0
* through plane 3 of one half of a 16-pixel group. Bit 7 of each byte
* is the leftmost of those eight pixels.
*
* Four tables hold every chunky byte already shifted into that layout.
* The first byte of a longword is looked up in the bits 6-7 table, the
* next in bits 4-5, then bits 2-3, then bits 0-1. ORing the four
* longwords is the movep register. Nothing is shifted at runtime.
*
* a4 is the program base, so it cannot hold a table. The delta path
* also needs the new buffer, the old buffer and the screen. That leaves
* three address registers. The bits 0-1 table is the 1024 bytes after
* the bits 2-3 table, and the low word of the index is added to 1024
* before that one lookup.
*
* The screen walk is two longwords at a time. That is one 16-pixel
* group: movep at displacement 0, movep at displacement 1, then the
* screen pointer advances by 8. The delta path compares each longword
* with the previous frame first and skips the lookup when they match.
* a4 is never modified.

* d0 holds one chunky longword, B0 B1 B2 B3. d4 comes back as the
* movep longword. d0 and d1 are clobbered. d5 keeps the odd bytes and
* d6 the even bytes. a3, a5 and a6 are the bits 6-7, 4-5 and 2-3 tables.
* B3's index is moved into the bits 0-1 table, which starts 1024 bytes
* after the bits 2-3 table.
        .macro c2p_expand
        move.l d0,d1
        and.l d5,d1
        lsl.l #2,d1
        addi.w #1024,d1
        move.l (a6,d1.w),d4
        swap d1
        or.l (a5,d1.w),d4
        and.l d6,d0
        lsr.l #6,d0
        or.l (a6,d0.w),d4
        swap d0
        or.l (a3,d0.w),d4
        .endm

* Whole view. The chunky pointer is the buffer at -3060(a4).
c2p_movep_full:
        move.l a5,-6322(a4)
        move.l sp,a5
        movem.l d0-a3/fp,-(sp)
        bsr c2p_build
        bsr c2p_screen
        move.l -3060(a4),a0
        move.w -3046(a4),d7
        beq.w c2p_full_leave
        subq.w #1,d7
        bsr c2p_pad
        move.w d1,-(sp)
c2p_full_row:
        move.w -3048(a4),d2
        move.w d2,d3
        lsr.w #1,d3
        beq.s c2p_full_odd
        subq.w #1,d3
c2p_full_pair:
        move.l (a0)+,d0
        c2p_expand
        movep.l d4,0(a2)
        move.l (a0)+,d0
        c2p_expand
        movep.l d4,1(a2)
        addq.w #8,a2
        dbf d3,c2p_full_pair
c2p_full_odd:
        btst #0,d2
        beq.s c2p_full_next
        move.l (a0)+,d0
        c2p_expand
        movep.l d4,0(a2)
        addq.w #8,a2
c2p_full_next:
        adda.w (sp),a2
        dbf d7,c2p_full_row
        addq.w #2,sp
c2p_full_leave:
        movem.l (sp)+,d0-a3/fp
        move.l -6322(a4),a5
        rts

* Changed longwords only. 4(sp) is the buffer to draw, 8(sp) is the
* previous frame. The caller pops the two pointers.
c2p_movep_delta:
        move.l a5,-6322(a4)
        move.l sp,a5
        movem.l d0-a3/fp,-(sp)
        move.l 4(a5),-(sp)
        move.l 8(a5),-(sp)
        bsr c2p_build
        move.l (sp)+,a1
        move.l (sp)+,a0
        bsr c2p_screen
        move.w -3046(a4),d7
        beq.w c2p_delta_leave
        subq.w #1,d7
        bsr c2p_pad
        move.w d1,-(sp)
c2p_delta_row:
        move.w -3048(a4),d2
        move.w d2,d3
        lsr.w #1,d3
        beq.w c2p_delta_odd
        subq.w #1,d3
c2p_delta_pair:
        move.l (a0)+,d0
        cmp.l (a1)+,d0
        bne.s c2p_delta_first
        move.l (a0)+,d0
        cmp.l (a1)+,d0
        bne.s c2p_delta_second
        addq.w #8,a2
        dbf d3,c2p_delta_pair
        bra.w c2p_delta_odd
c2p_delta_first:
        c2p_expand
        movep.l d4,0(a2)
        move.l (a0)+,d0
        cmp.l (a1)+,d0
        bne.s c2p_delta_both
        addq.w #8,a2
        dbf d3,c2p_delta_pair
        bra.s c2p_delta_odd
c2p_delta_both:
        c2p_expand
        movep.l d4,1(a2)
        addq.w #8,a2
        dbf d3,c2p_delta_pair
        bra.s c2p_delta_odd
c2p_delta_second:
        c2p_expand
        movep.l d4,1(a2)
        addq.w #8,a2
        dbf d3,c2p_delta_pair
c2p_delta_odd:
        btst #0,d2
        beq.s c2p_delta_next
        move.l (a0)+,d0
        cmp.l (a1)+,d0
        beq.s c2p_delta_skip
        c2p_expand
        movep.l d4,0(a2)
c2p_delta_skip:
        addq.w #8,a2
c2p_delta_next:
        adda.w (sp),a2
        dbf d7,c2p_delta_row
        addq.w #2,sp
c2p_delta_leave:
        movem.l (sp)+,d0-a3/fp
        move.l -6322(a4),a5
        rts

* a3 = bits 6-7, a5 = bits 4-5, a6 = bits 2-3. d5 and d6 isolate the
* odd and even bytes of a chunky longword. a2 is the view: row 16,
* 32 pixels in. The top margin is 16 scanlines of 160 bytes, and the
* side margin is 16 bytes.
c2p_screen:
        lea c2p_tab6(pc),a3
        lea c2p_tab4(pc),a5
        lea c2p_tab2(pc),a6
        move.l #0x00ff00ff,d5
        move.l #0xff00ff00,d6
        move.l 29428(a4),a2
        adda.w #2576,a2
        rts

* d1 = bytes from the end of this row's view to the next row's view.
* An odd final group still occupies the 8-byte block its movep writes
* into, so the advance is rounded up to a whole 16-pixel group.
c2p_pad:
        move.w -3048(a4),d0
        addq.w #1,d0
        lsr.w #1,d0
        lsl.w #3,d0
        move.w #160,d1
        sub.w d0,d1
        rts

* Fill the four tables once. Each entry is the movep longword for one
* chunky byte, with that byte's two pixels in the bit pair the table
* is named for and every other bit clear.
c2p_build:
        lea c2p_ready(pc),a0
        tst.w (a0)
        bne.s c2p_build_done
        moveq #0,d0
c2p_build_byte:
        moveq #6,d2
        lea c2p_tab6(pc),a0
        bsr.s c2p_store
        moveq #4,d2
        lea c2p_tab4(pc),a0
        bsr.s c2p_store
        moveq #2,d2
        lea c2p_tab2(pc),a0
        bsr.s c2p_store
        moveq #0,d2
        lea c2p_tab0(pc),a0
        bsr.s c2p_store
        addq.w #1,d0
        cmp.w #256,d0
        bne.s c2p_build_byte
        lea c2p_ready(pc),a0
        move.w #1,(a0)
c2p_build_done:
        rts

* d0.w = chunky byte 0..255. d2.w = 0, 2, 4 or 6. a0 = that table.
* d0 and d2 are preserved.
c2p_store:
        movem.l d0/d2/d5-d7,-(sp)
        moveq #0,d5
        move.b d0,d5
        move.w d5,d6
        lsr.w #4,d6
        and.w #15,d5
        moveq #0,d3
        moveq #0,d4
c2p_store_plane:
        moveq #0,d1
        btst d4,d6
        beq.s c2p_store_no_a
        move.w d2,d7
        addq.w #1,d7
        bset d7,d1
c2p_store_no_a:
        btst d4,d5
        beq.s c2p_store_no_b
        bset d2,d1
c2p_store_no_b:
        moveq #3,d7
        sub.w d4,d7
        lsl.w #3,d7
        lsl.l d7,d1
        or.l d1,d3
        addq.w #1,d4
        cmp.w #4,d4
        bne.s c2p_store_plane
        move.w d0,d1
        and.w #255,d1
        lsl.w #2,d1
        move.l d3,(a0,d1.w)
        movem.l (sp)+,d0/d2/d5-d7
        rts

c2p_ready:
        .word 0
        .even
c2p_tab6:
        .space 1024,0
c2p_tab4:
        .space 1024,0
c2p_tab2:
        .space 1024,0
c2p_tab0:
        .space 1024,0
.if c2p_tab0-c2p_tab2-1024
.error "bits 0-1 table must follow the bits 2-3 table"
.endif
