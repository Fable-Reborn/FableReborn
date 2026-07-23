# Soulforge Frontiers

Soulforge Frontiers is a self-contained PvE and collection update built on the
existing monster, Soulforge, and battle systems. It adds a four-week regional
rotation, a curated 48-splice encounter roster, weekly research objectives and
bosses, a stable Bestiary/Archive, lineage tracking, and permanent milestones.

The update does **not** change the campaign engine, races, classes, class
balance, pet elements, or pet skill trees. Existing class and battle modifiers
continue to work through the normal PvE code; Frontiers does not define a new
parallel combat ruleset.

## Player loop

1. Use `$frontier` or `$frontier forecast` to see the active weekly region.
2. Use `$pvelocations` and `$pveinfo <region id>` to check its level gate and
   tier rates, then choose that region through the normal `$pve` flow.
3. Defeat featured regulars and elites until all three research objectives are
   complete:

   - 5 featured regular victories;
   - 3 different featured regular or elite species defeated; and
   - 1 featured elite victory.

4. Use `$frontier boss` to challenge that rotation's boss. A successful clear
   is recorded once for the rotation and uses the normal 30-minute PvE
   cooldown.
5. Use `$frontier claim` to claim the weekly reward once.
6. Keep exploring, collecting eggs, creating splices, following lineages, and
   filling permanent Bestiary, Archive, and milestone records.

Only curated encounters from the currently active region count toward the
weekly objectives. Scouting, sightings, regional wilds, inactive regions, and
ordinary PvE victories do not advance them. A player below the active region's
level requirement is shown the lock and receives no impossible weekly
objectives.

The once-per-rotation reward is transactional:

- 15,000 money;
- 1 Materials Crate; and
- up to 5 Soulforge condition, capped at 100, when the player has already built
  a Soulforge.

Failure partway through the database transaction grants none of the reward,
and concurrent claim attempts cannot grant it twice.

## Player commands

`$frontier` is also available as `$frontiers`.

| Command | Purpose |
| --- | --- |
| `$frontier` | Interactive four-tab regional dashboard with showcase artwork, research, rotation, and guide pages. |
| `$frontier forecast` | Current and next three regions, dates, and personal level locks. Aliases: `rotation`, `regions`. |
| `$frontier progress` | Exact objective, boss, and reward state for this rotation. Aliases: `weekly`, `objectives`. |
| `$frontier bestiary [page]` | Opens on collection totals, then browses all approved wild species with a page selector and navigation buttons. Unknown identities stay concealed. Alias: `wilds`. |
| `$frontier archive [page]` | Opens on Archive totals, then browses splice species the player has encountered, created, or held with interactive pagination. Aliases: `splices`, `codex`. |
| `$frontier lineage <creature>` | Known parent recipes and immediate descendants. Alias: `tree`. |
| `$frontier track <creature>` | Track one splice as a personal creation target. With no argument it shows the current target; use `clear` to stop. Alias: `target`. |
| `$frontier boss` | Challenge the unlocked active regional boss through the existing PvE battle. Alias: `challenge`. |
| `$frontier claim` | Claim the successful weekly clear reward once. Alias: `reward`. |
| `$frontier milestones` | Permanent splice discovery, creation, lineage, generation, and weekly boss-clear milestones. Alias: `achievements`. |

The existing `$pvelocations`, `$pveinfo`, `$pve`, and `$scout` commands expose
the current region and its encounter pool. Inactive Frontier regions are omitted
from the standard PvE location lists, and the active region has a `⚡` surge
marker beside its normal unlocked or locked status.

## Four-week rotation

Rotation boundaries are Monday at 00:00 UTC. The checked-in anchor is
2026-07-13 00:00 UTC; after the fourth week, the order repeats.

