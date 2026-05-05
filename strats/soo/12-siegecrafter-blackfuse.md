## Siegecrafter Blackfuse (WIP)

### Overview

- Single-target boss with repeating weapon waves.
- Main goals:
  - Handle the active weapon on the floor.
  - Kill or disable the most dangerous weapon on the conveyor belt.
  - Manage `Crawler Mines` and `Automated Shredders` cleanly.
- Heroic adds a second weapon each cycle, so weapon priority and belt execution matter much more.

#### Heroic notes

- Heroic: boss uses two weapons per cycle.
  - One weapon stays active on the main platform.
  - One weapon is destroyed on the conveyor belt.
- Heroic: `Electrostatic Charge` forces a real tank swap plan.
- Heroic: sawblades persist and room space gets tighter over time.
- Heroic: most groups send a small, mobile belt team every cycle.

### Boss Abilities

- `Electrostatic Charge`
  - Heavy tank hit that leaves a debuff increasing damage taken from later charges.
  - Tank swap after each stack or according to your cooldown plan.
  - Heroic: stacks matter much more because tanks also deal with `Automated Shredder`.

- `Automated Shredder`
  - Spawns regularly and must be picked up by the off tank.
  - Casts `Death From Above`.
    - Jumps to a player and deals lethal damage in the impact zone.
    - Move out before it lands.
  - Shredders take bonus damage for a short time after landing from `Death From Above`.
    - Save burst for this window.
  - Tank should drag the shredder through damaging ground effects when possible.
    - This helps kill it before the next one spawns.

- `Crawler Mines`
  - Small mines fixate and move toward players.
  - If they reach someone or finish arming, they explode for heavy raid damage.
  - A player can soak one by touching it.
    - Use a strong defensive or immunity.
    - Classes assigned to mines should handle them consistently every set.

### Weapon Cycle

- Each cycle activates one weapon on the floor.
- A conveyor belt also carries weapons past the raid.
  - Players assigned to the belt jump up, kill one weapon, then return.
- Pick the belt target based on which floor weapon is hardest for your raid to handle.

### Floor Weapons

#### `Shockwave Missile Turret`

- Fires missiles at targeted locations.
- Missiles leave large swirl markers before impact.
- Move out quickly; impact is lethal or near-lethal.
- Keep the raid moving in a controlled direction so missiles do not box people in.

#### `Laser Turret`

- Fixates a player with a beam that leaves fire trails.
- If targeted:
  - Kite the laser around the edge of the room.
  - Do not cut through the raid.
  - Do not trap the mine-soakers or shredder tank.

#### `Crawler Mines`

- Mines spawn on the floor as the active weapon.
- Assigned players soak them one by one with personals.
- If a mine is missed, it is usually a wipe.

#### `Electromagnet`

- Pulls all sawblades across the room toward itself.
- This can drag blades through the raid unexpectedly.
- Watch blade paths and move early.
- Heroic: very dangerous once multiple blades are already out.

### Conveyor Belt

- Assigned belt players jump onto the pipe when the assembly line starts.
- Avoid the fire beams / holes while moving down the belt.
- Kill the assigned weapon before it reaches the end.
- Mobile burst DPS are best here.
- Common rule:
  - If your belt team cannot reliably kill a weapon, simplify the floor plan instead of greedily choosing harder targets.

### Heroic Weapon Priorities

- Common dangerous floor combinations are the ones that reduce room space:
  - `Laser Turret` + `Electromagnet`
  - `Shockwave Missile Turret` + `Electromagnet`
  - Multiple sawblade-heavy cycles in a row
- In general:
  - Kill `Electromagnet` on the belt when your room is already cluttered with sawblades.
  - Kill `Laser Turret` if your raid struggles to place beams cleanly.
  - Kill `Crawler Mines` if you do not have enough safe immunities/defensives available for that cycle.
  - Kill `Shockwave Missile Turret` if movement is already constrained and dodging will become unreliable.
- Keep the order consistent pull to pull so everyone knows what will be active downstairs.

### Positioning / Execution Notes

- Tank the boss near the center so the raid has room to rotate.
- Keep ranged loosely spread.
  - This reduces overlap from missiles and gives laser targets cleaner paths.
- Decide mine assignments before the pull.
- Decide belt assignments before the pull.
- Decide where laser players should kite before the pull.
- Heroic: conserve room space aggressively.
  - Bad sawblade placement early causes wipes later even if mechanics are otherwise clean.

### Video Guides

- Normal video guide (YouTube): https://www.youtube.com/watch?v=495kVDlRvPs
- Heroic video guide (YouTube): https://youtu.be/NDEKmjA1dA8
