# Skirmish

A small turn-based tactics game for the Atari 2600, in the style of Advance
Wars or Fire Emblem skirmishes. It reuses Combat DX's 48-pixel text kernel
and font and RayWalls II's E7 setup, work chunks and tools.

`skirmish.bin` is a 16K **E7** cartridge (M-Network: 16K ROM + 2K RAM). Stella
may not detect it on its own; if not, set the cartridge type to **E7** in the
game properties, or rename the file with a `.e7` extension.

## Milestones

| # | Milestone | Status |
|---|---|---|
| 1 | Tile map kernel, scrolling view, cursor, info lines | **Done**, tested |
| 2 | Units you can select; movement range on the map; hot-seat for two players | **Done**, tested |
| 3 | Combat, terrain effects, win conditions | **Done**, tested |
| 4 | CPU player (chunked) | Next |
| 5 | Overview screen, title, map select | |

## Playing (milestone 3)

* **Players:** two, hot-seat. Either joystick and either button work, so
  you can share one stick or use two.
* **Move the cursor** with the joystick. Holding a direction repeats after 14
  frames, then every 6. The view scrolls to keep the cursor one tile from the
  edge.
* **Fire on one of your units** that hasn't moved: it's selected (the bottom
  line shows `MOVE`). The cells it can reach get a light dotted shading.
* **Fire again:**
  * On a shaded empty cell: the unit moves there.
  * On the unit's own cell: it stays put (waits).
  * Anywhere else (out of reach, or on another unit): the selection is
    cancelled.
* **Attacking:** if a unit ends its move with an enemy in range, the cursor
  jumps to that enemy.
  * The middle line shows the target and its HP (` TROOP HP 10`).
  * The bottom line shows the forecast: `HIT 5 BACK 3` is the damage you
    deal and the damage you'd take back. `BACK -` means no damage back,
    either because the target won't survive or because it can't reach you.
  * Any joystick direction steps to the next target, then to `WAIT` (the
    cursor goes back to your unit), then round again.
  * Fire attacks the target, or on `WAIT` ends the move without fighting.
* **A unit that has moved** loses its box and keeps only its corners and
  symbol. The bottom line shows `--` as its status, and it can't be selected
  again this turn.
* **The unit line** reads name, HP, status: ` TROOP 10 P1`. Status is `P1`
  or `P2` (ready), `GO` (selected) or `--` (moved).
* **The turn passes** when every unit on your side has moved, or straight
  away with the console's **Select** switch. The top line switches to
  `P2` (the turn number goes up after P2), every unit is ready again, and
  the cursor jumps to that player's HQ.
* **Winning:** destroy every enemy unit, or end a move on the enemy's HQ.
  The top line shows `  P1  WINS  `; fire (or Reset) starts a new game.
* **Reset** restarts the game.
* **Sounds:** a blip on select, a tone on a move, a buzz when something
  isn't allowed, a chime at the start of a turn, a hit, a longer crash when a
  unit is destroyed, and a long tone for the win.

### Combat

* **HP:** every unit starts with 10.
* **Damage:**
  1. Start from the base value for attacker vs defender (table below).
  2. Scale it by the attacker's HP / 10, rounded, at least 1. A weakened
     unit hits weaker.
  3. Take off the defender's terrain defence, leaving at least 1.
* **Damage back:** a defender that survives strikes back with its remaining
  HP, if the attacker is at the defender's range.
* **Range:** melee units (troop, rider, heavy) attack at exactly 1 cell.
  Archers attack at exactly 2. So archers never take damage back from melee
  units, and can't attack something right next to them.
* **No luck:** the forecast is exactly what happens.

Base damage (attacker down the side, defender across the top):

| | Troop | Archer | Rider | Heavy |
|---|---|---|---|---|
| Troop | 5 | 6 | 4 | 2 |
| Archer | 5 | 5 | 6 | 2 |
| Rider | 6 | 7 | 5 | 3 |
| Heavy | 7 | 7 | 6 | 5 |

Terrain defence: forest 1, hill 2, HQ 2, everything else 0.

### Units and terrain

| Unit | Symbol | Moves | Forest | Hill | Plain / road / bridge / HQ | Water |
|---|---|---|---|---|---|---|
| Troop | X | 3 | 2 | 2 | 1 | no |
| Archer | dot | 3 | 2 | 2 | 1 | no |
| Rider | / | 5 | 3 | 3 | 1 | no |
| Heavy | oval | 3 | no | 3 | 1 | no |

* Player 1's counters are outlined; player 2's are solid with the symbol cut
  out.
* Enemy units block movement. Your own units can be passed through, but you
  can't stop on them.
* Each side has six units on the test map.
* All the numbers live in `gen.py` (`SYMBOLS`, `COSTS`, `BASE`, `RANGE`,
  `TERRDEF`, `MAXHP`). The tests read them from `build_map.json`, so
  changing them keeps the tests valid.

