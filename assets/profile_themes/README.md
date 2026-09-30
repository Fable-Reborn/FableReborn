# The Chronicle Collection

89 illustrated cosmetics plus the original `classic` profile: seven free starters and 83 collectible drops. This expansion adds 30 themes: six Common, six Uncommon, five Rare, four Epic, four Legendary, two Mythic and three **Transcendent**, the new tier above Mythic.

The Transcendent trio — **Genesis of the Sun**, **The Velvet Singularity**, and **The Worldtree's Heart** — uses a completely separate **1800×2400 illustrated folio** format. It draws directly from resolved profile values instead of reusing the standard panels. Each folio is minted like a numbered collector's coin: the painting melts into a light-etched field under a gilded, glowing filigree frame set with edition jewels, and the portrait sits in a coin crest whose legend reads *Transcendent · <name>* above and *Edition I/II/III of III* below. Title, name, level, power and stats use blooming chrome lettering; stats sit on glass plaques with gradient rails and lit tips; an iridescent sheen and sparkles finish the card. Each edition has its own metal and light: **Genesis** is solar gold with a sunburst crest and radiant rays, **Singularity** is platinum and amethyst with a starfield and an accretion ring that passes in front of the portrait, and **Worldtree** is jade and gold with a laurel wreath, vines and fireflies. Everything that does not depend on the player is built once per edition (~0.6s) and cached. Warm renders take ~0.35s. Gameplay calculations and ownership rules are unchanged. Optional in-game character portraits and missing pet artwork are supported.

The other 27 include **Cloverhoof Meadow** (pony), **The Opal Unicorn**, **Wings of the First Dawn** (Pegasus), and **The Graveborn Foal** (undead demon pony). Their cards retain the standard 1660×1460 size. The two new Mythics use prismatic decoration.

## Rarity tiers and drops

Activity trigger rates remain: adventures **20%**, Battle Tower **15%**, PvE **10%**, Ice Dragon **8% per party member**. PvE macro penalties suppress theme drops. PvP has no theme reward hook.

Every triggered roll chooses exactly once from the **same complete collectible pool**, including already-owned themes. Starters and event-exclusive themes are excluded. There are no stat, god, level or activity-specific theme restrictions. If the selected theme is owned, return no reward silently: no reroll, duplicate notice or new grant record. Ownership never changes the pool or weights.

Weights are per theme, not per rarity tier. With the current 83 collectible themes:

| Rarity | Weight per theme | Share of triggered rolls |
| --- | ---: | ---: |
| Common | 68 | 60.7215% |
| Uncommon | 26 | 26.3127% |
| Rare | 10 | 8.3343% |
| Epic | 4 | 3.3337% |
| Legendary | 1.25 | 0.9674% |
| Mythic | 0.75 | 0.3125% |
| Transcendent | 0.1 | 0.0179% |

An individual theme's probability per activity completion is `activity trigger × theme weight / 1679.8`. Actual new-reward probability falls as themes are collected; rarity selection probabilities stay constant. Adding themes changes the total weight, so this table must be regenerated when the pool changes. Parallel rolls hold the character row lock through the ownership check and grant, preventing duplicate announcements.

## Developer catalogue (contains spoilers)

All collectible rows below use the shared pool: **Adventure, PvE, Battle Tower and Ice Dragon**. Bestiary artwork references specific monsters, but earning it does not require defeating that monster.

