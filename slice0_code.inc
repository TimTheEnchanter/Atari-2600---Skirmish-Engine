; ---------------------------------------------------------------------------
; Slice 0: game logic, turns, flood fill
; ---------------------------------------------------------------------------

; ---- setup, one step per frame while boot = 1 (bootst counts the steps)
; 0: clear the cursor table; 1-4: copy map + unit table from slice 2 into
; bank 2, 64 bytes per step; 5: variables, then P1's first turn (boot becomes 2: waiting for
; the first view)
Boot:
        lda bootst
        bne .s1
        lda RBANK+3
        lda #0
        ldx #ENTO+63
.ent    sta RBW,x
        dex
        bpl .ent
        inc bootst
        rts
.s1     cmp #5
        beq .s2
        jsr BootCopy            ; (fixed: the data is in slice 2)
        inc bootst
        rts
.s2     lda #3
        sta swpr                ; a held Reset doesn't restart again
        lda #$80
        sta firepr
        lda #2
        sta boot
        lda #1                  ; side becomes 0, turn 1, cursor on HQ 1
        sta side
        jmp EndTurn

; ---- once per frame, in vertical blank
Logic:
        lda pendend             ; a turn that ended last frame: switch now
        beq .np                 ; (kept out of the busy frame for time)
        lda #0
        sta pendend
        jsr EndTurn
        jmp .done
.np     lda SWCHB               ; console: bit 0 reset, bit 1 select (0 = pressed)
        eor #$FF
        and #3
        tax
        eor swpr
        stx swpr
        and swpr                ; newly pressed
        lsr
        bcc .nores
        lda #1
        sta restart             ; Reset: restart after this frame
        rts
.nores  lsr
        bcc .nosel
        ldx over
        bne .nosel
        jsr EndTurn             ; Select: end the turn now
.nosel  lda INPT4               ; either fire button (bit 7 = 0 pressed)
        and INPT5
        eor #$80
        and #$80
        tax
        eor firepr
        stx firepr
        and firepr
        beq .nofire
        jsr Fire
.nofire lda SWCHA               ; either joystick: P0 high nibble, P1 low
        eor #$FF
        sta tmp
        lsr
        lsr
        lsr
        lsr
        ora tmp
        and #$0F                ; 1 up, 2 down, 4 left, 8 right
        beq .rel
        cmp joyprev
        bne .new
        dec rpt
        bne .done
        ldx #RPTFAST
        stx rpt
        bne .move
.new    sta joyprev
        ldx #RPTSLOW
        stx rpt
.move   ldx amode
        beq .cur
        jsr NextTarget          ; choosing a target: any direction = next
        jmp .done
.cur    sta tmp
        lsr tmp                 ; up
        bcc .m1
        lda cury
        beq .m1
        dec cury
.m1     lsr tmp                 ; down
        bcc .m2
        lda cury
        cmp #MAPH-1
        bcs .m2
        inc cury
.m2     lsr tmp                 ; left
        bcc .m3
        lda curx
        beq .m3
        dec curx
.m3     lsr tmp                 ; right
        bcc .m4
        lda curx
        cmp #MAPW-1
        bcs .m4
        inc curx
.m4     lda txtreq
        ora #6                  ; terrain and unit lines
        sta txtreq
        jsr Scroll
        jmp .done
.rel    sta joyprev
.done   jsr Sound
        jmp Cursor

; ---- the fire button: select a unit, move it, or cancel
Fire:
        lda over
        beq .play
        sta restart             ; game over: fire starts a new game
        rts
.play   lda amode
        beq .nosel
        jmp Strike
.nosel  lda sel
        bne .have
        jsr CellAtCursor        ; nothing selected: own, unmoved unit here?
        lsr
        lsr
        lsr
        lsr
        beq .bad1
        tay
        lda RBR+UKIND,y
        and #8
        sta tmp
        lda side
        asl
        asl
        asl
        cmp tmp
        bne .bad1               ; the other side's
        lda RBR+UST,y
        lsr
        bcs .bad1               ; already moved
        sty sel
        lda #1
        sta bfs                 ; work out its range
        lda #0
        sta showr
        lda txtreq
        ora #4
        sta txtreq
        lda #SND_SEL
        jmp PlaySnd
