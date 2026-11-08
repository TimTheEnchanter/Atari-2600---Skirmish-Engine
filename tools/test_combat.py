"""Milestone 3: attacking after a move, the forecast, damage and damage
back (against an independent Python version of the rules), terrain
defence, archers at range 2, waiting instead, destroying units, and both
ways to win (last enemy unit, enemy HQ).  Units are placed by writing the
cartridge's RAM (map nibble + unit table), then played with the joystick."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Game
import check
from test_turns import ok, FAILS, goto, settle, fire

def place(g, slot, x, y, hp=None):
    b2 = g.e.cart.rbanks[2]
    old = b2[0xC0 + slot]
    if b2[old] >> 4 == slot:
        b2[old] &= 0x0F
    c = y * 16 + x
    assert b2[c] >> 4 == 0, "cell taken"
    b2[c] = (b2[c] & 0x0F) | (slot << 4)
    b2[0xC0 + slot] = c
    if hp is not None:
        b2[0xE0 + slot] = (b2[0xE0 + slot] & 0x0F) | (hp << 4)
    g.w('need', 1)

def remove(g, slot):
    b2 = g.e.cart.rbanks[2]
    c = b2[0xC0 + slot]
    b2[c] &= 0x0F
    b2[0xD0 + slot] = 0xFF
    g.w('need', 1)

def slot_at(g, x, y):
    return g.e.cart.rbanks[2][y * 16 + x] >> 4

def new_game():
    g = Game(); g.frame(5); settle(g)
    return g

def move(g, frm, to):
    goto(g, *frm); settle(g); fire(g)
    goto(g, *to); settle(g); fire(g)

def forecast_text(f):
    return "HIT %d BACK %s" % (f[0], f[1] if f[1] else '-')

def run():
    # slots: P1 1 troop(2,3) 2 troop(2,5) 3 heavy(3,4) 4 archer(1,2) 5 rider(4,6) 6 archer(0,5)
    #        P2 7 troop(12,3) 8 troop(12,5) 9 archer(14,3) 10 heavy(15,4) 11 rider(14,6) 12 archer(11,2)
    print("melee attack with damage back")
    g = new_game()
    place(g, 7, 5, 5)                 # P2 troop onto plain at 06-06
    settle(g)
    move(g, (2, 5), (4, 5))           # P1 troop next to it
    ok(g.r('amode') == 1 and g.r('atgt') == 7, "after the move: choosing a target, cursor on the enemy")
    ok((g.r('curx'), g.r('cury')) == (5, 5), "cursor jumped to the target")
    f = check.ref_forecast(g, 2, 7)
    ok((g.r('fdmg'), g.r('fback')) == f, "forecast %s equals the reference" % (f,))
    ok(check.text_line(g, 2) == forecast_text(f), "bottom line shows %r" % forecast_text(f))
    ok(check.text_line(g, 1) == " TROOP HP 10", "middle line shows the target's HP")
    fire(g)
    cells, units = check.game_state(g)
    ok(units[7]['hp'] == 10 - f[0] and units[2]['hp'] == 10 - f[1],
       "HP after the fight: target %d, attacker %d" % (units[7]['hp'], units[2]['hp']))
    ok(g.r('amode') == 0 and (g.r('curx'), g.r('cury')) == (4, 5), "back to normal, cursor on the attacker")
    ok(check.text_line(g, 2) == " TROOP %2d --" % units[2]['hp'], "unit line shows the attacker's new HP")
    bad, _ = check.check_map(g)
    ok(not bad, "screen matches the reference")

    print("terrain defence")
    g = new_game()
    place(g, 7, 4, 3)                 # P2 troop into the forest at 05-04
    settle(g)
    move(g, (2, 5), (4, 4))           # P1 troop below it, on the road
    f = check.ref_forecast(g, 2, 7)
    ok(g.r('atgt') == 7 and (g.r('fdmg'), g.r('fback')) == f,
       "troop vs troop in forest: forecast %s (base 5, forest -1)" % (f,))
    ok(f[0] == 4, "forest takes 1 off the damage")

    print("archer at range 2: no damage back from melee")
    g = new_game()
    place(g, 8, 1, 7)                 # P2 troop two below the archer's target cell
    settle(g)
    move(g, (0, 5), (1, 5))           # archer to 02-06: the troop at 02-08 is 2 away
    ok(g.r('atgt') == 8, "archer targets the troop 2 cells away")
    f = check.ref_forecast(g, 6, 8)
    ok((g.r('fdmg'), g.r('fback')) == f and f[1] == 0, "forecast %s, nothing back" % (f,))
    ok(check.text_line(g, 2) == forecast_text(f), "bottom line shows %r" % forecast_text(f))
    fire(g)
    cells, units = check.game_state(g)
    ok(units[8]['hp'] == 10 - f[0] and units[6]['hp'] == 10, "only the troop is hurt")

    print("choosing between targets, and waiting")
    g = new_game()
    place(g, 7, 5, 5)
    place(g, 8, 4, 4)
    settle(g)
    move(g, (2, 5), (4, 5))           # enemies at 06-06 and 05-05
    tg = check.ref_targets(g, 2)
    seen = [g.r('atgt')]
    for _ in range(len(tg)):
        g.tap(right=True); settle(g)
        seen.append(g.r('atgt'))
    ok(seen == tg + [0], "joystick cycles the targets %s then WAIT: %s" % (tg, seen))
    ok(check.text_line(g, 2) == "    WAIT    ", "bottom line shows WAIT")
    ok((g.r('curx'), g.r('cury')) == (4, 5), "WAIT puts the cursor on the attacker")
    fire(g)
    cells, units = check.game_state(g)
    ok(units[7]['hp'] == 10 and units[8]['hp'] == 10 and units[2]['hp'] == 10 and g.r('amode') == 0,
       "fire on WAIT: nobody hurt")

    print("destroying a unit")
    g = new_game()
    place(g, 7, 5, 5, hp=2)
    settle(g)
    move(g, (2, 5), (4, 5))
    f = check.ref_forecast(g, 2, 7)
    ok(f[1] == 0 and check.text_line(g, 2) == "HIT %d BACK -" % f[0], "lethal forecast shows no damage back")
    fire(g)
    cells, units = check.game_state(g)
    ok(7 not in units and slot_at(g, 5, 5) == 0, "target removed from the unit table and the map")
    bad, _ = check.check_map(g)
    ok(not bad, "screen matches the reference (counter gone)")
    ok(g.r('over') == 0, "game goes on")

    print("damage back destroys the attacker")
    g = new_game()
    place(g, 10, 5, 5)                # P2 heavy
    place(g, 2, 2, 5, hp=1)           # P1 troop with 1 HP
    settle(g)
    move(g, (2, 5), (4, 5))
    f = check.ref_forecast(g, 2, 10)
    fire(g)
    cells, units = check.game_state(g)
    ok(2 not in units and slot_at(g, 4, 5) == 0 and units[10]['hp'] == 10 - f[0],
       "attacker destroyed by the damage back (forecast %s)" % (f,))

    print("winning: last enemy unit")
    g = new_game()
    for sl in (8, 9, 10, 11, 12):
        remove(g, sl)
    place(g, 7, 5, 5, hp=1)
    settle(g)
    move(g, (2, 5), (4, 5))
    fire(g)
    ok(g.r('over') == 1, "P1 wins")
    ok(check.text_line(g, 0) == "  P1  WINS  ", "top line shows P1 WINS")
    sl = slot_at(g, 2, 3)
    goto(g, 2, 3); settle(g); fire(g)
    ok(g.r('sel') == 0 and g.r('turn') == 1, "no more moves after the win; fire restarts")
    settle(g); g.frame(10); settle(g)
    cells, units = check.game_state(g)
    ok(g.r('over') == 0 and len(units) == 12 and g.r('side') == 0, "new game: 12 units, P1 to play")

    print("winning: enemy HQ")
    g = new_game()
    place(g, 5, 12, 4)                # P1 rider next to P2's HQ at 14-05
    settle(g)
    move(g, (12, 4), (13, 4))
    ok(g.r('over') == 1 and check.text_line(g, 0) == "  P1  WINS  ", "rider on P2's HQ: P1 wins")

    print("random fights against the reference")
    random.seed(7)
    good = total = 0
    for i in range(30):
        g = new_game() if i % 6 == 0 else g
        if g.r('over'):
            g = new_game()
        cells, units = check.game_state(g)
        side = g.r('side')
        mine = [s_ for s_, u in units.items() if u['side'] == side and not u['moved']]
        foes = [s_ for s_, u in units.items() if u['side'] != side]
        if not mine or not foes:
            g.e.swchb &= ~2; g.frame(3); g.e.swchb |= 2; settle(g); continue
        a = random.choice(mine); t = random.choice(foes)
        A = units[a]
        rng = g.mapinfo['range'][A['type']]
        # put the target at range from a cell next to the attacker it can reach
        g.tap(); settle(g)
        for _ in range(20):
            tx, ty = A['pos'] % 16 + random.randint(-2, 2), A['pos'] // 16 + random.randint(-2, 2)
            if 0 <= tx < 16 and 0 <= ty < 12 and slot_at(g, tx, ty) == 0 and \
               abs(tx - A['pos'] % 16) + abs(ty - A['pos'] // 16) == rng and \
               g.mapinfo['costs'][units[t]['type']][cells[ty * 16 + tx] & 15]:
                break
        else:
            continue
        place(g, t, tx, ty, hp=random.randint(1, 10))
        place(g, a, A['pos'] % 16, A['pos'] // 16, hp=random.randint(1, 10))
        settle(g)
        goto(g, A['pos'] % 16, A['pos'] // 16); settle(g); fire(g)
        fire(g)                       # wait in place, then pick this target
        n = 0
        while g.r('amode') and g.r('atgt') != t and n < 10:
            g.tap(right=True); settle(g); n += 1
        if g.r('atgt') != t:
            continue
        f = check.ref_forecast(g, a, t)
        before = check.game_state(g)[1]
        fire(g)
        after = check.game_state(g)[1]
        hp_t = after[t]['hp'] if t in after else 0
        hp_a = after[a]['hp'] if a in after else 0
        exp_t = max(0, before[t]['hp'] - f[0])
        exp_a = before[a]['hp'] - f[1] if exp_t else before[a]['hp']
        exp_a = max(0, exp_a)
        total += 1
        good += (g.r('fdmg'), g.r('fback')) == f and (hp_t, hp_a) == (exp_t, exp_a)
    ok(total >= 15 and good == total, "%d/%d random fights match the reference" % (good, total))

GAMES = []
_new = new_game
def new_game():
    g = _new(); GAMES.append(g)
    return g

if __name__ == '__main__':
    run()
    bad = sum(1 for g in GAMES for n in g.lines[2:] if n != 262)
    ok(bad == 0, "every frame 262 lines (%d frames)" % sum(len(g.lines) for g in GAMES))
    print("FAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
