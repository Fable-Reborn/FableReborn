# Changelog

All **dates and times are UTC** unless stated otherwise.

---

## Unreleased — 2026-11-20

| | |
|---|---|
| **Date** | 2026-11-20 |
| **Time (UTC)** | 03:40 |
| **ISO** | `2026-11-20T03:40:00Z` |

### Armory error cache / merch send failures

- `$armory` no longer keeps a stale page cache after merch, sell, equip, lock, or armor wear. The list reloads from the database so a sold piece cannot be merched again from the same embed.
- If Discord errors after the merchant already took the item, the player is told the action finished and the armory is refreshed instead of **Action failed** with the piece still shown.
- Merching the last item in a filter no longer blanks the whole armory as empty; Filters and Gear stay available.
- `$merchall` re-locks the same IDs before deleting, so a mid-sale inventory change cannot destroy extra gear. Discord is not sent while those rows are still locked.
- `$merge` upgrade + destroy runs in one transaction. Trader purchases drop the bought offer even if the success embed fails to send.
- Market buy is only treated as done if the buyer now owns the item. A listing vanishing because someone else bought it is still a failure.

### `$armory` / `$inventory` owner lock

- Only the player who opened `$armory` can use its buttons, item/action/sort selects, Filters, Inventory, Loadouts, Gear tab, and filter/market modals.
- `$inventory` category/item selects and consume modals are owner-only. Loadout select/rename modals are owner-only.
- A second player clicking a public menu gets an ephemeral **This armory isn't yours.** (or the inventory/loadout equivalent). No equip, merch, sell, drink, or preset apply runs.

### Gear shop stale price

- Relisting the same piece no longer lets a buyer confirm the old gold amount on an open stall.
- Buy reloads the live listing first, refreshes the stall, and confirms at the current price.
- Confirm charges only the agreed price. If the seller changes it again, the purchase is refused and nothing is taken.

### Crafting discovery

- Finding a piece unlocks only that slot, line, and rarity. A legendary Slayer helm does not teach the cuirass, greaves, or sabatons. Crafting does not teach patterns. Common starters are unchanged.
- On `$reload equipment`, extra `equipment_discoveries` rows from the old four-slot unlock are deleted unless the player actually found that piece (owned non-crafted item, crate event, or crate grant). `$gear recipesweep` dry-runs; `$gear recipesweep apply` deletes them.

### Crate armor rolls

- Gear rolls from crates reset each UTC day, not across a rolling 7-day pool. Daily caps stay 60 Common, 30 Uncommon, 20 Rare, 8 Magic, 4 Legendary. Extra crates still give a weapon only.

### Armory materials

- Five smithing goods per armor line, matching crate rarities. Higher crates can drop lower goods. Legendary goods only from Legendary crates and a lucky Abyssal Maw drop.
- Dragon party materials roll independently of the ice-dragon weapon drop (can get both, one, or neither). Stage chance ~12–28%, then one weighted good.

### Reload

- `$reload equipment` and `$reload profile` (plus `$reload crates`, `$reload help`, `$reload transaction` for copy) pick this up.
