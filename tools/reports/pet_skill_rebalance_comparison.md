# Pet Skill Rebalance Comparison

- Generated: 2026-03-17
- Scope: compares the old pet skill system against the remastered implementation now in the battle runtime.
- Notes:
  - "Old" means the old live behavior, not just the old tooltip.
  - When old tooltip and old runtime disagreed, both are called out.
  - This report focuses on skills and engine rules changed in the rebalance pass.

## System-Level Comparison

CHANGELOG
=========================================================================
 
 
PASSIVE TRIGGER CADENCE
-------------------------------------------------------------------------
Old: Many pet passives processed after every combat action for every
     living pet.
 
New: Per-turn pet effects now process on the acting pet's turn only.
     Death effects process once on death.
 
 
PASSIVE HEALING FORMULA
-------------------------------------------------------------------------
Old: Passive heals scaled straight from pet max HP with no effective
     ceiling. High-HP pets produced absurd sustain.
 
New: Passive heals now scale from the lower max HP between source and
     target and use hard caps.
       - Ally passive cap : 12% target max HP
       - Self passive cap  : 18%
       - Burst cap         : 40%
 
 
TEMPORARY BUFFS / DEBUFFS
-------------------------------------------------------------------------
Old: Many skills multiplied live stats directly and never reverted
     cleanly.
 
New: Temporary stat changes now use timed multipliers with refresh,
     expiry, and death cleanup.
 
 
OWNER PROTECTION
-------------------------------------------------------------------------
Old: Ocean's Embrace was backwards and moved pet damage to the owner.
     Guardian Angel did not reliably save the owner.
 
New: Owner guard/intercept logic now lives in the shared battle engine.
     Ocean's Embrace intercepts owner damage before it lands.
     Guardian Angel now reliably sacrifices the pet to save the owner.
 
 
ACTION DENIAL
-------------------------------------------------------------------------
Old: "stunned" and "paralyzed" were inconsistent. Tidal Force delay
     logic degraded in the wrong place.
 
New: Shared action-lock handling now consumes "stunned", "paralyzed",
     and "tidal_delayed" on the affected combatant's action.
 
 
SHIELD AND BYPASS RULES
-------------------------------------------------------------------------
Old: Several "ignore armor and shields" skills only ignored armor.
     Flame Barrier and Energy Shield secretly scaled from max HP.
 
New: Shield bypass is supported cleanly, and defense-based shields now
     scale from armor as their descriptions claim.
 
 
ULTIMATE REGISTRATION
-------------------------------------------------------------------------
Old: Multiple tier-10 skills were missing from the low-HP ultimate
     activation list.
 
New: Missing ultimates were registered, so they now actually arm and
     fire as ultimates.
 
 
DEATH CLEANUP
-------------------------------------------------------------------------
Old: Buffs created by a pet could outlive the pet and remain on
     allies/enemies indefinitely.
 
New: Pet-owned timed effects are now cleared when that pet dies.
 
 
=========================================================================

## Low-Tier Rebalance Pass

### 1-Point Skills

**Fire**
- `Flame Burst`: `1 SP` -> `1 SP`; unchanged at `15%` chance to deal `1.5x` damage.
- `Warmth`: `1 SP` -> `1 SP`; `5%` owner heal on pet attack -> `4%` owner heal on pet attack.
- `Fire Affinity`: `1 SP` -> `1 SP`; unchanged at `+20%` vs Nature and Water.

**Water**
- `Water Jet`: `1 SP` -> `1 SP`; `25%` full armor/shield bypass -> `15%` full armor/shield bypass.
- `Purify`: `1 SP` -> `1 SP`; unchanged at `cleanse 1 owner debuff per pet turn`.
- `Water Affinity`: `1 SP` -> `1 SP`; unchanged at `+20%` vs Fire and Electric.

