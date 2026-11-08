"""Test helpers for Skirmish: load ROM + symbols, drive the joystick, read RAM."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu2600 import Emu, save_png, PALETTE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_syms(path):
    syms = {}
    for ln in open(path):
        parts = ln.split()
        if len(parts) == 2 and parts[1].startswith('$'):
            syms[parts[0]] = int(parts[1][1:], 16)
    return syms

class Game:
    def __init__(self, render=True):
        self.e = Emu(open(os.path.join(ROOT, 'skirmish.bin'), 'rb').read(), render=render, cart='E7')
        self.s = load_syms(os.path.join(ROOT, 'skirmish.sym'))
        self.lines = []
        self.mapinfo = json.load(open(os.path.join(ROOT, 'build_map.json')))

    def r(self, name, i=0):
        return self.e.ram[(self.s[name] + i) & 0x7F]

    def w(self, name, v, i=0):
        self.e.ram[(self.s[name] + i) & 0x7F] = v & 0xFF

    def frame(self, n=1):
        for _ in range(n):
            self.lines.append(self.e.run_frame())
        return self.lines[-1]

    def joy(self, up=False, down=False, left=False, right=False, fire=False):
        bits = (1 if up else 0) | (2 if down else 0) | (4 if left else 0) | (8 if right else 0)
        self.e.swcha = (self.e.swcha & 0x0F) | ((~bits & 15) << 4)
        self.e.inpt[4] = 0x00 if fire else 0x80

    def tap(self, hold=2, rest=3, **dirs):
        self.joy(**dirs); self.frame(hold)
        self.joy(); self.frame(rest)

    def shot(self, path, scale=2):
        save_png(self.e.frame, path, lines=self.e.frame_lines, scale=scale)

    # first visible line: the frame buffer row where VBLANK went off
    def visible(self):
        f = self.e.frame
        for ln, v in self.e.last_vblog:
            if v == 0:
                return f[ln:ln + 192]
        return f[40:232]
