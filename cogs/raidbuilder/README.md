# Persistent GM raid builder

Each GM has **5 saved (published) raids and 10 drafts total**, shared across Normal
and Advanced, and across Good/Evil/Chaos. Limits are per Discord user, not per
server. A draft consumes a draft slot; publishing it moves it into a saved slot.
Starter templates and imported legacy raids with no recorded creator are shared
templates and do not consume anyone's personal slots.

## Open and create

Use your bot's command prefix (examples below use `$`):

```text
$raidmode builder
$raidmode create evil moon_expedition advanced
$raidmode builder evil moon_expedition
```

`$raidbuilder` is also an alias for `$raidmode`. In the panel, **New Draft** accepts
`trial`, `ritual`, `attrition` (Normal) or `advanced`. IDs must be unique across the
bot. The suggested ID includes your user ID; change its ending to name additional
raids. **Copy / Revise** copies a template or saved raid into your own editable draft.

Reopening without arguments resumes your last mode, raid, page and item for that
server. Explicit mode/raid arguments override the remembered selection. Expired
Discord panels still require opening a fresh panel.

## Save, publish and revise

- Submitted edits and structural changes autosave to PostgreSQL before success is
  acknowledged. The footer shows your saved and draft counts.
- **Publish** validates an Advanced encounter, consumes a saved slot and frees its
  draft slot. A saved raid is edited through **Copy / Revise**.
- Revising one of your saved raids consumes a draft slot. Publishing that revision
  replaces the same saved raid, so it works even when all five saved slots are full.
  Its existing active-mode binding is preserved. Running raids use a deep copy and
  retain their original rules.
- To make a separate raid instead, use **New Draft**. Copying another GM's raid or
  an unowned template also makes a separate personal raid.
- **Activate** selects the saved raid for its Good/Evil/Chaos route. There is still
  one global active raid per mode. Activation does not launch a raid.
- **Delete** removes your selected raid and frees its slot. Deleting an active raid
  clears that mode's route. Shared templates cannot be deleted from a personal panel.
- `$raidmode unpublish <id>` moves your saved raid back into the draft library and
  clears its active route; it requires a free draft slot.
- Two editors cannot silently overwrite each other. An outdated panel/form asks
  you to reopen it. A revision based on an older saved version cannot overwrite a
  subsequently published revision.

Run custom routing with `$raidmode good`, `$raidmode evil`, or `$raidmode chaos`.
The original `$goodspawn`, `$evilspawn`, and `$chaosspawn` remain their separate
legacy implementations. Legacy Chaos routing still requires boss HP; a custom
raid can use its configured HP. Existing command permissions are retained.

## Advanced authoring

Use **Structure** to add, duplicate, remove and reorder entries. **Edit** opens
selectors for typed settings and **Details** for text/numbers. No JSON or code is
required. Longer collections and destination menus have pagination.

| Page | Purpose |
| --- | --- |
| Overview | Name, description, player health, join and decision timers |
| Flow | Starting step, scene pacing and execution limit |
| Steps | Scenes, battles, votes, trials, conditional checks and endings |
| Step Links | Next/success and failure/tie/timeout destinations |
| Battle / Trial | Boss health/damage, battle round cap, trial success chance |
| Step Condition | Subject, comparison and threshold for a check step |
| Resources | Shared, named bounded meters such as corruption or ritual progress |
| Player Actions | Effect, target, amount and optional shared-resource cost |
| Choices | Voting options and their destination steps; first make a Choice step |
| Rules: When / If | Trigger, comparison and maximum firings per raid |
| Rules: Do | Effect, target, amount, resource or transition destination |
| Rewards | Existing gold/dragon-coin/crate reward settings, paid on victory |
| Validate / Simulate | Reproducible simulation with a chosen player count and seed |

Available rule triggers are step entry, round start/end and choice resolution.
Conditions inspect round number, living-player count, boss HP/HP percentage or a
named shared resource. Effects deal damage, heal, shield, adjust resources, damage
or heal the boss, narrate, or transition to another encounter step.

