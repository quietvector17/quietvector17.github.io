# Siege of Orgrimmar Strategies

Notes and reminders for Siege of Orgrimmar (SoO). This is intentionally concise and focused on "what to do".

## Immerseus

### DPS Phase

- Burn boss.
- `Corrosive Blast`
  - One-shots any non-tank.
  - Tank swap after every cast.
  - Large hit: position tanks at max safe healing range away from the raid.
- Sha pools spawn under players: move out.
- `Swirl`
  - Boss picks a point in the room and fires a moving water AoE around the room.

#### Heroic: Swelling Corruption

- Boss gains `Swelling Corruption` stacks.
- Each time the boss is attacked:
  - Boss loses 1 stack.
  - Attacker gains a stacking debuff (each hit increases damage taken).
    - `> 4` stacks is dangerous.
  - Attacker spawns a small add.
- Strategy:
  - Hit boss until ~3 debuff stacks, then AoE the small adds.
  - Keep the raid fairly stacked so the tank can pick up the spawned adds.

### Split Phase

- Starts when boss reaches 0 health.
- Adds spawn and move toward the center; if they reach it, they explode and deal raid damage.
- Two add types:
  - Sha Puddles (hostile)
    - Stunnable.
    - Grippable.
    - Allies in proximity gain a stacking damage buff and gain damage when they die.
      - Supposedly doesn’t last very long.
    - Count: 1 Sha Puddle per 4 corruption boss has remaining when this phase starts.
  - Contaminated Puddles (friendly)
    - Must be healed to full.
    - Move slower the more you heal them.
    - When healed to full: nearby players gain a healing buff and restore some mana.
    - Count: 1 Contaminated Puddle per 4 corruption cleansed from Immerseus.
      - Bias healing cooldowns toward the end.

### Fight Notes

- Boss does not die at 0 health.
- Resource bar represents corruption `100 -> 0` (fight over).
- Hero on pull with lust.
- Second pot on second DPS phase.

## Fallen Protectors

### Overall Win Condition / Pacing

- Need to kill all 3 bosses at the same time.
- Do not push multiple bosses to `66%` / `33%` at the same time (that’s when `Desperate Measures` happens).

#### Heroic push order (example)

- Cleave and multidot off `Rook Stonetoe` until `66%`.
- Push `Sun Tenderheart` to `66%` after `Rook` uses `Spinning Crane Kick`.
  - Watch for floor effects.
- Push `He Softfoot` as quick as you’re able to.
- Repeat this order one more time.
  - Good time to lust between `66%` and `33%`.
- Make sure they die at the same time after `33%`.

### Rook Stonetoe

- Frontal cone: face away from raid.
- Avoidable projectiles.
  - Heroic: speeds up with consecutive casts (eventually too fast to avoid).
- `Spinning Crane Kick` on a random player.
  - Move out of his kick.

#### Desperate Measures (Rook)

- Disappears and spawns 3 adds.
  - `Sorrow` (focus first)
    - Uses `Inferno Blast`.
      - Stack with melee to split damage.
      - Can be solo-soaked with immunities (similar to Static Shock on Lei Shen).
    - Heroic: stack on this as soon as it spawns (except He Softfoot tank).
  - `Misery`
    - Give tank extra healing.
  - `Gloom` (assign someone to interrupt)
    - Interrupt `Corruption Shock`.
  - Heroic: all 3 adds share health.

### He Softfoot

- `Garrote` random players.
- `Gouge` tank: stuns for 6 seconds and drops aggro.
  - Turn away from him to avoid it.
  - When avoided, it knocks back the tank instead.
- Poisons:
  - `Instant Poison`: extra damage to tank.
  - `Noxious Poison`: kite him in a circle around the raid.

#### Desperate Measures (He)

- Disappears and spawns `Embodied Anguish`.
  - Casts `Mark of Anguish` on a random player.
    - Receives stacking shadow damage.
    - Fixated by `Embodied Anguish`.
    - When you run out of CDs, transfer `Mark of Anguish` using the Extra Action Button.
      - Normal: give to a tank.
      - Heroic: can’t throw to tanks.
        - Rogues: Evasion
        - Mages: Ice Block
        - Hunters: Deterrence
        - Warlocks: Dark Bargain
        - Warriors: DBTS

