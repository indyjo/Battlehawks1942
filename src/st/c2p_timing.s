* Times the flight-view chunky-to-planar step.
* Appended at the end of the text so the original bytes stay put.
* S is the compare scan, in milliseconds. It is measured by walking the
* same two buffers the delta converter walks, with the same cmpm/dbne loop.
* B is the pixel expand: the real converter's time minus that scan.
* C is how many of the view's 8-pixel groups actually differed, in percent.
* R is the wall time from handing back to the game until the next pass
* starts, in milliseconds. The first pass shows 0.
* A full redraw has nothing to compare, so S is 0 and C is 100.
* The extra scan is not part of S or B, but it does lengthen every delta frame.
* The workspace patch includes this at the end of the text section.
* It is assembled only when C2P_TIMING is defined.

c2p_time_full:
        lea c2p_ret(pc),a0
        move.l (sp),(a0)
        lea c2p_after(pc),a0
        move.l a0,(sp)
        movem.l d0-d7/a0-a3/a6,-(sp)
        jsr c2p_read
        jsr c2p_gap
        lea c2p_t0(pc),a0
        move.l d0,(a0)
        lea c2p_seek_ticks(pc),a0
        clr.l (a0)
        lea c2p_changes(pc),a0
        move.w #-1,(a0)
        movem.l (sp)+,d0-d7/a0-a3/a6
        .ifdef ST_C2P_MOVEP
        bra.w c2p_movep_full
        .else
        move.l a5,-6322(a4)
        jmp 0x15816.l
        .endif

c2p_time_delta:
        lea c2p_buf0(pc),a0
        move.l 4(sp),(a0)
        lea c2p_buf1(pc),a0
        move.l 8(sp),(a0)
        lea c2p_ret(pc),a0
        move.l (sp),(a0)
        lea c2p_after(pc),a0
        move.l a0,(sp)
        movem.l d0-d7/a0-a3/a6,-(sp)
        jsr c2p_read
        jsr c2p_gap
        lea c2p_t0(pc),a0
        move.l d0,(a0)
        jsr c2p_seek
        lea c2p_changes(pc),a0
        move.w d0,(a0)
        jsr c2p_read
        sub.l c2p_t0(pc),d0
        lea c2p_seek_ticks(pc),a0
        move.l d0,(a0)
        jsr c2p_read
        lea c2p_t0(pc),a0
        move.l d0,(a0)
        movem.l (sp)+,d0-d7/a0-a3/a6
        .ifdef ST_C2P_MOVEP
        bra.w c2p_movep_delta
        .else
        move.l a5,-6322(a4)
        jmp 0x158f0.l
        .endif

c2p_after:
        movem.l d0-d4/a0-a3,-(sp)
        jsr c2p_read
        sub.l c2p_t0,d0
        sub.l c2p_seek_ticks,d0
        bpl.s c2p_blit_ok
        moveq #0,d0
c2p_blit_ok:
        jsr c2p_ms
        lea c2p_blit_ms(pc),a0
        move.w d0,(a0)
        move.l c2p_seek_ticks(pc),d0
        jsr c2p_ms
        lea c2p_seek_ms(pc),a0
        move.w d0,(a0)
        jsr c2p_percent
        lea c2p_pct(pc),a0
        move.w d0,(a0)
        jsr c2p_draw
        jsr c2p_read
        lea c2p_mark(pc),a0
        move.l d0,(a0)
        movem.l (sp)+,d0-d4/a0-a3
        move.l c2p_ret,-(sp)
        rts

