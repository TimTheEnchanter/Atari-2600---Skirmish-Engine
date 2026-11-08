#!/usr/bin/env python3
"""Compact Atari 2600 emulator for testing: 6502 (with decimal mode),
TIA (playfield, players, missiles, ball, collisions, HMOVE, VDEL, sizes),
RIOT (RAM, timer, ports), 2K/4K/F8/F8SC/F6SC and E7 (M-Network) carts.

Rendering is optional (render=False skips pixel work; collisions are then
not computed).  Frames are 160 x up to 262 lines of palette indices.
"""
import numpy as np

# ---------------------------------------------------------------- palette
def make_palette():
    import colorsys
    hues = [0, 52, 38, 24, 5, 330, 295, 255, 228, 210, 190, 165, 130, 95, 72, 45]
    pal = []
    for c in range(128):
        hue = c >> 3; lum = c & 7
        v = 0.12 + lum / 7.0 * 0.86
        if hue == 0:
            r = g = b = v
        else:
            r, g, b = colorsys.hsv_to_rgb(hues[hue] / 360.0, 0.75 - lum * 0.06, v)
        pal.append((int(r * 255), int(g * 255), int(b * 255)))
    return np.array(pal, dtype=np.uint8)
PALETTE = make_palette()

# ---------------------------------------------------------------- CPU tables
# (mode, cycles) per opcode; extra cycle on page cross for reads marked 'p'
IMP, ACC, IMM, ZP, ZPX, ZPY, ABS, ABX, ABY, IND, IZX, IZY, REL = range(13)

class Cart:
    def __init__(self, data, kind=None):
        self.data = bytes(data)
        n = len(data)
        self.kind = kind or {2048: '2K', 4096: '4K', 8192: 'F8', 16384: 'F6'}.get(n)
        if self.kind is None:
            raise ValueError("unsupported ROM size %d" % n)
        self.bank = {'F8': 1, 'F6': 3}.get(self.kind, 0)   # power-up bank (last)
        self.sc = False
        self.scram = bytearray(128)
        # E7: lower slot = ROM slice 0-6 or 1K RAM; 256-byte RAM bank 0-3
        self.slice = 0
        self.ram1k_on = False
        self.ram1k = bytearray(1024)
        self.rbank = 0
        self.rbanks = [bytearray(256) for _ in range(4)]
        self.bad = []                  # E7: writes to ROM / reads of write ports

    def access(self, a):
        if self.kind == 'E7':
            if 0x1FE0 <= a <= 0x1FE6: self.slice = a - 0x1FE0; self.ram1k_on = False
            elif a == 0x1FE7: self.ram1k_on = True
            elif 0x1FE8 <= a <= 0x1FEB: self.rbank = a - 0x1FE8
            return
        if self.kind == 'F8':
            if a == 0x1FF8: self.bank = 0
            elif a == 0x1FF9: self.bank = 1
        elif self.kind == 'F6':
            if 0x1FF6 <= a <= 0x1FF9: self.bank = a - 0x1FF6

    def read_e7(self, a):
        o = a & 0xFFF
        if o < 0x800:
            if self.ram1k_on:
                if o >= 0x400: return self.ram1k[o - 0x400]
                if len(self.bad) < 50: self.bad.append(('read1k-wport', a))
                return self.ram1k[o]
            return self.data[self.slice * 2048 + o]
        if o < 0xA00:
            if o >= 0x900: return self.rbanks[self.rbank][o - 0x900]
            if len(self.bad) < 50: self.bad.append(('readbank-wport', a))
            return self.rbanks[self.rbank][o - 0x800]
        return self.data[7 * 2048 + (o - 0x800)]

    def read(self, a):
        a &= 0x1FFF
        if self.kind == 'E7':
            v = self.read_e7(a)
            self.access(a)
            return v
        self.access(a)
        if self.sc and 0x1080 <= a < 0x1100:
            return self.scram[a - 0x1080]
        if self.kind == '2K':
            return self.data[a & 0x7FF]
        if self.kind == '4K':
            return self.data[a & 0xFFF]
        return self.data[self.bank * 4096 + (a & 0xFFF)]

    def write(self, a, v):
        a &= 0x1FFF
        self.access(a)
        if self.kind == 'E7':
            o = a & 0xFFF
            if o < 0x400 and self.ram1k_on: self.ram1k[o] = v
            elif 0x800 <= o < 0x900: self.rbanks[self.rbank][o - 0x800] = v
            elif o < 0xFE0 and len(self.bad) < 50: self.bad.append(('write-rom', a))
            return
        if self.sc and 0x1000 <= a < 0x1080:
            self.scram[a - 0x1000] = v