| Cycle week | Region | Unlock | Rolled tiers | Regional wild elements |
| --- | --- | ---: | --- | --- |
| 1 | Floodroot Basin (`floodroot_basin`) | Level 1 | 1-3 | Water, Nature |
| 2 | Stormbreak Reach (`stormbreak_reach`) | Level 20 | 3-5 | Wind, Electric |
| 3 | Dawnscar Expanse (`dawnscar_expanse`) | Level 40 | 5-7 | Fire, Light |
| 4 | The Fractured Verge (`fractured_verge`) | Level 60 | 7-10 | Dark, Corrupted |

Every unlocked region remains visitable. Its ordinary pool contains public base
monsters whose tier and element fit that region. During its active week, the
region additionally receives its eleven featured regular/elite splices. The
regional boss is never put into the random encounter pool; it is resolved only
after `$frontier boss` verifies the player's objectives.

Do not reorder the rotation or change its anchor in the middle of a live week.
Weekly progress is keyed by the deterministic absolute rotation week, so
schedule changes should be deployed on a boundary with an explicit migration
decision.

## Curated 48-splice roster

[`data/frontier_roster.json`](data/frontier_roster.json) is the runtime content
contract. Each of the four regions contains exactly:

- 9 regular Generation 0 splices;
- 2 elite Generation 1-3 splices; and
- 1 separately gated `[FINAL]` boss.

That gives 36 regulars, 8 elites, and 4 bosses: 48 curated recipes in total.
Legacy `splice_combinations.id` values identify the exact recipes, while stable
catalog recipe/species IDs protect player records from display-name ambiguity.

Regular Generation 0 entries are egg-eligible. Elites and bosses never drop
eggs. A tier is rolled first using the region's configured tier weights, then a
monster is selected using its within-tier encounter weight. Consequently, an
entry's raw weight is not its overall encounter percentage.

Stored legacy splice stats are not trusted directly for PvE balance. Each
featured creature is scaled toward the public monster median for its assigned
tier, bounded to a safe profile, and then given its role multiplier. Elites get
1.35x HP and 1.10x Attack/Defense; bosses get 2.25x HP and 1.20x
Attack/Defense. Existing per-encounter PvE level scaling still applies after
this normalization.

Roster loading is deliberately strict. Invalid region IDs, duplicate recipe
IDs, unreachable tiers, bad role counts, an egg-eligible elite/boss, or a boss
without `[FINAL]` rejects the Frontier configuration. Live database drift is
also checked: missing recipes, renamed results, and generation mismatches are
skipped and logged instead of silently substituting a different monster.

## Stable catalog and migrations

`cogs.frontier_catalog` must load before the player-facing Frontiers cog. Its
first load performs an additive, idempotent PostgreSQL migration and imports
the existing `monsters.json`, `splice_combinations`, pets, and eggs under a
transaction-scoped advisory lock.

The catalog adds these tables:

- `frontier_catalog_migrations` — migration/import record;
- `frontier_species` — stable wild, splice, and legacy-reference identities;
- `frontier_species_sources` — legacy source snapshots;
- `frontier_recipes` — canonical unordered parent pairs plus preserved outcome
  variants;
- `frontier_discovery_ledger` — append-only, retry-safe discovery events; and
- `frontier_discoveries` — efficient per-player discovery projection.

The gameplay cog adds:

- `frontier_weekly_progress` — per-player rotation objectives, boss clear, and
  claim state;
- `frontier_weekly_defeats` — deduplicated qualifying battle events; and
- `frontier_lineage_tracks` — one active personal lineage target per player.

Nullable foreign-key links are added to the legacy tables without replacing
their current names or behavior:

- `monster_pets.frontier_species_id`;
- `monster_eggs.frontier_species_id`; and
- `splice_combinations.frontier_recipe_id`,
  `frontier_parent1_species_id`, `frontier_parent2_species_id`, and
  `frontier_result_species_id`.

Legacy rows are never deleted or renamed. Conflicting outcomes for the same
parent pair remain separate recipe variants, with one deterministic primary
used for old records that cannot distinguish the variant. Discovery writes use
per-player deduplication keys, and weekly reward state is locked in the same
transaction as its currency/crate/repair updates.

