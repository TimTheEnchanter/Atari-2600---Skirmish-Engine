; ---------------------------------------------------------------------------
; Fixed area ($FA00-$FFDF): reset, main loop, work dispatcher, view builder,
; object positioning and the display kernels
; ---------------------------------------------------------------------------

; ---- text line kernel: 6 x 2 characters from bank 3 (pair column j at
; TXT+j*15), 5 font rows x 2 scanlines, drawn with the 48-pixel trick (from
; Combat DX's menu).  Y = first row (line * 5), tend = Y + 5.  11 WSYNCs.
; A page crossing at the branch costs one cycle (65 -> 66): still in time.
TextLine:
.tr     sta WSYNC               ; 0
        lda RBR+TXT+0,y         ; 4
        sta GRP0                ; 7
        lda RBR+TXT+15,y         ; 11
        sta GRP1                ; 14
        lda RBR+TXT+30,y        ; 18
        sta GRP0                ; 21
        ldx RBR+TXT+60,y        ; 25
        lda RBR+TXT+75,y        ; 29
        sta tmp                 ; 32
        lda RBR+TXT+45,y        ; 36
        sty tmp2                ; 39
        ldy tmp                 ; 42
        sta GRP1                ; 45
        stx GRP0                ; 48
        sty GRP1                ; 51
        sta GRP0                ; 54
        ldy tmp2                ; 57
        sta WSYNC               ; second scanline of this font row
        lda RBR+TXT+0,y
        sta GRP0
        lda RBR+TXT+15,y
        sta GRP1
        lda RBR+TXT+30,y
        sta GRP0
        ldx RBR+TXT+60,y
        lda RBR+TXT+75,y
        sta tmp
        lda RBR+TXT+45,y
        sty tmp2
        ldy tmp
        sta GRP1
        stx GRP0
        sty GRP1
        sta GRP0
        ldy tmp2                ; 57
        iny                     ; 59
        cpy tend                ; 62
        bne .tr                 ; 65
        sta WSYNC
        lda #0
        sta GRP0
        sta GRP1
        sta GRP0
        rts
TextLineEnd

; ---- power up
; Runs in overscan time (a restart comes straight after the screen), so the
; frame stays 262 lines.  The rest of the setup runs in the next frames'
; vertical blanks (Boot), and the screen stays blank until the view is ready.
Start:
        sei
        cld
        ldx #$FF
        txs
        lda #OSTIME
        sta TIM64T
        lda #0
        ldx #$3F
.tia    sta $00,x               ; TIA registers
        dex
        bpl .tia
        ldx #$7F
.ram    sta $80,x               ; zero page RAM
        dex
        bpl .ram
        lda #$FF
        sta bt                  ; builder idle
        sta dvx                 ; nothing on screen yet
        sta entrow
        lda #1
        sta boot
.ost    lda INTIM
        bne .ost

; ---- main loop: 3 + 37 + 192 + 30 lines
Main:
        lda #2
        sta WSYNC
        sta VBLANK
        sta VSYNC
        sta WSYNC
        sta WSYNC
        sta WSYNC
        lda #0
        sta VSYNC
        lda #VBTIME
        sta TIM64T
        inc frame
        jsr Flip
        lda SLICE+0
        ldx boot
        dex
        bne .lg
        jsr Boot                ; boot = 1: setup steps
        jmp .pa
.lg     jsr Logic               ; input, scrolling, cursor
.pa
        jsr PosAll
        jsr Work
        jsr Screen
        lda restart
        beq .ok
        jmp Start               ; Reset pressed: restart in this overscan
.ok     lda #OSTIME
        sta TIM64T
        jsr Work
.os     lda INTIM
        bne .os
        jmp Main

; ---- Boot step 1-4 (called from slice 0, A = step 1-4): copy 64 bytes of
; map + unit table from slice 2 into bank 2, then give slice 0 back
BootCopy:
        sec
        sbc #1
        asl
        asl
        asl
        asl
        asl
        asl
        tay                     ; (step - 1) * 64
        lda SLICE+2
        lda RBANK+2
        ldx #64
.m      lda MapData,y
        sta RBW,y
        iny
        dex
        bne .m
        lda SLICE+0
        rts

; ---- work chunks while the timer allows: text, flood fill, then tiles
Work:
.lp     lda txtreq
        beq .bf
        lda INTIM
        cmp #TEXTT
        bcc .bf
        lda SLICE+1
        jsr TextChunk
        jmp .lp
.bf     lda bfs
        beq .bld
        ldx #BFST
        cmp #3
        beq .thr
        ldx #CLRT
.thr    stx tmp
        lda INTIM
        cmp tmp
        bcc .bld
        lda SLICE+0
        jsr BfsChunk
        jmp .lp
.bld    lda bt
        bmi .done               ; builder idle
        lda INTIM
        cmp #TILET
        bcc .done
        jsr BuildTile
        jmp .lp
.done   rts

; ---- show a finished back buffer; start a build when the view must change
Flip:
        lda ready
        beq .nf
        lda #0
        sta ready
        lda front
        eor #1
        sta front
        lda bvx
        sta dvx
        lda bvy
        sta dvy
.nf     lda need
        bne .start              ; contents changed: (re)start now
        lda bt
        bpl .busy               ; a build is running
        lda vx
        cmp dvx
        bne .start
        lda vy
        cmp dvy
        beq .busy
.start  lda #0
        sta need
        sta bt
        sta bc
        sta brow
        lda vx
        sta bvx
        lda vy
        sta bvy
        asl
        asl
        asl
        asl
        clc
        adc vx
        sta bcell               ; map index of the view's top left cell
        lda front
        eor #1                  ; back buffer: 0 = A, 1 = B
        asl
        ora #>WR1K              ; write page $F0 or $F2
        sta bhi
.busy   rts

; ---- one tile of the back buffer: the unit's counter, or the terrain with
; the movement range dots on it when the cell is in reach
BuildTile:
        lda RAM1K               ; 1K RAM in the lower slot (written)
        lda RBANK+2             ; the map
        ldy #0
        sty ovl
        ldx bcell
        lda RBR+MAPO,x
        cmp #$10
        bcc .terr
        lsr                     ; unit slot
        lsr
        lsr
        lsr
        tay
        lda RBR+UGFX,y          ; its counter
        bne .gfx
.terr   asl
        asl
        asl
        sta gp
        lda showr
        beq .gfx2
        lda RBANK+0
        lda RBR+DIST,x
        beq .gfx2
        inc ovl
        bne .gfx2
.gfx    sta gp
.gfx2   lda #>TileGfx
        sta gp+1
        ldx bc
        ldy brow
        lda ColLo,x
        clc
        adc RowOff,y
        sta dp
        lda ColHi,x
        ora bhi
        sta dp+1
        ldy #7
        lda ovl
        bne .ov
.cp     lda (gp),y
        sta (dp),y
        dey
        bpl .cp
        bmi .adv
.ov     lda (gp),y
        ora DotGfx,y
        sta (dp),y
        dey
        bpl .ov
.adv    inc bcell               ; next tile
        inc bt
        inx
        cpx #VIEWW
        bne .same
        ldx #0
        inc brow
        lda bcell
        clc
        adc #MAPW-VIEWW
        sta bcell
.same   stx bc
        lda bt
        cmp #VIEWW*VIEWH
        bne .more
        lda #$FF                ; done: idle, flip next frame
        sta bt
        sta ready
.more   rts

; ---- position both players (three close copies each) and the ball
PosAll:
        lda #3
        sta NUSIZ0
        sta NUSIZ1
        lda #1
        sta VDELP0
        sta VDELP1
        sta VDELBL
        lda #$35                ; ball 8 wide, playfield priority, reflected
        sta CTRLPF
        lda #TILEX+POSADJ
        ldx #0
        jsr PosObj
        lda #TILEX+8+POSADJ
        ldx #1
        jsr PosObj
        lda ballx
        clc
        adc #POSADJ+BALLADJ
        ldx #4
        jsr PosObj
        sta WSYNC
        sta HMOVE
        rts

POSADJ  = 0             ; PosObj puts a player at exactly x
BALLADJ = 1             ; the ball appears one pixel left of a player

; A = x, X = object (0 P0, 1 P1, 2 M0, 3 M1, 4 ball)
PosObj:
        sec
        sbc #3
        sta WSYNC
        sec
.div    sbc #15
        bcs .div
        eor #7
        asl
        asl
        asl
        asl
        sta HMP0,x
        sta RESP0,x
        rts

; ---- the visible screen: text line 0, the map, text lines 1 and 2
Screen:
        lda boot
        beq .wt
        lda dvx                 ; first view on screen and text composed?
        bmi .blank
        lda txtreq
        bne .blank
        lda #0
        sta boot
.blank  lda INTIM
        bne .blank
        ldy #193                ; a blank frame (VBLANK stays on)
.bl     sta WSYNC
        dey
        bne .bl
        rts
.wt     lda INTIM
        bne .wt
        lda RAM1K               ; kernel reads the 1K RAM ...
        lda RBANK+3             ; ... and bank 3 (text lines, cursor table)
        sta WSYNC
        lda #0
        sta VBLANK
        sta PF0
        sta PF1
        sta PF2
        sta ENABL
        lda #TXTBK
        sta COLUBK
        lda #BORDER
        sta COLUPF
        lda #TXTCOL
        sta COLUP0
        sta COLUP1
        lda #5
        sta tend
        ldy #TOPGAP
.top    sta WSYNC
        dey
        bne .top
        jsr TextLine            ; line 0 (11), Y = 0
        ldy #MIDGAP-2
.g1     sta WSYNC
        dey
        bne .g1
        sta WSYNC               ; parchment and borders from here
        lda #MAPBK
        sta COLUBK
        lda #$F0
        sta PF0
        lda #$FF
        sta PF1
        lda #$03
        sta PF2
        lda #INK
        sta COLUP0
        sta COLUP1
        lda RBR+ENTO+63         ; cursor bar for the top graphic row
        sta ENABL
        sta WSYNC
        lda front
        bne .kb
        jmp MapKernA            ; 128 lines, returns to MapDone
.kb     jmp MapKernB
MapDone sta WSYNC
        lda #0
        sta GRP0
        sta GRP1                ; also moves ENABL (0) to the displayed ball
        sta GRP0
        ldy #LOWGAP-2
.g2     sta WSYNC
        dey
        bne .g2
        sta WSYNC
        lda #TXTBK
        sta COLUBK
        lda #0
        sta PF0
        sta PF1
        sta PF2
        lda #TXTCOL
        sta COLUP0
        sta COLUP1
        ldy #5
        lda #10
        sta tend
        jsr TextLine            ; line 1 (11)
        ldy #TXTGAP
.g3     sta WSYNC
        dey
        bne .g3
        ldy #10
        lda #15
        sta tend
        jsr TextLine            ; line 2 (11)
        ldy #BOTGAP
.bot    sta WSYNC
        dey
        bne .bot
        lda #2
        sta VBLANK
        rts

        include "fixed_kern.inc"
