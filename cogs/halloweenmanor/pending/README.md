# Pending edits

The live game files are not part of this work. Nothing in this folder is imported.

When a change belongs in an existing module, write it here as `pending/<original-name>.snippet.py`. Do not edit the live file until this event is ready to ship.

| When we ship, this lands in | Pending file |
|---|---|
| `cogs/profile/themes.py` inside `EVENT_THEMES` | `themes.snippet.py` — applied as `hallowmanor`, The Last Lantern |
| `cogs/halloween/__init__.py` spooky shop | `spookyshop.snippet.py` |
| `cogs/help/__init__.py` seasonal command list | a few manor command names, added at ship time |
| `cogs/game_master/__init__.py` shop reset defaults | no change; item 7 keeps the existing `ssbg` stock of 1 |
| `cogs/game_master/__init__.py` event load | `event_boot.snippet.py` — Halloween starts off after every restart |
| `cogs/adventure/__init__.py` narrative | `adventure.snippet.py` — seasonal lines only while the flag is on |
| `config.toml` | `cogs.halloween` and `cogs.halloweenmanor` |

`config.toml` is gitignored. It is currently not loading this cog.