At the initial development migration, the import verified 1,583 stable species
identities and 1,435 legacy recipe rows (1,433 canonical parent pairs), with no
unlinked pets, eggs, or splice rows. These figures are a dated verification
snapshot, not hard-coded runtime limits; subsequent content and player-created
splices can increase them. Activating the eight new base monsters raised the
development catalog to 1,591 species while retaining all 1,435 recipes and zero
unlinked legacy rows. The four Fractured Verge additions bring the equivalent
checked-in catalog seed to 1,595 species; production counts are reported by the
catalog synchronisation at startup.

## Twelve new base monsters: live

[`data/new_monsters_staging.json`](data/new_monsters_staging.json) contains twelve
new regional splice roots and their activation record. The first eight were
delivered and activated on 2026-07-16; four Fractured Verge roots followed on
2026-07-24. All twelve have public Frontier-only runtime records in
`monsters.json`, appear as permanent wild encounters exclusively in their
assigned region, can drop eggs, and can serve as Generation 0 Soulforge parents.
They are excluded from every ordinary PvE location.

| Monster | Region | Tier | Element | Suggested asset |
| --- | --- | ---: | --- | --- |
| Bloomback Tortoise | Floodroot Basin | 1 | Nature | `bloomback_tortoise.png` |
| Tidereef Kelpie | Floodroot Basin | 3 | Water | `tidereef_kelpie.png` |
| Galecrest Lynx | Stormbreak Reach | 3 | Wind | `galecrest_lynx.png` |
| Voltscale Pangolin | Stormbreak Reach | 3 | Electric | `voltscale_pangolin.png` |
| Cloudray | Stormbreak Reach | 5 | Wind | `cloudray.png` |
| Arcglass Mantis | Stormbreak Reach | 5 | Electric | `arcglass_mantis.png` |
| Cinderhorn Ram | Dawnscar Expanse | 5 | Fire | `cinderhorn_ram.png` |
| Dawnveil Moth | Dawnscar Expanse | 7 | Light | `dawnveil_moth.png` |
| Gloamspine Jackal | The Fractured Verge | 7 | Dark | `gloamspine_jackal.png` |
| Riftmolt Scarab | The Fractured Verge | 8 | Corrupted | `riftmolt_scarab.png` |
| Umbracrown Basilisk | The Fractured Verge | 9 | Dark | `umbracrown_basilisk.png` |
| Nullstar Behemoth | The Fractured Verge | 10 | Corrupted | `nullstar_behemoth.png` |

On 2026-07-24, all twelve new wilds received a 66% increase to HP, attack, and
defense. Runtime and staging values are 166% of their approved baselines, rounded
to the nearest integer.

The complete shared art direction and twelve individual prompts are in
[`data/new_monster_image_prompts.md`](data/new_monster_image_prompts.md). The
prompt file is retained as the visual reference for future replacements or
variants.

### Safe artwork activation checklist

This checklist was completed for the first eight monsters on 2026-07-16 and the
four Fractured Verge monsters on 2026-07-24. It is kept as the repeatable
procedure for future artwork additions or replacements.

1. Generate each monster separately from its named prompt. Supply the original
   square PNG at 1024x1024 or larger, preferably with transparency, and keep the
   suggested filename.
2. Review the full-resolution image and a Discord-embed-size preview. Confirm
   an original design, one complete creature, readable silhouette, no cropped
   anatomy, no extra creature, and no text, logo, signature, or watermark.
3. Test the transparent asset on both light and dark backgrounds. If the source
   has a flat fallback background, remove it cleanly before publishing.
4. Upload the approved PNG to a durable public HTTPS location that Discord can
   fetch. Do not use a temporary attachment/session URL.
5. Put that permanent URL into the matching staging record, but leave the
   staging file and its records disabled/private during review.
6. Revalidate every staged assignment against the roster: the `region_id` must
   exist, its `element` must belong to that region, and its `tier` must be one
   of that region's configured tier keys. Runtime selection enforces tier,
   element, and the explicit `frontier_region_id`; an exclusive assigned to a
   different region must never enter the pool.