**Electric**
- `Static Shock`: `1 SP` -> `2 SP`; `30%` paralyze chance -> `20%` paralyze chance.
- `Power Surge`: `1 SP` -> `1 SP`; `+15%` owner damage for `4` turns -> `+10%` owner damage for `3` turns.
- `Electric Affinity`: `1 SP` -> `1 SP`; unchanged at `+20%` vs Water and Nature.

**Nature**
- `Vine Whip`: `1 SP` -> `1 SP`; `25%` chance for `50%` damage reduction -> `20%` chance for `35%` damage reduction for `2` turns.
- `Natural Healing`: `1 SP` -> `1 SP`; `6%` self-heal per pet turn -> `5%` self-heal per pet turn.
- `Nature Affinity`: `1 SP` -> `1 SP`; unchanged at `+20%` vs Electric and Wind.

**Wind**
- `Wind Slash`: `1 SP` -> `1 SP`; `25%` full defense bypass -> `15%` full defense bypass.
- `Wind Walk`: `1 SP` -> `1 SP`; `+20%` dodge -> `+15%` dodge.
- `Wind Affinity`: `1 SP` -> `1 SP`; unchanged at `+20%` vs Electric and Nature.

**Light**
- `Light Beam`: `1 SP` -> `1 SP`; `30%` chance and `-50%` accuracy -> `25%` chance and `-35%` accuracy for `2` turns.
- `Divine Shield`: `1 SP` -> `1 SP`; `40%` dark resist and `10%` general resist -> `30%` dark/corrupted resist and `8%` general resist.
- `Light Affinity`: `1 SP` -> `1 SP`; `+40%` vs Dark/Corrupted -> `+25%` vs Dark/Corrupted.

**Dark**
- `Shadow Strike`: `1 SP` -> `1 SP`; `25%` chance for `50%` partial true damage -> `25%` chance for `40%` partial true damage.
- `Dark Shield`: `1 SP` -> `1 SP`; broken permanent conversion -> `20%` absorb plus `+10%` damage for `2` turns when struck.
- `Dark Affinity`: `1 SP` -> `1 SP`; `+40%` vs Light/Corrupted -> `+25%` vs Light/Corrupted.

**Corrupted**
- `Chaos Strike`: `1 SP` -> `1 SP`; random damage `50-150%` -> `75-125%`.
- `Corrupt Shield`: `1 SP` -> `1 SP`; `30%` absorb and `25%` corruption chance -> `20%` absorb and `20%` corruption chance.
- `Corrupted Affinity`: `1 SP` -> `2 SP`; `+30%` universal damage with no weaknesses -> `+15%` universal damage and ignores weakness penalties.

### 2-Point Skills

**Fire**
- `Burning Rage`: `2 SP` -> `2 SP`; below `30%` HP gain `+25%` damage -> below `35%` HP gain `+20%` damage.
- `Fire Shield`: `2 SP` -> `2 SP`; `20%` full block chance -> `18%` full block chance.
- `Heat Wave`: `2 SP` -> `2 SP`; `70%` splash -> `55%` splash.

**Water**
- `Tsunami Strike`: `2 SP` -> `2 SP`; max `+50%` damage at full HP -> max `+40%` damage at full HP.
- `Healing Rain`: `2 SP` -> `2 SP`; `8%` team heal per pet turn -> `5%` team heal per pet turn.
- `Fluid Movement`: `2 SP` -> `2 SP`; `25%` dodge -> `20%` dodge.

**Electric**
- `Thunder Strike`: `2 SP` -> `2 SP`; chains for `60%` and `60%` -> chains for `50%` and `50%`.
- `Energy Shield`: `2 SP` -> `2 SP`; `250%` defense shield -> `200%` defense shield.
- `Quick Charge`: `2 SP` -> `2 SP`; guaranteed first action -> major initiative boost without overriding true priority skills.

**Nature**
- `Photosynthesis`: `2 SP` -> `2 SP`; daytime `+20%` damage -> daytime `+15%` damage.
- `Growth Spurt`: `2 SP` -> `2 SP`; `+3%` all stats up to `10` stacks -> `+2%` all stats up to `5` stacks.
- `Forest Camouflage`: `2 SP` -> `2 SP`; `30%` untargetable chance -> `25%` untargetable chance.

