# Custom GM nodes

A node pack is a reusable mechanic made from 1–30 connected Advanced raid steps.
For example: a guild gate, a pressure puzzle, a ritual, a multi-phase boss, or a
branching conversation. It carries its actions, meters, roles, teams and statuses.
It expands into editable steps when inserted, so a GM can change every part.

## Make one without coding

1. Open an Advanced draft's **Visual Canvas**.
2. Build the steps and rules for the mechanic.
3. Open **Node Library**, name the pack, select its connected steps and choose an
   entry. **Save Selected Steps** keeps a copy in this browser.
4. Expand the saved pack and click **Download Node**.
5. Attach the `.node.json` file to `$raidmode node import my_puzzle` to save it
   privately in your persistent GM library.
6. Use `$raidmode node publish my_puzzle` when ready to share that version.

Canvas copies are local files/browser storage until imported. The HTML editor
cannot directly publish to Discord. Shared nodes are visible to all GMs using
this bot, across servers. Do not include unreleased story details you want private.

Existing Discord steps can also be saved directly:

```text
$raidmode node save my_raid gate,pressure_check my_puzzle
```

The first step ID is the entry. Select all connected steps belonging to the pack;
every selected step must be reachable from the entry. Outgoing success links
become `$next` ports and failure links become `$failure` ports. Fix broken links
before saving. Catalogues are copied from the raid, so check that any enemy-specific
actions refer to enemies included in the pack; remove unrelated entries from the
downloaded pack if necessary. Collections remain subject to normal engine limits.

## Have AI make one

Download the prompt using **Download AI Prompt** in Canvas or:

```text
$raidmode node prompt
```

Send [NODE_AUTHORING_PROMPT.txt](NODE_AUTHORING_PROMPT.txt) and your mechanic idea to
your AI. Save its JSON response as `my_puzzle.node.json`; import it into Canvas or
attach it to `$raidmode node import my_puzzle`. The command also provides a working
Guild Beacon example. People who prefer editing JSON can use the same format.

The prompt lists the schema, effects, limits, targets, conditions and supported
Fable connections. AI output receives the same engine validation as other imports.
Unknown step types, effects and Fable sources are rejected. Import does not publish.

## Reuse and share

```text
$raidmode node list
$raidmode node list 2
$raidmode node add my_raid my_puzzle
$raidmode node add my_raid my_puzzle arrival
$raidmode node export my_puzzle
$raidmode node publish my_puzzle
$raidmode node unpublish my_puzzle
$raidmode node delete my_puzzle
```

Use your server's actual prefix. `node list` shows your private work and published
community packs, ten per page. Omit the last argument of `node add` to insert before
the raid start. Supply a step ID to insert after its Next output. Choice and ending
steps cannot be insertion anchors. The new pack's Next port reconnects to the old
destination; its Failure port uses the anchor's failure link, otherwise the first
defeat ending, otherwise the continuation. Review links and simulate afterward.

Canvas's Node Library includes your library and community versions as of download
time, within a 2 MB library snapshot budget. If some packs do not fit, the editor
explains how to export them individually. Download a fresh canvas to get new releases,
or import an exported node file. `$raidmode canvas <draft_id>` sends the HTML by DM
because it contains your private nodes; the builder's Visual Canvas > Edit download
is private to you and works when DMs are blocked.
On insertion, internal IDs are remapped. Meters, statuses and actions get separate
copies for each insertion; identical teams and roles can be reused. Normal raid
limits apply: 100 steps and 25 entries per actor/action/meter catalogue.

Saving changes to a published pack updates your private working copy. Other GMs
continue receiving the last published version until you publish again. Only the
creator can edit, publish, unpublish or delete that library entry. Other GMs can
export it and import under a new ID to create their own version. Inserted copies
never auto-update. Unpublishing/deleting a pack does not remove existing copies.

There are **100 node packs per GM**, independent of the **5 saved raids and 10
drafts** shared across Normal/Advanced. Node packs work in Advanced raids. Neither
importing nor publishing a node activates or launches a raid.

## Connect to Fable or invent a mechanic

Add a **System** step, select a Fable data source and an output meter. The available
sources are total character levels, average character level, number of players
belonging to a guild, and number of distinct party guilds. Data is read once from
the joined characters at raid start. It is clamped to the meter's bounds, then
ordinary conditions and rules can use it. Set suitable meter bounds for your party.
For example, read guild membership, check whether the meter is at least one, and
route to an allied guard or an ambush.

Simulations use each System step's **Simulated value**, labelled in the trace.
Unavailable live data follows the Failure output; live play never substitutes
the simulation value. These sources read data and do not change characters.

New raid-local systems can be built from meters, actions, statuses, conditions,
votes and transitions: reputation, keys, crafting progress or a boss's rage.
They last for the current raid. Node files cannot install arbitrary code, run
commands, query SQL, call URLs, award extra currency or persist new global systems.
A new game integration needs a supported adapter added to the bot first.

For developers, register read-only sources in `integrations.SYSTEM_SOURCES`, return
their values from `load_system_values`, expose them in `canvas_nodes.js` and the AI
prompt, and test live/missing/simulation behavior. Economy writes or new permanent
progression systems require their own server-side design and authorization; they
are not inferred from a file's fields. Full engine validation runs on node import,
insertion, raid publication and launch. Canvas checks are an early preview.

Storage uses the existing PostgreSQL registry and compare-and-swap revision checks.
No new table or manual migration is needed: older registries start with an empty
node library. A bot reload/deploy is required to expose the new commands.
