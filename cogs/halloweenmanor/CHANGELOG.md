# Hollow Manor (`halloweenmanor` cog) — Changelog

All notable changes to this cog are documented here.

## [0.1.0] — 2026-09-29

### Added

- **Hollow Manor raid**, started by a GM with `$manor open` while the Halloween event flag is on.
  - Creates a fresh `#hollow-manor` channel in the same category. Players can see it. They cannot type in it.
  - One message is edited for the whole night. The picture changes by room, and the progress bar is drawn onto that picture.
  - **Investigate** joins the search roster. **Keep watch** stays at the gate for a smaller bone reward. Players can switch until the gate closes (3 minutes).
  - Each search room lasts 90 seconds. Investigators press **Search** and get a private choice only they can see. One choice per room.
  - Watchers who press Search are turned away. Investigators who never search are paid as watchers.
  - The house clears when searches reach about 70% of every investigator searching every room. One idle investigator does not block the clear by themselves.
  - Active searchers earn more bones, better bag odds, a chance at an uncommon crate for a full search, and a small chance at **The Last Lantern** profile theme.
  - Watchers earn a flat bone payout and a low bag chance.
  - Personal rewards are sent by DM. **My reward** on the final picture repeats the receipt if the DM did not arrive.
  - `$manor status`, `$manor skip`, `$manor end`, and `$manor close`.
  - Raid state is stored in Redis so a restart can resume an open manor. Rewards already applied are not paid twice.

### Notes

- Adventure flavor is a separate list in `adventure_flavor.py`. It is used only while the Halloween flag is on, and only after `pending/adventure.snippet.py` is pasted. The normal adventure stories are not rewritten.
- On ship, `pending/event_boot.snippet.py` makes a restart leave Halloween off in memory. `$gmevent halloween on` is what turns bones, the shop, the manor, and the adventure lines on together.

- Phase art in `assets/halloween/manor/` and the theme banner `assets/profile_themes/hollowmanor.png` are stand-ins. Replace those PNGs to change the paintings without changing the raid. The bar is drawn in the bottom slot every time the picture updates.
- Bones stay the seasonal currency. The spooky shop stays the place those bones are spent.
- Load `cogs.halloweenmanor` next to `cogs.halloween` in `config.toml`. That file is gitignored, so the GitHub push will not include the local config change.

## Shop and theme (recorded here because they ship with this update)

### Added

- **`$spookyshop` item 7 is The Last Lantern**, the `$prpg` theme, in the seasonal background slot. 2,500 bones, stock 1 (`profile.ssbg`). The old event-background image is not sold. Buying it again is refused.

### Fixed

- Rare crate is charged at 60 bones, matching the shop listing. It was charging 50.
- Magic crate success text now says 250 bones, matching the charge. It used to say 500.
- `$ss buy` rejects an item number outside 1–10 instead of doing nothing.

### Database

- No new column. The theme uses the existing seasonal-background stock, `profile.ssbg`.