**Wind**
- `Gale Force`: `2 SP` -> `2 SP`; `-30%` enemy accuracy for `1` turn -> `-20%` enemy accuracy for `1` turn.
- `Air Shield`: `2 SP` -> `2 SP`; projectile immunity and `50%` other reduction -> projectile immunity and `40%` other reduction.
- `Swift Strike`: `2 SP` -> `2 SP`; always first -> always first and `+5%` damage.

**Light**
- `Holy Strike`: `2 SP` -> `2 SP`; `+50%` vs Dark/Corrupted -> `+40%` vs Dark/Undead/Corrupted.
- `Healing Light`: `2 SP` -> `3 SP`; `12%` team heal per pet turn -> `7%` team heal per pet turn.
- `Holy Aura`: `2 SP` -> `2 SP`; `+20%` dark/debuff resistance -> `+15%` dark/debuff resistance.

**Dark**
- `Dark Embrace`: `2 SP` -> `2 SP`; `+50%` damage below owner `50%` HP -> `+35%` damage below owner `50%` HP.
- `Soul Bind`: `2 SP` -> `2 SP`; `50%` damage sharing -> `35%` damage sharing.
- `Night Vision`: `2 SP` -> `2 SP`; unchanged at `perfect accuracy / anti-stealth`.

**Corrupted**
- `Reality Warp`: `2 SP` -> `2 SP`; `10%` warp chance with `3`-turn cooldown -> `8%` warp chance with `4`-turn cooldown.
- `Reality Distortion`: `2 SP` -> `2 SP`; `20%` proc chance with `2`-turn cooldown -> `15%` proc chance with `3`-turn cooldown.
- `Void Sight`: `2 SP` -> `2 SP`; `+40%` dodge -> `+25%` dodge while keeping illusion/stealth detection.

## Meaningful Buff Pass

This follow-up pass targeted skills that were not just numerically behind, but also too hollow or too low-impact in the live runtime.

- `Inferno Mastery`: upgraded into a real Fire payoff. It now grants stronger fire scaling, stronger resistance, a longer overdrive window, and a teamwide infernal momentum buff.
- `Phoenix Rebirth`: no longer just revives. It now returns the pet with more HP and a short reborn-power window so the revive actually swings the fight.
- `Sun God's Blessing`: now hits harder, buffs harder, and scorches the whole enemy team instead of being just a good nuke.
- `World Tree's Gift`: now truly "seizes the battlefield" by shielding and empowering allies while actively suppressing enemies.
- `Wind's Guidance`: fully remastered away from a mostly dead redirect flag. It now has a real defensive identity by blowing heavy hits off course and punishing the attacker.
- `Air Currents` and `Freedom's Call`: converted from awkward permanent stat mutation into refreshable tempo buffs with real initiative pressure.
- `Dark Ritual`: rebuilt from a risky random proc into a deterministic blood-rampage payoff with sustained damage and lifesteal.
- `Lord of Shadows`: upgraded from "one skeleton and vibes" into an actual battlefield swing with a stronger summon, allied empowerment, and enemy fear.

## Wind Follow-Up Pass

This pass specifically targeted the remaining weak point in the roster: Wind created disruption, but too often failed to convert that disruption into real fight-winning momentum.

- `Gale Force`: upgraded from a light accuracy poke into a real short control debuff that also cuts enemy damage.
- `Tornado Strike`: now creates a real teamwide storm zone instead of feeling like a soft single-target setup.
- `Wind Tunnel`: now actually fulfills its fantasy by improving both offense and defense.
- `Storm Lord`: upgraded into a real battlefield takeover with ally haste, ally empowerment, enemy suppression, and storm damage pressure.
- `Wind's Guidance`: buffed into a more reliable defensive punish tool.
- `Freedom's Call`: now gives Wind a stronger mid-fight team conversion window.
- `Sky's Blessing`: now creates both a survival window and a genuine tempo swing.
- `Swift Strike`: buffed so the speed fantasy also carries meaningful damage.
- `Air Currents`: now boosts the whole team, not just "everyone except the pet," and adds real offensive conversion.
- `Zephyr's Dance`: rebuilt into a proper capstone that seizes turn order and punishes the enemy team instead of just nudging initiative.