.bad1   lda #SND_BAD
        jmp PlaySnd
.have   lda bfs
        beq .rdy
        rts                     ; range not ready yet
.rdy
        jsr CellAtCursor
        sta tmp
        stx tmp2                ; target cell
        lsr
        lsr
        lsr
        lsr
        beq .empty
        cmp sel
        bne .cancel             ; another unit is there
.empty  lda RBANK+0
        lda RBR+DIST,x
        beq .cancel             ; out of reach
        lda RBANK+2             ; move: clear the old cell, fill the new one
        ldy sel
        ldx RBR+UPOS,y
        lda RBR+MAPO,x
        and #$0F
        sta RBW+MAPO,x
        lda sel
        asl
        asl
        asl
        asl
        ldx tmp2
        ora RBR+MAPO,x          ; (terrain only: the cell was empty or ours)
        sta RBW+MAPO,x
        txa
        sta RBW+UPOS,y
        lda RBR+UST,y
        ora #1
        sta RBW+UST,y
        jsr SetGfx
        lda sel
        sta att
        jsr Deselect
        ldx tmp2                ; on the enemy HQ: captured, game won
        lda RBR+MAPO,x
        and #$0F
        sta tmp
        lda #T_HQ2
        sec
        sbc side
        cmp tmp
        bne .nocap
        lda side
        jmp Win
.nocap  lda #0                  ; any enemy in range? then choose a target
        sta atgt
        jsr NextTarget
        lda atgt
        beq .notgt
        lda #1
        sta amode
        lda #SND_MOVE
        bpl .snd
.notgt  lda #SND_MOVE
        jmp Done
.cancel jsr Deselect
.bad    lda #SND_BAD
        bpl .snd
.snd    jmp PlaySnd

Deselect:
        lda #0
        sta sel
        sta showr
        sta bfs
        lda #1
        sta need                ; redraw without the dots (and the moved unit)
        lda txtreq
        ora #4
        sta txtreq
        rts

; Y = slot (bank 2 selected): its counter = side*8 + moved*4 + type
SetGfx:
        lda RBR+UST,y
        and #1
        asl
        asl
        ora RBR+UKIND,y
        asl
        asl
        asl
        ora #$80
        sta RBW+UGFX,y
        rts

; Z set if every unit of the side to play has moved
AllMoved:
        lda RBANK+2
        lda side
        asl
        asl
        asl
        sta tmp
        ldy #15
.l      lda RBR+UKIND,y
        bmi .nx                 ; empty slot
        and #8
        cmp tmp
        bne .nx
        lda RBR+UST,y
        lsr
        bcs .nx
        lda #1                  ; found one still to move: Z clear
        rts
.nx     dey
        bne .l
        lda #0
        rts

; ---- next player: clear moved flags, cursor to their HQ
EndTurn:
        lda #0
        sta amode
        sta att
        sta atgt
        sta sel
        sta showr
        sta bfs
        lda side
        eor #1
        sta side
        bne .p2
        lda turn
        cmp #99
        bcs .p2
        inc turn
.p2     lda RBANK+2
        ldy #15
.l      lda RBR+UKIND,y
        bmi .nx
        lda RBR+UST,y
        and #$FE
        sta RBW+UST,y
        jsr SetGfx
.nx     dey
        bne .l
        ldx side
        lda HQCell,x
        and #$0F
        sta curx
        lda HQCell,x
        lsr
        lsr
        lsr
        lsr
        sta cury
        lda #1
        sta need
        lda #7
        sta txtreq
        jsr Scroll
        lda #SND_TURN
        jmp PlaySnd

