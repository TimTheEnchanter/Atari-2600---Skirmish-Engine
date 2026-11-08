#!/usr/bin/env python3
"""Skirmish data generator: tile and unit graphics, terrain costs, the test
map and its units, font, strings, the text composer and the map kernels.

Writes  fixed_data.inc   (tile graphics page, small tables)       -> fixed area
        fixed_kern.inc   (map kernels A and B)                     -> fixed area
        slice0_data.inc  (unit stats, costs, combat tables)        -> slice 0
        slice1_data.inc  (font, names, digits, text composer)      -> slice 1
        slice2_data.inc  (map and unit table, copied at boot)      -> slice 2
        build_map.json   (everything the tests need)
"""

def byte_rows(name, vals, per=16):
    s = "%s\n" % name if name else ""
    for i in range(0, len(vals), per):
        s += "    .byte " + ",".join("$%02X" % (v & 255) for v in vals[i:i + per]) + "\n"
    return s

def bits8(rows):
    """8 strings of 8 chars, top first -> 8 bytes, index 7 = top row"""
    assert len(rows) == 8, rows
    out = []
    for r in rows:
        assert len(r) == 8, r
        out.append(int(r.replace('#', '1').replace('.', '0'), 2))
    return out[::-1]

# ------------------------------------------------------------- terrain
# Row 7 (the top row) stays blank on every tile: it is the grid gap and the
# cursor's top bar.  Index = terrain number (low nibble of a map cell).
TERRAIN = [
 ("PLAIN", " PLAIN", [
  "........",
  "........",
  "........",
  "........",
  "........",
  ".#.#....",
  "..#.....",
  "........"]),
 ("FOREST", "FOREST", [
  "........",
  "..#.....",
  ".###..#.",
  "#####.#.",
  "..#..###",
  "..#.####",
  ".....###",
  "......#."]),
 ("HILL", "  HILL", [
  "........",
  "........",
  "...##...",
  "..#..#..",
  ".#....#.",
  "#......#",
  "........",
  "........"]),
 ("WATER", " WATER", [
  "........",
  "........",
  ".##..##.",
  "#..##..#",
  "........",
  ".##..##.",
  "#..##..#",
  "........"]),
 ("ROADH", "  ROAD", [
  "........",
  "........",
  "........",
  "##.##.##",
  "........",
  "##.##.##",
  "........",
  "........"]),
 ("ROADV", "  ROAD", [
  "........",
  "..#.#...",
  "........",
  "..#.#...",
  "..#.#...",
  "........",
  "..#.#...",
  "..#.#..."]),
 ("ROADX", "  ROAD", [
  "........",
  "..#.#...",
  "........",
  "##...###",
  "........",
  "##...###",
  "........",
  "..#.#..."]),
 ("BRIDGE", "BRIDGE", [
  "........",
  "########",
  "#..#..#.",
  "........",
  "........",
  "#..#..#.",
  "########",
  "........"]),
 ("HQ1", "HQ  P1", [
  "........",
  "#.#.#.#.",
  "#######.",
  "#.....#.",
  "#.###.#.",
  "#.#.#.#.",
  "#######.",
  "........"]),
 ("HQ2", "HQ  P2", [
  "........",
  "#.#.#.#.",
  "#######.",
  "#######.",
  "##...##.",
  "##.#.##.",
  "#######.",
  "........"]),
]
TERR_IDX = {t[0]: i for i, t in enumerate(TERRAIN)}
assert len(TERRAIN) <= 16

# ------------------------------------------------------------- units
# Wargame counters: a 7x6 box (rows 1-6) with a NATO-style symbol inside.
# Player 1 counters are outlined; player 2 counters are solid with the
# symbol cut out.  A unit that has moved this turn shows only corners + symbol.
# Graphic index = side * 8 + moved * 4 + type (type 0-3).
# name, text, symbol, move points, cost per terrain (0 = can't enter)
SYMBOLS = [
 ("TROOP",  " TROOP", ["#...#", ".#.#.", ".#.#.", "#...#"], 3),   # X  infantry
 ("ARCHER", "ARCHER", [".....", ".###.", ".###.", "....."], 3),   # dot (ranged)
 ("RIDER",  " RIDER", ["....#", "..##.", ".##..", "#...."], 5),   # /  cavalry
 ("HEAVY",  " HEAVY", [".###.", "#...#", "#...#", ".###."], 3),   # oval (armour)
]
#           PLAIN FOREST HILL WATER ROADH ROADV ROADX BRIDGE HQ1 HQ2
COSTS = {
 "TROOP":  [1, 2, 2, 0, 1, 1, 1, 1, 1, 1],
 "ARCHER": [1, 2, 2, 0, 1, 1, 1, 1, 1, 1],
 "RIDER":  [1, 3, 3, 0, 1, 1, 1, 1, 1, 1],
 "HEAVY":  [1, 0, 3, 0, 1, 1, 1, 1, 1, 1],
}

