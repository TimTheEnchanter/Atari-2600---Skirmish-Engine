"""Screenshots: start, a rider's movement range, units that have moved,
P2's turn, the rider's range with an enemy beside it (from test_turns), and
an animated GIF of selecting and moving a unit."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Game, PALETTE
from PIL import Image
import test_turns as T

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shots')

def img(g, scale=3):
    v = g.visible()
    im = Image.fromarray(PALETTE[v], 'RGB')
    return im.resize((160 * scale * 2, 192 * scale), Image.NEAREST)

def lit(g):
    while (g.r('frame') + 1) & 0x18 == 0:
        g.frame()
    g.frame()

g = Game(); g.frame(5); T.settle(g); lit(g)
img(g).save(os.path.join(OUT, 'start.png'))
T.goto(g, 4, 6); T.settle(g); T.fire(g); lit(g)
img(g).save(os.path.join(OUT, 'rider_range.png'))
T.goto(g, 7, 7); T.settle(g); T.fire(g)           # rider moves down the road
T.goto(g, 2, 5); T.settle(g); T.fire(g)
T.goto(g, 3, 6); T.settle(g); T.fire(g)           # troop moves
T.goto(g, 3, 4); T.settle(g); T.fire(g); T.fire(g)  # heavy waits
T.goto(g, 2, 3); T.settle(g); lit(g)
img(g).save(os.path.join(OUT, 'moved.png'))
g.e.swchb &= ~2; g.frame(3); g.e.swchb |= 2; T.settle(g)
T.goto(g, 12, 5); T.settle(g); T.fire(g); lit(g)
img(g).save(os.path.join(OUT, 'p2_turn.png'))

# gif: select the archer at (1,2), show the range, move it to (2,1)... (3,2)
g = Game(); g.frame(5); T.settle(g)
frames = []
def rec(n):
    for i in range(n):
        g.frame()
        if i % 2 == 0:
            frames.append(img(g, 2))
def go(x, y):
    while (g.r('curx'), g.r('cury')) != (x, y):
        cx, cy = g.r('curx'), g.r('cury')
        g.joy(left=x < cx, right=x > cx, up=y < cy, down=y > cy); rec(3)
        g.joy(); rec(5)
rec(20); go(4, 6); rec(10)
g.joy(fire=True); rec(4); g.joy(); rec(30)
go(7, 8); rec(10)
g.joy(fire=True); rec(4); g.joy(); rec(30)
frames[0].save(os.path.join(OUT, 'turn.gif'), save_all=True, append_images=frames[1:], duration=33, loop=0)
# combat: forecast, result, a win, and a GIF of a fight
from test_combat import place, remove
g = Game(); g.frame(5); T.settle(g)
place(g, 7, 5, 5); place(g, 8, 4, 4); T.settle(g)
frames = []
def rec2(n):
    for i in range(n):
        g.frame()
        if i % 2 == 0:
            frames.append(img(g, 2))
def go2(x, y):
    while (g.r('curx'), g.r('cury')) != (x, y):
        cx, cy = g.r('curx'), g.r('cury')
        g.joy(left=x < cx, right=x > cx, up=y < cy, down=y > cy); rec2(3)
        g.joy(); rec2(5)
rec2(10); go2(2, 5); g.joy(fire=True); rec2(4); g.joy(); rec2(20)
go2(4, 5); g.joy(fire=True); rec2(4); g.joy(); rec2(40)
img(g).save(os.path.join(OUT, 'forecast.png'))
for _ in range(3):                    # second target, WAIT, back to the first
    g.joy(right=True); rec2(3); g.joy(); rec2(30)
g.joy(fire=True); rec2(4); g.joy(); rec2(40)
lit(g); img(g).save(os.path.join(OUT, 'after_fight.png'))
frames[0].save(os.path.join(OUT, 'fight.gif'), save_all=True, append_images=frames[1:], duration=33, loop=0)
g = Game(); g.frame(5); T.settle(g)
for sl in (8, 9, 10, 11, 12):
    remove(g, sl)
place(g, 7, 5, 5, hp=1); T.settle(g)
T.goto(g, 2, 5); T.settle(g); T.fire(g); T.goto(g, 4, 5); T.settle(g); T.fire(g); T.fire(g)
g.frame(20); img(g).save(os.path.join(OUT, 'win.png'))

for f in ('corner.png', 'p2_soldier.png', 'scroll.gif'):
    p = os.path.join(OUT, f)
    if os.path.exists(p): os.remove(p)
print(sorted(os.listdir(OUT)))
