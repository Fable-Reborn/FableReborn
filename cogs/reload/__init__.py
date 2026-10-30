"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

import discord
from discord.ext import commands

from utils import boot_cogs
from utils.checks import is_gm


CONFIG_PATH = Path("config.toml")
COGS_DIR = Path(__file__).resolve().parents[1]


def _cog_name(text: str) -> str:
    name = text.strip().strip(",").strip('"')
    return name if name.startswith("cogs.") else f"cogs.{name}"


class BootCogsView(discord.ui.View):
    """The boot list, 25 cogs a page: tick the ones to load at boot, then Save."""

    PAGE = 25

    def __init__(self, author_id: int, bot, entries: list, listed: set):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.bot = bot
        self.original = {e.name: e.enabled for e in entries}
        self.entries = entries
        self.listed = listed
        self.page = 0
        self.message = None
        self.build()

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.entries) // self.PAGE))

    def shown(self):
        return self.entries[self.page * self.PAGE:(self.page + 1) * self.PAGE]

    def build(self):
        self.clear_items()
        loaded = set(self.bot.extensions)
        options = []
        for e in self.shown():
            state = "always on" if e.name in boot_cogs.PROTECTED else ("running now" if e.name in loaded else "not running now")
            if e.name not in self.listed:
                state += " · not in config yet"
            options.append(discord.SelectOption(label=e.name[len("cogs."):][:100], value=e.name, description=state[:100], default=e.enabled))
        select = discord.ui.Select(
            placeholder=f"Load at boot (page {self.page + 1}/{self.pages})",
            min_values=0, max_values=len(options), options=options, row=0,
        )
        select.callback = self.on_select
        self.add_item(select)
        for label, step in (("◀", -1), ("▶", 1)):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=1, disabled=self.pages == 1)
            button.callback = self.turner(step)
            self.add_item(button)
        save = discord.ui.Button(label="Save", style=discord.ButtonStyle.success, row=1)
        save.callback = self.on_save
        self.add_item(save)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self.on_cancel
        self.add_item(cancel)

    def changes(self):
        on = [e.name for e in self.entries if e.enabled and not self.original.get(e.name)]
        off = [e.name for e in self.entries if not e.enabled and self.original.get(e.name)]
        return on, off

    def embed(self) -> discord.Embed:
        on, off = self.changes()
        enabled = sum(e.enabled for e in self.entries)
        embed = discord.Embed(
            title="Cogs that load at boot",
            description=(
                f"**{enabled}** on, **{len(self.entries) - enabled}** off, from `config.toml`.\n"
                "Tick the cogs to load at boot, then **Save**. Changes apply at the next restart; "
                "use `$load` / `$unload` to change the running bot now.\n"
                f"Always on: {', '.join(sorted(n[5:] for n in boot_cogs.PROTECTED))}. "
                f"Loaded whatever the list says: {', '.join(sorted(n[5:] for n in boot_cogs.ALWAYS_LOADED))}."
            ),
            colour=discord.Colour.blurple(),
        )
        if on or off:
            text = "\n".join([f"+ {n[5:]}" for n in on] + [f"- {n[5:]}" for n in off])
            embed.add_field(name="Not saved yet", value=f"```diff\n{text[:1000]}\n```", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu isn't yours.", ephemeral=True)
            return False
        return True

    async def on_select(self, interaction: discord.Interaction):
        picked = set(interaction.data.get("values", []))
        for e in self.shown():
            e.enabled = e.name in picked or e.name in boot_cogs.PROTECTED
        self.build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    def turner(self, step: int):
        async def turn(interaction: discord.Interaction):
            self.page = (self.page + step) % self.pages
            self.build()
            await interaction.response.edit_message(embed=self.embed(), view=self)
        return turn

    async def on_save(self, interaction: discord.Interaction):
        on, off = self.changes()
        if not on and not off:
            return await interaction.response.send_message("Nothing has changed.", ephemeral=True)
        # Cogs that were never in the list stay out of it unless they were switched on.
        keep = [e for e in self.entries if e.name in self.listed or e.enabled]
        try:
            backup = boot_cogs.save(CONFIG_PATH, keep)
        except Exception as error:
            return await interaction.response.send_message(f"Couldn't save: {type(error).__name__}: {error}", ephemeral=True)
        self.original = {e.name: e.enabled for e in self.entries}
        self.listed = {e.name for e in keep}
        self.stop()
        embed = self.embed()
        saved = "\n".join([f"+ {n[5:]}" for n in on] + [f"- {n[5:]}" for n in off])
        embed.add_field(
            name="Saved",
            value=f"```diff\n{saved[:900]}\n```Applies at the next restart. The old file was kept as `{backup.name}`.",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(content="Nothing was changed.", embed=None, view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class ReloadCog(commands.Cog):
    GIT_PULL_ALLOWED_USER_IDS = {
        171645746993561600,
        295173706496475136,
        273652235588599808,
    }
    GIT_PULL_CWD = Path("/home/fableadmin/FableRPG-FINAL/FableRPG-FINAL/Fable")

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _normalize_module_name(module: str) -> str:
        name = module.strip()
        if name.endswith(".py"):
            name = name[:-3]
        return name.replace("\\", ".").replace("/", ".")

    def _reset_runtime_storage_clients(self):
        for cog_name in ("Patreon", "ProcessSplice"):
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for attr in ("_r2_client", "_r2_bucket", "_r2_public_base_url"):
                if hasattr(cog, attr):
                    setattr(cog, attr, None)

    def _load_utils_config_module(self):
        """Load config module from utils/config.py explicitly to avoid root config.py conflicts."""
        config_module = importlib.import_module("utils.config")
        module_file = (getattr(config_module, "__file__", None) or "").replace("\\", "/")
        if module_file.endswith("/utils/config.py"):
            return importlib.reload(config_module)

        # Fallback: load the module directly from file path if module resolution is polluted.
        config_path = Path(__file__).resolve().parents[2] / "utils" / "config.py"
        spec = importlib.util.spec_from_file_location("utils.config", str(config_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to create module spec for {config_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["utils.config"] = module
        return module

    async def _reload_runtime_config(self):
        # Reload config module so class/code changes in utils/config.py are applied.
        config_module = self._load_utils_config_module()
        self.bot.config = config_module.ConfigLoader("config.toml")
        self.bot.version = self.bot.config.bot.version
        self.bot.BASE_URL = self.bot.config.external.base_url
        self.bot.support_server_id = self.bot.config.game.support_server_id
        self.bot.activity = discord.Game(
            name=f"Fable v{self.bot.version}"
            if self.bot.config.bot.is_beta
            else self.bot.BASE_URL
        )
        self._reset_runtime_storage_clients()

        # Best effort: refresh visible presence immediately.
        try:
            await self.bot.change_presence(activity=self.bot.activity)
        except Exception:
            pass

    @is_gm()
    @commands.command(name="unload", hidden=True)
    async def unload_cog(self, ctx, cog_name: str):
        try:

            # Unload the existing cog
            await ctx.send("Unloading Cog...")
            await self.bot.unload_extension(f"cogs.{cog_name}")
            await ctx.send(f"{cog_name} has been unloaded.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @is_gm()
    @commands.command(name="load", hidden=True)
    async def load_cog(self, ctx, cog_name: str):
        try:

            # Unload the existing cog
            await ctx.send("Loading Cog...")
            # Reload the cog using Discord.py's reload_extension
            await self.bot.load_extension(f"cogs.{cog_name}")
            await ctx.send(f"{cog_name} has been loaded.")
        except Exception as e:

            await ctx.send(e)
            print(e)

    @is_gm()
    @commands.command(name="reload", hidden=True)
    async def reload(self, ctx, cog: str):
        extension = cog if cog.startswith("cogs.") else f"cogs.{cog}"
        try:
            await self.bot.reload_extension(extension)
            await ctx.send(f"Successfully reloaded cog: {extension}")
        except commands.ExtensionNotLoaded:
            await self.bot.load_extension(extension)
            await ctx.send(f"Cog was not loaded; loaded now: {extension}")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog not found: {extension}")
        except Exception as e:
            await ctx.send(f"Failed to reload cog: {extension}\n{type(e).__name__}: {e}")

    @is_gm()
    @commands.command(name="reloadconfig", aliases=["rcfg"], hidden=True)
    async def reload_config(self, ctx):
        try:
            await self._reload_runtime_config()
            await ctx.send("Reloaded `utils.config` and `config.toml` successfully.")
        except Exception as e:
            await ctx.send(f"Failed to reload config\n{type(e).__name__}: {e}")

    @is_gm()
    @commands.command(name="reloadfile", hidden=True)
    async def reload_file(self, ctx, *, module: str):
        module_name = self._normalize_module_name(module)
        try:
            if module_name in {"config.toml", "utils.config", "config"}:
                await self._reload_runtime_config()
                return await ctx.send(
                    f"Reloaded runtime config via `{module}`."
                )

            mod = importlib.import_module(module_name)
            importlib.reload(mod)
            await ctx.send(f"Reloaded module: `{module_name}`")
        except Exception as e:
            await ctx.send(
                f"Failed to reload `{module}`\n{type(e).__name__}: {e}"
            )

    @is_gm()
    @commands.command(name="gitpull", hidden=True)
    async def git_pull(self, ctx):
        if ctx.author.id not in self.GIT_PULL_ALLOWED_USER_IDS:
            return await ctx.send("You are not allowed to run this command.")

        await ctx.send(f"Running git pull in `{self.GIT_PULL_CWD}`...")

        async def run_git(*args):
            result = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(self.GIT_PULL_CWD),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            return (
                result.returncode,
                stdout.decode(errors="replace").strip(),
                stderr.decode(errors="replace").strip(),
            )

        command_chain = [
            ("reset", "--hard"),
            ("pull",),
        ]

        output_parts = []
        try:
            for args in command_chain:
                exit_code, stdout_text, stderr_text = await run_git(*args)
                output_parts.append(
                    (
                        f"$ git {' '.join(args)}\n"
                        f"exit_code={exit_code}\n\n"
                        f"[stdout]\n{stdout_text or '(empty)'}\n\n"
                        f"[stderr]\n{stderr_text or '(empty)'}"
                    )
                )
                if exit_code != 0:
                    break
        except Exception as e:
            return await ctx.send(f"Failed to run git pull: {type(e).__name__}: {e}")

        combined = "\n\n".join(output_parts).replace("```", "'''")

        chunk_size = 1900
        for i in range(0, len(combined), chunk_size):
            await ctx.send(f"```{combined[i:i + chunk_size]}```")
    # ---- which cogs load at boot (config.toml) ----------------------------------------------------

    def _boot_entries(self):
        text = CONFIG_PATH.read_text(encoding="utf-8")
        entries = boot_cogs.read(text)
        listed = {e.name for e in entries}
        extra = [boot_cogs.Entry(name, False) for name in boot_cogs.available(COGS_DIR)
                 if name not in listed and name not in boot_cogs.ALWAYS_LOADED]
        return entries + extra, listed

    @is_gm()
    @commands.group(name="bootcogs", aliases=["startupcogs"], invoke_without_command=True, hidden=True)
    async def bootcogs(self, ctx):
        """See and change which cogs load when the bot boots (config.toml's initial_extensions)."""
        try:
            entries, listed = self._boot_entries()
        except Exception as error:
            return await ctx.send(f"Couldn't read config.toml: {type(error).__name__}: {error}")
        view = BootCogsView(ctx.author.id, self.bot, entries, listed)
        view.message = await ctx.send(embed=view.embed(), view=view)

    async def _switch(self, ctx, names: str, on: bool):
        wanted = [_cog_name(n) for n in names.replace(",", " ").split() if n.strip()]
        if not wanted:
            return await ctx.send(f"Name the cogs: `$bootcogs {'on' if on else 'off'} pets quests`")
        try:
            entries, listed = self._boot_entries()
        except Exception as error:
            return await ctx.send(f"Couldn't read config.toml: {type(error).__name__}: {error}")
        known = {e.name: e.enabled for e in entries}
        unknown = [n for n in wanted if n not in known]
        if unknown:
            return await ctx.send(f"No such cog: {', '.join(n[5:] for n in unknown)}")
        locked = [n for n in wanted if n in boot_cogs.PROTECTED]
        if not on and locked:
            return await ctx.send(f"{', '.join(n[5:] for n in locked)} always load (they hold the GM tools).")
        if all(known[n] == on for n in wanted):
            return await ctx.send(f"Nothing to change: {', '.join(n[5:] for n in wanted)} already {'load' if on else 'stay off'} at boot.")
        current = [e for e in entries if e.name in listed]
        changed = boot_cogs.apply(current, set(wanted) if on else set(), set() if on else set(wanted))
        try:
            backup = boot_cogs.save(CONFIG_PATH, changed)
        except Exception as error:
            return await ctx.send(f"Couldn't save: {type(error).__name__}: {error}")
        await ctx.send(
            f"{'Switched on' if on else 'Switched off'} at boot: {', '.join(n[5:] for n in wanted)}. "
            f"Applies at the next restart (old file kept as `{backup.name}`)."
        )

    @is_gm()
    @bootcogs.command(name="on", aliases=["enable"], hidden=True)
    async def bootcogs_on(self, ctx, *, cogs: str = ""):
        """Load these cogs at boot: $bootcogs on pets quests"""
        await self._switch(ctx, cogs, True)

    @is_gm()
    @bootcogs.command(name="off", aliases=["disable"], hidden=True)
    async def bootcogs_off(self, ctx, *, cogs: str = ""):
        """Don't load these cogs at boot: $bootcogs off vote"""
        await self._switch(ctx, cogs, False)


async def setup(bot):
    await bot.add_cog(ReloadCog(bot))
