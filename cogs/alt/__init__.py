"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

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
import copy

import discord
from discord.ext import commands

from classes.converters import MemberWithCharacter
from utils.checks import has_char
from utils.i18n import _


class Alt(commands.Cog):
    ALT_ROLE_ID = None

    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        alt_ids = getattr(ids_section, "alt", {}) if ids_section else {}
        if not isinstance(alt_ids, dict):
            alt_ids = {}
        self.alt_role_id = alt_ids.get("alt_role_id", self.ALT_ROLE_ID)
        self.bot.loop.create_task(self.initialize_tables())

    async def initialize_tables(self):
        """Ensure alt link tables exist and are up to date."""
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alt_links (
                    main bigint NOT NULL,
                    alt bigint NOT NULL,
                    declared_at timestamp with time zone DEFAULT now() NOT NULL,
                    CONSTRAINT alt_links_main_unique UNIQUE (main),
                    CONSTRAINT alt_links_alt_unique UNIQUE (alt),
                    CONSTRAINT alt_links_main_alt_check CHECK (main <> alt)
                );
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alt_link_requests (
                    main bigint NOT NULL,
                    alt bigint NOT NULL,
                    requested_at timestamp with time zone DEFAULT now() NOT NULL,
                    CONSTRAINT alt_link_requests_main_unique UNIQUE (main),
                    CONSTRAINT alt_link_requests_alt_unique UNIQUE (alt),
                    CONSTRAINT alt_link_requests_main_alt_check CHECK (main <> alt)
                );
                """
            )
            # Cleanup legacy token column if present
            await conn.execute(
                "ALTER TABLE alt_link_requests DROP COLUMN IF EXISTS token;"
            )
            # Ensure constraints exist in case tables were created without them
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_links_main_unique') THEN
                        ALTER TABLE alt_links ADD CONSTRAINT alt_links_main_unique UNIQUE (main);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_links_alt_unique') THEN
                        ALTER TABLE alt_links ADD CONSTRAINT alt_links_alt_unique UNIQUE (alt);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_links_main_alt_check') THEN
                        ALTER TABLE alt_links ADD CONSTRAINT alt_links_main_alt_check CHECK (main <> alt);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_link_requests_main_unique') THEN
                        ALTER TABLE alt_link_requests ADD CONSTRAINT alt_link_requests_main_unique UNIQUE (main);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_link_requests_alt_unique') THEN
                        ALTER TABLE alt_link_requests ADD CONSTRAINT alt_link_requests_alt_unique UNIQUE (alt);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alt_link_requests_main_alt_check') THEN
                        ALTER TABLE alt_link_requests ADD CONSTRAINT alt_link_requests_main_alt_check CHECK (main <> alt);
                    END IF;
                END $$;
                """
            )
        await self.sync_alt_roles()

    async def _get_support_guild(self) -> discord.Guild | None:
        support_server_id = self.bot.config.game.support_server_id
        if support_server_id is None:
            return None
        return self.bot.get_guild(support_server_id)

    async def _is_gm_user(self, user_id: int) -> bool:
        config_gms = set(getattr(self.bot.config.game, "game_masters", []) or [])
        if user_id in config_gms:
            return True
        try:
            async with self.bot.pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT 1 FROM game_masters WHERE user_id = $1",
                    user_id,
                )
            return result is not None
        except Exception:
            return False

    async def assign_alt_role(self, member: discord.Member) -> None:
        if member is None:
            return
        alt_role = member.guild.get_role(self.alt_role_id) if self.alt_role_id else None
        if not alt_role or alt_role in member.roles:
            return
        try:
            await member.add_roles(alt_role, reason="Alt link role assignment")
        except discord.Forbidden:
            pass

    async def assign_alt_role_by_id(self, alt_id: int) -> None:
        guild = await self._get_support_guild()
        if guild is None:
            return
        alt_role = guild.get_role(self.alt_role_id) if self.alt_role_id else None
        if not alt_role:
            return
        member = guild.get_member(alt_id)
        if member is None:
            try:
                member = await guild.fetch_member(alt_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        await self.assign_alt_role(member)

    async def sync_alt_roles(self) -> None:
        """Assign alt role to any linked alts in the support server."""
        await self.bot.wait_until_ready()
        guild = await self._get_support_guild()
        if guild is None:
            return
        alt_role = guild.get_role(self.alt_role_id) if self.alt_role_id else None
        if not alt_role:
            return

        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("SELECT alt FROM alt_links;")

        for row in rows:
            alt_id = int(row["alt"])
            member = guild.get_member(alt_id)
            if member is None:
                try:
                    member = await guild.fetch_member(alt_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue
            if alt_role not in member.roles:
                try:
                    await member.add_roles(alt_role, reason="Alt link role sync")
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Assign alt role in support server if the user is a linked alt."""
        support_server_id = self.bot.config.game.support_server_id
        if support_server_id is None or member.guild.id != support_server_id:
            return

        async with self.bot.pool.acquire() as conn:
            is_alt = await conn.fetchval(
                "SELECT 1 FROM alt_links WHERE alt = $1;",
                member.id,
            )

        if not is_alt:
            return

        await self.assign_alt_role(member)

    @commands.group(invoke_without_command=True, brief=_("Run commands as your linked alt"))
    @has_char()
    async def alt(self, ctx, *, command: str | None = None):
        """Run a command as your linked alt account."""
        if command is None:
            return await ctx.send(
                _("Usage: `{prefix}alt <command>` or `{prefix}alt register <account>`").format(
                    prefix=ctx.clean_prefix
                )
            )

        if ctx.guild is None:
            return await ctx.send(_("Alt commands must be used in a server."))

        async with self.bot.pool.acquire() as conn:
            alt_id = await conn.fetchval(
                "SELECT alt FROM alt_links WHERE main = $1;",
                ctx.author.id,
            )

        if not alt_id:
            return await ctx.send(
                _("You don't have an alt linked yet. Use `{prefix}alt register <account>`.").format(
                    prefix=ctx.clean_prefix
                )
            )

        member = ctx.guild.get_member(int(alt_id))
        command_author = member
        if not member:
            if not await self._is_gm_user(ctx.author.id):
                return await ctx.send(
                    _("Your linked alt must be in this server to run commands.")
                )
            command_author = await self.bot.get_user_global(int(alt_id))
            if not command_author:
                return await ctx.send(
                    _("I couldn't fetch your linked alt account. Check the link and try again.")
                )

        command_lower = command.strip().lower()
        if command_lower.startswith("alt"):
            return await ctx.send(_("You can't run `{prefix}alt` from within `{prefix}alt`.").format(prefix=ctx.clean_prefix))

        fake_msg = copy.copy(ctx.message)
        fake_msg._update(dict(channel=ctx.channel, content=ctx.clean_prefix + command))
        fake_msg.author = command_author

        new_ctx = await ctx.bot.get_context(fake_msg, cls=commands.Context)
        new_ctx.alt_invoker_id = ctx.author.id
        await ctx.bot.invoke(new_ctx)

    @alt.command(name="register", brief=_("Register an alt account"))
    @has_char()
    async def register(self, ctx, account: MemberWithCharacter):
        """Register an alt account and send a confirmation request."""
        if account.id == ctx.author.id:
            return await ctx.send(_("You can't register yourself as your alt."))

        async with self.bot.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM alt_links WHERE main = $1 OR alt = $1 OR main = $2 OR alt = $2;",
                ctx.author.id,
                account.id,
            )
            if existing:
                return await ctx.send(
                    _("Either you or that account is already linked as a main/alt.")
                )

            pending = await conn.fetchval(
                "SELECT 1 FROM alt_link_requests WHERE main = $1 OR alt = $1 OR main = $2 OR alt = $2;",
                ctx.author.id,
                account.id,
            )
            if pending:
                return await ctx.send(
                    _("There is already a pending alt request for either account.")
                )

            await conn.execute(
                "INSERT INTO alt_link_requests (main, alt) VALUES ($1, $2);",
                ctx.author.id,
                account.id,
            )

        try:
            view = AltConfirmView(self.bot, ctx.author.id, account.id)
            message = await account.send(
                _(
                    "{main} wants to link you as an alt. "
                    "Only accept if this is truly your alt. "
                    "This link is permanent and cannot be undone."
                ).format(main=ctx.author.name),
                view=view,
            )
            view.message = message
        except discord.Forbidden:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                    ctx.author.id,
                    account.id,
                )
            await ctx.send(
                _("I couldn't DM your alt. Ask them to enable DMs and try again.")
            )
            return

        await ctx.send(
            _("Confirmation sent to {alt}. They must accept the request within 5 minutes.").format(
                alt=account.display_name
            )
        )


class AltConfirmView(discord.ui.View):
    def __init__(self, bot, main_id: int, alt_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.main_id = main_id
        self.alt_id = alt_id
        self.message = None

    async def _finalize(self, interaction: discord.Interaction, accepted: bool):
        if interaction.user.id != self.alt_id:
            return await interaction.response.send_message(
                "❌ This request isn't for you.", ephemeral=True
            )

        async with self.bot.pool.acquire() as conn:
            request = await conn.fetchrow(
                "SELECT main, alt FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                self.main_id,
                self.alt_id,
            )
            if not request:
                return await interaction.response.send_message(
                    "❌ This alt link request is no longer pending.", ephemeral=True
                )

            if accepted:
                existing = await conn.fetchval(
                    "SELECT 1 FROM alt_links WHERE main = $1 OR alt = $1 OR main = $2 OR alt = $2;",
                    self.main_id,
                    self.alt_id,
                )
                if existing:
                    await conn.execute(
                        "DELETE FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                        self.main_id,
                        self.alt_id,
                    )
                    return await interaction.response.send_message(
                        "❌ This alt link is already active.", ephemeral=True
                    )

                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO alt_links (main, alt) VALUES ($1, $2);",
                        self.main_id,
                        self.alt_id,
                    )
                    await conn.execute(
                        "DELETE FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                        self.main_id,
                        self.alt_id,
                    )

                await interaction.response.send_message(
                    "✅ Alt link confirmed. This link is permanent.",
                    ephemeral=True,
                )

                alt_cog = self.bot.get_cog("Alt")
                if alt_cog:
                    await alt_cog.assign_alt_role_by_id(self.alt_id)

                main_user = await self.bot.get_user_global(self.main_id)
                if main_user:
                    try:
                        prefix = self.bot.config.bot.global_prefix
                        await main_user.send(
                            f"{interaction.user.name} confirmed the alt link. "
                            f"You can now use `{prefix}alt <command>`."
                        )
                    except discord.Forbidden:
                        pass
            else:
                await conn.execute(
                    "DELETE FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                    self.main_id,
                    self.alt_id,
                )
                await interaction.response.send_message(
                    "❌ Alt link declined.",
                    ephemeral=True,
                )

                main_user = await self.bot.get_user_global(self.main_id)
                if main_user:
                    try:
                        await main_user.send("Your alt link request was declined.")
                    except discord.Forbidden:
                        pass

        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
        self.stop()

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, False)

    async def on_timeout(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM alt_link_requests WHERE main = $1 AND alt = $2;",
                self.main_id,
                self.alt_id,
            )
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


async def setup(bot):
    await bot.add_cog(Alt(bot))