## Fire

### Inferno Mastery
Old:
Tooltip said "all fire skills 2x effectiveness + 30% fire resistance + activates at low HP."
Runtime was mostly passive, not a properly registered ultimate, and did not deliver a real "fight turns around now" moment.

New:
Real ultimate. Fire effectiveness was reduced from absurd to strong, fire resistance was raised to 35%, and the pet enters a 3-turn inferno overdrive window with bonus pressure.

### Warmth
Old:
Tooltip said owner heals 5% of pet max HP every time the pet attacks.
Runtime was worse than that: because per-turn logic was running constantly, it healed even when the pet had not attacked and scaled off giant pet HP pools.

New:
Only heals when the pet actually attacks. Heal is based on the lower max HP between pet and owner and is capped by the passive heal rules.

### Flame Barrier
Old:
Tooltip said shield equals 300% of pet defense.
Runtime built the shield from pet max HP instead.

New:
Shield now scales from armor/defense, starts active, and only reignites at 50% strength on the pet's next turn after breaking instead of rebuilding instantly.

### Burning Spirit
Old:
Tooltip implied attack-based burn application.
Runtime used a random per-turn burn roll, detached from the actual attack event.

New:
Burn is applied off the attack event, to the attacked target, with the skill behaving like an actual offensive proc.

### Eternal Flame
Old:
Tooltip said pet could not die while owner was above 50% HP.
Runtime checked the inverse threshold and mostly behaved like a dead flag.

New:
If a lethal hit lands while the owner is at or above the threshold, the pet stays alive at 1 HP.

### Combustion
Old:
Tooltip said 200% of pet attack on death.
Runtime used pet max HP and could conflict with other death processing.

New:
Death trigger is processed exactly once and explosion damage is based on pet damage/attack as intended.

### Sun God's Blessing
Old:
Tooltip promised a huge team buff for 5 turns.
Runtime behavior was closer to a boosted hit plus unreliable secondary effects.

New:
It is now a real ultimate spike: a 2.75x solar hit, splash damage to other enemies, and a strong timed team buff window.

### Phoenix Rebirth
Old:
The revive existed, but the ultimate registration path was inconsistent.

New:
It now participates in the ultimate system correctly and still revives once with an immediate defensive payoff.

## Water

### Water Jet
Old:
Tooltip said it ignored armor and shields.
Runtime only bypassed armor in the shared damage path.

New:
It now bypasses both armor and shield on the hit.

### Ocean's Wrath
Old:
Tooltip said 2x damage to all enemies plus a team heal.
Runtime did not behave as a true teamwide burst-heal pattern.

New:
It now acts like a proper tide burst: 2x main strike, splash pressure, and a capped burst-heal to all allies.

### Purify
Old:
Tooltip said remove one random debuff from the owner each turn.
Runtime cleansed the whole team repeatedly.

New:
It now removes one random debuff from the owner per pet turn.

### Healing Rain
Old:
Healed all allies for 8% of pet max HP every "turn," but the old engine effectively applied it after many actions with no real ceiling.

New:
Heals once on the pet's turn, scales from the lower max HP between pet and ally, and respects passive healing caps.

### Immortal Waters
Old:
Tooltip said owner cannot die while the pet is alive.
Runtime was an awkward auto-trigger when the owner was nearly dead, and it was not properly registered as an ultimate.

New:
Real low-HP ultimate. Grants the owner a 2-turn death floor and a burst heal.

### Ocean's Embrace
Old:
Tooltip said the pet absorbs owner damage.
Runtime transferred part of the pet's incoming damage to the owner instead.

New:
Owner-targeted damage is intercepted in the shared battle engine and rerouted onto the pet first.

