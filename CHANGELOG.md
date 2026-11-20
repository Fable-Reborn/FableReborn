# Changelog

All **dates and times are UTC** unless stated otherwise.

---

## Unreleased — 2026-11-20

| | |
|---|---|
| **Date** | 2026-11-20 |
| **Time (UTC)** | 03:40 |
| **ISO** | `2026-11-20T03:40:00Z` |

### `$armory` / `$inventory` owner lock

- Only the player who opened `$armory` can use its buttons, item/action/sort selects, Filters, Inventory, Loadouts, Gear tab, and filter/market modals.
- `$inventory` category/item selects and consume modals are owner-only. Loadout select/rename modals are owner-only.
- A second player clicking a public menu gets an ephemeral **This armory isn't yours.** (or the inventory/loadout equivalent). No equip, merch, sell, drink, or preset apply runs.

### Gear shop stale price

- Relisting the same piece no longer lets a buyer confirm the old gold amount on an open stall.
- Buy reloads the live listing first, refreshes the stall, and confirms at the current price.
- Confirm charges only the agreed price. If the seller changes it again, the purchase is refused and nothing is taken.

### Armory materials

- Five smithing goods per armor line, matching crate rarities. Higher crates can drop lower goods. Legendary goods only from Legendary crates and a lucky Abyssal Maw drop.
- Dragon party materials roll independently of the ice-dragon weapon drop (can get both, one, or neither). Stage chance ~12–28%, then one weighted good.

### Reload

- `$reload equipment` and `$reload profile` (plus `$reload crates`, `$reload help`, `$reload transaction` for copy) pick this up.
