"""Reference renderer: what the map window and text lines should show,
compared pixel by pixel with the emulator's frame."""
import numpy as np

MAP_TOP = 26            # visible line of the first map line
TXT_TOP = (9, 159, 173) # visible line of the first font row of text lines 0-2
WIN_X = 56              # first pixel of view column 0

CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:"

def game_state(g):
    """map cells and unit table, read from the cartridge RAM (bank 2)"""
    b2 = g.e.cart.rbanks[2]
    cells = list(b2[0:192])
    units = {}
    for slot in range(1, 16):
        k = b2[0xD0 + slot]
        if k != 0xFF:
            units[slot] = dict(pos=b2[0xC0 + slot], side=k >> 3, type=k & 3,
                               moved=b2[0xE0 + slot] & 1, hp=b2[0xE0 + slot] >> 4,
                               gfx=b2[0xF0 + slot])
    return cells, units

def ref_range(g, slot):
    """reference flood fill: {cell: moves left + 1} for the unit in slot"""
    import heapq
    mi = g.mapinfo
    cells, units = game_state(g)
    u = units[slot]
    cost = mi['costs'][u['type']]
    best = {u['pos']: mi['move'][u['type']] + 1}
    heap = [(-best[u['pos']], u['pos'])]
    while heap:
        nv, c = heapq.heappop(heap); v = -nv
        if best.get(c) != v:
            continue
        x, y = c % 16, c // 16
        for nx, ny in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
            if not (0 <= nx < 16 and 0 <= ny < 12):
                continue
            n = ny * 16 + nx
            k = cost[cells[n] & 15]
            if k == 0:
                continue
            s_ = cells[n] >> 4
            if s_ and units[s_]['side'] != u['side']:
                continue
            w = v - k
            if w >= 1 and w > best.get(n, 0):
                best[n] = w
                heapq.heappush(heap, (-w, n))
    return best

def expected_map(g):
    """48 x 128 boolean ink image of the view on screen"""
    mi = g.mapinfo
    tg = mi['tilegfx']
    cells, units = game_state(g)
    rng = ref_range(g, g.r('sel')) if g.r('showr') and g.r('sel') else {}
    dvx, dvy = g.r('dvx'), g.r('dvy')
    img = np.zeros((128, 48), dtype=bool)
    for r in range(8):
        for c in range(6):
            ci = (dvy + r) * 16 + dvx + c
            cell = cells[ci]
            u = cell >> 4
            if u:
                un = units[u]
                base = (16 + un['side'] * 8 + un['moved'] * 4 + un['type']) * 8
                dots = [0] * 8
            else:
                base = (cell & 15) * 8
                dots = mi['dots'] if ci in rng else [0] * 8
            for k in range(8):           # k = graphic row index, 7 = top
                b = tg[base + k] | dots[k]
                y = (r * 8 + (7 - k)) * 2
                for bit in range(8):
                    if b >> (7 - bit) & 1:
                        img[y:y + 2, c * 8 + bit] = True
    return img

def cursor_mask(g):
    """48 x 128 boolean: where the cursor bars should be (ignoring blink)"""
    m = np.zeros((128, 48), dtype=bool)
    sc = g.r('curx') - g.r('dvx'); sr = g.r('cury') - g.r('dvy')
    if 0 <= sc < 6 and 0 <= sr < 8:
        top = sr * 16
        m[top:top + 2, sc * 8:sc * 8 + 8] = True
        m[top + 14:top + 16, sc * 8:sc * 8 + 8] = True
    return m

def check_map(g, ink=0x00, border=0x42, bk=0xFC):
    v = g.visible()
    win = v[MAP_TOP:MAP_TOP + 128, WIN_X:WIN_X + 48]
    exp = expected_map(g)
    cur = cursor_mask(g)
    got_ink = win == (ink >> 1)
    got_cur = win == (border >> 1)
    got_bk = win == (bk >> 1)
    bad = []
    # outside the cursor: ink exactly where expected, background elsewhere
    ok_ink = (got_ink == exp) | cur
    ok_bk = (got_bk == ~exp) | cur
    if not ok_ink.all() or not ok_bk.all():
        ys, xs = np.nonzero(~(ok_ink & ok_bk))
        bad.append("map mismatch at %d pixels, first (line %d, x %d)" % (len(ys), ys[0], xs[0]))
    # cursor: all cursor or all not (blink)
    if cur.any():
        on = got_cur[cur]
        if on.any() and not on.all():
            bad.append("cursor partly drawn")
        if (got_cur & ~cur).any():
            bad.append("cursor colour outside the cursor")
    # borders: just outside the window
    if not (v[MAP_TOP:MAP_TOP + 128, WIN_X - 1] == border >> 1).all() or \
       not (v[MAP_TOP:MAP_TOP + 128, WIN_X + 48] == border >> 1).all():
        bad.append("border not adjacent to the window")
    return bad, (got_cur & cur).any()

def text_line(g, k):
    """decode text line k from the frame: 12 characters (3x5 glyphs, 4 px apart)"""
    GLYPHS = g.mapinfo['glyphs']
    v = g.visible()
    top = TXT_TOP[k]
    bg = v[top][0]
    s = ""
    for ch in range(12):
        x0 = WIN_X + ch * 4
        rows = []
        for r in range(5):
            line = v[top + r * 2]
            line2 = v[top + r * 2 + 1]
            bits = "".join('#' if line[x0 + i] != bg else '.' for i in range(3))
            bits2 = "".join('#' if line2[x0 + i] != bg else '.' for i in range(3))
            if bits != bits2:
                return None
            rows.append(bits)
        rows_ = rows
        match = [c for c in CHARS if GLYPHS[c] == rows]
        s += match[0] if match else '?'
    return s

def ref_damage(g, atype, ahp, dtype, dcell, cells):
    """the game's damage rule, written independently"""
    mi = g.mapinfo
    base = mi['base'][atype][dtype]
    d = 0 if base == 0 or ahp == 0 else max(1, (base * ahp + 5) // 10)
    d -= mi['terrdef'][cells[dcell] & 15]
    return max(1, d)

def ref_forecast(g, a, t):
    """(damage to target, damage back or 0) for slots a attacking t"""
    mi = g.mapinfo
    cells, units = game_state(g)
    A, T = units[a], units[t]
    dmg = ref_damage(g, A['type'], A['hp'], T['type'], T['pos'], cells)
    left = T['hp'] - dmg
    back = 0
    dist = abs(A['pos'] % 16 - T['pos'] % 16) + abs(A['pos'] // 16 - T['pos'] // 16)
    if left > 0 and mi['range'][T['type']] == dist:
        back = ref_damage(g, T['type'], left, A['type'], A['pos'], cells)
    return dmg, back

def ref_targets(g, a):
    cells, units = game_state(g)
    A = units[a]; rng = g.mapinfo['range'][A['type']]
    out = []
    for sl, u in sorted(units.items()):
        if u['side'] != A['side']:
            d = abs(A['pos'] % 16 - u['pos'] % 16) + abs(A['pos'] // 16 - u['pos'] // 16)
            if d == rng:
                out.append(sl)
    return out