### Poseidon's Call
Old:
Tooltip promised long-duration team and enemy stat swings.
Runtime used direct stat mutation patterns that could stack badly.

New:
Applies a timed tide blessing to allies and a timed curse to enemies, with clean expiry.

## Electric

### Thunder Strike
Old:
Tooltip said crits chain to 2 nearby enemies.
Runtime only had one chain damage entry, so it did not really hit 2 targets correctly.

New:
Chains correctly to 2 extra enemies at 60% each.

### Storm Lord (Electric)
Old:
Tooltip promised chain-lightning pressure and pseudo double-turn energy.
Runtime value tuning was inflated and cleanup was weak.

New:
Now functions as a high-pressure 3x ultimate with timed team haste/offense instead of uncontrolled stat mutation.

### Power Surge
Old:
Every attack could multiply owner damage again and again.

New:
Refresh-only timed +15% owner damage for 4 turns. It no longer stacks forever.

### Energy Shield
Old:
Tooltip said 250% of defense.
Runtime created the barrier from pet max HP.

New:
Barrier now scales from armor/defense and only recharges to 60% strength on the pet's next turn after breaking, so it no longer acts like an infinite wall.

### Overcharge
Old:
Randomly procced, sacrificed too much HP, gave too much power, and stacked badly.

New:
Once per battle, under 60% HP, the pet sacrifices 20% HP to grant the owner +35% all stats for 2 turns.

### Infinite Energy
Old:
Missing from the ultimate registration list and used raw stat mutation that had to be manually unwound.

New:
Real ultimate. Grants the whole team +35% all stats and unlimited ability usage for 3 turns with clean timed expiry.

### Electromagnetic Field
Old:
25% enemy accuracy reduction, but it was repeatedly applied as a permanent mutation pattern.

New:
15% timed accuracy debuff that refreshes cleanly.

### Zeus's Wrath
Old:
Text oversold the duration and protection window.
Runtime was closer to a high number burst plus sticky flags.

New:
3-turn protection/debuff-immunity window with cleaner timed buff handling and a controlled damage spike.

## Nature

### Photosynthesis
Old:
Daytime bonus mutated damage on repeat and could snowball if processed too often.

New:
Daytime bonus is applied on attack instead of being permanently baked in every per-turn pass.

### Gaia's Wrath
Old:
Tooltip said 2x damage to all enemies and a giant team heal.
Runtime was much narrower and mostly acted like a self-heal-over-time pattern.

New:
2x ultimate strike, team burst-heal, and a 3-turn self-regeneration window.

### Natural Healing
Old:
Looked simple, but under the old cadence it could tick far too often.

New:
Self-heal is now bounded by the per-turn cadence and passive self-heal cap.

### Life Force
Old:
Pet could repeatedly sacrifice HP to dump huge healing into the owner.

New:
Emergency button only. Once per battle, below the owner HP threshold, the pet sacrifices 20% HP for a capped burst heal.

### Nature's Blessing
Old:
Tooltip described an environmental buff.
Runtime effectively assumed "nature environment" constantly and stacked team stats permanently.

New:
Converted into a reusable timed +10% all-stats team blessing with clean refresh/expiry.

### Immortal Growth
Old:
Text promised team regeneration and immunity.
It was not fully registered as an ultimate and the regen behavior was inconsistent.

New:
Registered ultimate. Applies teamwide regeneration plus DoT immunity for 3 turns, with proper cleanup.

### World Tree's Gift
Old:
Mostly battlefield-control flavor plus debuff immunity.

New:
Adds real team shielding on top of battlefield control and immunity, making it a real defensive ultimate window.

## Wind

### Wind Slash
Old:
Tooltip said true damage through armor and shields.
Runtime still let shields absorb the hit.

New:
Now bypasses shields as well.

### Gale Force
Old:
Used a direct luck reduction path that could stick around incorrectly.

New:
Timed enemy accuracy debuff with proper expiry.