; map cell under the cursor -> A, its index -> X (bank 2 left selected)
CellAtCursor:
        lda RBANK+2
        lda cury
        asl
        asl
        asl
        asl
        ora curx
        tax
        lda RBR+MAPO,x
        rts

; ---- keep the cursor inside the view, one tile from the edge where possible
Scroll:
        lda curx
        sec
        sbc vx
        bcc .xlo                ; cursor left of the view
        cmp #1
        bcc .xlo
        cmp #VIEWW-1
        bcc .xok
        lda curx                ; vx = curx - 4, at most MAXVX
        sec
        sbc #VIEWW-2
        cmp #MAXVX
        bcc .xset
        lda #MAXVX
        bcs .xset
.xlo    lda curx                ; vx = curx - 1, at least 0
        sec
        sbc #1
        bcs .xset
        lda #0
.xset   sta vx
.xok    lda cury
        sec
        sbc vy
        bcc .ylo
        cmp #1
        bcc .ylo
        cmp #VIEWH-1
        bcc .yok
        lda cury
        sec
        sbc #VIEWH-2
        cmp #MAXVY
        bcc .yset
        lda #MAXVY
        bcs .yset
.ylo    lda cury
        sec
        sbc #1
        bcs .yset
        lda #0
.yset   sta vy
.yok    rts

; ---- cursor: ball x and the two bar rows in ENT, relative to the view on screen
Cursor:
        lda RBANK+3
        ldx entrow
        bmi .nc
        lda #0
        sta RBW+ENTO,x
        sta RBW+ENTO-7,x
        lda #$FF
        sta entrow
.nc     lda curx
        sec
        sbc dvx
        cmp #VIEWW
        bcs .hide               ; not in the displayed view (scroll pending)
        asl
        asl
        asl
        adc #TILEX
        sta ballx
        lda cury
        sec
        sbc dvy
        cmp #VIEWH
        bcs .hide
        asl
        asl
        asl
        sta tmp
        lda #63
        sec
        sbc tmp
        tax                     ; top bar: graphic row 63 - 8 * screen row
        lda frame
        and #$18
        beq .hide               ; blink: off 8 frames in 32
        lda #2
        sta RBW+ENTO,x
        sta RBW+ENTO-7,x        ; bottom bar: 7 rows lower
        stx entrow
.hide   rts

; ---- sound: one channel, a fixed tone for a few frames
PlaySnd:
        tax
        lda SndC,x
        sta AUDC0
        lda SndF,x
        sta AUDF0
        lda SndT,x
        sta sndt
        lda #8
        sta AUDV0
        rts

Sound:
        lda sndt
        beq .off
        dec sndt
        rts
.off    sta AUDV0
        rts

SndC    .byte 4, 4, 15, 12, 8, 8, 12
SndF    .byte 8, 14, 20, 9, 10, 24, 6
SndT    .byte 5, 8, 14, 18, 10, 30, 60

; ---- combat -------------------------------------------------------------

; fire while choosing a target: attack it (or wait if the cursor is on the
; attacker itself).  The forecast already holds both results.
Strike:
        lda RBANK+2
        lda #SND_MOVE
        sta dtmp2
        ldy atgt
        beq .end                ; wait
        lda #SND_HIT
        sta dtmp2
        lda RBR+UST,y           ; target HP - damage
        lsr
        lsr
        lsr
        lsr
        sec
        sbc fdmg
        beq .kt
        bcc .kt
        jsr SetHP
        lda fback
        beq .end
        ldy att                 ; attacker HP - damage back
        lda RBR+UST,y
        lsr
        lsr
        lsr
        lsr
        sec
        sbc fback
        beq .ka
        bcc .ka
        jsr SetHP
        jmp .end
.ka     ldy att
.kt     lda #SND_KILL
        sta dtmp2
        jsr Kill
.end    ldy att                 ; cursor back on the attacker's cell
        lda RBR+UPOS,y
        jsr CursorTo
        lda #0
        sta amode
        sta atgt
        sta att
        lda #1
        sta need
        lda over
        beq .go
        rts                     ; someone won (Kill set it up)
