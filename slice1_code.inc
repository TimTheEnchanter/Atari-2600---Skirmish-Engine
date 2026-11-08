; ---------------------------------------------------------------------------
; Slice 1: text lines (work chunks).  All three lines live in bank 3.
; ---------------------------------------------------------------------------

; ---- compose one pending text line
TextChunk:
        lda txtreq
        lsr
        bcc .n0
        jmp Text0
.n0     lsr
        bcc .n1
        jmp Text1
.n1
; line 2: while choosing a target, the forecast (HIT d BACK d) or WAIT;
; otherwise the unit under the cursor: name, HP, status (P1 P2 -- GO)
        lda amode
        beq .unit
        ldx atgt
        bne .fc
        ldx #11
.wt     lda WaitText,x
        sta str,x
        dex
        bpl .wt
        jmp .go2
.fc     ldx #3
.ht     lda HitText,x
        sta str,x
        lda BackText,x
        sta str+6,x
        dex
        bpl .ht
        lda #CH_SPACE
        sta str+5
        sta str+10
        ldx fdmg
        lda Ones,x
        sta str+4
        lda #CH_DASH            ; no damage back
        ldx fback
        beq .nb
        lda Ones,x
.nb     sta str+11
        jmp .go2
.unit   jsr CellAt
        lsr
        lsr
        lsr
        lsr
        beq .none
        tay                     ; slot
        lda RBR+UKIND,y
        and #3
        sta tmp
        asl
        adc tmp
        asl                     ; type * 6
        tax
        lda #CH_SPACE
        sta str+6
        sta str+9
        lda RBR+UST,y           ; HP
        lsr
        lsr
        lsr
        lsr
        sty tmp
        tay
        lda Tens,y
        cmp #CH_0
        bne .t10
        lda #CH_SPACE
.t10    sta str+7
        lda Ones,y
        sta str+8
        ldy tmp
        lda #6                  ; GO (selected)
        cpy sel
        beq .st
        lda RBR+UST,y
        lsr
        lda #4                  ; -- (moved)
        bcs .st
        lda RBR+UKIND,y         ; P1 / P2
        and #8
        lsr
        lsr
.st     tay                     ; status offset
        lda StatText,y
        sta str+10
        lda StatText+1,y
        sta str+11
        ldy #0
.nm     lda UnitName,x
        sta str,y
        inx
        iny
        cpy #6
        bne .nm
        jmp .go2
.none   ldx #11
        lda #CH_SPACE
.sp     sta str,x
        dex
        bpl .sp
.go2    lda RBANK+3
        ldy #10
        jsr Compose
        lda txtreq
        and #~4
        sta txtreq
        rts

; line 0: player and turn, or the winner
Text0:
        lda over
        beq .play
        ldx #11                 ; "  Pn  WINS  "
        lda #CH_SPACE
.cl     sta str,x
        dex
        bpl .cl
        lda #CH_P
        sta str+2
        lda over                ; 1 / 2
        asl
        asl
        adc over
        adc #CH_0
        sta str+3
        ldx #3
.wn     lda WinText,x
        sta str+6,x
        dex
        bpl .wn
        jmp .go0
.play   lda #CH_P
        sta str
        lda side
        asl
        asl
        adc side
        adc #CH_0+5
        sta str+1
        lda #CH_SPACE
        sta str+2
        sta str+3
        sta str+4
        sta str+9
        ldx #3
.tt     lda TurnText,x
        sta str+5,x
        dex
        bpl .tt
        ldx turn
        lda Tens,x
        sta str+10
        lda Ones,x
        sta str+11
.go0    lda RBANK+3
        ldy #0
        jsr Compose
        lda txtreq
        and #~1
        sta txtreq
        rts

; line 1: terrain under the cursor and its coordinates, or (choosing a
; target) the target's name and HP
Text1:
        lda amode
        beq .terr
        ldy atgt
        beq .terr
        lda RBANK+2
        lda RBR+UKIND,y
        and #3
        sta tmp
        asl
        adc tmp
        asl
        tax
        ldy #0
.un     lda UnitName,x
        sta str,y
        inx
        iny
        cpy #6
        bne .un
        ldx #3
.hp     lda HPText,x
        sta str+6,x
        dex
        bpl .hp
        ldy atgt
        lda RBR+UST,y
        lsr
        lsr
        lsr
        lsr
        tax
        lda Tens,x
        sta str+10
        lda Ones,x
        sta str+11
        jmp .go1
.terr   jsr CellAt
        and #$0F
        sta tmp
        asl
        adc tmp
        asl                     ; terrain * 6
        tax
        ldy #0
.tn     lda TerrName,x
        sta str,y
        inx
        iny
        cpy #6
        bne .tn
        lda #CH_SPACE
        sta str+6
        lda #CH_DASH
        sta str+9
        ldx curx
        inx
        lda Tens,x
        sta str+7
        lda Ones,x
        sta str+8
        ldx cury
        inx
        lda Tens,x
        sta str+10
        lda Ones,x
        sta str+11
.go1    lda RBANK+3
        ldy #5
        jsr Compose
        lda txtreq
        and #~2
        sta txtreq
        rts

; map cell under the cursor -> A (bank 2 left selected)
CellAt:
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
