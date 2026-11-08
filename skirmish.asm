; ---------------------------------------------------------------------------
; Skirmish (work in progress) - milestone 3: combat, terrain defence, win conditions
; A small turn-based tactics game for the Atari 2600.
;
; Cartridge: E7 (M-Network): 16K ROM in eight 2K slices + 2K RAM
;   $F000-$F7FF  lower slot: ROM slice 0-6 (hotspots $FFE0-$FFE6)
;                or 1K RAM (hotspot $FFE7): write $F000-$F3FF, read $F400-$F7FF
;   $F800-$F9FF  256-byte RAM bank 0-3 (hotspots $FFE8-$FFEB)
;                write $F800-$F8FF, read $F900-$F9FF
;   $FA00-$FFFF  fixed: ROM slice 7 (upper 1.5K)
;
; RAM use
;   1K RAM    two view buffers (A at $000, B at $200), 6 columns x 64 bytes
;             each: column c at +c*64, graphic row y (63 = top) at +y.
;             The kernel shows the front buffer; the builder fills the back.
;   bank 0    movement range: DIST (remaining moves + 1 per cell, 0 = out of
;             reach) and the flood fill's queue (64 cells, circular)
;   bank 1    free
;   bank 2    the map: 16 x 12 cells, low nibble terrain, high nibble unit slot;
;             unit table at $C0: UPOS, UKIND, UST, UGFX (16 slots, 0 unused)
;             (UST = HP << 4 | moved)
;   bank 3    cursor bar table (ENT) + all three text lines (TXT)
;
; Slices:  0 = game logic, turns, flood fill, map and unit data
;          1 = text: font, names, composer
;          2 = map and unit data (copied into bank 2 at boot)
;          7 = fixed: reset, main loop, kernels, view builder, tile graphics
;
; Build:  python3 gen.py ; python3 tools/asm6502.py skirmish.asm skirmish.bin -s skirmish.sym
; ---------------------------------------------------------------------------
        processor 6502

VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
CTRLPF  = $0A
PF0     = $0D
PF1     = $0E
PF2     = $0F
RESP0   = $10
ENABL   = $1F
GRP0    = $1B
GRP1    = $1C
HMP0    = $20
VDELP0  = $25
VDELP1  = $26
VDELBL  = $27
HMOVE   = $2A
HMCLR   = $2B
AUDV0   = $19
SWCHA   = $280
SWCHB   = $282
INTIM   = $284
TIM64T  = $296

; E7 hotspots (any access switches)
SLICE   = $FFE0         ; + n : lower slot = ROM slice n (0..6)
RAM1K   = $FFE7         ; lower slot = 1K RAM
RBANK   = $FFE8         ; + n : RAM bank n at $F800/$F900
RBW     = $F800         ; RAM bank write port
RBR     = $F900         ; RAM bank read port
WR1K    = $F000         ; 1K RAM write port
RD1K    = $F400         ; 1K RAM read port
BUFA    = $000          ; view buffer offsets in the 1K RAM
BUFB    = $200

; RAM bank layout
ENTO    = $01           ; bank 3: ENABL value per graphic row (ENTO+y), ENTO-1 = 0
TXT     = $80           ; bank 3: text, column j at TXT+j*15, line k rows at +k*5
MAPO    = $00           ; bank 2: the map
UPOS    = $C0           ; bank 2: unit table: map cell
UKIND   = $D0           ;   side * 8 + type (0-3), $FF = no unit
UST     = $E0           ;   HP << 4 | moved this turn
UGFX    = $F0           ;   TileGfx offset of its counter
DIST    = $00           ; bank 0: remaining moves + 1 per cell
QUEUE   = $C0           ; bank 0: flood fill queue (64)

; colours
TXTBK   = $42           ; text bars: dark red, like the borders
TXTCOL  = $FC           ; ... parchment text
MAPBK   = $FC           ; map: parchment
INK     = $00           ; map tiles: black ink
BORDER  = $42           ; side borders and cursor: dark red

; layout (scanlines)
TOPGAP  = 8
MIDGAP  = 6             ; text 0 -> map
LOWGAP  = 5             ; map -> text 1
TXTGAP  = 3             ; text 1 -> text 2
TXTLINES= 11            ; WSYNCs per text line
MAPLINES= 128
BOTGAP  = 192-TOPGAP-TXTLINES-MIDGAP-MAPLINES-LOWGAP-TXTLINES-TXTGAP-TXTLINES

TILEX   = 56            ; screen x of view column 0 (columns are 8 px apart)

; sounds: AUDC * 32 + length in frames (see Sound)
SND_SEL  = 0
SND_MOVE = 1
SND_BAD  = 2
SND_TURN = 3
SND_HIT  = 4
SND_KILL = 5
SND_WIN  = 6

AUDC0   = $15
AUDF0   = $17
INPT4   = $0C
INPT5   = $0D

; cursor auto-repeat (frames)
RPTSLOW = 14
RPTFAST = 6

