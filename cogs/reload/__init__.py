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

from utils.checks import is_gm


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

        await ctx.send(
            f"Running `git pull` in `{self.GIT_PULL_CWD}`..."
        )

        try:
            result = await asyncio.create_subprocess_exec(
                "git",
                "pull",
                cwd=str(self.GIT_PULL_CWD),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
        except Exception as e:
            return await ctx.send(f"Failed to run git pull: {type(e).__name__}: {e}")

        stdout_text = stdout.decode(errors="replace").strip()
        stderr_text = stderr.decode(errors="replace").strip()
        combined = (
            f"$ git pull\n"
            f"exit_code={result.returncode}\n\n"
            f"[stdout]\n{stdout_text or '(empty)'}\n\n"
            f"[stderr]\n{stderr_text or '(empty)'}"
        ).replace("```", "'''")

        chunk_size = 1900
        for i in range(0, len(combined), chunk_size):
            await ctx.send(f"```{combined[i:i + chunk_size]}```")


async def setup(bot):
    await bot.add_cog(ReloadCog(bot))
