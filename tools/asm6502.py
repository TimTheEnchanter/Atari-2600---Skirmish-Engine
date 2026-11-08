#!/usr/bin/env python3
"""Small DASM-syntax 6502 assembler (subset) for Atari 2600 work.

Supports: labels (global, '.local', with or without ':'), '=' / equ / set,
org [,fill], rorg, rend, seg / seg.u, ds, dc.b/.byte/byte/dc.w/.word/word,
hex, align, include, processor, subroutine, echo, if/ifconst/ifnconst/
else/endif, repeat/repend, err, mac/endm (simple {1}..{9} macros).
Expressions: $hex %bin decimal 'c', + - * / % & | ^ << >> ~ unary -,
<lo >hi, (), [], * or . for the current address, == != < > <= >= && ||.
Opcode suffix .w forces absolute, .b forces zero page.

usage: asm6502.py in.asm out.bin [-l listing.txt] [-s symbols.txt]
"""
import sys, os, re

OPS = {
 'ADC':{'imm':0x69,'zp':0x65,'zpx':0x75,'abs':0x6D,'absx':0x7D,'absy':0x79,'indx':0x61,'indy':0x71},
 'AND':{'imm':0x29,'zp':0x25,'zpx':0x35,'abs':0x2D,'absx':0x3D,'absy':0x39,'indx':0x21,'indy':0x31},
 'ASL':{'acc':0x0A,'zp':0x06,'zpx':0x16,'abs':0x0E,'absx':0x1E},
 'BIT':{'zp':0x24,'abs':0x2C},
 'BPL':{'rel':0x10},'BMI':{'rel':0x30},'BVC':{'rel':0x50},'BVS':{'rel':0x70},
 'BCC':{'rel':0x90},'BCS':{'rel':0xB0},'BNE':{'rel':0xD0},'BEQ':{'rel':0xF0},
 'BRK':{'imp':0x00},
 'CMP':{'imm':0xC9,'zp':0xC5,'zpx':0xD5,'abs':0xCD,'absx':0xDD,'absy':0xD9,'indx':0xC1,'indy':0xD1},
 'CPX':{'imm':0xE0,'zp':0xE4,'abs':0xEC},
 'CPY':{'imm':0xC0,'zp':0xC4,'abs':0xCC},
 'DEC':{'zp':0xC6,'zpx':0xD6,'abs':0xCE,'absx':0xDE},
 'EOR':{'imm':0x49,'zp':0x45,'zpx':0x55,'abs':0x4D,'absx':0x5D,'absy':0x59,'indx':0x41,'indy':0x51},
 'CLC':{'imp':0x18},'SEC':{'imp':0x38},'CLI':{'imp':0x58},'SEI':{'imp':0x78},
 'CLV':{'imp':0xB8},'CLD':{'imp':0xD8},'SED':{'imp':0xF8},
 'INC':{'zp':0xE6,'zpx':0xF6,'abs':0xEE,'absx':0xFE},
 'JMP':{'abs':0x4C,'ind':0x6C},
 'JSR':{'abs':0x20},
 'LDA':{'imm':0xA9,'zp':0xA5,'zpx':0xB5,'abs':0xAD,'absx':0xBD,'absy':0xB9,'indx':0xA1,'indy':0xB1},
 'LDX':{'imm':0xA2,'zp':0xA6,'zpy':0xB6,'abs':0xAE,'absy':0xBE},
 'LDY':{'imm':0xA0,'zp':0xA4,'zpx':0xB4,'abs':0xAC,'absx':0xBC},
 'LSR':{'acc':0x4A,'zp':0x46,'zpx':0x56,'abs':0x4E,'absx':0x5E},
 'NOP':{'imp':0xEA},
 'ORA':{'imm':0x09,'zp':0x05,'zpx':0x15,'abs':0x0D,'absx':0x1D,'absy':0x19,'indx':0x01,'indy':0x11},
 'TAX':{'imp':0xAA},'TXA':{'imp':0x8A},'DEX':{'imp':0xCA},'INX':{'imp':0xE8},
 'TAY':{'imp':0xA8},'TYA':{'imp':0x98},'DEY':{'imp':0x88},'INY':{'imp':0xC8},
 'ROL':{'acc':0x2A,'zp':0x26,'zpx':0x36,'abs':0x2E,'absx':0x3E},
 'ROR':{'acc':0x6A,'zp':0x66,'zpx':0x76,'abs':0x6E,'absx':0x7E},
 'RTI':{'imp':0x40},'RTS':{'imp':0x60},
 'SBC':{'imm':0xE9,'zp':0xE5,'zpx':0xF5,'abs':0xED,'absx':0xFD,'absy':0xF9,'indx':0xE1,'indy':0xF1},
 'STA':{'zp':0x85,'zpx':0x95,'abs':0x8D,'absx':0x9D,'absy':0x99,'indx':0x81,'indy':0x91},
 'TXS':{'imp':0x9A},'TSX':{'imp':0xBA},'PHA':{'imp':0x48},'PLA':{'imp':0x68},
 'PHP':{'imp':0x08},'PLP':{'imp':0x28},
 'STX':{'zp':0x86,'zpy':0x96,'abs':0x8E},
 'STY':{'zp':0x84,'zpx':0x94,'abs':0x8C},
}
SIZE = {'imp':1,'acc':1,'imm':2,'zp':2,'zpx':2,'zpy':2,'abs':3,'absx':3,'absy':3,
        'ind':3,'indx':2,'indy':2,'rel':2}