; ---- zero page ($80-$FF) ----
frame   = $80
tmp     = $81
tmp2    = $82
gp      = $83           ; builder: tile graphic pointer (2)
dp      = $85           ; builder: destination pointer (2)
curx    = $87           ; cursor, map cell
cury    = $88
vx      = $89           ; wanted view origin
vy      = $8A
dvx     = $8B           ; origin of the view on screen
dvy     = $8C
bvx     = $8D           ; origin of the view being built
bvy     = $8E
bt      = $8F           ; builder: tiles done 0..47, $FF = idle
bc      = $90           ; builder: column 0..5
brow    = $91           ; builder: row 0..7
bcell   = $92           ; builder: map index of the current tile
bhi     = $93           ; builder: back buffer write page ($F0 / $F2)
front   = $94           ; buffer on screen: 0 = A, 1 = B
ready   = $95           ; back buffer complete, flip at the next frame
need    = $96           ; rebuild even if the origin is unchanged
joyprev = $97
rpt     = $98
txtreq  = $99           ; bit k: text line k needs composing
str     = $9A           ; 12 character codes ($9A-$A5)
ballx   = $A6           ; cursor x (screen)
entrow  = $A7           ; ENT index of the cursor's top bar, $FF = none
turn    = $A8
side    = $A9           ; 0 = P1, 1 = P2
tend    = $AA           ; text kernel: last row index + 1
tline   = $AB           ; composer: line offset
ct      = $AC           ; composer: 5 rows of the left character ($AC-$B0)
sel     = $B1           ; selected unit slot, 0 = none
showr   = $B2           ; movement range ready: draw the dots
bfs     = $B3           ; flood fill: 0 idle, 1 clear, 2 clear + seed, 3 running
qhead   = $B4
qtail   = $B5
bcost   = $B6           ; flood fill: cost row (type * 16)
bside   = $B7           ; ... side of the moving unit (0 / 8)
bv      = $B8           ; ... DIST of the cell being expanded
bcellv  = $B9           ; ... that cell
firepr  = $BA           ; fire button last frame
swpr    = $BB           ; console switches last frame
sndt    = $BC           ; sound frames left
sndf    = $BD           ; sound pitch
ovl     = $BE           ; builder: overlay this tile
boot    = $BF           ; 1 setting up, 2 waiting for the first view, 0 running
restart = $C0           ; Reset pressed
bootst  = $C1           ; setup step
amode   = $C2           ; attack choice after a move: 1 = choosing a target
att     = $C3           ; the unit that moved (attacker)
atgt    = $C4           ; target slot under the cursor, 0 = wait
fdmg    = $C5           ; forecast: damage to the target
fback   = $C6           ; ... and back to the attacker (0 = none)
trng    = $C7           ; attacker's range
dta     = $C8           ; Damage: attacker type, attacker HP,
dha     = $C9           ;   defender type, defender cell
dtd     = $CA
dcd     = $CB
dtmp    = $CC
dtmp2   = $CD
over    = $CE           ; 0 playing, 1 P1 won, 2 P2 won
pendend = $CF           ; end the turn at the next frame
; $D0-$F0 free, stack above

VBTIME  = 44
OSTIME  = 35
; a timer reading of N guarantees about (N-1)*64 cycles: threshold = worst/64 + 2
TILET   = 7             ; one tile (worst 316 cycles)
TEXTT   = 17            ; one text line (worst 947 cycles)
BFST    = 11            ; one flood fill step (worst 517 cycles)
CLRT    = 21            ; clear half of DIST (worst 1157 cycles)

; ===========================================================================
; Slice 0: game logic, turns, flood fill, map and unit data
; ===========================================================================
        org $0000
        rorg $F000
        include "slice0_data.inc"
        include "slice0_code.inc"
Slice0End
        if Slice0End > $F800
        err
        endif

; ===========================================================================
; Slice 1: text
; ===========================================================================
        org $0800
        rorg $F000
        include "slice1_data.inc"       ; font first (page aligned)
        include "slice1_code.inc"
Slice1End
        if Slice1End > $F800
        err
        endif

; ===========================================================================
; Slice 2: map and unit data
; ===========================================================================
        org $1000
        rorg $F000
        include "slice2_data.inc"
        if UnitData != MapData + MAPW*MAPH
        err                     ; BootCopy copies both as one 256-byte block
        endif
Slice2End

; ===========================================================================
; Slice 7 (fixed, $FA00-$FFFF)
; ===========================================================================
        org $3A00
        rorg $FA00
        include "fixed_data.inc"        ; TileGfx must be first (page aligned)
        include "fixed_code.inc"
FixedEnd
        if FixedEnd > $FFE0
        err
        endif
        org $3FE0
        rorg $FFE0
        ds 12, 0                ; $FFE0-$FFEB: hotspots, never executed
        org $3FFC
        rorg $FFFC
        .word Start
        .word Start