7. Check names case-insensitively against every existing `monsters.json` wild
   and intended splice name. Do not activate a collision until its stable
   catalog identity and compatibility consequences are reviewed.
8. Only after all checks pass, copy this runtime shape into the matching tier
   array in `monsters.json`:

   ```json
   {
     "name": "Monster Name",
     "hp": 100,
     "attack": 100,
     "defense": 100,
     "element": "Element",
     "url": "https://durable.example/monster.png",
     "ispublic": true,
     "frontier_only": true,
     "frontier_region_id": "region_id"
   }
   ```

   Translate staging `region_id` into runtime `frontier_region_id`. Do not copy
   `content_id`, `enabled`, design notes, or field notes into the runtime object.
   Do not pre-seed these monsters into `monsters.json` as private placeholders:
   their first catalog import should be the reviewed, public Frontier-only record.
9. Parse both JSON files and run the validation suite before starting the bot:

   ```text
   python -m json.tool monsters.json
   python -m json.tool cogs/soulforge_frontiers/data/frontier_roster.json
   python -m json.tool cogs/soulforge_frontiers/data/new_monsters_staging.json
   python -m unittest tests.test_frontier_catalog tests.test_soulforge_frontier_pve tests.test_soulforge_frontiers_gameplay tests.test_soulforge_frontiers_progression -v
   ```

10. Restart the bot for the safest activation. A controlled hot reload must
    reload `cogs.frontier_catalog` so the new stable wild identities are
    imported and reload `cogs.battles` so its cached `monsters.json` pool is
    rebuilt; then reload `cogs.soulforge_frontiers`.
11. Smoke-test `$pvelocations`, `$pveinfo <region id>`, `$frontier`, the Bestiary,
    and a development-account encounter in each affected tier. Confirm there
    are no roster-drift warnings, the new wild is recorded under the intended
    stable species, and no Frontier-only wild appears in an ordinary PvE zone.

## Operational rollout

1. Take a database snapshot before the first production migration.
2. Deploy the catalog, Frontier data/helpers, gameplay cog, Battles integration,
   Soulforge creation event hooks, and configuration together.
3. Run the JSON/unit checks above. A bad checked-in roster should stop Frontier
   content from loading rather than be bypassed.
4. On a full restart, ensure `cogs.frontier_catalog` completes before
   `cogs.soulforge_frontiers` is set up. If loading manually, use catalog first,
   Frontiers second, and reload Battles after any `monsters.json` change.
5. Review startup logs for catalog import counts, migration errors, and Frontier
   roster-drift warnings.
6. Smoke-test with both a level-unlocked and level-locked development account.
   Verify weekly progress deduplication, one boss clear, one claim, crate and
   money changes, and Soulforge repair at both ordinary and near-100 condition.
7. Check the next Monday 00:00 UTC boundary: active location, forecast, fresh
   objective row, boss gate, and previous reward state must remain separate.

## Rollback

- For an application rollback, revert the Frontiers/Battles/event-hook changes
  and remove the player-facing extension from the load list, then restart or
  reload Battles. Unloading only the player-facing cog is insufficient because
  an already-loaded Battles cog retains its configured Frontier locations.
- Leave the additive catalog, discovery, weekly, and lineage tables and nullable
  legacy link columns in place during an incident rollback. Older code ignores
  them, while retaining them preserves identities and player history for a safe
  re-enable.
- For a bad roster release, restore the last verified
  `frontier_roster.json` and reload Battles plus the Frontiers cog. Do not edit
  legacy `splice_combinations` rows to make them fit the roster.
- For a newly activated wild that must be withdrawn, set its runtime
  `monsters.json` record to `ispublic: false` and restart/reload Battles. Do not
  delete pets, eggs, catalog species, or discovery history already created from
  it. If it must also disappear from the Bestiary, retire/hide the catalog
  species in a reviewed migration instead of deleting its stable ID.
- The untouched campaign, race, class, and pet-skill systems require no rollback
  or data migration for this update.