| Collection | Key | Theme | Rarity |
| --- | --- | --- | --- |
| Origins | `classic` | Original Chronicle | Starter |
| Origins | `dragon` | Ashen Sovereign | Starter |
| Origins | `evil` | The Hollow Crown | Starter |
| Origins | `chaos` | Violet Rupture | Starter |
| Origins | `good` | Dawnward | Starter |
| Origins | `forest` | Verdant Oath | Starter |
| Origins | `frost` | Winterveil | Starter |
| Divine | `elysia` | Elysia's Mercy | Rare |
| Divine | `sepulchure` | Sepulchure's Requiem | Rare |
| Divine | `drakath` | Drakath's Paradox | Rare |
| Companions | `moonbunny` | Moonpetal Burrow | Common |
| Companions | `slime` | Slime Royalty | Common |
| Companions | `frogzard` | Frogzard Festival | Uncommon |
| Companions | `chickencow` | Cloudmilk Meadow | Common |
| Companions | `mushroom` | Mosslight Hollow | Common |
| Mythic | `leviathan` | Abyssal Monarch | Epic |
| Mythic | `phoenix` | Cindersong | Epic |
| Mythic | `storm` | Stormbreaker | Rare |
| Mythic | `eclipse` | Eclipse Devourer | Legendary |
| Mythic | `bloodmoon` | Bloodmoon Hunt | Epic |
| Mythic | `astral` | Starfall Archive | Epic |
| Wonders | `kitsune` | Foxfire Masquerade | Rare |
| Wonders | `mimic` | The Gilded Maw | Rare |
| Wonders | `lotus` | Lotus Dream | Uncommon |
| Wonders | `clockwork` | Clockwork Seraph | Uncommon |
| Elven | `darkelf` | Nightglass Court | Uncommon |
| Elven | `woodelf` | Heartwood Covenant | Common |
| Elven | `highelf` | Starglass Dominion | Rare |
| Divine | `elysia_ascendant` | Elysia Ascendant | Legendary |
| Divine | `sepulchure_unbound` | Sepulchure Unbound | Legendary |
| Divine | `drakath_incarnate` | Drakath Incarnate | Legendary |
| Companions | `lanternwake` | Lanternwake | Uncommon |
| Wonders | `glasswing` | Glasswing Reverie | Uncommon |
| Wonders | `porcelain` | Porcelain Tempest | Uncommon |
| Mythic | `firstflame` | Crown of the First Flame | Legendary |
| Mythic | `unwritten` | The World Unwritten | Mythic |
| Mythic | `laststar` | Cathedral of the Last Star | Mythic |
| Bestiary | `tynfdarius` | Emperor of the Caldera | Epic |
| Bestiary | `mechaknight` | The Iron Apocalypse | Epic |
| Bestiary | `umbracrown` | Garden of the Petrified | Legendary |
| Bestiary | `deimos` | Chains of the Dread King | Legendary |
| Bestiary | `voiddragon` | Sovereign of the Rift | Legendary |
| Bestiary | `nullstar` | Hunger Beyond Heaven | Mythic |
| Wonders | `boneglass` | Boneglass Requiem | Epic |
| Wonders | `drownedpearl` | Pearl of the Drowned | Legendary |
| Mythic | `worldheart` | Anvil of Creation | Mythic |
| Wonders | `sandreign` | Empire in the Hourglass | Epic |
| Wonders | `emberkettle` | The Last Warm Hearth | Common |
| Companions | `mossback` | Mossback Caravan | Common |
| Companions | `brassbeak` | Brassbeak Post | Common |
| Companions | `moonharvest` | Moonberry Harvest | Common |
| Wonders | `stormheron` | Heron of the Thunder Marsh | Uncommon |
| Companions | `velvetprowl` | Velvet Prowler | Uncommon |
| Companions | `emberbloom` | Emberbloom Sanctuary | Uncommon |
| Wonders | `tideweaver` | The Tideweaver | Uncommon |
| Wonders | `amberreliquary` | The Amber Reliquary | Rare |
| Companions | `frostgardener` | The Frost Gardener | Rare |
| Mythic | `leviathanswake` | The Leviathan's Wake | Epic |
| Mythic | `gravebloom` | Where Titans Sleep | Epic |
| Mythic | `allworlds` | Covenant of All Worlds | Mythic |
| Journeys | `cloverpony` | Cloverhoof Meadow | Common |
| Journeys | `breadandembers` | Bread and Embers | Common |
| Journeys | `silverhook` | Silverhook Landing | Common |
| Journeys | `coalwhisker` | Coalwhisker Mine | Common |
| Journeys | `patchworkcamp` | Patchwork Camp | Common |
| Journeys | `thimbleguard` | The Thimble Guard | Common |
| Journeys | `jadeapothecary` | The Jade Apothecary | Uncommon |
| Journeys | `silkroadwyrm` | The Silkroad Wyrm | Uncommon |
| Journeys | `bellkeeper` | The Bellkeeper | Uncommon |
| Journeys | `inkfin` | Inkfin Atelier | Uncommon |
| Journeys | `gildedrook` | The Gilded Rook | Uncommon |
| Journeys | `auroraferry` | Aurora Ferry | Uncommon |
| Relics | `rubyforge` | The Ruby Forge | Rare |
| Relics | `opalunicorn` | The Opal Unicorn | Rare |
| Relics | `amethystbastion` | Amethyst Bastion | Rare |
| Relics | `honeycrown` | Court of Honey | Rare |
| Relics | `duskmoth` | Duskmoth Reliquary | Rare |
| Relics | `thundercolossus` | The Thunder Colossus | Epic |
| Relics | `sableopera` | The Sable Opera | Epic |
| Relics | `coralcitadel` | The Coral Citadel | Epic |
| Relics | `dawnpegasus` | Wings of the First Dawn | Epic |
| Eternities | `seraphimvault` | The Seraphim Vault | Legendary |
| Eternities | `winterregent` | The Winter Regent | Legendary |
| Eternities | `gravepony` | The Graveborn Foal | Legendary |
| Eternities | `opalodyssey` | The Opal Odyssey | Legendary |
| Eternities | `dreamsovereign` | Sovereign of Dreams | Mythic |
| Eternities | `eternityloom` | The Eternity Loom | Mythic |
| Transcendent | `sunweaver` | Genesis of the Sun | Transcendent |
| Transcendent | `nightpalace` | The Velvet Singularity | Transcendent |
| Transcendent | `worldtreeheart` | The Worldtree's Heart | Transcendent |

