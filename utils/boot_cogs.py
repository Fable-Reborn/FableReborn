"""Which cogs load when the bot boots: the `initial_extensions` list in config.toml.

Reads the list (a cog commented out, `#"cogs.vote",`, counts as switched off) and writes it
back with only that block changed, so the rest of config.toml (tokens, settings, comments) is
left exactly as it was. Switched-off cogs stay in the list as comments, so they're easy to see
and switch back on. Changes take effect at the next boot.

Discord-free so the command and tests can share it.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomli

# Always switched on: the cogs that hold the GM tools (this command included), so a bad save
# can't lock staff out.
PROTECTED = frozenset({"cogs.game_master", "cogs.reload", "cogs.owner"})
# Loaded at boot whatever the list says (classes/bot.py adds them).
ALWAYS_LOADED = frozenset({"cogs.fables", "cogs.factions", "cogs.aiplayer", "cogs.elixirs"})

_START = re.compile(r"^\s*initial_extensions\s*=\s*\[")
_ENTRY = re.compile(r'^\s*(#)?\s*"([^"]+)"\s*,?\s*(?:#.*)?$')


@dataclass
class Entry:
    name: str
    enabled: bool


def _block(lines: list[str]) -> tuple[int, int]:
    """The line numbers of `initial_extensions = [` and its closing `]`."""
    for start, line in enumerate(lines):
        if _START.match(line):
            if "]" in line.split("[", 1)[1]:
                raise ValueError("initial_extensions must be written one cog per line")
            for end in range(start + 1, len(lines)):
                if lines[end].strip().startswith("]"):
                    return start, end
            raise ValueError("initial_extensions has no closing ]")
    raise ValueError("config.toml has no initial_extensions list")


def read(text: str) -> list[Entry]:
    """The cogs in the list, in order (each once), and whether each is switched on."""
    lines = text.splitlines()
    start, end = _block(lines)
    entries: dict[str, Entry] = {}
    for line in lines[start + 1:end]:
        match = _ENTRY.match(line)
        if not match:
            continue
        commented, name = bool(match.group(1)), match.group(2).strip()
        if name in entries:
            entries[name].enabled = entries[name].enabled or not commented
        else:
            entries[name] = Entry(name, not commented)
    return list(entries.values())


def available(cogs_dir: Path) -> list[str]:
    """Every cog in the cogs folder: a package with __init__.py, or a module."""
    names = []
    for path in sorted(Path(cogs_dir).iterdir()):
        if path.name.startswith(("_", ".")):
            continue
        if path.is_dir() and (path / "__init__.py").exists():
            names.append(f"cogs.{path.name}")
        elif path.suffix == ".py":
            names.append(f"cogs.{path.stem}")
    return names


def render(text: str, entries: list[Entry]) -> str:
    """config.toml with its initial_extensions block rewritten from entries, everything else untouched."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    start, end = _block(lines)
    indent = "    "
    for line in lines[start + 1:end]:
        if _ENTRY.match(line):
            indent = line[: len(line) - len(line.lstrip())] or indent
            break
    body = [f'{indent}{"" if e.enabled else "#"}"{e.name}",' for e in entries]
    out = lines[:start + 1] + body + lines[end:]
    result = newline.join(out)
    if text.endswith(("\n", "\r\n")):
        result += newline
    # It must still be valid TOML, with exactly the cogs that are switched on.
    loaded = tomli.loads(result)
    bot = loaded.get("bot", loaded)
    if list(bot.get("initial_extensions", [])) != [e.name for e in entries if e.enabled]:
        raise ValueError("the rewritten config.toml doesn't list the cogs it should")
    return result


def apply(entries: list[Entry], enable: set[str], disable: set[str]) -> list[Entry]:
    """The list with these cogs switched on or off (new ones added at the end). Protected cogs stay on."""
    disable = set(disable) - PROTECTED
    out = [Entry(e.name, (e.enabled or e.name in enable) and e.name not in disable) for e in entries]
    known = {e.name for e in out}
    out += [Entry(name, True) for name in sorted(enable) if name not in known]
    for e in out:
        if e.name in PROTECTED:
            e.enabled = True
    return out


def save(path: Path, entries: list[Entry]) -> Path:
    """Writes the list into config.toml, keeping a copy of the old file next to it. Returns the copy's path."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    result = render(text, entries)
    backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, backup)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(result, encoding="utf-8", newline="")
    temporary.replace(path)
    return backup