.go     lda dtmp2
; A = sound: the unit's action is over; end the turn if nobody is left to move
Done:
        pha
        lda txtreq
        ora #6
        sta txtreq
        jsr AllMoved
        bne .more
        inc pendend             ; everyone has moved: next frame ends the turn
.more   pla
        jmp PlaySnd

; Y = slot, A = new HP (1-15)
SetHP:
        asl
        asl
        asl
        asl
        sta dtmp
        lda RBR+UST,y
        and #$0F
        ora dtmp
        sta RBW+UST,y
        rts

; Y = slot: remove the unit; if its side has none left, the other side wins
Kill:
        ldx RBR+UPOS,y
        lda RBR+MAPO,x
        and #$0F
        sta RBW+MAPO,x
        lda RBR+UKIND,y
        and #8
        sta dtmp
        lda #$FF
        sta RBW+UKIND,y
        ldy #15
.l      lda RBR+UKIND,y
        bmi .nx
        and #8
        cmp dtmp
        beq .alive
.nx     dey
        bne .l
        lda dtmp                ; none left: the other side (0 / 1) wins
        eor #8
        lsr
        lsr
        lsr
        jmp Win
.alive  rts

; A = winning side (0 / 1)
Win:
        clc
        adc #1
        sta over
        lda #0
        sta amode
        sta sel
        sta showr
        sta bfs
        lda #1
        sta need
        lda #7
        sta txtreq
        lda #SND_WIN
        jmp PlaySnd

; A = map cell: put the cursor there and scroll to it
CursorTo:
        pha
        and #$0F
        sta curx
        pla
        lsr
        lsr
        lsr
        lsr
        sta cury
        jmp Scroll