def counter(sym, solid, moved):
    """a counter; once moved, only its corners and symbol are left (moved
    units are only ever seen during their own side's turn, so the
    outline / solid side cue isn't needed then)"""
    rows = ["........"]                     # row 7: grid gap
    if moved:
        rows.append("##...##.")
        rows.append("#" + sym[0] + "#.")
        rows += ["." + s + ".." for s in sym[1:3]]
        rows.append("#" + sym[3] + "#.")
        rows.append("##...##.")
    else:
        rows.append("#######.")
        for s in sym:
            inner = "".join('.' if c == '#' else '#' for c in s) if solid else s
            rows.append("#" + inner + "#.")
        rows.append("#######.")
    rows.append("........")                 # row 0
    return rows

unit_gfx = [[0] * 8 for _ in range(16)]
for t, (_, _, sym, _) in enumerate(SYMBOLS):
    for side in (0, 1):
        for moved in (0, 1):
            unit_gfx[side * 8 + moved * 4 + t] = bits8(counter(sym, side == 1, moved))

terr_gfx = [[0] * 8 for _ in range(16)]
for i, (_, _, rows) in enumerate(TERRAIN):
    g = bits8(rows)
    assert g[7] == 0, "terrain %s: top row must be blank" % TERRAIN[i][0]
    terr_gfx[i] = g

# movement range overlay: a light halftone over the whole tile
DOTS = bits8(["#.#.#.#.", "........", "#.#.#.#.", "........",
              "#.#.#.#.", "........", "#.#.#.#.", "........"])