class AsmError(Exception):
    pass

class Undefined(Exception):
    pass

TOK = re.compile(r"\s*(\$[0-9A-Fa-f]+|%[01]+|\d+|'.'?|[A-Za-z_.][A-Za-z0-9_.]*|<<|>>|==|!=|<=|>=|&&|\|\||[-+*/%&|^~()<>\[\]!#,])")

class Expr:
    def __init__(self, asm, text):
        self.asm = asm
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = TOK.match(text, pos)
            if not m:
                if text[pos:].strip() == '':
                    break
                raise AsmError("bad expression: " + text)
            self.toks.append(m.group(1))
            pos = m.end()
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek(); self.i += 1; return t

    def parse(self):
        v = self.lor()
        if self.peek() is not None:
            raise AsmError("junk in expression: " + ' '.join(self.toks))
        return v

    def binop(self, sub, ops):
        v = sub()
        while self.peek() in ops:
            op = self.take(); w = sub()
            v = ops[op](v, w)
        return v

    def lor(self):  return self.binop(self.land, {'||': lambda a,b: int(bool(a) or bool(b))})
    def land(self): return self.binop(self.bor, {'&&': lambda a,b: int(bool(a) and bool(b))})
    def bor(self):  return self.binop(self.bxor, {'|': lambda a,b: a|b})
    def bxor(self): return self.binop(self.band, {'^': lambda a,b: a^b})
    def band(self): return self.binop(self.eq, {'&': lambda a,b: a&b})
    def eq(self):   return self.binop(self.rel, {'==': lambda a,b: int(a==b), '!=': lambda a,b: int(a!=b)})
    def rel(self):
        # '<' and '>' are binary comparison only between operands
        return self.binop(self.shift, {'<=': lambda a,b: int(a<=b), '>=': lambda a,b: int(a>=b),
                                        '<': lambda a,b: int(a<b), '>': lambda a,b: int(a>b)})
    def shift(self): return self.binop(self.add, {'<<': lambda a,b: a<<b, '>>': lambda a,b: a>>b})
    def add(self):  return self.binop(self.mul, {'+': lambda a,b: a+b, '-': lambda a,b: a-b})
    def mul(self):
        def div(a, b):
            if b == 0: raise AsmError("division by zero")
            return int(a / b) if (a < 0) != (b < 0) else a // b
        return self.binop(self.unary, {'*': lambda a,b: a*b, '/': div, '%': lambda a,b: a % b})

    def unary(self):
        t = self.peek()
        if t == '-': self.take(); return -self.unary()
        if t == '~': self.take(); return ~self.unary()
        if t == '!': self.take(); return int(not self.unary())
        if t == '<': self.take(); return self.unary() & 0xFF
        if t == '>': self.take(); return (self.unary() >> 8) & 0xFF
        if t == '#': self.take(); return self.unary()
        return self.atom()

    def atom(self):
        t = self.take()
        if t is None: raise AsmError("missing operand")
        if t in ('(', '['):
            v = self.lor()
            c = self.take()
            if c not in (')', ']'): raise AsmError("missing )")
            return v
        if t[0] == '$': return int(t[1:], 16)
        if t[0] == '%': return int(t[1:], 2)
        if t[0].isdigit(): return int(t)
        if t[0] == "'": return ord(t[1])
        if t in ('*', '.'): return self.asm.pc
        if t == '*': return self.asm.pc
        return self.asm.lookup(t)