Screenshots in `shots/`:
* `start.png`: the opening view.
* `rider_range.png`: a rider's range.
* `moved.png`: moved units.
* `p2_turn.png`: P2's turn with a troop selected.
* `rider_blocked.png`: a range cut by an enemy unit.
* `turn.gif`: selecting and moving a rider.
* `forecast.png`: a troop choosing a target.
* `after_fight.png`: the result of that fight.
* `win.png`: P1 wins.
* `fight.gif`: a move, the target choice and the attack.

## How it works

### Memory map (E7)

| Address | Contents |
|---|---|
| `$F000-$F7FF` | Lower slot: ROM slice 0–6, or the 1K RAM (write `$F000`, read `$F400`) |
| `$F800-$F9FF` | 256-byte RAM bank 0–3 (write `$F8xx`, read `$F9xx`) |
| `$FA00-$FFFF` | Fixed: ROM slice 7 |

**RAM:**
* **1K RAM:** the two view buffers (A at `$000`, B at `$200`). Each is
  6 columns × 64 bytes; column c is at +c×64, graphic row y (63 = top) at +y.
* **Bank 0:** the movement range. `DIST` (`$00-$BF`) holds moves left + 1
  for each cell, 0 = out of reach. The flood fill's queue (`$C0-$FF`) holds
  64 cells, circular.
* **Bank 1:** free.
* **Bank 2:**
  * The map (`$00-$BF`): low nibble = terrain, high nibble = unit slot.
  * The unit table (`$C0-$FF`), 16 slots each, slot 0 unused:
    * `UPOS`: map cell.
    * `UKIND`: side × 8 + type, `$FF` = empty.
    * `UST`: HP × 16 + moved (bit 0).
    * `UGFX`: offset of its counter in the tile graphics.
