# City Wars Help

This guide covers the live city-war system: how to attack a city, how to defend one, what commands matter, and what the rewards and risks are.

## Overview

City wars are guild-based.

- Cities are owned by the guild leading the alliance.
- Attacks are launched live by the attacking guild.
- Defenders can be pre-assigned and do not need to be online.
- A city must be fully cleared before it can be occupied:
  - active fortifications
  - city guards
  - stationed city pet

## Vault Bonuses

Owning a city increases the owning guild's vault cap:

- Tier 1: `x1.5`
- Tier 2: `x2.0`
- Tier 3: `x3.0`
- Tier 4: `x4.0`

If a city is conquered, the defending guild loses `25%` of the gold stored above its normal base vault cap.

## Attacking a City

### Requirements

- Only the alliance leader can start a city attack.
- Use: `alliance attack <city>`
- The city must not already be under attack.
- The city must not be on post-attack cooldown.
- Your guild must be able to pay the attack cost.
- You cannot attack your own city.

### Rally Phase

When an attack starts, a join button is posted for `10 minutes`.

- At least `3` eligible members of the attacking guild must join.
- Joined attackers must belong to the same guild as the alliance leader who started the attack.
- Players assigned as city guards cannot join attacks while stationed.

After the rally window:

- the alliance leader chooses the `3` frontline attackers
- the attack may bring `1` pet
- the pet owner must be one of the chosen frontline attackers
- the attack pet does not need to be equipped

### Attack Pet Rules

- The pet must belong to a chosen frontline attacker.
- The pet cannot be boarded in daycare.
- The pet must be in `young` or `adult` growth stage.
- Attack pets are scaled for city war and capped relative to their owner's city-war combat budget.

### Battle Flow

City war uses a fixed frontline:

- `3` attacking players
- up to `1` attacking pet
- up to `3` defending guards
- up to `1` defending city pet

Battle order:

1. Active fortifications are fought first.
2. After fortifications are gone, city guards and the stationed city pet fight.
3. If every defender is cleared, the attackers can occupy the city immediately.

Important notes:

- City-war combat uses compressed city-war stats, not raw character stats.
- Fortifications are slot-based now, not a stack of unlimited walls.
- The attack battle has a `15 minute` limit.
- If attackers do not clear the city in time, the defense holds.

### After Winning

If the attackers destroy every active defender:

- use `alliance occupy <city>`
- occupancy resets the city's buildings to level `0`
- the previous owner loses `25%` of vault gold above base cap
- the new owner gets `15 minutes` of occupy protection before others can occupy again

### Attacking Checklist

- Confirm your guild can pay the attack cost.
- Make sure at least `3` eligible members can join the rally.
- Decide your best `3` frontline attackers before the timer ends.
- Decide which joined attacker should supply the pet.
- Be ready to occupy immediately if the city falls.

## Defending a City

Defending is mostly preparation done in advance.

- Defenders do not need to be online when the attack happens.
- The city automatically uses the assigned guards, guard pet, and active fortifications.

### Defense Slots

Each city has `3` active defense slots:

- `1` wall slot
- `1` weapon slot
- `1` utility slot

Only one active defense can occupy each slot.

Current defenses:

- Wall:
  - `outer wall` - `80,000 HP`, `$500,000`
  - `inner wall` - `40,000 HP`, `$200,000`
- Weapon:
  - `cannons` - `1,000 HP`, `120 defense`, `$200,000`
  - `archers` - `2,000 HP`, `100 defense`, `$100,000`
  - `tower` - `5,000 HP`, `100 defense`, `$200,000`
  - `ballista` - `1,000 HP`, `60 defense`, `$100,000`
- Utility:
  - `moat` - `20,000 HP`, `50 defense`, `$150,000`

Commands:

- Build a defense: `alliance build defense <name>`
- View active defenses: `alliance defenses`
- Remove a defense: `alliance destroy <defense>`

Notes:

- Cities cannot build or change defenses while under attack.
- Legacy stacked defenses from the old system are not part of the new active slot system.

### City Guards

Cities can assign up to `3` city guards.

Commands:

- View guards: `alliance guards`
- Add a guard: `alliance guards add <member>`
- Remove a guard: `alliance guards remove <member>`

Guard rules:

- Guards must belong to the guild that owns the city.
- Assigned guards are real guild members saved as the city's defenders.
- Guards do not need to be online when the city is attacked.
- While stationed, guards cannot:
  - join city attacks
  - start guild adventures
  - join guild adventures

### City Guard Pet

Each city can assign `1` stationed pet.

Commands:

- View the guard pet: `alliance guards pet`
- Assign the guard pet: `alliance guards pet set <member> <pet>`
- Remove the guard pet: `alliance guards pet remove`

Guard pet rules:

- The pet owner must be a currently assigned city guard.
- The pet must belong to the guild that owns the city.
- The pet does not need to be equipped.
- The pet cannot be boarded in daycare.
- The pet must be `young` or `adult`.
- The guard pet is scaled for city war and capped relative to its owner's city-war combat budget.

### Buildings and Value

Cities also have upgradeable buildings which affect both passive guild benefits and attack cost.

Use:

- `alliance buildings`
- `alliance build building <thief|raid|trade|adventure>`

The stronger a city's buildings are, the more expensive it is to attack.

### Defending Checklist

- Fill all `3` defense slots.
- Assign all `3` city guard slots if possible.
- Assign a guard pet to one of those guards.
- Keep strong defenders stationed if you expect a war.
- Remember that city ownership increases vault cap, but also increases conquest risk if you store above base cap.

## Occupation and Loss

You cannot occupy a city until all of these are gone:

- active fortifications
- city guards
- stationed city pet

Use:

- `alliance occupy <city>`

If your guild already owns a city, you cannot occupy another one.

## Quick Command Reference

### Attackers

- `alliance attack <city>`
- `alliance occupy <city>`

### Defenders

- `alliance defenses`
- `alliance build defense <name>`
- `alliance destroy <defense>`
- `alliance guards`
- `alliance guards add <member>`
- `alliance guards remove <member>`
- `alliance guards pet`
- `alliance guards pet set <member> <pet>`
- `alliance guards pet remove`
- `alliance buildings`
- `alliance build building <name>`
- `alliance abandon`

## Practical Advice

### If you are attacking

- Plan your `3` frontline attackers before pressing the button.
- Bring a pet only if it meaningfully improves the chosen frontline.
- Attack only when you can occupy immediately after winning.
- Do not waste an attack window if the city is already mostly empty and someone else is ready to occupy first.

### If you are defending

- Treat guard duty as a real roster decision.
- Do not leave defense slots empty.
- Make sure the stationed pet belongs to one of the assigned guards.
- If your city raises your vault cap far above base, keep in mind that conquest can now hit stored overflow gold.