## Player commands and collection browser

Use your server's command prefix in place of `$` if different.

- `$prpg themes` (or `$prpg wardrobe`) shows only owned themes and their collections.
- Locked names, descriptions, source hints, and artwork stay hidden so discoveries are a surprise.
- Successful drops immediately announce the awarded theme's name and rarity, with preview and equip commands. Ice Dragon announces each recipient's reward as it is granted.
- **Preview full card** and `$prpg preview <theme>` only preview owned themes.
- **Equip theme** or `$prpg theme <theme>` saves an owned theme. Names and aliases work too.
- **Claim progress** refreshes ownership and claims free starter themes.
- `$prpg theme classic` restores the original appearance.
- `$prpg` shows your saved theme; `$prpg @user` shows that player's saved, owned theme.

All seven Origins themes are free. The other 83 themes come from gameplay drops or GM/event grants. Ownership is permanent for the character; changing stats or gods does not remove it. Character deletion removes ownership through the database foreign key.

The browser is owner-only and expires after five minutes. The server checks ownership again for previews and equips, including stale buttons. Previewing never equips. Menus stay below Discord option and embed limits.

## GM and event rewards

`$gmprpgtheme @player <theme>` permanently grants one theme, without equipping it.
It uses the existing `is_gm` permission check. Grants record their timestamp and
`gm:<issuer_id>` source and are idempotent. No awards were issued during development.

`$gmtranscendent @player` grants one random Transcendent theme the player does not own yet, announced like a drop. It never picks a duplicate and says so when the player already owns all three. Same `is_gm` check and `gm:<issuer_id>` source.

An event cog can call `grant_theme(bot.pool, user_id, THEMES[key], "event:<event-id>")`
from `cogs.profile.theme_unlocks` when issuing its rewards. Drop sources and rarity
weights live in `COLLECTIBLE_THEMES`; per-activity rates live in `DROP_CHANCES`.
Already-recorded ownership is preserved when drop settings change.

### Event themes

Step-by-step instructions for GMs: [EVENT_THEMES_GUIDE.md](../../EVENT_THEMES_GUIDE.md).

GMs and admins can add event-only themes without touching any other file. Open
`cogs/profile/themes.py`, find the **EVENT THEMES** section and add an entry:

```python
EVENT_THEMES = (
    event_theme(
        "harvest2026", "Harvest Moon Festival",
        accent="#f2a65a", event="Harvest Festival 2026",
        emoji="🎃", motif="lantern",   # optional
    ),
)
```

Only the key, name, accent colour and event name are required. The rest of the palette
is derived from the accent. Optional artwork goes in `assets/profile_themes/<key>.png`.
Without art, the banner is plain. Reload the Profile cog; a typo raises a clear error.

Event themes appear in an **Events** wardrobe collection. They never drop and are never
auto-claimed. Bot owners and GMs can use:

- `$gmeventtheme list` shows every event theme and whether its art is installed.
- `$gmeventtheme preview <theme>` renders it on your own card without granting it.
- `$gmeventtheme give @a @b 1234567890 <theme>` awards it to several players at once (mentions or IDs).

Add `profile_flag="column"` to unlock a theme automatically for every player whose
`profile.column` BOOLEAN is true. The column is created (default false) on cog load
when missing. The claim is recorded as `event-flag:<column>` and stays permanent.
A disabled example using the Halloween `spookyclass` column is in the section.

Event cogs can call `await grant_event_theme(bot.pool, user_id, "harvest2026")` from
`cogs.profile.theme_unlocks`. Never delete or rename an awarded event theme: owners
would fall back to the classic card.