### Wind Shear
Old:
Large defense shred, but it depended on direct stat mutation.

New:
Timed teamwide enemy armor debuff with cleanup.

### Storm Lord (Wind)
Old:
Was missing from the real ultimate registration path and its control state cleanup was weak.

New:
Proper ultimate. Big strike plus a short battlefield-control window with timed enemy suppression.

### Sky's Blessing
Old:
Text said 40% dodge and enemies lose 2 turns.
Runtime used loose tags that were hard to reason about.

New:
35% team dodge for 2 turns and up to 2 enemies stunned for 2 turns.

### Zephyr's Dance
Old:
Strong turn-flow fantasy, but the speed/slow tags did not clean up well.

New:
Timed ally speed and enemy slow windows with explicit durations and cleanup.

## Light

### Light Burst
Old:
Tooltip said 120% primary and 60% splash.
Runtime only gave 100% on the primary target.

New:
Primary hit now properly runs at 120% with 60% splash.

### Solar Flare
Old:
Tooltip said 3x damage to all enemies plus a cleanse.
Runtime was much closer to an oversized single-target nuke.

New:
3x main-target blast, 60% splash to the rest of the enemy team, and full team debuff cleanse.

### Healing Light
Old:
Healed all allies from raw pet max HP with no cap under the old trigger cadence.

New:
Heals once per pet turn, scales from lower max HP, and respects passive ally-heal caps.

### Guardian Angel
Old:
Tooltip said owner heals to full.
Runtime did not reliably fire in the correct owner-death moment.

New:
The pet sacrifices itself, restores the owner to 60% HP, and grants a shield.

### Divine Protection
Old:
Missing from the ultimate registration list and tuned as a much longer, larger wall than the rest of the tree.

New:
Properly registered 2-turn team invincibility plus a big burst heal.

### Divine Favor
Old:
25% proc for a random +30% stat blessing, with sticky stat mutation problems.

New:
25% proc for a timed +15% blessing to random damage, armor, or luck.

### Celestial Blessing
Old:
Huge +50% all-stats and long physical immunity window.

New:
Still an excellent ultimate, but trimmed to +25% all stats and 2 turns of physical immunity so it stays explosive without being dominant for too long.

## Dark And Corrupted

### Dark Pact
Old:
40% pet HP sacrifice for +100% owner dark power over 4 turns, and it could repeat badly.

New:
Once-per-battle desperation transfer: 25% pet HP for +35% owner damage over 2 turns.

### Eternal Night
Old:
Massive 75% team damage window plus lifesteal over 5 turns, with bad permanence behavior.

New:
Timed 3-turn power spike: +35% team damage and 15% bonus lifesteal.

### Void Mastery
Old:
Tooltip promised inversion of all enemy buffs.
Runtime mostly set dead or weak flags and did not really deliver the fantasy.

New:
Now strips key protective states, applies timed enemy damage/armor/luck penalties, and gives the pet side a short reality-control payoff.

### Reality Tear
Old:
Tooltip said "ignore all defenses."
Runtime still let shields matter.

New:
Now bypasses shield as well as armor handling.

### End of Days
Old:
Created big chaos flags and used duration handling that could leave the battlefield in a broken state.

New:
3-turn apocalypse package: team blessing, enemy curse, timed damage/armor/accuracy suppression, and clean cleanup.

### Void Lord
Old:
Text sold 3x damage, 50% reduction, and battlefield control.
Runtime repeatedly multiplied enemy and owner stats every tick and could spiral.

New:
Keeps the core fantasy, but does it with bounded timed effects: big strike, active damage reduction, owner blessing, and enemy domination/control without permanent stat drift.

## Ultimate Registration Fixes

These skills were explicitly added to the ultimate activation list so they now arm and fire as true low-HP ultimates:

- `Inferno Mastery`
- `Phoenix Rebirth`
- `Immortal Waters`
- `Infinite Energy`
- `Immortal Growth`
- `Storm Lord` (Wind version)
- `Divine Protection`
- `End of Days`

