"""Random-input stress test: every frame must be 262 lines; report the
smallest timer slack at the end of vertical blank and overscan, the cost of
each work chunk, and how fast the view follows a scrolling cursor."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Game

def slack_run(frames=3000, seed=1):
    random.seed(seed)
    g = Game(render=False)
    e = g.e
    s = g.s
    vb_wait = s['Screen']            # first instruction: the INTIM wait
    os_wait = s['Main.os'] if 'Main.os' in s else None
    chunks = {s['BuildTile']: 'tile', s['TextChunk']: 'text', s['BfsChunk']: 'bfs'}
    VB = s['VBTIME'] * 64; OS = s['OSTIME'] * 64
    vmin = omin = 99999
    cost = {'tile': 0, 'text': 0, 'clear': 0, 'fill': 0}
    j = 0
    for f in range(frames):
        if f % 6 == 0:
            j = random.randrange(16) if random.random() < 0.8 else 0
            if random.random() < 0.3:
                j |= 16                  # fire: select / move / cancel
        g.joy(up=j & 1, down=j & 2, left=j & 4, right=j & 8, fire=(j & 16) and f % 6 < 2)
        if f % 400 == 399:
            e.swchb &= ~2                # Select: end the turn
        elif f % 400 == 2:
            e.swchb |= 2
        fr = e.frames
        seen_v = seen_o = False
        cur = None
        while e.frames == fr:
            pc = e.pc
            if pc in chunks and cur is None and e.sp >= 0xF0:
                kind = chunks[pc]
                if kind == 'bfs':
                    kind = 'fill' if g.r('bfs') == 3 else 'clear'
                cur = (kind, e.cycles, e.sp)
            if pc == vb_wait and not seen_v:
                vmin = min(vmin, VB - (e.cycles - e.tim_start)); seen_v = True
            if os_wait is not None and pc == os_wait and not seen_o:
                omin = min(omin, OS - (e.cycles - e.tim_start)); seen_o = True
            sp0 = e.sp
            e.step()
            if cur and e.sp == cur[2] + 2 and e.read(e.pc - 3) == 0x20:
                cost[cur[0]] = max(cost[cur[0]], e.cycles - cur[1]); cur = None
        g.lines.append(e.last_frame_lines)
    bad = [n for n in g.lines[2:] if n != 262]
    return vmin, omin, len(bad), cost

def scroll_rate():
    """hold right then down: how many frames until the screen shows each new origin"""
    g = Game(render=False)
    g.frame(5)
    waits = []
    for dirs in (dict(right=True), dict(down=True), dict(left=True), dict(up=True)):
        g.joy(**dirs)
        for _ in range(120):
            want = (g.r('vx'), g.r('vy'))
            n = 0
            while (g.r('dvx'), g.r('dvy')) != want and n < 30:
                g.frame(); n += 1
            if n: waits.append(n)
            g.frame()
        g.joy(); g.frame(20)
    return waits

if __name__ == '__main__':
    for seed in (1, 2, 3):
        vmin, omin, bad, cost = slack_run(seed=seed)
        print("seed %d: vblank spare %d cycles, overscan spare %d cycles, frames not 262: %d, "
              "worst chunk cost: tile %d, text %d, range clear %d, range step %d"
              % (seed, vmin, omin, bad, cost['tile'], cost['text'], cost['clear'], cost['fill']))
    w = scroll_rate()
    print("view catches up with the cursor in %d-%d frames (mean %.1f) over %d scroll steps"
          % (min(w), max(w), sum(w) / len(w), len(w)))