## Deployment and storage

Deploy the modified Adventure, Battles and Profile cogs, `themes.py`, `theme_picker.py`, `theme_unlocks.py`,
and the banner/font files under this directory. Reload the Profile extension or
restart the bot. Its existing database role needs DDL permission, as before.

`Profile.cog_load` idempotently adds `profile.prpg_theme` if needed and creates
`profile_theme_unlocks` with a unique `(user_id, theme_key)` key. The migration uses
an advisory transaction lock to serialize first-time creation across shards.
Players who already have one of the six original illustrated themes equipped
keep that theme through a `legacy-equipped` grant. All seven Origins starter
themes are automatically claimed when ownership is synchronized.

No live PostgreSQL schema or Discord bot was changed during development. Verify
against your deployment after reloading. No new runtime Python package is required.

Unlock claims and equips lock the character row in a transaction; all user values
are SQL parameters. Unknown/unowned stored selections render as classic. Missing
or corrupt artwork falls back to a matching background while preserving the stats.

## Rendering and artwork

Themed output stays at 1660 x 1460 PNG, classic at 1660 x 940. Every illustrated
card now has motif-specific ornaments, a decorated avatar ring, collection/rarity
information, an XP progress strip and wealth/XP ranks. The original six receive
the same visual upgrades. Existing character, item, pet and combat calculations
are preserved. The classic appearance remains unchanged.

All 59 banners are paintings made with the built-in imagegen tool. Exact
prompts are in [prompts.json](prompts.json) for the launch six and
[expansion-prompts.json](expansion-prompts.json) for the first 21 additions, and
[god-reference-prompts.json](god-reference-prompts.json) for the three god variants.
The previous six prompts are preserved in [ascendant-prompts.json](ascendant-prompts.json).
The previous ten prompts and monster reference mappings are in [legends-prompts.json](legends-prompts.json).
The previous thirteen prompts are in [covenant-prompts.json](covenant-prompts.json).
Bestiary references are Avatar Tynfdarius, Mech-a-Knight and Umbracrown Basilisk (tier 9),
and Deimos, Void Dragon and Nullstar Behemoth (tier 10). Their original images were
inspected and supplied to imagegen to retain their recognizable designs.
The Exalted god set uses the tier-11 image references from `monsters.json`:
Elysia's black hair, white/crimson robes and golden phoenix throne; Sepulchure's
crimson DoomKnight armor and skull sword; Drakath's orange eyes, horned shoulders,
purple chest eye and black cloak. Source URLs and downloaded reference images are
preserved under `references/` for provenance and are not needed at runtime. Fonts are
Cinzel and Lato from Google Fonts, with SIL Open Font Licenses under `fonts/`.

Prismatic decoration is applied automatically when a prismatic theme is equipped or previewed by its owner.
It stays cosmetic, uses the existing image dimensions, and keeps all stat panels, bars and avatar pixels visible.
Its frame is rendered locally in Python; no additional database columns or player settings are required.

Everything loads locally at runtime; no image-generation API is called. At most six
standard banners and three Transcendent art panels are cached, never composed player cards.

The new artwork was generated with the built-in ImageGen tool and saved in this directory.
[Transcendent prompts](transcendent-prompts.json) include the Worldtree aspect-ratio correction;
[Odyssey prompts](odyssey-prompts.json) contain all 27 additional concepts.

## Preview gallery and validation

[Inspect the three remastered Transcendent folios](previews/transcendent-showcase.jpg) and
[the 27 new banners](previews/odyssey-showcase.jpg).

[Open the local gallery](previews/index.html) or [overview](previews/collection.jpg).
Individual full cards and collection contact sheets are in `previews/`.
[The previous thirteen banners](previews/covenant-showcase.jpg) have their own review sheet,
including a full-width Mythic spotlight. [Covenant's complete card](previews/allworlds.png)
shows the exclusive finish. The previous [ten-theme showcase](previews/legends-showcase.jpg) remains available.
Samples use fictional character data and placeholder avatar/pet portraits.
Preview files are review artifacts and are not required by the live bot.

Regenerate samples with `python scripts/render_profile_theme_previews.py`
(requires the test dependencies). The script runs the production card renderer.

Run `python -m pytest tests/test_profile_themes.py tests/test_profile_theme_unlocks.py -q`.
Tests exercise full-card rendering, font/assets, aliases, fallback/cache behavior,
real Discord command routing, every unlock boundary, persistent ownership,
idempotent/concurrent claims, grants, stale equips, owner-only UI and Discord limits.
