# Campaign Content Pipeline

## Workflow

1. A GM runs `$gmquest export` in Discord.
2. Open `assets/html/campaign_editor.html` locally in a browser.
3. Import the downloaded JSON package.
4. Edit campaigns, branching nodes, quests, cutscenes, monsters, encounters, requirements, and consequences.
5. Validate and download the updated package.
6. Attach it to `$gmquest import` in Discord.

Imports are validated and committed in one database transaction. Invalid packages do not partially update content.

## Player Commands

- `$campaign` shows the current chapter or available campaigns.
- `$campaign start <key>` begins a campaign.
- `$campaign choose <number>` records a branch choice.
- `$campaign reputation` shows faction reputation.
- `$quests` continues to show and turn in the active generated quest.

## Supported Requirements

Campaigns, nodes, quests, and branch transitions can require completed quests or campaigns, previous choices, reputation, level, class, god, race, money, guild membership, owned or equipped items, owned or equipped pets, badges, and campaign unlock keys.

## Encounters

Campaign encounters currently bridge to existing Discord battle commands through `launch_command`. Existing battle modes keep ownership of their lobby and combat rules. Party size is enforced when the battle source reports its participants, including dragon-party progression.

The JSON preserves a `settings` object for a future generic campaign battle runner. It is not currently applied to arbitrary custom combat.

## Consequences

Nodes and choices can grant permanent unlock keys and generic reputation changes. Quest rewards support money, crates, named items, monster eggs, no material reward, or a bundle of those rewards.

