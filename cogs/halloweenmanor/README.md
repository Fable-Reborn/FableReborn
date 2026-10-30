# Hollow Manor

A GM-started Halloween raid in its own channel. Bones and `$spookyshop` stay the seasonal loop. This cog is the night people show up for.

This folder is development only. It is not loaded. Do not edit live cogs while building it. Changes that belong in an existing `.py` file go in `pending/` as a snippet named after that file. See `pending/README.md`.

## Enable later

1. Paste the snippets in `pending/` into the live files they name. The theme uses the existing `ssbg` shop stock. No new column.
2. In `config.toml` (not committed), load both:

```toml
"cogs.halloween",
"cogs.halloweenmanor",
```

3. After every bot start, Halloween is off until a GM runs `$gmevent halloween on`. Loading the cogs does not turn the event on. Then `$manor open` from the category where the channel should appear.

## GM commands

| Command | What it does |
|---|---|
| `$manor open` | Creates `#「👻」hallow-manor` under category `1403273394853511240` (`MANOR_CATEGORY_ID`), pings **Night Watch**, and posts the gate. Refuses if Halloween is off, a manor is already open, or the server has already opened 5 manors today (resets midnight UTC). |
| `$manor watch` / `$night watch` | Opt in to Night Watch pings for the manor and the phantom door. `$manor unwatch` / `$night unwatch` turns the ping off. |
| `$manor status` | Phase, headcount, and bar progress. Anyone can use this. |
| `$manor skip` | Closes the current room and moves to the next. |
| `$manor end` | Settles rewards from the current progress. |
| `$manor close` | Settles if needed, then deletes the channel. |
| `$manor log` | GM only. Paginated manor history (10 per page). ▶️ shows older runs. Also shows today's opens out of 5. |
| `$manor log <id>` | GM only. One manor's players, their role and rooms searched, the rewards each received, and when they joined. |

Every manor is logged in the `hollow_manor_runs` and `hollow_manor_participants` tables. The cog creates them on load.

The bot needs **Manage Channels**, **Send Messages**, **Embed Links**, and **Attach Files**.

## What players do

The channel has no chat. Two buttons at the gate:

- **Investigate** — private orders in each room. Better rewards.
- **Keep watch** — stay on the roster. Smaller bone reward.

The gate is open for 3 minutes. Each of the hall, cellar, and heart stays open for 90 seconds. An investigator gets one choice per room. The choice is an ephemeral message, so only they see it, and the buttons die when the room closes.

A DM tells investigators when the next room opens. If DMs are closed, the **Search** button on the picture is the fallback.

## The picture

`assets/halloween/manor/` holds `gate.png`, `hall.png`, `cellar.png`, `heart.png`, and `cleared.png` at 1200×675. The bot draws the bar in the bottom band. Replace a PNG and restart the bot to change that room. The bar code does not need to change if the slot stays at the bottom.

The public picture refreshes at most once every 1.5 seconds, so a crowd of clicks does not edit the message on every press.

## Rewards

Numbers live in `rewards.py`.

Watchers, and investigators who never search:

- 38 bones, or 63 if the house is cleared
- about an 8% chance at a trick-or-treat bag (4% if the raid is under half progress)

Investigators, per room they actually search:

- 38 bones plus 50 per room, plus 25 if the house is cleared
- bag chance 40% plus 15% per room
- a full three-room search can roll a second bag (25%) and a crate (20%). The crate type uses the same even split as an automatic Ragnarok spawn: Divine, Fortune, Legendary, or Materials, 25% each
- two rooms: 12% chance at a Halloween profile theme they do not own, doubled if the house is cleared, capped at 50%
- three rooms: 25%, same clear bonus and cap
- the pool is The Last Lantern, Hollow Rider, Wraithwake, and Bonecourt Revel
- under half progress, theme and crate chances are off and bag chances are halved
- if they already own every Halloween theme, a full search pays 25 extra bones instead of another theme

The house clears when searches reach about 70% of (investigators × 3). A solo investigator still has to search all three rooms.

## Profile theme

**The Last Lantern** (`hallowmanor`) replaces the seasonal background in `$spookyshop`. It costs 2,500 bones, one purchase, and it is a `$prpg` theme. Manor search can also drop it or the other Halloween 2026 themes: **Hollow Rider** (`headlesshorseman`), **Wraithwake** (`ghostship`), and **Bonecourt Revel** (`dancingskeletons`). They are not in the normal profile-theme drop pool. Equip with `$prpg theme <key>`.

## Phantom door

A GM starts a night with `$door start 24h` (or `3d` / `7d`). Doors appear at random times any hour of the day, never while a manor is open, and never two at once. The first 72 hours of a night use 18–22 doors per day; after that, 12–15. The channel is public at the top of the manor category. Only **Night Watch** is pinged.

`$door chaos 8h` (or `3h` / `24h`) is the finale night. Doors still appear at random times, but much more often: a lead door opens, then 3–8 more follow within seconds at other ranks in the Halloween category. Night Watch is pinged when chaos starts and on each lead door. Sitout does not bench anyone during chaos. `$door stop` ends it.

Players press **Knock** and wait. When the door answers, one visitor is chosen by tickets (pity is hidden). Everyone who knocked gets a crumb. Trick visitors get bones plus the gag (the Stick of Shame on that variant). Treat visitors get more bones and a bag chance. Ethereal (~5%, and only if at least two people knocked) grants a named weapon in the high odd window: **93–99** one-hand or **185–197** two-hand (`2 × stat − 1`).

| Command | Who | What it does |
|---|---|---|
| `$night watch` / `$night unwatch` | Everyone | Night Watch ping on/off. `$manor watch` is the same opt-in. |
| `$door start [window]` | GM | Plan the night. Times are not posted. |
| `$door now` | GM | Spawn one door immediately at the top of the Halloween category. |
| `$door chaos [window]` | GM | Chaos night. Default `8h`. Random clusters: one door, then 3–8 more within seconds at different ranks. |
| `$door stop` | GM | Cancel leftovers and close every live door. |
| `$door log` | GM | Paginated door history (10 per page). ▶️ shows older doors. `$door log <id>` is one door's knockers and rewards. |

Art lives in `assets/halloween/door/`. The queue uses `closed.jpg`. Trick and treat crack `ajar.jpg` first; ethereal cracks `ajar-ethereal.jpg`, then `ethereal.jpg`.