* d0 = 38400 Hz ticks since boot, low 16 bits of the 200 Hz clock.
* Timer C still counts by 192 at 2.4576 MHz / 64. The game uses Timer D.
* A user-mode read of $4BA or the MFP is a bus error in Hatari, which
* aborts flight setup before it installs the palette. GEMDOS Super
* makes the same read, and the trap is inside both samples of a delta.
c2p_read:
        clr.l -(sp)
        move.w #32,-(sp)
        trap #1
        addq.l #6,sp
        lea c2p_ssp(pc),a0
        move.l d0,(a0)
        move.l 0x4ba.l,d0
        moveq #0,d1
        move.b 0xfffffa23.w,d1
        move.l 0x4ba.l,d2
        cmp.l d2,d0
        beq.s c2p_read_ok
        move.l d2,d0
        moveq #0,d1
        move.b 0xfffffa23.w,d1
c2p_read_ok:
        mulu #192,d0
        sub.l d1,d0
        lea c2p_sample(pc),a0
        move.l d0,(a0)
        move.l c2p_ssp(pc),-(sp)
        move.w #32,-(sp)
        trap #1
        addq.l #6,sp
        move.l c2p_sample(pc),d0
        rts

* d0 = tick count at the start of this pass. Store the gap since the
* previous pass returned, in milliseconds. d0 is preserved.
c2p_gap:
        movem.l d0-d1/a0,-(sp)
        lea c2p_mark(pc),a0
        move.l (a0),d1
        beq.s c2p_gap_none
        sub.l d1,d0
        jsr c2p_ms
        bra.s c2p_gap_store
c2p_gap_none:
        moveq #0,d0
c2p_gap_store:
        lea c2p_gap_ms(pc),a0
        move.w d0,(a0)
        movem.l (sp)+,d0-d1/a0
        rts

* Walk both chunky buffers. d0 = number of 8-pixel groups that differ.
* Returns 0 when the sizes are not the flight view.
c2p_seek:
        move.l c2p_buf0,d0
        beq.s c2p_seek_none
        move.l c2p_buf1,d0
        beq.s c2p_seek_none
        move.w -3046(a4),d2
        beq.s c2p_seek_none
        cmpi.w #200,d2
        bhi.s c2p_seek_none
        move.w -3048(a4),d0
        beq.s c2p_seek_none
        cmpi.w #40,d0
        bhi.s c2p_seek_none
        movea.l c2p_buf0,a0
        movea.l c2p_buf1,a1
        subq.w #1,d2
        moveq #0,d0
c2p_seek_row:
        move.w -3048(a4),d7
        subq.w #1,d7
c2p_seek_cmp:
        cmpm.l (a0)+,(a1)+
        dbne d7,c2p_seek_cmp
        beq.s c2p_seek_next
        addq.w #1,d0
        dbf d7,c2p_seek_cmp
c2p_seek_next:
        dbf d2,c2p_seek_row
        rts
c2p_seek_none:
        moveq #0,d0
        rts

* d0 = ticks in, milliseconds in d0, capped at 999.
c2p_ms:
        cmp.l #37962,d0
        bls.s c2p_ms_fit
        move.w #999,d0
        rts
c2p_ms_fit:
        divu #38,d0
        andi.l #0xffff,d0
        rts

* d0 = percent of 8-pixel groups that differed. 100 on a full redraw.
c2p_percent:
        lea c2p_changes(pc),a0
        cmpi.w #-1,(a0)
        bne.s c2p_percent_n
        moveq #100,d0
        rts
c2p_percent_n:
        move.w -3046(a4),d1
        mulu -3048(a4),d1
        beq.s c2p_percent_0
        moveq #0,d0
        move.w c2p_changes,d0
        mulu #100,d0
        divu d1,d0
        andi.l #0xffff,d0
        rts
c2p_percent_0:
        moveq #0,d0
        rts

* Paint "S### B### C### R###" on the top row of the 3D view.
c2p_draw:
        move.l 29428(a4),d0
        bne.s c2p_draw_go
        rts