* **Bank 3:** the cursor table (`ENT`) and all three text lines (`TXT`:
  pair column j at +j×15, line k's rows at +k×5).
* **Zero page:** `$80-$CF` used; `$D0-$F0` free.

The flood fill and the text code run from ROM slices, which share the lower
slot with the 1K RAM. That's why their data is in the RAM banks: those stay
reachable from any slice, now and for the AI later.

**ROM:**
* **Slice 0:** game logic (input, select / move / cancel, turns, sound),
  combat, the flood fill, and the cost and combat tables. About 290 bytes
  free.
* **Slice 1:** text (font, names, the composer, the three lines). About
  340 bytes free.
* **Slice 2:** the map and unit table. A fixed-area routine (`BootCopy`)
  copies them into bank 2 at startup. About 1.8K free.
* **Fixed slice:** the rest:
  * Startup, the main loop and the work dispatcher.
  * The view builder.
  * Object positioning.
  * The screen, both map kernels and the text kernel.
  * The tile graphics, including the range overlay.
  * About 220 bytes free.
* Slices 3–6 are empty.

### Display

* **Map kernel:** the 48-pixel trick from Combat DX's menu, with the same
  write cycles (45/48/51/54). P0 sits at x = 56 and P1 at 64, three close
  copies each with vertical delay, so the 6 tiles run from 56 to 103. That
  window is symmetric about the screen's centre, so a reflected playfield
  draws the border on both sides.
* There is one kernel per buffer, generated by `gen.py`.
* **Cursor:** the ball, with playfield priority. Its ENABL value for the
  next row is loaded at the end of each row. Because VDELBL is on, it only
  shows from the next GRP1 write (cycle 14 of the next line), so the bars
  line up exactly with graphic rows.
* **Text lines:** Combat DX's menu loop. All three lines now come from bank
  3; the kernel gets the line's first row in Y and its end in `tend`.
* **No page alignment needed:** a page crossing at either kernel's loop
  branch only costs one cycle, and every line starts with a WSYNC. Dropping
  the alignment freed most of a page in the fixed slice.

### View building

* The builder fills the back buffer one tile per work chunk (worst 308
  cycles):
  * A cell with a unit gets that unit's counter (`UGFX`).
  * An empty cell gets its terrain.
  * When a range is showing and the cell is in reach, the terrain is ORed
    with the shading pattern.
* When all 48 tiles are done, the buffers flip at the start of the next
  frame.
* Anything that changes what's on the map sets `need`, which restarts the
  build at once.
* A full view takes about 4 frames.

### Movement range

* The flood fill relaxes cells from a queue: a cell is added again whenever
  it's reached with more moves left. So it gives the best path with mixed
  costs, not just the shortest in steps.
* It runs as work chunks:
  * Two chunks clear `DIST` (worst 1,062 cycles each).
  * Each further chunk takes one cell off the queue and tries its four
    neighbours (worst 516 cycles).
* A range is usually ready within a frame or two of pressing fire.
* In 40 random selections the queue never held more than 15 of its 64
  entries.

### Combat code

* **Choosing targets:** after a move, `NextTarget` scans the unit table for
  enemies at exactly the attacker's range (Manhattan distance). It moves the
  cursor and computes the forecast.
* **Damage:** `Damage` is two table lookups (base value, then the HP-scaled
  value from an 8 × 11 table) and the terrain subtraction, with no
  multiplication at run time.
* **Resolving:** `Strike` applies the forecast. `Kill` removes a unit and,
  if its side has none left, calls `Win`.
* **HQ capture:** checked right after a move.
* **End of turn:** a move or fight that ends the turn sets `pendend`, and
  the turn changes at the start of the next frame. Doing it in the same frame
  (move + target scan + end of turn) came to 2,700 cycles, more than
  vertical blank has.

### Frame budget

* **Work chunks** run while the timer allows, in both vertical blank and
  overscan. Each has its own threshold: worst cost / 64 + 2, from measured
  worst cases.

  | Chunk | Threshold |
  |---|---|
  | Text line (worst 947 cycles) | 17 |
  | Range clear (1,157) | 21 |
  | Range step (517) | 11 |
  | Tile (316) | 7 |

* **The heaviest input frame** is a move with a fight right after it (move,
  scan for targets, forecast, check whether anyone is left to move). It
  costs 1,853 cycles, about 460 under the vertical blank budget.
* **Startup and Reset:** `Start` only clears the TIA and zero page, then
  waits out an overscan's worth of timer. A restart runs straight after the
  screen, so that frame is 262 lines too. The rest of the setup (clear the
  cursor table, copy the map and units 64 bytes at a time, start P1's turn)
  runs one step per frame. The screen stays blank until the first view and
  the text are ready: 8 frames after power-on.

## Testing (bundled emulator)

* `tools/test_combat.py` places units by writing the cartridge's RAM, then
  plays with the joystick. Its 31 checks run against an independent Python
  version of the rules (`check.py`). Covered:
  * A melee fight with damage back.
  * Forest defence.
  * An archer at range 2 taking nothing back.
  * Cycling two targets and `WAIT`, and waiting.
  * Destroying a target; damage back destroying the attacker.
  * Winning by destroying the last enemy and by taking the HQ, and fire
    starting a new game.
  * 29 random fights (random units, HP and terrain) whose forecast and result
    must match the Python rules.
  * Every frame 262 lines.

  Result: 0 failures.

* `tools/test_turns.py` scripts a game and checks 44 things (random moves
  that end next to an enemy now attack). The screen
  checks compare the map window pixel by pixel with a Python rendering made
  from the cartridge's RAM, using a separate Python flood fill for the range.
  Covered:
  * Selecting, the range, moving, waiting and cancelling.
  * Refusals: an enemy unit, a moved unit, an empty cell.
  * The heavy's range (no forest).
  * An enemy unit blocking a rider.
  * The text lines.
  * Select ending the turn, and the turn passing automatically after P2's
    last unit.
  * Reset.
  * 40 random selections whose ranges must equal the reference.
  * Every frame 262 lines, and no stray writes to ROM or reads of write
    ports.

  Result: 0 failures.
* `tools/test_view.py` walks the cursor over all 192 cells, checking the
  map window pixel by pixel, the decoded text lines and the scroll margins.
  Result: no failures.
* `tools/test_timing.py`: 3 × 3,000 frames of random joystick, fire and
  Select input. Every frame is 262 lines. The smallest margins left are 128
  cycles in vertical blank and 154 in overscan, and the script also reports
  the worst cost of each chunk.
* `tools/shots.py` writes the screenshots and the GIF.
* **Not yet tried in Stella or on hardware.** If tiles show doubled or
  shifted columns there, adjust the P0/P1 position first (`TILEX`, `POSADJ`
  in `fixed_code.inc`), then `BALLADJ` for the cursor.

## Building

```
python3 gen.py
python3 tools/asm6502.py skirmish.asm skirmish.bin -s skirmish.sym
python3 tools/test_combat.py
python3 tools/test_turns.py
python3 tools/test_view.py
python3 tools/test_timing.py
```

`gen.py` holds the art (ASCII, top row first), the unit stats and terrain
costs, the test map (one character per cell plus a unit list), the font and
names. It writes these files:
* `fixed_data.inc`, `fixed_kern.inc`: fixed slice.
* `slice0_data.inc`: costs and combat tables.
* `slice1_data.inc`: font, names and the composer.
* `slice2_data.inc`: the map and units.
* `build_map.json`: used by the tests.

## Notes for milestone 4 (CPU player)

* **Where:** the CPU player can live in slice 3. It needs the flood fill and
  `Damage`. The tables are small enough to copy into its slice, or a few
  fixed-area trampolines (like `BootCopy`) can call slice 0.
* **How it decides:** for each of its units, flood fill its range. For every
  reachable cell, score:
  * the best attack from there (forecast damage dealt minus damage taken,
    big bonus for a kill);
  * the threat of standing there (enemies that could reach it next turn);
  * terrain defence;
  * distance to the enemy HQ.

  Then move to the best cell and attack.
* **Time:** a range already runs as chunks (2 clears plus about 20–50
  steps). Scoring cells adds roughly 100–200 cycles each, which is about one
  to two seconds of thinking per unit.
* **Players:** a menu or difficulty switch picks 1 or 2 players.
* **RAM:** bank 1 is still free for the scoring work.
