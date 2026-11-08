"""Milestone 2 rules: selecting, the movement range, moving, waiting,
cancelling, refusing bad selections, ending turns (by Select and
automatically), and a full scripted hot-seat round.  Every check of the
screen is pixel-exact against tools/check.py's reference rendering."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Game
import check

FAILS = []
def ok(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        FAILS.append(what)

def goto(g, x, y):
    for _ in range(60):
        cx, cy = g.r('curx'), g.r('cury')
        if (cx, cy) == (x, y):
            return
        g.tap(left=x < cx, right=x > cx, up=y < cy, down=y > cy)
    raise RuntimeError("cursor stuck")

def settle(g):
    for _ in range(60):
        g.frame()
        if g.r('bfs') == 0 and g.r('bt') == 0xFF and g.r('need') == 0 and g.r('ready') == 0 \
           and g.r('txtreq') == 0 and (g.r('dvx'), g.r('dvy')) == (g.r('vx'), g.r('vy')):
            break
    g.frame(2)

def screen_ok(g, what):
    bad, _ = check.check_map(g)
    ok(not bad, what + " (screen matches reference)" + ("" if not bad else ": %s" % bad))

def fire(g):
    g.tap(fire=True)
    settle(g)

def unit_at(g, x, y):
    cells, units = check.game_state(g)
    return cells[y * 16 + x] >> 4

def dist_ok(g):
    ref = check.ref_range(g, g.r('sel'))
    d = g.e.cart.rbanks[0]
    got = {c: d[c] for c in range(192) if d[c]}
    return got == ref, len(ref)

def run():
    g = Game()
    g.frame(5); settle(g)
    print("start")
    ok(g.r('side') == 0 and g.r('turn') == 1, "P1 to play, turn 1")
    ok((g.r('curx'), g.r('cury')) == (1, 4), "cursor on P1's HQ")

    print("select and move")
    goto(g, 2, 5); settle(g)
    ok(check.text_line(g, 2) == " TROOP 10 P1", "unit line shows TROOP 10 P1")
    fire(g)
    s = g.r('sel')
    ok(s == unit_at(g, 2, 5) and s != 0, "fire selects the troop")
    ok(g.r('showr') == 1, "range computed")
    m, n = dist_ok(g)
    ok(m, "flood fill equals the reference (%d cells)" % n)
    ok(check.text_line(g, 2) == " TROOP 10 GO", "unit line shows GO")
    screen_ok(g, "range dots drawn")
    goto(g, 4, 5); settle(g)
    fire(g)
    ok(unit_at(g, 4, 5) == s and unit_at(g, 2, 5) == 0, "troop moved to 05-06")
    ok(g.r('sel') == 0 and g.r('showr') == 0, "selection cleared")
    cells, units = check.game_state(g)
    ok(units[s]['moved'] == 1 and units[s]['pos'] == 5 * 16 + 4, "unit table updated")
    ok(units[s]['gfx'] == 0x80 + (0 * 8 + 4 + 0) * 8, "counter switched to the moved style")
    ok(check.text_line(g, 2) == " TROOP 10 --", "unit line shows --")
    screen_ok(g, "moved troop drawn faded, no dots")
    fire(g)
    ok(g.r('sel') == 0, "a moved unit can't be selected again")

    print("refusals and cancel")
    goto(g, 12, 3); settle(g)
    fire(g)
    ok(g.r('sel') == 0, "can't select a P2 unit on P1's turn")
    goto(g, 5, 5); settle(g)
    fire(g)
    ok(g.r('sel') == 0, "fire on an empty cell does nothing")
    goto(g, 3, 4); settle(g)          # heavy
    fire(g)
    hv = g.r('sel')
    ok(hv != 0, "heavy selected")
    m, n = dist_ok(g)
    ok(m, "heavy's range equals the reference (%d cells; forests closed to it)" % n)
    rng = check.ref_range(g, hv)
    ok(all((check.game_state(g)[0][c] & 15) != 1 for c in rng), "no forest in the heavy's range")
    goto(g, 10, 10); settle(g)
    fire(g)
    ok(g.r('sel') == 0 and unit_at(g, 3, 4) == hv, "fire out of reach cancels; heavy stays")
    screen_ok(g, "dots gone after cancel")
    goto(g, 3, 4); settle(g)
    fire(g)
    goto(g, 2, 3); settle(g)          # another P1 unit's cell
    fire(g)
    ok(g.r('sel') == 0 and unit_at(g, 3, 4) == hv, "fire on another unit cancels")
    goto(g, 3, 4); settle(g)
    fire(g); fire(g)                  # select, then fire on itself = wait
    cells, units = check.game_state(g)
    ok(units[hv]['moved'] == 1 and unit_at(g, 3, 4) == hv, "fire on its own cell: waits in place")

    print("enemy units block movement")
    g2 = Game(); g2.frame(5); settle(g2)
    # put a P2 troop next to P1's rider at (4,6) by editing the map: slot 7 to (5,6)
    b2 = g2.e.cart.rbanks[2]
    old = b2[0xC0 + 7]
    b2[old] &= 0x0F
    b2[6 * 16 + 5] = (b2[6 * 16 + 5] & 0x0F) | (7 << 4)
    b2[0xC0 + 7] = 6 * 16 + 5
    g2.w('need', 1)
    goto(g2, 4, 6); settle(g2); fire(g2)
    m, n = dist_ok(g2)
    ok(m, "rider's range with an enemy beside it equals the reference (%d cells)" % n)
    ok((6 * 16 + 5) not in check.ref_range(g2, g2.r('sel')), "enemy cell not in range")
    screen_ok(g2, "rider's range drawn")
    g2.shot(os.path.join(check_dir(), 'rider_blocked.png'), scale=3)

    print("ending turns")
    g.e.swchb &= ~2; g.frame(3); g.e.swchb |= 2; settle(g)
    ok(g.r('side') == 1 and g.r('turn') == 1, "Select ends P1's turn: P2 to play, still turn 1")
    ok((g.r('curx'), g.r('cury')) == (13, 4), "cursor jumps to P2's HQ")
    ok(check.text_line(g, 0) == "P2   TURN 01", "top line shows P2")
    cells, units = check.game_state(g)
    ok(all(u['moved'] == 0 for u in units.values()), "moved flags cleared")
    screen_ok(g, "P2's view after the turn change")
    # P2 moves every unit: each one waits in place -> the turn passes automatically
    p2 = [(sl, u) for sl, u in units.items() if u['side'] == 1]
    for i, (sl, u) in enumerate(p2):
        goto(g, u['pos'] % 16, u['pos'] // 16); settle(g)
        fire(g); fire(g)
        if i < len(p2) - 1:
            ok(g.r('side') == 1, "P2 unit %d done, still P2's turn" % (i + 1))
    ok(g.r('side') == 0 and g.r('turn') == 2, "after P2's last unit: P1 to play, turn 2")
    ok(check.text_line(g, 0) == "P1   TURN 02", "top line shows turn 02")

    print("reset")
    g.e.swchb &= ~1; g.frame(3); g.e.swchb |= 1; g.frame(5); settle(g)
    cells, units = check.game_state(g)
    ok(g.r('turn') == 1 and g.r('side') == 0 and unit_at(g, 4, 5) == 0 and unit_at(g, 2, 5) != 0,
       "Reset restarts the game")

    bad = [n for n in g.lines[2:] if n != 262] + [n for n in g2.lines[2:] if n != 262]
    ok(not bad, "every frame 262 lines (%d frames)" % (len(g.lines) + len(g2.lines)))
    ok(not g.e.cart.bad and not g2.e.cart.bad, "no writes to ROM or reads of write ports")

def check_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shots')

def random_ranges(n=40, seed=5):
    """select random units after random moves and compare each range"""
    print("random ranges")
    random.seed(seed)
    g = Game(render=False)
    g.frame(5); settle(g)
    good = 0; total = 0; qmax = 0
    for i in range(n):
        cells, units = check.game_state(g)
        mine = [(sl, u) for sl, u in units.items() if u['side'] == g.r('side') and not u['moved']]
        if not mine:
            g.e.swchb &= ~2; g.frame(3); g.e.swchb |= 2; settle(g); continue
        sl, u = random.choice(mine)
        goto(g, u['pos'] % 16, u['pos'] // 16); settle(g)
        g.tap(fire=True)
        # watch the queue length while the fill runs
        for _ in range(30):
            q = (g.r('qtail') - g.r('qhead')) & 63
            qmax = max(qmax, q)
            g.frame()
            if g.r('bfs') == 0:
                break
        settle(g)
        m, _ = dist_ok(g); total += 1; good += m
        rng = [c for c in check.ref_range(g, sl) if not (cells[c] >> 4) or c == u['pos']]
        c = random.choice(rng)
        goto(g, c % 16, c // 16); settle(g)
        fire(g)
        while g.r('amode'):           # next to an enemy: attack the first target
            fire(g)
        if g.r('over'):
            break
    ok(good == total, "%d/%d random ranges equal the reference" % (good, total))
    ok(qmax < 48, "flood fill queue never above %d of 64 entries (frame samples)" % qmax)

if __name__ == '__main__':
    run()
    random_ranges()
    print("FAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