c2p_draw_go:
        lea c2p_text,a1
        move.b #10,(a1)
        move.w c2p_seek_ms,d0
        lea 1(a1),a1
        jsr c2p_digits
        lea c2p_text,a1
        move.b #13,4(a1)
        move.b #11,5(a1)
        move.w c2p_blit_ms,d0
        lea 6(a1),a1
        jsr c2p_digits
        lea c2p_text,a1
        move.b #13,9(a1)
        move.b #12,10(a1)
        move.w c2p_pct,d0
        lea 11(a1),a1
        jsr c2p_digits
        lea c2p_text,a1
        move.b #13,14(a1)
        move.b #14,15(a1)
        move.w c2p_gap_ms,d0
        lea 16(a1),a1
        jsr c2p_digits
        movea.l 29428(a4),a0
        adda.w #2576,a0
        lea c2p_text,a1
        moveq #18,d4
c2p_char:
        moveq #0,d0
        move.b (a1)+,d0
        lsl.w #3,d0
        lea c2p_font,a2
        adda.w d0,a2
        move.l a0,a3
        moveq #7,d3
c2p_glyph:
        move.b (a2)+,d0
        move.b d0,(a3)
        move.b d0,2(a3)
        move.b d0,4(a3)
        move.b d0,6(a3)
        lea 160(a3),a3
        dbf d3,c2p_glyph
        move.l a0,d0
        btst #0,d0
        bne.s c2p_odd
        addq.l #1,a0
        bra.s c2p_next
c2p_odd:
        addq.l #7,a0
c2p_next:
        dbf d4,c2p_char
        rts

* d0 = 0..999. Write three digit codes at a1. a1 is preserved.
c2p_digits:
        andi.l #65535,d0
        divu #100,d0
        move.b d0,(a1)
        clr.w d0
        swap d0
        divu #10,d0
        move.b d0,1(a1)
        swap d0
        move.b d0,2(a1)
        rts

c2p_ssp:
        .long 0
c2p_sample:
        .long 0
c2p_t0:
        .long 0
c2p_seek_ticks:
        .long 0
c2p_ret:
        .long 0
c2p_buf0:
        .long 0
c2p_buf1:
        .long 0
c2p_changes:
        .word 0
c2p_seek_ms:
        .word 0
c2p_blit_ms:
        .word 0
c2p_pct:
        .word 0
c2p_gap_ms:
        .word 0
c2p_mark:
        .long 0
c2p_text:
        .space 19,0

* 8x8 glyphs, leftmost pixel in the high bit. 0-9, S, B, C, space, R.
c2p_font:
        .byte 0x3c,0x66,0x6e,0x76,0x66,0x66,0x3c,0x00
        .byte 0x18,0x38,0x18,0x18,0x18,0x18,0x3c,0x00
        .byte 0x3c,0x66,0x06,0x1c,0x30,0x60,0x7e,0x00
        .byte 0x3c,0x66,0x06,0x1c,0x06,0x66,0x3c,0x00
        .byte 0x0c,0x1c,0x3c,0x6c,0x7e,0x0c,0x0c,0x00
        .byte 0x7e,0x60,0x7c,0x06,0x06,0x66,0x3c,0x00
        .byte 0x1c,0x30,0x60,0x7c,0x66,0x66,0x3c,0x00
        .byte 0x7e,0x06,0x0c,0x18,0x30,0x30,0x30,0x00
        .byte 0x3c,0x66,0x66,0x3c,0x66,0x66,0x3c,0x00
        .byte 0x3c,0x66,0x66,0x3e,0x06,0x0c,0x38,0x00
        .byte 0x3c,0x66,0x60,0x3c,0x06,0x66,0x3c,0x00
        .byte 0x7c,0x66,0x66,0x7c,0x66,0x66,0x7c,0x00
        .byte 0x3c,0x66,0x60,0x60,0x60,0x66,0x3c,0x00
        .byte 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00
        .byte 0x7c,0x66,0x66,0x7c,0x6c,0x66,0x66,0x00
* Text length must stay even. An odd length puts the data segment on an
* odd address, and the first move.l through a4 is an address error.
        .even
