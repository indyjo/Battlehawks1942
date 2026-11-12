* Amiga flight colors and the Setpalette call that installs them.
* The workspace patch includes this at data 0xDC2. It is assembled only
* when AMIGA_PALETTE is defined. Sixteen colors, then the installer:
* together they fill the 64-byte gap that ends at data 0xE02.
        .word 0x0000
        .word 0x0225
        .word 0x0030
        .word 0x0056
        .word 0x0500
        .word 0x0111
        .word 0x0420
        .word 0x0555
        .word 0x0222
        .word 0x0227
        .word 0x0151
        .word 0x0457
        .word 0x0722
        .word 0x0444
        .word 0x0772
        .word 0x0777
        pea -29244(a4)
        move.w #6,-(sp)
        jsr -32178(a4)
        addq.w #6,sp
        lea -29244(a4),a0
        lea -29148(a4),a1
        moveq #15,d0
Lcopy:
        move.w (a0)+,(a1)+
        dbf d0,Lcopy
        rts
