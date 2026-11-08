"""Walk the cursor over every map cell.  At each one, once the view has
settled, compare the map window pixel by pixel with a reference rendering
of the map, and decode the three text lines from the screen."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Game
import check

def expected_text(g):
    mi = g.mapinfo
    x, y = g.r('curx'), g.r('cury')
    cells, units = check.game_state(g)
    cell = cells[y * 16 + x]
    l1 = mi['terrnames'][cell & 15] + " %02d-%02d" % (x + 1, y + 1)
    sl = cell >> 4
    if sl:
        u = units[sl]
        st = "GO" if sl == g.r('sel') else "--" if u['moved'] else "P%d" % (1 + u['side'])
        l2 = mi['unitnames'][u['type']] + " %2d " % u['hp'] + st
    else:
        l2 = " " * 12
    return ["P%d   TURN %02d" % (1 + g.r('side'), g.r('turn')), l1, l2]

def settle(g):
    for _ in range(40):
        g.frame()
        if (g.r('dvx'), g.r('dvy')) == (g.r('vx'), g.r('vy')) and g.r('bt') == 0xFF \
           and g.r('txtreq') == 0:
            break
    # make sure the cursor is in its visible blink phase
    while (g.r('frame') + 1) & 0x18 == 0:
        g.frame()
    g.frame()

def run():
    g = Game()
    g.frame(5)
    fails = 0; checked = 0; cursor_seen = 0
    # go to the top left corner
    for _ in range(20):
        g.tap(left=True, up=True)
    path = []
    for y in range(12):
        xs = range(16) if y % 2 == 0 else range(15, -1, -1)
        path += [(x, y) for x in xs]
    for (tx, ty) in path:
        while (g.r('curx'), g.r('cury')) != (tx, ty):
            cx, cy = g.r('curx'), g.r('cury')
            g.tap(left=tx < cx, right=tx > cx, up=ty < cy, down=ty > cy)
        settle(g)
        bad, on = check.check_map(g)
        txt = [check.text_line(g, k) for k in range(3)]
        exp = expected_text(g)
        if txt != exp:
            bad.append("text %r, expected %r" % (txt, exp))
        if not on:
            bad.append("cursor not drawn")
        sx, sy = tx - g.r('dvx'), ty - g.r('dvy')
        if not (0 < sx < 5 or g.r('dvx') in (0, 10)) or not (0 < sy < 7 or g.r('dvy') in (0, 4)):
            bad.append("cursor at screen %d,%d without scrolling" % (sx, sy))
        checked += 1
        if bad:
            fails += 1
            if fails < 10:
                print("cell", tx, ty, "view", g.r('dvx'), g.r('dvy'), bad)
    bad_lines = [n for n in g.lines[2:] if n != 262]
    print("cells checked %d, failures %d, frames %d, frames not 262: %d"
          % (checked, fails, len(g.lines), len(bad_lines)))
    return fails == 0 and not bad_lines

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