### Sun Tenderheart

- `Mind Sear` randomly.
  - Doesn’t damage the target, but damages surrounding targets.
  - If targeted: move away.
  - Interruptible; will cast on a different player when interrupted.
- **Casts `Shadow Word: Bane`**
  - Must dispel instantly; will spread to nearby players if it deals damage.
  - Mass Dispelable.
- `Calamity`
  - 50% max HP damage to entire raid.
  - Can use CDs; use defensives/personals if low.
  - Heroic: deals increasing damage with every cast (`30% -> 40% -> 50% -> ...`).

#### Desperate Measures (Sun)

- Room will go dark: stand in the bubble to reduce damage taken.
- Kill two adds to end this phase (a lot of cleave).
- Chain raid CDs here.

## Norushen

- 7 minute enrage.

### Corruption Basics

- Start fight with 75 corruption (Heroic: 50 corruption).
  - The more you have, the less damage you do to the boss.
  - At 75 corruption, you do 50% damage to the boss.
  - Does not reduce damage dealt to adds.
- General idea: cleanse as many DPS as possible before phasing (50%).

### Orbs / Trials ("balls")

- Golden orbs spawn around the room over time.
  - Clicking a golden orb transports you into your own realm.
  - You will generally send 2 DPS, 1 tank, 1 healer for every set of balls.
    - DPS challenge increases number of adds.
- Tank swap mechanic (increasing damage with consecutive casts).

#### Heroic notes

- Stack in melee, pop hero, zerg boss.
- Healers still want to get cleansed.
- Can send in a giga-cranker single target DPS to get more damage.
- Once adds start spawning in P2, they must die quickly.
  - A healer must be standing where the add is dying to instantly soak the pool.

### Golden Orbs (Role Details)

- Clicking an orb sends you into a personal realm.

#### Tank realm

- Survive 1 minute vs `Titanic Corruption`.
  - `Titanic Smash`: avoidable frontal cone.
  - `Hurl Corruption`: interruptible.
  - Burst of Corruption: ~300K shadow damage.
  - Piercing Corruption: ~600K physical damage.
- Ported out and set to 0 corruption after surviving for 1 minute.
  - Tanks take less damage for having no corruption.

#### Healer realm

- Enter a realm with several friendly NPCs + 1 `Greater Corruption`.
  - Deals constant shadow damage to the player and NPCs.
  - Applies a dispellable DoT on the player if not dispelled.
- Must defeat `Greater Corruption` to exit.
- Can damage the corruption or heal allies to increase their damage dealt.
  - Offensive healers do well here (Disc priest).
- Ported out and set to 0 corruption after killing `Greater Corruption`.
  - Healers gain increased healing for having no corruption.

#### DPS realm

- Killing a mob inside spawns a new copy of it in the other realm with new abilities.
- Number of enemies varies depending on corruption level.
  - `Manifestation of Corruption` (kill first)
    - Casts a frontal cone attack: `Tear Reality`.
    - In the outside realm, they pulse damage and melee the tank.
      - Leave a shadow pool on the ground underneath.
      - Pool deals massive damage every second until it gets picked up.
      - Picking up the pool gives the player 25 corruption (can’t exceed 100 corruption).
      - Move out of raid before it dies; melee run away before it dies to not insta-soak pool.
      - Heroic: AoE pulses increase corruption by 2.
      - Heroic: pool AoE pulses increase corruption by 2.
  - `Essence of Corruption` (kill after)
    - Have a shield blocking front-damage.
    - Put a line on you that shoots out a bolt of corruption.
      - Dodge this.
      - If this line hits the boss in the outer realm, the boss gains a stacking damage buff.
        - Stun or interrupt until they’re dead.
  - Need to defeat every mob within 1 minute in order to clear corruption.