class Emu:
    def __init__(self, rom, render=True, superchip=None, cart=None):
        self.cart = Cart(rom, cart)
        if superchip is None:
            superchip = (self.cart.kind in ('F8', 'F6'))
        if self.cart.kind == 'E7': superchip = False
        self.cart.sc = superchip
        self.ram = bytearray(128)
        self.render = render
        # cpu
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.flags = 0x24  # N V - B D I Z C
        self.cycles = 0
        # tia
        self.reg = [0] * 64
        self.line = 0
        self.clk0 = 0          # cpu cycle at start of current line (in color clocks*?)
        self.lineclk = 0       # color clock position in line 0..227
        self.drawn = 0         # color clock already rendered on this line
        self.pos = [0, 0, 0, 0, 0]  # P0 P1 M0 M1 BL
        self.grp_new = [0, 0]; self.grp_old = [0, 0]
        self.enabl_new = 0; self.enabl_old = 0
        self.cx = 0
        self.frame_buf = np.zeros((262, 160), dtype=np.uint8)
        self.frame = None
        self.frame_lines = 0
        self.frames = 0
        self.hmove_blank = False
        self.vsync_on = False
        self.lines_this_frame = 0
        self.last_frame_lines = 0
        self.dirty = True
        self.vblog = []; self.last_vblog = []
        # riot
        self.swcha = 0xFF
        self.swchb = 0x0B   # color, no reset/select, diff B
        self.inpt = [0x80] * 6
        self.tim_val = 0; self.tim_int = 1024; self.tim_start = 0
        self.timint_flag = 0
        self.swacnt = 0; self.swbcnt = 0
        self.audio_log = []
        self.reset()

    # -------------------------------------------------------- memory
    def read(self, a):
        a &= 0x1FFF
        if a & 0x1000:
            return self.cart.read(a)
        if a & 0x80 == 0:
            return self.tia_read(a & 0x0F)
        if a & 0x200 == 0:
            return self.ram[a & 0x7F]
        return self.riot_read(a)

    def write(self, a, v):
        a &= 0x1FFF
        if a & 0x1000:
            self.cart.write(a, v); return
        if a & 0x80 == 0:
            self.tia_write(a & 0x3F, v); return
        if a & 0x200 == 0:
            self.ram[a & 0x7F] = v; return
        self.riot_write(a, v)

    def reset(self):
        lo = self.read(0xFFFC); hi = self.read(0xFFFD)
        self.pc = lo | (hi << 8)

    # -------------------------------------------------------- RIOT
    def timer_read(self):
        t = self.cycles - self.tim_start
        n = self.tim_val
        I = self.tim_int
        if t < 1:
            return n
        ndec = (t - 1) // I + 1
        if ndec <= n:
            return n - ndec
        t0 = (n - 1) * I + 1 if n > 0 else 0
        under = t0 + I
        if t < under:
            return 0
        self.timint_flag = 0x80
        return (0xFF - (t - under)) & 0xFF

    def riot_read(self, a):
        r = a & 0x17
        if a & 0x04 == 0:
            r = a & 0x03
            if r == 0: return self.swcha
            if r == 1: return self.swacnt
            if r == 2: return self.swchb
            return self.swbcnt
        if a & 1 == 0:
            return self.timer_read()
        self.timer_read()
        return self.timint_flag

    def riot_write(self, a, v):
        if a & 0x14 == 0x14:
            self.tim_val = v
            self.tim_int = [1, 8, 64, 1024][a & 3]
            self.tim_start = self.cycles
            self.timint_flag = 0
        elif a & 0x04 == 0:
            r = a & 3
            if r == 1: self.swacnt = v
            if r == 3: self.swbcnt = v

    # -------------------------------------------------------- TIA
    def tia_read(self, r):
        if r < 8:
            self.catch_up()
            v = 0
            bits = self.cx
            # each read register has two bits (7,6)
            v = ((bits >> (r * 2)) & 3) << 6
            return v
        if r < 14:
            return self.inpt[r - 8]
        return 0

    def cur_clock(self):
        return (self.cycles * 3 - self.clk0)

    def catch_up(self):
        c = self.cur_clock()
        while c >= 228:
            self.render_to(228)
            self.end_line()
            c = self.cur_clock()
        self.render_to(c)

    def end_line(self):
        self.clk0 += 228
        self.line += 1
        self.lines_this_frame += 1
        self.drawn = 0
        self.hmove_blank = False

    def obj_masks(self):
        if not self.dirty:
            return self.masks
        R = self.reg
        x = np.arange(160)
        # playfield
        pf = np.zeros(40, dtype=bool)
        pf0, pf1, pf2 = R[0x0D], R[0x0E], R[0x0F]
        bits = []
        for b in range(4, 8): bits.append((pf0 >> b) & 1)
        for b in range(7, -1, -1): bits.append((pf1 >> b) & 1)
        for b in range(0, 8): bits.append((pf2 >> b) & 1)
        left = np.array(bits, dtype=bool)
        right = left[::-1] if R[0x0A] & 1 else left
        pfm = np.repeat(np.concatenate([left, right]), 4)

        def player(i):
            nus = R[0x04 + i] & 7
            vdel = R[0x25 + i] & 1
            g = self.grp_old[i] if vdel else self.grp_new[i]
            if R[0x0B + i] & 8:
                g = int('{:08b}'.format(g)[::-1], 2)
            m = np.zeros(160, dtype=bool)
            if g == 0:
                return m
            copies = {0: [0], 1: [0, 16], 2: [0, 32], 3: [0, 16, 32], 4: [0, 64],
                      5: [0], 6: [0, 32, 64], 7: [0]}[nus]
            s = 2 if nus == 5 else 4 if nus == 7 else 1
            p = self.pos[i]
            for off in copies:
                for k in range(8 * s):
                    if (g >> (7 - k // s)) & 1:
                        m[(p + off + k) % 160] = True
            return m

        def missile(i):
            m = np.zeros(160, dtype=bool)
            if not (R[0x1D + i] & 2) or (R[0x28 + i] & 2):
                return m
            nus = R[0x04 + i]
            w = 1 << ((nus >> 4) & 3)
            copies = {0: [0], 1: [0, 16], 2: [0, 32], 3: [0, 16, 32], 4: [0, 64],
                      5: [0], 6: [0, 32, 64], 7: [0]}[nus & 7]
            p = self.pos[2 + i]
            for off in copies:
                for k in range(w):
                    m[(p + off + k) % 160] = True
            return m

        bl = np.zeros(160, dtype=bool)
        en = self.enabl_old if R[0x27] & 1 else self.enabl_new
        if en & 2:
            w = 1 << ((R[0x0A] >> 4) & 3)
            for k in range(w):
                bl[(self.pos[4] + k) % 160] = True
        self.masks = (pfm, player(0), player(1), missile(0), missile(1), bl)
        self.dirty = False
        return self.masks

    def render_to(self, c):
        if c <= self.drawn:
            return
        a, b = self.drawn, min(c, 228)
        self.drawn = b
        if not self.render:
            return
        if b <= 68:
            return
        a = max(a, 68)
        xa, xb = a - 68, b - 68
        if self.lines_this_frame >= 262:
            return
        pfm, p0, p1, m0, m1, bl = self.obj_masks()
        sl = slice(xa, xb)
        # collisions
        P0, P1, M0, M1, BL, PF = p0[sl], p1[sl], m0[sl], m1[sl], bl[sl], pfm[sl]
        def any_(u, v): return bool(np.any(u & v))
        cx = self.cx
        # register bit layout: reg r bits 7,6 -> self.cx bit (2r+1, 2r)
        pairs = [(M0, P1, 1), (M0, P0, 0), (M1, P0, 3), (M1, P1, 2),
                 (P0, PF, 5), (P0, BL, 4), (P1, PF, 7), (P1, BL, 6),
                 (M0, PF, 9), (M0, BL, 8), (M1, PF, 11), (M1, BL, 10),
                 (BL, PF, 13), (P0, P1, 15), (M0, M1, 14)]
        for u, v, bit in pairs:
            if not (cx >> bit) & 1 and any_(u, v):
                cx |= 1 << bit
        self.cx = cx
        # colours
        R = self.reg
        if self.reg[0x01] & 2:
            self.frame_buf[self.lines_this_frame, xa:xb] = 0
            return
        bk, cpf, c0, c1 = R[0x09] >> 1, R[0x08] >> 1, R[0x06] >> 1, R[0x07] >> 1
        out = np.full(xb - xa, bk, dtype=np.uint8)
        ctrl = R[0x0A]
        if ctrl & 2:  # score mode
            xs = np.arange(xa, xb)
            pfc = np.where(xs < 80, c0, c1)
        else:
            pfc = cpf
        pfb = PF | BL
        if ctrl & 4:
            out = np.where(P1 | M1, c1, out)
            out = np.where(P0 | M0, c0, out)
            out = np.where(pfb, np.where(BL, cpf, pfc) if ctrl & 2 else cpf, out)
        else:
            out = np.where(PF, pfc, out)
            out = np.where(BL, cpf, out)
            out = np.where(P1 | M1, c1, out)
            out = np.where(P0 | M0, c0, out)
        if self.hmove_blank and xa < 8:
            out[:max(0, min(8, xb) - xa)] = 0
        self.frame_buf[self.lines_this_frame, xa:xb] = out

    def tia_write(self, r, v):
        self.catch_up()
        R = self.reg
        c = self.cur_clock()
        if r == 0x01:
            self.vblog.append((self.lines_this_frame, v & 2))
        if r == 0x00:  # VSYNC
            if v & 2 and not self.vsync_on:
                self.new_frame()
            self.vsync_on = bool(v & 2)
        elif r == 0x02:  # WSYNC
            if c > 0:
                rest = 228 - c
                self.cycles += (rest + 2) // 3
                self.catch_up()
            return
        elif r == 0x1B:
            self.grp_new[0] = v; self.grp_old[1] = self.grp_new[1]
        elif r == 0x1C:
            self.grp_new[1] = v; self.grp_old[0] = self.grp_new[0]
            self.enabl_old = self.enabl_new
        elif r == 0x1F:
            self.enabl_new = v
        elif 0x10 <= r <= 0x14:
            obj = r - 0x10
            if c < 68:
                p = 3 if obj < 2 else 2
            else:
                p = c - 68 + (5 if obj < 2 else 4)
            self.pos[obj] = p % 160
        elif r == 0x2A:  # HMOVE
            for i, hr in enumerate((0x20, 0x21, 0x22, 0x23, 0x24)):
                m = R[hr] >> 4
                if m >= 8: m -= 16
                self.pos[i] = (self.pos[i] - m) % 160
            if c < 68:
                self.hmove_blank = True
        elif r == 0x2B:  # HMCLR
            for hr in (0x20, 0x21, 0x22, 0x23, 0x24):
                R[hr] = 0
        elif r == 0x2C:
            self.cx = 0
        elif r == 0x28 or r == 0x29:  # RESMPx
            if v & 2:
                i = r - 0x28
                self.pos[2 + i] = (self.pos[i] + 3) % 160
        elif r in (0x15, 0x16, 0x17, 0x18, 0x19, 0x1A):
            self.audio_log.append((self.frames, r, v))
            if len(self.audio_log) > 20000:
                del self.audio_log[:10000]
        R[r] = v
        self.dirty = True

    def new_frame(self):
        self.last_frame_lines = self.lines_this_frame
        self.frame = self.frame_buf.copy()
        self.frame_lines = self.lines_this_frame
        self.last_vblog = self.vblog
        self.vblog = []
        self.frame_buf[:] = 0
        self.lines_this_frame = 0
        self.frames += 1

    # -------------------------------------------------------- CPU
    def push(self, v):
        self.write(0x100 | self.sp, v); self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.read(0x100 | self.sp)

    def setnz(self, v):
        self.flags = (self.flags & 0x7D) | (v & 0x80) | (0 if v else 2)

    def run_frame(self, max_cycles=200000):
        """Run until the next VSYNC start. Returns line count of finished frame."""
        f = self.frames
        start = self.cycles
        while self.frames == f:
            self.step()
            if self.cycles - start > max_cycles:
                raise RuntimeError("frame did not finish (pc=$%04X)" % self.pc)
        return self.last_frame_lines

    def step(self):
        pc = self.pc
        op = self.read(pc)
        self.pc = (pc + 1) & 0xFFFF
        f = OPFUNCS[op]
        if f is None:
            raise RuntimeError("illegal opcode $%02X at $%04X" % (op, pc))
        f(self)

# --------------------------------------------------------------- opcode impl
OPFUNCS = [None] * 256

def rd16(e, a):
    return e.read(a) | (e.read((a + 1) & 0xFFFF) << 8)

def addr(e, mode, rmw=False, write=False):
    """returns (address, extra_cycles)"""
    if mode == IMM:
        a = e.pc; e.pc = (e.pc + 1) & 0xFFFF; return a, 0
    if mode == ZP:
        a = e.read(e.pc); e.pc = (e.pc + 1) & 0xFFFF; return a, 0
    if mode == ZPX:
        a = (e.read(e.pc) + e.x) & 0xFF; e.pc = (e.pc + 1) & 0xFFFF; return a, 0
    if mode == ZPY:
        a = (e.read(e.pc) + e.y) & 0xFF; e.pc = (e.pc + 1) & 0xFFFF; return a, 0
    if mode == ABS:
        a = rd16(e, e.pc); e.pc = (e.pc + 2) & 0xFFFF; return a, 0
    if mode == ABX or mode == ABY:
        b = rd16(e, e.pc); e.pc = (e.pc + 2) & 0xFFFF
        a = (b + (e.x if mode == ABX else e.y)) & 0xFFFF
        return a, (1 if (a & 0xFF00) != (b & 0xFF00) and not (rmw or write) else 0)
    if mode == IZX:
        z = (e.read(e.pc) + e.x) & 0xFF; e.pc = (e.pc + 1) & 0xFFFF
        return e.read(z) | (e.read((z + 1) & 0xFF) << 8), 0
    if mode == IZY:
        z = e.read(e.pc); e.pc = (e.pc + 1) & 0xFFFF
        b = e.read(z) | (e.read((z + 1) & 0xFF) << 8)
        a = (b + e.y) & 0xFFFF
        return a, (1 if (a & 0xFF00) != (b & 0xFF00) and not write else 0)
    raise ValueError

BASE = {IMM: 2, ZP: 3, ZPX: 4, ZPY: 4, ABS: 4, ABX: 4, ABY: 4, IZX: 6, IZY: 5}
STBASE = {ZP: 3, ZPX: 4, ZPY: 4, ABS: 4, ABX: 5, ABY: 5, IZX: 6, IZY: 6}
RMWBASE = {ZP: 5, ZPX: 6, ABS: 6, ABX: 7}

def mk_read(mode, fn):
    def f(e):
        a, x = addr(e, mode)
        # time the read at the end of the instruction
        e.cycles += BASE[mode] + x - 1
        v = e.read(a)
        e.cycles += 1
        fn(e, v)
    return f

def mk_store(mode, reg):
    def f(e):
        a, _ = addr(e, mode, write=True)
        e.cycles += STBASE[mode]
        e.write(a, getattr(e, reg))
    return f

def mk_rmw(mode, fn):
    if mode == ACC:
        def f(e):
            e.cycles += 2
            e.a = fn(e, e.a)
        return f
    def f(e):
        a, _ = addr(e, mode, rmw=True)
        v = e.read(a)
        e.cycles += RMWBASE[mode]
        e.write(a, fn(e, v))
    return f

def op_lda(e, v): e.a = v; e.setnz(v)
def op_ldx(e, v): e.x = v; e.setnz(v)
def op_ldy(e, v): e.y = v; e.setnz(v)
def op_and(e, v): e.a &= v; e.setnz(e.a)
def op_ora(e, v): e.a |= v; e.setnz(e.a)
def op_eor(e, v): e.a ^= v; e.setnz(e.a)
def op_bit(e, v):
    e.flags = (e.flags & 0x3D) | (v & 0xC0) | (0 if (e.a & v) else 2)
def cmp_(e, r, v):
    t = (r - v) & 0x1FF
    e.flags = (e.flags & 0x7C) | (t & 0x80) | (0 if t & 0xFF else 2) | (1 if r >= v else 0)
def op_cmp(e, v): cmp_(e, e.a, v)
def op_cpx(e, v): cmp_(e, e.x, v)
def op_cpy(e, v): cmp_(e, e.y, v)
def op_adc(e, v):
    c = e.flags & 1
    a = e.a
    if e.flags & 8:
        lo = (a & 0xF) + (v & 0xF) + c
        hi = (a >> 4) + (v >> 4)
        if lo > 9: lo += 6
        if lo > 0xF: hi += 1
        z = ((a + v + c) & 0xFF) == 0
        n = (hi << 4) & 0x80
        vf = ((~(a ^ v)) & (a ^ (hi << 4)) & 0x80)
        if hi > 9: hi += 6
        cf = hi > 0xF
        r = ((hi << 4) | (lo & 0xF)) & 0xFF
        e.flags = (e.flags & 0x3C) | (0x80 if n else 0) | (0x40 if vf else 0) | (2 if z else 0) | (1 if cf else 0)
        e.a = r
    else:
        t = a + v + c
        vf = (~(a ^ v)) & (a ^ t) & 0x80
        e.a = t & 0xFF
        e.flags = (e.flags & 0x3C) | (e.a & 0x80) | (0x40 if vf else 0) | (0 if e.a else 2) | (1 if t > 0xFF else 0)
def op_sbc(e, v):
    c = e.flags & 1
    a = e.a
    t = a - v - (1 - c)
    vf = (a ^ v) & (a ^ t) & 0x80
    r = t & 0xFF
    if e.flags & 8:
        lo = (a & 0xF) - (v & 0xF) - (1 - c)
        hi = (a >> 4) - (v >> 4)
        if lo < 0:
            lo -= 6; hi -= 1
        if hi < 0:
            hi -= 6
        res = ((hi << 4) | (lo & 0xF)) & 0xFF
    else:
        res = r
    e.flags = (e.flags & 0x3C) | (r & 0x80) | (0x40 if vf else 0) | (0 if r else 2) | (1 if t >= 0 else 0)
    e.a = res

def r_asl(e, v):
    e.flags = (e.flags & 0xFE) | (v >> 7); v = (v << 1) & 0xFF; e.setnz(v); return v
def r_lsr(e, v):
    e.flags = (e.flags & 0xFE) | (v & 1); v >>= 1; e.setnz(v); return v
def r_rol(e, v):
    c = e.flags & 1
    e.flags = (e.flags & 0xFE) | (v >> 7); v = ((v << 1) | c) & 0xFF; e.setnz(v); return v
def r_ror(e, v):
    c = e.flags & 1
    e.flags = (e.flags & 0xFE) | (v & 1); v = (v >> 1) | (c << 7); e.setnz(v); return v
def r_inc(e, v):
    v = (v + 1) & 0xFF; e.setnz(v); return v
def r_dec(e, v):
    v = (v - 1) & 0xFF; e.setnz(v); return v

def reg_ops():
    T = OPFUNCS
    def mdef(op, modes, fn, kind):
        for m, code in modes.items():
            if kind == 'r': T[code] = mk_read(m, fn)
            elif kind == 'm': T[code] = mk_rmw(m, fn)
    std = lambda a: {IMM: a + 9 - 0x8 if False else None}
    groups = {
        op_ora: 0x00, op_and: 0x20, op_eor: 0x40, op_adc: 0x60, op_lda: 0xA0, op_cmp: 0xC0, op_sbc: 0xE0,
    }
    for fn, b in groups.items():
        modes = {IZX: b + 0x01, ZP: b + 0x05, IMM: b + 0x09, ABS: b + 0x0D,
                 IZY: b + 0x11, ZPX: b + 0x15, ABY: b + 0x19, ABX: b + 0x1D}
        mdef(None, modes, fn, 'r')
    for m, c in {IZX: 0x81, ZP: 0x85, ABS: 0x8D, IZY: 0x91, ZPX: 0x95, ABY: 0x99, ABX: 0x9D}.items():
        T[c] = mk_store(m, 'a')
    for m, c in {ZP: 0x86, ABS: 0x8E, ZPY: 0x96}.items(): T[c] = mk_store(m, 'x')
    for m, c in {ZP: 0x84, ABS: 0x8C, ZPX: 0x94}.items(): T[c] = mk_store(m, 'y')
    mdef(None, {IMM: 0xA2, ZP: 0xA6, ABS: 0xAE, ZPY: 0xB6, ABY: 0xBE}, op_ldx, 'r')
    mdef(None, {IMM: 0xA0, ZP: 0xA4, ABS: 0xAC, ZPX: 0xB4, ABX: 0xBC}, op_ldy, 'r')
    mdef(None, {IMM: 0xE0, ZP: 0xE4, ABS: 0xEC}, op_cpx, 'r')
    mdef(None, {IMM: 0xC0, ZP: 0xC4, ABS: 0xCC}, op_cpy, 'r')
    mdef(None, {ZP: 0x24, ABS: 0x2C}, op_bit, 'r')
    for fn, b in ((r_asl, 0x00), (r_rol, 0x20), (r_lsr, 0x40), (r_ror, 0x60)):
        mdef(None, {ZP: b + 0x06, ACC: b + 0x0A, ABS: b + 0x0E, ZPX: b + 0x16, ABX: b + 0x1E}, fn, 'm')
    mdef(None, {ZP: 0xE6, ABS: 0xEE, ZPX: 0xF6, ABX: 0xFE}, r_inc, 'm')
    mdef(None, {ZP: 0xC6, ABS: 0xCE, ZPX: 0xD6, ABX: 0xDE}, r_dec, 'm')

    def imp(code, fn):
        def f(e):
            e.cycles += 2; fn(e)
        T[code] = f
    def tax(e): e.x = e.a; e.setnz(e.x)
    def tay(e): e.y = e.a; e.setnz(e.y)
    def txa(e): e.a = e.x; e.setnz(e.a)
    def tya(e): e.a = e.y; e.setnz(e.a)
    def tsx(e): e.x = e.sp; e.setnz(e.x)
    def txs(e): e.sp = e.x
    def inx(e): e.x = (e.x + 1) & 0xFF; e.setnz(e.x)
    def dex(e): e.x = (e.x - 1) & 0xFF; e.setnz(e.x)
    def iny(e): e.y = (e.y + 1) & 0xFF; e.setnz(e.y)
    def dey(e): e.y = (e.y - 1) & 0xFF; e.setnz(e.y)
    for code, fn in ((0xAA, tax), (0xA8, tay), (0x8A, txa), (0x98, tya), (0xBA, tsx), (0x9A, txs),
                     (0xE8, inx), (0xCA, dex), (0xC8, iny), (0x88, dey)):
        imp(code, fn)
    for code, mask, val in ((0x18, 0xFE, 0), (0x38, 0xFE, 1), (0x58, 0xFB, 0), (0x78, 0xFB, 4),
                            (0xB8, 0xBF, 0), (0xD8, 0xF7, 0), (0xF8, 0xF7, 8)):
        imp(code, (lambda m, v: (lambda e: setattr(e, 'flags', (e.flags & m) | v)))(mask, val))
    imp(0xEA, lambda e: None)
    # unofficial NOPs commonly used
    for c in (0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA):
        imp(c, lambda e: None)
    def nopzp(e): e.pc = (e.pc + 1) & 0xFFFF; e.cycles += 3
    T[0x04] = T[0x44] = T[0x64] = nopzp

    def pha(e): e.cycles += 3; e.push(e.a)
    def php(e): e.cycles += 3; e.push(e.flags | 0x30)
    def pla(e): e.cycles += 4; e.a = e.pull(); e.setnz(e.a)
    def plp(e): e.cycles += 4; e.flags = (e.pull() & 0xCF) | 0x20
    T[0x48] = pha; T[0x08] = php; T[0x68] = pla; T[0x28] = plp

    def branch(mask, want):
        def f(e):
            off = e.read(e.pc); e.pc = (e.pc + 1) & 0xFFFF
            e.cycles += 2
            if bool(e.flags & mask) == want:
                if off >= 0x80: off -= 256
                n = (e.pc + off) & 0xFFFF
                e.cycles += 1 + (1 if (n & 0xFF00) != (e.pc & 0xFF00) else 0)
                e.pc = n
        return f
    for code, m, w in ((0x10, 0x80, False), (0x30, 0x80, True), (0x50, 0x40, False), (0x70, 0x40, True),
                       (0x90, 1, False), (0xB0, 1, True), (0xD0, 2, False), (0xF0, 2, True)):
        T[code] = branch(m, w)

    def jmp(e): e.pc = rd16(e, e.pc); e.cycles += 3
    def jmpi(e):
        p = rd16(e, e.pc)
        e.pc = e.read(p) | (e.read((p & 0xFF00) | ((p + 1) & 0xFF)) << 8)
        e.cycles += 5
    def jsr(e):
        t = rd16(e, e.pc)
        r = (e.pc + 1) & 0xFFFF
        e.push(r >> 8); e.push(r & 0xFF)
        e.pc = t; e.cycles += 6
    def rts(e):
        lo = e.pull(); hi = e.pull()
        e.pc = (((hi << 8) | lo) + 1) & 0xFFFF; e.cycles += 6
    def rti(e):
        e.flags = (e.pull() & 0xCF) | 0x20
        lo = e.pull(); hi = e.pull(); e.pc = (hi << 8) | lo; e.cycles += 6
    def brk(e):
        r = (e.pc + 1) & 0xFFFF
        e.push(r >> 8); e.push(r & 0xFF); e.push(e.flags | 0x30)
        e.flags |= 4
        e.pc = rd16(e, 0xFFFE); e.cycles += 7
    T[0x4C] = jmp; T[0x6C] = jmpi; T[0x20] = jsr; T[0x60] = rts; T[0x40] = rti; T[0x00] = brk

reg_ops()

# --------------------------------------------------------------- helpers
def save_png(frame, path, lines=None, scale=2):
    from PIL import Image
    f = frame if lines is None else frame[:lines]
    img = PALETTE[f]
    im = Image.fromarray(img, 'RGB')
    im = im.resize((im.width * scale * 2, im.height * scale), Image.NEAREST)
    im.save(path)

if __name__ == '__main__':
    import sys
    rom = open(sys.argv[1], 'rb').read()
    e = Emu(rom)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    for i in range(n):
        L = e.run_frame()
    print("lines in last frame:", L)
    save_png(e.frame, sys.argv[2], lines=e.frame_lines)
