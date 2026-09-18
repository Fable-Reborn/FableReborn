# The Chronicle Collection

Six illustrated PRPG cosmetics, plus the unchanged original `classic` card.
All themes are free to select. They confer no gameplay benefits or alignment restrictions.

| Key | Theme | Art direction |
| --- | --- | --- |
| `dragon` | Ashen Sovereign | Obsidian dragon, molten gold, volcanic citadel |
| `evil` | The Hollow Crown | Blood eclipse, skeletal throne, blackened steel |
| `chaos` | Violet Rupture | Amethyst lightning, shattered dimensions, eldritch eye |
| `good` | Dawnward | Celestial guardian, feathered wings, pearl and sun gold |
| `forest` | Verdant Oath | Sacred stag, luminous antlers, emerald forest cathedral |
| `frost` | Winterveil | Ice queen, crystalline kingdom, midnight auroras |
| `classic` | Original Chronicle | Existing parchment-and-bronze card |

## Player commands

Use your server's command prefix in place of `$` if different.

- `$prpg themes` — browse the collection and equip from an owner-only dropdown.
- `$prpg preview dragon` — render your own full card without changing your selection.
- `$prpg theme dragon` — save a theme across restarts.
- `$prpg theme classic` — return to the original card (`reset`, `normal`, and `default` also work).
- `$prpg` — your saved theme; `$prpg @user` — that player's saved theme.
- Full names and friendly aliases work, e.g. `$prpg theme The Hollow Crown` or `$prpg theme purple`.

## Installation and storage

Deploy `cogs/profile/__init__.py`, `themes.py`, `theme_picker.py`, and this entire asset
directory, then reload the Profile extension or restart the bot. `Profile.cog_load`
idempotently adds `profile.prpg_theme TEXT NOT NULL DEFAULT 'classic'` using the bot's
existing PostgreSQL connection. Existing characters retain their original appearance.
No live database was changed during development. The bot database role needs its
existing schema-alteration permission. No new Python package is required.

Selection writes are parameterized and limited to the invoking user's profile row.
Unknown stored themes fall back to classic. Missing/corrupt artwork falls back to
a matching colour background while keeping the user's stats visible.

Themed output is 1660 × 1460 PNG; classic remains 1660 × 940.
Only six decoded background illustrations are cached, never composed player cards.
All artwork and fonts load locally; image generation is not called at runtime.

## Artwork and review

Original banner PNGs were generated with the built-in imagegen tool. The exact final
prompt set is saved in [prompts.json](prompts.json). These are separate paintings,
not palette swaps. Cinzel and Lato fonts come from the Google Fonts repository;
their SIL Open Font Licenses are included in `fonts/`.

The `previews/` directory contains full cards rendered from the production renderer
with fictional sample data and a placeholder avatar/pet portrait. It is not required
at runtime. [View the collection](previews/collection.jpg).

Run the offline checks with `python -m pytest tests/test_profile_themes.py -q`.
They exercise full rendering, aliases, fallback behavior, cache isolation, player-scoped
saves, preview isolation, picker ownership and Discord command routing. Live Discord
and PostgreSQL integration still require verification after deployment.