class Assembler:
    def __init__(self):
        self.syms = {}
        self.macros = {}
        self.listing = []

    def lookup(self, name):
        full = self.fullname(name)
        if full in self.syms:
            return self.syms[full]
        if name.upper() in self.syms_ci:
            return self.syms_ci[name.upper()]
        self.undefined = True
        if self.final:
            raise AsmError("undefined symbol: " + name)
        raise Undefined(name)

    def fullname(self, name):
        if name.startswith('.') and len(name) > 1:
            return self.scope + name
        return name

    def define(self, name, value, redefinable=False):
        full = self.fullname(name)
        old = self.syms.get(full)
        if old is not None and old != value and not redefinable and self.passno_defined.get(full) == self.passno:
            raise AsmError("symbol redefined: %s" % name)
        if old != value:
            self.changed = True
        self.syms[full] = value
        self.syms_ci[full.upper()] = value
        self.passno_defined[full] = self.passno

    def ev(self, text, default=0):
        try:
            return Expr(self, text).parse()
        except Undefined:
            return None

    # ------------------------------------------------------------
    def read_file(self, path):
        with open(path) as f:
            lines = f.read().split('\n')
        out = []
        base = os.path.dirname(path)
        for n, ln in enumerate(lines):
            out.append((path, n + 1, ln, base))
        return out

    def assemble(self, path):
        self.path = path
        self.syms_ci = {}
        self.passno_defined = {}
        for p in range(1, 12):
            self.passno = p
            self.final = False
            self.changed = False
            self.undefined = False
            self.run_pass(path)
            if not self.changed and not self.undefined and p > 1:
                break
        self.passno += 1
        self.final = True
        self.changed = False
        self.run_pass(path)
        return self.image()

    def image(self):
        if not self.mem:
            return b''
        lo = min(self.mem); hi = max(self.mem)
        out = bytearray([self.fill] * (hi - lo + 1))
        for a, v in self.mem.items():
            out[a - lo] = v
        return bytes(out)

    def run_pass(self, path):
        self.pc = 0
        self.phys = 0
        self.rorg_active = False
        self.uninit = False
        self.mem = {}
        self.fill = 0
        self.scope = ''
        self.listing = []
        self.cond = []        # stack of (active, taken)
        self.echoes = []
        self.process(self.read_file(path))
        if self.final:
            for e in self.echoes:
                print(e)

    def active(self):
        return all(c[0] for c in self.cond)

    def emit(self, b):
        if self.uninit:
            self.pc += 1; self.phys += 1; return
        b &= 0xFF
        if self.final and self.phys in self.mem:
            raise AsmError("overlapping output at $%04X" % self.phys)
        self.mem[self.phys] = b
        self.pc += 1; self.phys += 1

    def process(self, lines):
        i = 0
        while i < len(lines):
            fname, lno, raw, base = lines[i]
            i += 1
            try:
                r = self.line(raw, base, lines, i)
                if isinstance(r, int):
                    i = r
            except AsmError as e:
                raise AsmError("%s:%d: %s\n  %s" % (fname, lno, e, raw))

    def split_comment(self, s):
        out = []; q = False
        for k, ch in enumerate(s):
            if ch == "'" and not q and k + 2 < len(s) + 1 and k + 2 <= len(s) - 1 and s[k+2] == "'":
                pass
            if ch == ';' and not q:
                break
            if ch == '"':
                q = not q
            out.append(ch)
        return ''.join(out).rstrip()

    def line(self, raw, base, lines, nexti):
        s = self.split_comment(raw.replace('\t', ' '))
        if not s.strip():
            return None
        label = None
        if s[0] not in ' ':
            m = re.match(r'([A-Za-z_.][A-Za-z0-9_.]*):?', s)
            if not m:
                raise AsmError("bad label")
            label = m.group(1)
            s = s[m.end():]
        parts = s.strip().split(None, 1)
        op = parts[0] if parts else ''
        arg = parts[1].strip() if len(parts) > 1 else ''
        opu = op.upper()
        if opu.startswith('.') and opu[1:] in ('BYTE','WORD','BYTES','ORG','ALIGN','EQU','INCLUDE','HEX','DS','IF','ELSE','ENDIF','ENDM','REPEAT','REPEND'):
            opu = opu[1:]

        # conditional assembly
        if opu in ('IF', 'IFCONST', 'IFNCONST'):
            if not self.active():
                self.cond.append((False, True)); return None
            if opu == 'IF':
                v = self.ev(arg)
                c = bool(v) if v is not None else False
            else:
                try:
                    Expr(self, arg).parse(); d = True
                except Undefined:
                    d = False
                except AsmError:
                    d = False
                c = d if opu == 'IFCONST' else not d
            self.cond.append((c, c)); return None
        if opu == 'ELSE':
            a, t = self.cond.pop()
            outer = self.active()
            self.cond.append((outer and not t, True)); return None
        if opu in ('ENDIF', 'EIF'):
            self.cond.pop(); return None
        if not self.active():
            return None

        if opu == 'MAC' or opu == 'MACRO':
            name = arg.split()[0].upper()
            body = []
            j = nexti
            while j < len(lines):
                t = self.split_comment(lines[j][2]).strip().upper()
                if t in ('ENDM', '.ENDM'):
                    break
                body.append(lines[j]); j += 1
            self.macros[name] = body
            return j + 1

        if opu in ('REPEAT', 'REPEAT'):
            n = self.ev(arg)
            depth = 0; j = nexti; body = []
            while j < len(lines):
                t = self.split_comment(lines[j][2]).strip().upper()
                if t in ('REPEAT', '.REPEAT') or t.startswith('REPEAT '):
                    depth += 1
                if t in ('REPEND', '.REPEND'):
                    if depth == 0: break
                    depth -= 1
                body.append(lines[j]); j += 1
            for _ in range(n or 0):
                self.process(body)
            return j + 1

        if opu in ('=', 'EQU', 'SET'):
            v = self.ev(arg)
            if label is None:
                raise AsmError("equate without label")
            if v is None:
                self.undefined = True
                return None
            if not label.startswith('.'):
                pass
            self.define(label, v, redefinable=(opu == 'SET'))
            return None

        if label is not None:
            if not label.startswith('.'):
                self.scope = label
            self.define(label, self.pc)

        if not op:
            return None

        if opu == 'PROCESSOR' or opu == 'END':
            return None
        if opu == 'SUBROUTINE':
            self.scope = '__sub%d_%d' % (id(lines), nexti)
            return None
        if opu == 'INCLUDE':
            fn = arg.strip().strip('"')
            p = os.path.join(base, fn)
            if not os.path.exists(p):
                p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)
            self.process(self.read_file(p))
            return None
        if opu == 'SEG' or opu == 'SEG.U':
            self.uninit = (opu == 'SEG.U')
            return None
        if opu == 'ORG':
            a = arg.split(',')
            v = self.ev(a[0])
            if v is None: raise AsmError("org needs defined value")
            if len(a) > 1:
                self.fill = self.ev(a[1]) or 0
            self.pc = v; self.phys = v
            return None
        if opu == 'RORG':
            v = self.ev(arg)
            if v is None: raise AsmError("rorg needs defined value")
            self.pc = v
            return None
        if opu == 'REND':
            self.pc = self.phys
            return None
        if opu == 'ALIGN':
            n = self.ev(arg)
            while self.pc % n:
                self.emit(self.fill)
            return None
        if opu in ('DS', 'DS.B', 'DS.W'):
            a = [x.strip() for x in arg.split(',')]
            n = self.ev(a[0])
            if n is None: raise AsmError("ds needs a defined count")
            if opu == 'DS.W': n *= 2
            fillv = self.ev(a[1]) if len(a) > 1 else 0
            for _ in range(n):
                self.emit(fillv or 0)
            return None
        if opu in ('BYTE', 'DC.B', 'DC', 'BYTES', 'DB'):
            for item in self.split_args(arg):
                if item.startswith('"'):
                    for ch in item.strip('"'):
                        self.emit(ord(ch))
                    continue
                v = self.ev(item)
                self.emit(v if v is not None else 0)
            return None
        if opu in ('WORD', 'DC.W', 'DW'):
            for item in self.split_args(arg):
                v = self.ev(item)
                v = v if v is not None else 0
                self.emit(v & 0xFF); self.emit((v >> 8) & 0xFF)
            return None
        if opu == 'HEX':
            h = arg.replace(' ', '')
            for k in range(0, len(h), 2):
                self.emit(int(h[k:k+2], 16))
            return None
        if opu == 'ECHO':
            vals = []
            for item in self.split_args(arg):
                if item.startswith('"'):
                    vals.append(item.strip('"'))
                else:
                    v = self.ev(item)
                    vals.append('$%X' % v if v is not None else '?')
            self.echoes.append(' '.join(vals))
            return None
        if opu == 'ERR':
            raise AsmError("ERR directive")

        if opu in self.macros:
            args = self.split_args(arg)
            body = []
            for (f, n, ln, b) in self.macros[opu]:
                for k, a in enumerate(args):
                    ln = ln.replace('{%d}' % (k + 1), a)
                body.append((f, n, ln, b))
            self.process(body)
            return None

        force = None
        if '.' in opu:
            opu, suf = opu.split('.', 1)
            force = suf
        if opu not in OPS:
            raise AsmError("unknown opcode or directive: " + op)
        self.instr(opu, arg, force)
        return None

    def split_args(self, arg):
        out = []; cur = ''; q = False; depth = 0
        for ch in arg:
            if ch == '"': q = not q
            if not q and ch in '([': depth += 1
            if not q and ch in ')]': depth -= 1
            if ch == ',' and not q and depth == 0:
                out.append(cur.strip()); cur = ''
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    def instr(self, op, arg, force):
        modes = OPS[op]
        a = arg.strip()
        au = a.upper().replace(' ', '')
        mode = None; expr = None
        if a == '' :
            mode = 'imp' if 'imp' in modes else 'acc'
        elif au == 'A' and 'acc' in modes:
            mode = 'acc'
        elif a.startswith('#'):
            mode = 'imm'; expr = a[1:]
        elif 'rel' in modes:
            mode = 'rel'; expr = a
        elif au.endswith(',X)') and a.startswith('('):
            mode = 'indx'; expr = a[1:a.upper().rindex(',X)')]
        elif au.endswith('),Y') and a.startswith('('):
            mode = 'indy'; expr = a[1:a.upper().rindex('),Y')]
        elif op == 'JMP' and a.startswith('(') and au.endswith(')'):
            mode = 'ind'; expr = a[1:-1]
        else:
            idx = None
            if au.endswith(',X'): idx = 'x'; expr = a[:a.upper().rindex(',X')]
            elif au.endswith(',Y'): idx = 'y'; expr = a[:a.upper().rindex(',Y')]
            else: expr = a
            v = self.ev(expr)
            zp_ok = (v is not None and 0 <= v < 0x100)
            if force and force.upper() in ('W', 'WX', 'WY'):
                zp_ok = False
            if force and force.upper() in ('B', 'BX', 'BY'):
                zp_ok = True
            if v is None and self.passno > 1 and not self.final:
                zp_ok = False
            base = 'zp' if zp_ok else 'abs'
            mode = base + (idx or '')
            if mode not in modes:
                if mode == 'zpy' and 'absy' in modes: mode = 'absy'
                elif mode == 'zpx' and 'absx' in modes: mode = 'absx'
                elif mode == 'zp' and 'abs' in modes: mode = 'abs'
                elif mode == 'abs' and 'zp' in modes and v is None: mode = 'zp'
            if mode not in modes:
                raise AsmError("bad addressing mode for %s" % op)
        if mode not in modes:
            raise AsmError("bad addressing mode %s for %s" % (mode, op))
        opc = modes[mode]
        start = self.pc
        self.emit(opc)
        v = self.ev(expr) if expr is not None else 0
        if v is None: v = 0
        n = SIZE[mode]
        if mode == 'rel':
            off = v - (start + 2)
            if self.final and not -128 <= off <= 127:
                raise AsmError("branch out of range (%d)" % off)
            self.emit(off & 0xFF)
        elif n == 2:
            if self.final and mode != 'imm' and not 0 <= v < 0x100:
                raise AsmError("zero page value out of range")
            if self.final and mode == 'imm' and not -128 <= v <= 255:
                raise AsmError("immediate value out of range: %d" % v)
            self.emit(v & 0xFF)
        elif n == 3:
            self.emit(v & 0xFF); self.emit((v >> 8) & 0xFF)

def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__); sys.exit(1)
    src, out = args[0], args[1]
    sym = None
    if '-s' in args:
        sym = args[args.index('-s') + 1]
    a = Assembler()
    try:
        img = a.assemble(src)
    except AsmError as e:
        print("error:", e); sys.exit(1)
    with open(out, 'wb') as f:
        f.write(img)
    if sym:
        with open(sym, 'w') as f:
            for k, v in sorted(a.syms.items(), key=lambda kv: kv[1]):
                if not k.startswith('__sub'):
                    f.write('%-24s $%04X\n' % (k, v))
    print("%s: %d bytes" % (out, len(img)))

if __name__ == '__main__':
    main()