; the next enemy in range of the attacker after atgt (wrapping to 0 = wait,
; the attacker's own cell); cursor to it, forecast, text lines
NextTarget:
        lda RBANK+2
        ldy att
        lda RBR+UPOS,y
        sta tmp
        lda RBR+UKIND,y
        sta dtmp2
        and #3
        tax
        lda RangeTab,x
        sta trng
        ldy atgt
.l      iny
        cpy #16
        bcs .none
        lda RBR+UKIND,y
        bmi .l
        eor dtmp2
        and #8
        beq .l                  ; same side
        lda RBR+UPOS,y
        sta tmp2
        jsr Dist
        cmp trng
        bne .l
        sty atgt
        jsr Forecast
        lda tmp2
        jmp .cur
.none   lda #0
        sta atgt
        lda tmp
.cur    jsr CursorTo
        lda txtreq
        ora #6
        sta txtreq
        rts

; attacker att vs target atgt: fdmg, and fback if the target survives and
; the attacker is at the target's range
Forecast:
        ldy att
        lda RBR+UKIND,y
        and #3
        sta dta
        lda RBR+UST,y
        lsr
        lsr
        lsr
        lsr
        sta dha
        ldy atgt
        lda RBR+UKIND,y
        and #3
        sta dtd
        lda RBR+UPOS,y
        sta dcd
        jsr Damage
        sta fdmg
        lda #0
        sta fback
        ldy atgt
        lda RBR+UST,y
        lsr
        lsr
        lsr
        lsr
        sec
        sbc fdmg
        beq .x                  ; target destroyed
        bcc .x
        sta dha                 ; the target strikes back with what's left
        ldx dtd
        lda RangeTab,x
        cmp trng
        bne .x                  ; attacker out of its range
        lda dtd
        ldx dta
        sta dta
        stx dtd
        ldy att
        lda RBR+UPOS,y
        sta dcd
        jsr Damage
        sta fback
.x      rts

; dta / dha attack dtd standing on dcd -> A = damage (at least 1)
Damage:
        lda dta
        asl
        asl
        ora dtd
        tax
        lda BaseTab,x
        tax
        lda Times11,x
        clc
        adc dha
        tax
        lda DmgTab,x
        sta dtmp
        ldx dcd
        lda RBR+MAPO,x
        and #$0F
        tax
        lda dtmp
        sec
        sbc TerrDef,x
        beq .one
        bcs .ok
.one    lda #1
.ok     rts

; tmp, tmp2 = cells -> A = Manhattan distance (keeps Y)
Dist:
        lda tmp
        and #$0F
        sta dtmp
        lda tmp2
        and #$0F
        sec
        sbc dtmp
        bcs .p1
        eor #$FF
        adc #1
.p1     sta dtmp
        lda tmp
        lsr
        lsr
        lsr
        lsr
        sta dha                 ; (free here: Forecast sets it afterwards)
        lda tmp2
        lsr
        lsr
        lsr
        lsr
        sec
        sbc dha
        bcs .p2
        eor #$FF
        adc #1
.p2     clc
        adc dtmp
        rts

; ---- flood fill (work chunks).  DIST = remaining moves + 1, 0 = not reached.
; Enemy units block; friendly units can be passed through.
BfsChunk:
        lda bfs
        cmp #3
        bcs BfsStep
        lsr                     ; 1: clear DIST 0-95, 2: clear 96-191 and seed
        lda RBANK+0
        lda #0
        ldx #95
        bcc .h2
.c1     sta RBW+DIST,x
        dex
        bpl .c1
        inc bfs
        rts
.h2
.c2     sta RBW+DIST+96,x
        dex
        bpl .c2
        lda RBANK+2             ; seed from the selected unit
        ldy sel
        lda RBR+UKIND,y
        and #8
        sta bside
        lda RBR+UKIND,y
        and #3
        tax
        asl
        asl
        asl
        asl
        sta bcost               ; cost row: type * 16
        lda MovePts,x
        clc
        adc #1
        ldx RBR+UPOS,y
        ldy RBANK+0
        sta RBW+DIST,x
        txa
        sta RBW+QUEUE
        lda #0
        sta qhead
        lda #1
        sta qtail
        lda #3
        sta bfs
        rts

BfsStep:
        lda RBANK+0
        ldx qhead
        cpx qtail
        bne .pop
        lda #0                  ; queue empty: done
        sta bfs
        lda #1
        sta showr
        sta need
        rts
.pop    lda RBR+QUEUE,x
        sta bcellv
        inx
        txa
        and #63
        sta qhead
        ldx bcellv
        lda RBR+DIST,x
        sta bv
        txa                     ; up
        sec
        sbc #MAPW
        bcc .n1
        tax
        jsr Relax
.n1     lda bcellv              ; down
        cmp #MAPW*(MAPH-1)
        bcs .n2
        adc #MAPW
        tax
        jsr Relax
.n2     lda bcellv              ; left
        and #MAPW-1
        beq .n3
        ldx bcellv
        dex
        jsr Relax
.n3     lda bcellv              ; right
        and #MAPW-1
        cmp #MAPW-1
        beq .n4
        ldx bcellv
        inx
        jsr Relax
.n4     rts

; X = neighbour cell: enter it with what is left after its cost
Relax:
        lda RBANK+2
        lda RBR+MAPO,x
        sta tmp2
        and #$0F
        ora bcost
        tay
        lda CostTab,y
        beq .no                 ; can't enter
        sta tmp
        lda tmp2
        lsr
        lsr
        lsr
        lsr
        beq .free
        tay
        lda RBR+UKIND,y
        and #8
        cmp bside
        bne .no                 ; enemy unit blocks
.free   lda bv
        sec
        sbc tmp
        beq .no                 ; not enough moves left
        bcc .no
        ldy RBANK+0
        cmp RBR+DIST,x
        bcc .no
        beq .no                 ; no better than before
        sta RBW+DIST,x
        txa
        ldy qtail
        sta RBW+QUEUE,y
        iny
        tya
        and #63
        sta qtail
.no     rts