Example: on **Rules: When / If**, choose **Round end**, **Boss HP %**, **<=**, `50`,
and firing limit `1`. On **Rules: Do**, select that same rule, choose **Transition**
and the **Eclipse** destination created on Steps. The battle changes phase when the
threshold is reached. Give Eclipse its own battle settings, actions/rules and links.
Player actions are currently shared across all battle steps.

Rules execute in their displayed order. The first matching transition stops further
rules for that trigger. Resource meters and player health/shields persist between
steps; entering a battle initializes that battle's boss health and round counter.
Rule firing counts persist throughout the raid, including revisited steps. A rule
whose firing limit is one is a once-per-raid rule, not once per visit.

Battle actions resolve in participant order, spending shared resource costs in that
order. Missing/unaffordable choices use the first free action. Player effects cannot
revive eliminated players. `Self` refers to the acting player; for encounter rules,
which have no player actor, it uses the first living participant. Boss attacks choose
one random survivor. Votes use the unique highest vote count; ties/no valid votes
take the configured failure link. Defeat occurs immediately when nobody survives.

Trial steps roll one party-wide success check. Branching Check steps inspect state
without a roll. `round` is zero on a non-battle step; use a resource when carrying
progress between steps. Simulations use the same engine, make random valid player
choices, and award no rewards. They are a functional preview, not a balance estimate.

Drafts may temporarily contain broken links while being edited. Publishing/running
validates references, resource bounds, action costs, a free fallback action, and a
path to an ending from every reachable step. Execution is bounded even when a GM
creates a conditional loop. Limits: 100 steps, 100 rules per step, 25 shared resources,
25 actions, 25 choices per voting step, 100 rounds per battle, 1,000 engine steps.

## Storage and migration

`RaidBuilder.cog_load` creates two tables using the existing `bot.pool`:

- `raid_builder_registry`: the shared registry and an optimistic revision counter.
- `raid_builder_preferences`: per-user/per-server navigation.

The first load imports `assets/data/raid_builder_registry.json` exactly once under
a PostgreSQL transaction/advisory lock. The source file is never rewritten. Existing
definitions, statuses and active-mode bindings are retained; no creator is guessed
for historical data. Subsequent loads use the database even if the checkout's JSON
changes. A malformed source or unavailable database must be repaired; the builder
does not silently overwrite it with defaults. Database backups must include these
tables. Deployment requires the bot database role to create these tables on first load.

Registry content uses JSON **TEXT**, preserving the dictionary order of existing
normal-mode actions. Schema upgrading preserves intentionally removed action entries.
The revision check covers the complete registry, so edits from different clusters
(even to different raids) can cause a safe stale-edit rejection. Preferences are
stored independently and do not invalidate content forms.

This first version does not checkpoint running raids across bot restarts, implement
reward replay/recovery, expose historical revision restore, provide a browser canvas,
or add custom teams/roles/status effects. It supplies a working bounded encounter
engine and Discord authoring interface that can be extended with those capabilities.

## Verification

Automated coverage:

```text
python -m pytest tests/test_raidbuilder_default_selection.py tests/test_raidbuilder_engine.py tests/test_raidbuilder_persistence.py -q
```

Tests cover normal regression behavior, combined quotas, preserved ordering/deletions,
failed saves, stale writers/forms, preference resume, saved-raid revision replacement,
editor controls, engine transitions and the live adapter's payout branch. Storage
tests use a shared async database double; they do not replace PostgreSQL integration
testing. No live Discord or production database was changed during development.

Before deploying, run the builder against a staging database and Discord server:
load twice to verify one-time migration, create/edit/publish an Advanced raid, restart
the bot and reopen the builder, then run a short zero-reward encounter. Confirm a
second bot process rejects a stale save. Backups and history in the old JSON remain
available for comparison; do not run an old file-only builder concurrently after migration.