# ------------------------------------------------------------- combat
# Base damage, attacker row vs defender column (troop, archer, rider, heavy),
# scaled by the attacker's HP / 10 (rounded, at least 1), then reduced by the
# defender's terrain (at least 1).  Every unit starts with 10 HP.  Attack
# range: exactly 1 (melee) or exactly 2 (archer).  A defender that survives
# strikes back if the attacker is at its range.
BASE = {
 "TROOP":  [5, 6, 4, 2],
 "ARCHER": [5, 5, 6, 2],
 "RIDER":  [6, 7, 5, 3],
 "HEAVY":  [7, 7, 6, 5],
}
RANGE = {"TROOP": 1, "ARCHER": 2, "RIDER": 1, "HEAVY": 1}
#        PLAIN FOREST HILL WATER ROADH ROADV ROADX BRIDGE HQ1 HQ2
TERRDEF = [0, 1, 2, 0, 0, 0, 0, 0, 2, 2]
MAXHP = 10
def scaled(base, hp):
    if base == 0 or hp == 0:
        return 0
    return max(1, (base * hp + 5) // 10)

# ------------------------------------------------------------- test map
MAPW, MAPH = 16, 12
MAP = [
 "fff..hh...~~.hhf",
 "ff....h...~...ff",
 "f..ff.....~..f..",
 "...ff....~~.....",
 ".A-----+--=--B..",
 ".......|.~...|hh",
 "..hh...|.~...|.f",
 "..h....|~~...|ff",
 "f......|~....|.f",
 "ff.....+=----+..",
 "fff..hh.~...hh..",
 "hhf....~~...hfff",
]
LEG = {'.': "PLAIN", 'f': "FOREST", 'h': "HILL", '~': "WATER", '-': "ROADH",
       '|': "ROADV", '+': "ROADX", '=': "BRIDGE", 'A': "HQ1", 'B': "HQ2"}
# (x, y): (side, type)   side 0 = P1, 1 = P2; type 0 troop 1 archer 2 rider 3 heavy
UNITS = [
 ((2, 3), (0, 0)), ((2, 5), (0, 0)), ((3, 4), (0, 3)), ((1, 2), (0, 1)), ((4, 6), (0, 2)), ((0, 5), (0, 1)),
 ((12, 3), (1, 0)), ((12, 5), (1, 0)), ((14, 3), (1, 1)), ((15, 4), (1, 3)), ((14, 6), (1, 2)), ((11, 2), (1, 1)),
]
assert len(UNITS) <= 15
assert len(MAP) == MAPH and all(len(r) == MAPW for r in MAP)
cells = []
hq = [None, None]
for y, row in enumerate(MAP):
    for x, ch in enumerate(row):
        cells.append(TERR_IDX[LEG[ch]])
        if ch == 'A': hq[0] = y * 16 + x
        if ch == 'B': hq[1] = y * 16 + x
# unit table (bank 2, $C0-$FF): UPOS, UKIND, UST, UGFX, 16 slots each, slot 0 unused
upos = [0] * 16; ukind = [0xFF] * 16; ust = [0] * 16; ugfx = [0] * 16   # UST: HP << 4 | moved
for i, ((x, y), (side, typ)) in enumerate(UNITS):
    slot = i + 1
    c = y * 16 + x
    assert COSTS[SYMBOLS[typ][0]][cells[c] & 15], "unit on impassable terrain at %d,%d" % (x, y)
    cells[c] |= slot << 4
    upos[slot] = c; ukind[slot] = side * 8 + typ; ust[slot] = MAXHP << 4
    ugfx[slot] = 0x80 + (side * 8 + typ) * 8

# ------------------------------------------------------------- font
CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:"
GLYPHS = {
 ' ': ["...", "...", "...", "...", "..."],
 'A': [".#.", "#.#", "###", "#.#", "#.#"], 'B': ["##.", "#.#", "##.", "#.#", "##."],
 'C': [".##", "#..", "#..", "#..", ".##"], 'D': ["##.", "#.#", "#.#", "#.#", "##."],
 'E': ["###", "#..", "##.", "#..", "###"], 'F': ["###", "#..", "##.", "#..", "#.."],
 'G': [".##", "#..", "#.#", "#.#", ".##"], 'H': ["#.#", "#.#", "###", "#.#", "#.#"],
 'I': ["###", ".#.", ".#.", ".#.", "###"], 'J': ["..#", "..#", "..#", "#.#", ".#."],
 'K': ["#.#", "#.#", "##.", "#.#", "#.#"], 'L': ["#..", "#..", "#..", "#..", "###"],
 'M': ["#.#", "###", "###", "#.#", "#.#"], 'N': ["##.", "#.#", "#.#", "#.#", "#.#"],
 'O': [".#.", "#.#", "#.#", "#.#", ".#."], 'P': ["##.", "#.#", "##.", "#..", "#.."],
 'Q': [".#.", "#.#", "#.#", "##.", ".##"], 'R': ["##.", "#.#", "##.", "#.#", "#.#"],
 'S': [".##", "#..", ".#.", "..#", "##."], 'T': ["###", ".#.", ".#.", ".#.", ".#."],
 'U': ["#.#", "#.#", "#.#", "#.#", "###"], 'V': ["#.#", "#.#", "#.#", "#.#", ".#."],
 'W': ["#.#", "#.#", "###", "###", "#.#"], 'X': ["#.#", "#.#", ".#.", "#.#", "#.#"],
 'Y': ["#.#", "#.#", ".#.", ".#.", ".#."], 'Z': ["###", "..#", ".#.", "#..", "###"],
 '0': ["###", "#.#", "#.#", "#.#", "###"], '1': [".#.", "##.", ".#.", ".#.", "###"],
 '2': ["##.", "..#", ".#.", "#..", "###"], '3': ["##.", "..#", ".#.", "..#", "##."],
 '4': ["#.#", "#.#", "###", "..#", "..#"], '5': ["###", "#..", "##.", "..#", "##."],
 '6': [".##", "#..", "###", "#.#", "###"], '7': ["###", "..#", ".#.", ".#.", ".#."],
 '8': ["###", "#.#", "###", "#.#", "###"], '9': ["###", "#.#", "###", "..#", "##."],
 '-': ["...", "...", "###", "...", "..."], ':': ["...", ".#.", "...", ".#.", "..."],
}
def code(ch): return CHARS.index(ch) * 5
def codes(s): return [code(c) for c in s]
fhi = []; flo = []
for ch in CHARS:
    for row in GLYPHS[ch]:
        v = int(row.replace('#', '1').replace('.', '0'), 2)
        fhi.append(v << 5); flo.append(v << 1)
assert len(fhi) <= 256

# ------------------------------------------------------------- outputs
consts = [
 "MAPW = %d" % MAPW, "MAPH = %d" % MAPH,
 "VIEWW = 6", "VIEWH = 8",
 "MAXVX = %d" % (MAPW - 6), "MAXVY = %d" % (MAPH - 8),
 "CH_SPACE = %d" % code(' '), "CH_DASH = %d" % code('-'), "CH_0 = %d" % code('0'),
 "CH_P = %d" % code('P'), "MAXHP = %d" % MAXHP,
 "T_HQ1 = %d" % TERR_IDX["HQ1"], "T_HQ2 = %d" % TERR_IDX["HQ2"],
 "START_X = %d" % (hq[0] % 16), "START_Y = %d" % (hq[0] // 16),
]
for i, (n, _, _) in enumerate(TERRAIN):
    if n not in ("HQ1", "HQ2"):
        consts.append("T_%s = %d" % (n, i))

# fixed area data: one page of tile graphics, then tables
fx = ["; generated by gen.py", "\n".join(consts), "",
      "; tile graphics page (must be page aligned): terrain 0-15, then units",
      "; (side * 8 + moved * 4 + type); 8 bytes each, index 7 = top row"]
fx.append(byte_rows("TileGfx", sum(terr_gfx, []) + sum(unit_gfx, [])))
fx.append("; movement range overlay, and nothing")
fx.append(byte_rows("DotGfx", DOTS))
fx.append("; builder: column -> buffer offset, row -> line offset (top row first)")
fx.append(byte_rows("ColLo", [(c & 3) * 64 for c in range(6)]))
fx.append(byte_rows("ColHi", [c >> 2 for c in range(6)]))
fx.append(byte_rows("RowOff", [56 - 8 * r for r in range(8)]))
with open("fixed_data.inc", "w") as f:
    f.write("\n".join(fx) + "\n")

# map kernels: one per buffer (1K RAM read port $F400 / $F600).
# Each graphic row is two scanlines (A and B); Y = row index 63..0 (top first).
# Line B ends by loading the next row's cursor bar into ENABL (VDELBL is on,
# so it shows from the next GRP1 write, which is cycle 14 of the next line).
def line(base):
    c = lambda k: "RD1K+%s+%d" % (base, k * 64)
    return [
     "        sta WSYNC               ; 0",
     "        lda %s,y       ; 4" % c(0),
     "        sta GRP0                ; 7",
     "        lda %s,y       ; 11" % c(1),
     "        sta GRP1                ; 14",
     "        lda %s,y       ; 18" % c(2),
     "        sta GRP0                ; 21",
     "        ldx %s,y       ; 25" % c(4),
     "        lda %s,y       ; 29" % c(5),
     "        sta tmp                 ; 32",
     "        lda %s,y       ; 36" % c(3),
     "        sty tmp2                ; 39",
     "        ldy tmp                 ; 42",
     "        sta GRP1                ; 45  tile 4",
     "        stx GRP0                ; 48  tile 5",
     "        sty GRP1                ; 51  tile 6",
     "        sta GRP0                ; 54",
     "        ldy tmp2                ; 57",
    ]
kern = ["; generated by gen.py: map kernels.  A page crossing at the loop branch",
        "; costs one cycle (69 -> 70), still before the next line's WSYNC."]
for nm, base in (("MapKernA", "BUFA"), ("MapKernB", "BUFB")):
    kern.append(nm)
    kern.append("        ldy #63")
    kern.append(".row")
    kern += line(base)
    kern += line(base)
    kern += ["        lda RBR+ENTO-1,y        ; 61  next row's cursor bar",
             "        sta ENABL               ; 64",
             "        dey                     ; 66",
             "        bpl .row                ; 69",
             "        jmp MapDone             ; 71",
             nm + "End"]
with open("fixed_kern.inc", "w") as f:
    f.write("\n".join(kern) + "\n")

# slice 2: map and unit table (Boot copies them into bank 2)
s2 = ["; generated by gen.py"]
s2.append("; test map, %dx%d, row-major: low nibble terrain, high nibble unit slot" % (MAPW, MAPH))
s2.append(byte_rows("MapData", cells))
s2.append("; unit table, copied to bank 2 $C0: UPOS, UKIND (side*8+type, $FF none),")
s2.append("; UST (HP << 4 | moved), UGFX")
s2.append(byte_rows("UnitData", upos + ukind + ust + ugfx))
with open("slice2_data.inc", "w") as f:
    f.write("\n".join(s2) + "\n")

# slice 0: unit stats, movement costs, combat tables
s0 = ["; generated by gen.py"]
s0.append("; move points by type")
s0.append(byte_rows("MovePts", [s[3] for s in SYMBOLS]))
s0.append("; cost to enter, [type * 16 + terrain], 0 = can't")
ct = []
for s in SYMBOLS:
    row = COSTS[s[0]] + [0] * (16 - len(COSTS[s[0]]))
    assert len(COSTS[s[0]]) == len(TERRAIN)
    ct += row
s0.append(byte_rows("CostTab", ct))
s0.append("; combat: base damage [attacker type * 4 + defender type]")
s0.append(byte_rows("BaseTab", sum([BASE[x[0]] for x in SYMBOLS], [])))
s0.append("; attack range by type (exact distance)")
s0.append(byte_rows("RangeTab", [RANGE[x[0]] for x in SYMBOLS]))
s0.append("; terrain defence")
s0.append(byte_rows("TerrDef", TERRDEF + [0] * (16 - len(TERRDEF))))
assert len(TERRDEF) == len(TERRAIN)
s0.append("; damage scaled by HP: DmgTab[base * 11 + hp]")
s0.append(byte_rows("Times11", [b * 11 for b in range(8)]))
s0.append(byte_rows("DmgTab", [scaled(b, h) for b in range(8) for h in range(11)]))
s0.append("; HQ cells (cursor goes there at the start of a turn)")
s0.append(byte_rows("HQCell", hq))
with open("slice0_data.inc", "w") as f:
    f.write("\n".join(s0) + "\n")

# slice 1: font (page aligned), names, digits, composer
s1 = ["; generated by gen.py (must start on a page boundary)"]
s1.append(byte_rows("FontHi", fhi))
s1.append("    ds %d, 0" % (256 - len(fhi)))
s1.append(byte_rows("FontLo", flo))
s1.append("; terrain names (6 characters each)")
s1.append(byte_rows("TerrName", sum([codes(t[1]) for t in TERRAIN], []) +
                    codes("  ----") * (16 - len(TERRAIN))))
s1.append("; unit names by type")
s1.append(byte_rows("UnitName", sum([codes(s[1]) for s in SYMBOLS], [])))
s1.append("; unit status (2 characters): ready P1, ready P2, moved, selected")
s1.append(byte_rows("StatText", codes("P1") + codes("P2") + codes("--") + codes("GO")))
s1.append("; attack forecast, wait, win, target HP")
s1.append(byte_rows("HitText", codes("HIT ")))
s1.append(byte_rows("BackText", codes("BACK")))
s1.append(byte_rows("WaitText", codes("    WAIT    ")))
s1.append(byte_rows("WinText", codes("WINS")))
s1.append(byte_rows("HPText", codes(" HP ")))
s1.append("; 2-digit decimal, 0-99")
s1.append(byte_rows("Tens", [code(str(n // 10)) for n in range(100)]))
s1.append(byte_rows("Ones", [code(str(n % 10)) for n in range(100)]))
s1.append(byte_rows("TurnText", codes("TURN")))

# composer: 12 character codes in str..str+11 -> text line at RBW+TXT (bank 3).
# Layout: pair column j at TXT + j*15; line k's 5 rows at + k*5.  Y = k*5.
cmp_ = ["; build one text line: str (12 char codes) -> bank 3, line offset in Y (k*5)",
        "Compose:", "        sty tline"]
for k in range(6):
    cmp_ += ["        ldx str+%d" % (2 * k)]
    for r in range(5):
        cmp_ += ["        lda FontHi+%d,x" % r, "        sta ct+%d" % r]
    cmp_ += ["        ldx str+%d" % (2 * k + 1), "        ldy tline"]
    for r in range(5):
        cmp_ += ["        lda FontLo+%d,x" % r, "        ora ct+%d" % r,
                 "        sta RBW+TXT+%d,y" % (k * 15 + r)]
cmp_.append("        rts")
s1.append("\n".join(cmp_))
with open("slice1_data.inc", "w") as f:
    f.write("\n".join(s1) + "\n")

if __name__ == "__main__":
    import json
    json.dump({"map": cells, "w": MAPW, "h": MAPH, "glyphs": GLYPHS, "chars": CHARS,
               "terrain": [t[0] for t in TERRAIN], "terrnames": [t[1] for t in TERRAIN],
               "unitnames": [s[1] for s in SYMBOLS], "move": [s[3] for s in SYMBOLS],
               "costs": [COSTS[s[0]] for s in SYMBOLS], "hq": hq,
               "base": [BASE[s[0]] for s in SYMBOLS], "range": [RANGE[s[0]] for s in SYMBOLS],
               "terrdef": TERRDEF, "maxhp": MAXHP,
               "units": [[upos[i], ukind[i]] for i in range(16)],
               "tilegfx": sum(terr_gfx, []) + sum(unit_gfx, []), "dots": DOTS},
              open("build_map.json", "w"))
    print("wrote fixed_data.inc, fixed_kern.inc, slice0_data.inc, slice1_data.inc, slice2_data.inc")
