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

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui.button import Button

from classes.converters import IntGreaterThan
from utils import random
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from .core import DESCRIPTIONS as ROLE_DESC
from .core import ADVANCED_BASE_ROLE_BY_ADVANCED
from .core import ADVANCED_ROLE_TIERS_BY_BASE
from .core import Game
from .core import Role as ROLES
from .core import Side as WW_SIDE
from .core import parse_custom_roles
from .core import role_level_from_xp
from .core import send_traceback
from .core import unavailable_roles_for_mode
from .role_config import (
    MAX_ROLE_LEVEL,
    ROLE_XP_PER_LEVEL,
    ROLE_XP_CHANNEL_IDS,
    ROLE_XP_LONER_WIN,
    ROLE_XP_LOSS,
    ROLE_XP_REQUIRE_GM_START,
    ROLE_XP_WIN,
    ROLE_XP_WIN_ALIVE,
)

class NewWerewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}
        self._role_xp_tables_ready = False
        self._role_xp_table_lock = asyncio.Lock()
        self.bot.loop.create_task(self._warm_role_xp_tables())

    async def _warm_role_xp_tables(self) -> None:
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            # Do not fail cog load on startup DB race; tables are retried on game start.
            pass

    async def _ensure_role_xp_tables(self) -> None:
        if self._role_xp_tables_ready:
            return
        async with self._role_xp_table_lock:
            if self._role_xp_tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS newwerewolf_role_xp (
                        user_id bigint NOT NULL,
                        role_name text NOT NULL,
                        xp integer NOT NULL DEFAULT 0 CHECK (xp >= 0),
                        updated_at timestamp with time zone NOT NULL DEFAULT now(),
                        CONSTRAINT newwerewolf_role_xp_pk PRIMARY KEY (user_id, role_name)
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS newwerewolf_role_xp_user_idx
                    ON newwerewolf_role_xp (user_id);
                    """
                )
            self._role_xp_tables_ready = True

    async def _is_gm_user(self, user_id: int) -> bool:
        config_gms = set(getattr(self.bot.config.game, "game_masters", []) or [])
        if user_id in config_gms:
            return True
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM game_masters WHERE user_id = $1",
                    user_id,
                )
        except Exception:
            return False
        return row is not None

    def _get_role_xp_channel_ids(self) -> set[int]:
        configured_channel_ids = {int(channel_id) for channel_id in ROLE_XP_CHANNEL_IDS}
        if configured_channel_ids:
            return configured_channel_ids
        official_channel = getattr(
            self.bot.config.game,
            "official_tournament_channel_id",
            None,
        )
        if official_channel is None:
            return set()
        return {int(official_channel)}

    async def _is_role_xp_eligible_match(self, ctx) -> bool:
        channel_ids = self._get_role_xp_channel_ids()
        if not channel_ids:
            return False
        if ctx.channel.id not in channel_ids:
            return False
        if ROLE_XP_REQUIRE_GM_START and not await self._is_gm_user(ctx.author.id):
            return False
        return True

    async def _award_role_xp(self, game: Game, *, eligible: bool) -> None:
        if not eligible:
            return
        if not hasattr(self.bot, "pool"):
            return

        updates: list[tuple[int, str, int]] = []
        loner_win_sides = {
            WW_SIDE.WHITE_WOLF,
            WW_SIDE.FLUTIST,
            WW_SIDE.SUPERSPREADER,
            WW_SIDE.JESTER,
            WW_SIDE.HEAD_HUNTER,
        }
        for player in game.players:
            if not player.initial_roles:
                role_for_xp = player.role
            else:
                role_for_xp = player.initial_roles[0]
            if player.has_won:
                if player.side in loner_win_sides:
                    gained_xp = ROLE_XP_LONER_WIN
                elif not player.dead:
                    gained_xp = ROLE_XP_WIN_ALIVE
                else:
                    gained_xp = ROLE_XP_WIN
            else:
                gained_xp = ROLE_XP_LOSS
            updates.append((player.user.id, role_for_xp.name.casefold(), gained_xp))

        if not updates:
            return

        async with self.bot.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO newwerewolf_role_xp (user_id, role_name, xp)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, role_name)
                DO UPDATE SET
                    xp = newwerewolf_role_xp.xp + EXCLUDED.xp,
                    updated_at = now()
                """,
                updates,
            )

        await game.ctx.send(_("📈 Role XP was granted for this GM game."))

    @staticmethod
    def _role_display_name(role: ROLES) -> str:
        return role.name.title().replace("_", " ")

    async def _fetch_user_role_xp_map(self, user_id: int) -> dict[str, int]:
        if not hasattr(self.bot, "pool"):
            return {}
        try:
            await self._ensure_role_xp_tables()
        except Exception:
            pass
        try:
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT role_name, xp
                    FROM newwerewolf_role_xp
                    WHERE user_id = $1
                    """,
                    user_id,
                )
        except Exception:
            return {}

        xp_map: dict[str, int] = {}
        for row in rows:
            role_name = str(row["role_name"]).strip().casefold()
            try:
                xp_value = max(0, int(row["xp"] or 0))
            except (TypeError, ValueError):
                continue
            xp_map[role_name] = xp_value
        return xp_map

    @staticmethod
    def _chunk_lines(lines: list[str], *, max_chars: int = 3800) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current and current_len + len(line) + 1 > max_chars:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks

    async def _start_multiplayer_game(
        self,
        ctx,
        *,
        mode: str,
        speed: str,
        min_players: int,
        custom_roles: list[ROLES] | None = None,
    ) -> None:
        if self.games.get(ctx.channel.id):
            await ctx.send(_("There is already a game in here!"))
            return

        game_speeds = ["Normal", "Extended", "Fast", "Blitz"]
        if speed not in game_speeds:
            await ctx.send(
                _(
                    "Invalid game speed. Use `{prefix}help nww` to get help on this"
                    " command."
                ).format(prefix=ctx.clean_prefix)
            )
            return

        try:
            await self._ensure_role_xp_tables()
        except Exception:
            # Progression DB failures should not block playing the game.
            pass

        self.games[ctx.channel.id] = "forming"

        additional_text = _(
            "Use `{prefix}help nww` to get help on werewolf commands. Use `{prefix}nww"
            " roles` to view descriptions of game roles and their goals to win. Use"
            " `{prefix}nww modes` and `{prefix}nww speeds` to see info about available"
            " game modes and speeds."
        ).format(prefix=ctx.clean_prefix)

        mode_emojis = {"Huntergame": "🔫", "Valentines": "💕", "Custom": "🧩"}
        mode_emoji = mode_emojis.get(mode, "")
        mode_label = mode_emoji + mode + mode_emoji

        if (
            self.bot.config.game.official_tournament_channel_id
            and ctx.channel.id == self.bot.config.game.official_tournament_channel_id
        ):
            view = JoinView(
                Button(style=ButtonStyle.primary, label=_("Join the Werewolf game!")),
                message=_("You joined the Werewolf game."),
                timeout=60 * 10,
            )
            text = _(
                "**{author} started a mass-game of Werewolf!**\n**{mode}** mode on"
                " **{speed}** speed. You can join in the next 10 minutes."
                " **Minimum of {min_players} players are required.**"
            )

            await ctx.send(
                embed=discord.Embed(
                    title=_("Werewolf Mass-game!"),
                    description=text.format(
                        author=ctx.author.mention,
                        mode=mode_label,
                        speed=speed,
                        min_players=min_players,
                    ),
                    colour=self.bot.config.game.primary_colour,
                )
                .set_author(
                    name=str(ctx.author), icon_url=ctx.author.display_avatar.url
                )
                .add_field(name=_("New to Werewolf?"), value=additional_text),
                view=view,
            )

            await asyncio.sleep(60)
            view.stop()
            players = list(view.joined)
        else:
            view = JoinView(
                Button(style=ButtonStyle.primary, label=_("Join the Werewolf game!")),
                message=_("You joined the Werewolf game."),
                timeout=120,
            )
            view.joined.add(ctx.author)
            title = _("Werewolf game!")
            text = _(
                "**{author} started a game of Werewolf!**\n**{mode}** mode on"
                " **{speed}** speed. Minimum of"
                " **{min_players}** players are required. Starting in 2 minutes."
            )

            try:
                await ctx.send(
                    embed=discord.Embed(
                        title=title,
                        description=text.format(
                            author=ctx.author.mention,
                            mode=mode_label,
                            speed=speed,
                            min_players=min_players,
                        ),
                        colour=self.bot.config.game.primary_colour,
                    )
                    .set_author(
                        name=str(ctx.author), icon_url=ctx.author.display_avatar.url
                    )
                    .add_field(name=_("New to Werewolf?"), value=additional_text),
                    view=view,
                )
            except discord.errors.Forbidden:
                del self.games[ctx.channel.id]
                await ctx.send(
                    _(
                        "An error happened during the Werewolf. Missing Permission:"
                        " `Embed Links` . Please check the **Edit Channel >"
                        " Permissions** and **Server Settings > Roles** then try again!"
                    )
                )
                return

            await asyncio.sleep(60 * 2)
            view.stop()
            players = list(view.joined)

        if len(players) < min_players:
            del self.games[ctx.channel.id]
            await self.bot.reset_cooldown(ctx)
            await ctx.send(
                _(
                    "Not enough players joined... We didn't reach the minimum"
                    " {min_players} players. 🙁"
                ).format(min_players=min_players)
            )
            return

        if custom_roles is not None:
            max_roles = len(players) + 2
            if len(custom_roles) > max_roles:
                del self.games[ctx.channel.id]
                await self.bot.reset_cooldown(ctx)
                await ctx.send(
                    _(
                        "You specified **{specified}** roles, but this game can only use"
                        " up to **{max_roles}** roles with **{players}** players."
                    ).format(
                        specified=len(custom_roles),
                        max_roles=max_roles,
                        players=len(players),
                    )
                )
                return

        role_xp_eligible = await self._is_role_xp_eligible_match(ctx)
        players = random.shuffle(players)
        try:
            game = Game(ctx, players, mode, speed, custom_roles=custom_roles)
            self.games[ctx.channel.id] = game
            await game.run()
            await self._award_role_xp(game, eligible=role_xp_eligible)
        except Exception as e:
            await send_traceback(ctx, e)
            del self.games[ctx.channel.id]
            raise

        try:
            del self.games[ctx.channel.id]
        except KeyError:  # got stuck in between
            pass

    @commands.group(
        invoke_without_command=True,
        case_insensitive=True,
        aliases=["nww"],
        brief=_("Starts a game of NewWerewolf"),
    )
    @locale_doc
    async def newwerewolf(
        self,
        ctx,
        mode: str.title | None = "Classic",
        speed: str.title = "Normal",
        min_players: IntGreaterThan(1) = None,
    ):
        _(
            """
            `[mode]` - The mode to play, see below for available options. (optional and defaults to Classic)
            `[speed]` - The game speed to play, see below available options. (optional and defaults to Normal)
            `[min_players]` - The minimum players needed to play. (optional and defaults depending on the game mode: Classic: 5, Imbalanced: 5, Huntergame: 8, Villagergame: 5, Valentines: 8, IdleRPG: 5)

            Starts a game of NewWerewolf. Find the werewolves, before they find you!
            Your goal to win is indicated on the role you have.
            **Game modes:** `Classic` (default), `Imbalanced`, `Huntergame`, `Villagergame`, `Valentines`, `IdleRPG`. Use `{prefix}nww modes` for detailed info.
            **Game speeds** (in seconds): `Normal`: 60 (default), `Extended`: 90, `Fast`: 45, `Blitz`: 30. Use `{prefix}nww speeds` for detailed info.
            **Aliases:**
            `nww`
            **Examples:**
            `{prefix}nww Blitz` for Classic mode on Blitz speed
            `{prefix}nww Imbalanced` for Imbalanced mode on Normal speed
            `{prefix}nww Valentines Extended` for Valentines mode on Extended speed
            `{prefix}nww Huntergame Fast` for Huntergame mode on Fast speed
            """
        )
        # TODO:
        # Bizarro: Roles are flipped.
        # Random: Roles are reassigned randomly every night.
        # Zombie (Classic-based, another team) - There's a chance that a random player will be randomly resurrected as Zombie and they can devour any villagers or werewolves with the other zombies.

        game_modes = [
            "Classic",
            "Imbalanced",
            "Huntergame",
            "Villagergame",
            "Valentines",
            "Idlerpg",
        ]
        game_speeds = ["Normal", "Extended", "Fast", "Blitz"]
        minimum_players = {
            "Classic": 5,
            "Imbalanced": 5,
            "Huntergame": 8,
            "Villagergame": 5,
            "Valentines": 8,
            "IdleRPG": 5,
        }

        mode_token = str(mode or "Classic").strip().title()
        speed_token = str(speed or "Normal").strip().title()

        # Support shorthand like `nww Blitz` and keep roster behavior tied to mode.
        # Blitz/Fast/Extended/Normal are speeds, not separate role rosters.
        if mode_token in game_speeds:
            inferred_speed = mode_token
            inferred_mode = "Classic"
            if speed_token in game_modes:
                inferred_mode = speed_token
            elif speed_token.isdigit() and min_players is None:
                parsed_min_players = int(speed_token)
                if parsed_min_players <= 1:
                    return await ctx.send(
                        _("Minimum players must be greater than 1.")
                    )
                min_players = parsed_min_players
            mode_token = inferred_mode
            speed_token = inferred_speed

        if mode_token not in game_modes:
            return await ctx.send(
                _(
                    "Invalid game mode. Use `{prefix}help nww` to get help on this"
                    " command."
                ).format(prefix=ctx.clean_prefix)
            )
        if mode_token == "Idlerpg":
            mode_token = "IdleRPG"

        if not min_players:
            min_players = minimum_players.get(mode_token, 5)

        await self._start_multiplayer_game(
            ctx,
            mode=mode_token,
            speed=speed_token,
            min_players=min_players,
        )

    @newwerewolf.command(
        name="custom",
        aliases=["cstm"],
        brief=_("Starts a custom-role multiplayer Werewolf game"),
    )
    @locale_doc
    async def newwerewolf_custom(self, ctx, *, roles: str):
        _(
            """Start a custom-role Werewolf game.

            Usage example:
            `{prefix}nww custom witch, werewolf, jester`

            Notes:
            - Separate roles with commas.
            - Repeating a role means it can spawn multiple times.
            - Any unfilled slots are generated with the normal balanced role system.
            - The game always guarantees at least one Werewolf-team role and one Villager-team role."""
        )

        parsed_roles, invalid_tokens = parse_custom_roles(roles)
        if invalid_tokens:
            invalid_display = ", ".join(f"`{token}`" for token in invalid_tokens)
            return await ctx.send(
                _(
                    "I couldn't recognize these roles: {roles}\nUse `{prefix}nww roles`"
                    " to see valid names."
                ).format(roles=invalid_display, prefix=ctx.clean_prefix)
            )

        if not parsed_roles:
            return await ctx.send(
                _(
                    "You need to specify at least one role.\nExample: `{prefix}nww"
                    " custom witch, werewolf, jester`"
                ).format(prefix=ctx.clean_prefix)
            )
        unavailable = unavailable_roles_for_mode(parsed_roles, "Custom")
        if unavailable:
            unique_unavailable: list[ROLES] = []
            seen: set[ROLES] = set()
            for role in unavailable:
                if role in seen:
                    continue
                seen.add(role)
                unique_unavailable.append(role)
            unavailable_display = ", ".join(
                f"`{role.name.replace('_', ' ').title()}`" for role in unique_unavailable
            )
            return await ctx.send(
                _(
                    "These roles are disabled or not allowed in **Custom** mode:"
                    " {roles}\nEdit `cogs/newwerewolf/role_config.py` to change role"
                    " availability."
                ).format(roles=unavailable_display)
            )

        await self._start_multiplayer_game(
            ctx,
            mode="Custom",
            speed="Normal",
            min_players=3,
            custom_roles=parsed_roles,
        )

    @newwerewolf.command(brief=_("See available werewolf game modes"))
    @locale_doc
    async def modes(self, ctx):
        _("""Used to see the list of available werewolf game modes.""")
        return await ctx.send(
            embed=discord.Embed(
                title=_("Werewolf Game Modes"),
                description=_(
                    """\
**Game modes:** `Classic` (default), `Imbalanced`, `Huntergame`, `Villagergame`, `Valentines`, `IdleRPG`, `Custom`.
`Classic`: Play the classic werewolf game. (default)
`Imbalanced`: Some roles that are only available in larger games have chances to join even in smaller games. (The size of the game being referred here is about the number of players, i.e. 5-player game is small)
`Huntergame`: Only Hunters and Werewolves are available.
`Villagergame`: No special roles, only Villagers and Werewolves are available.
`Valentines`: There are multiple lovers or couples randomly chosen at the start of the game. A chain of lovers might exist upon the Amor's arrows. If the remaining players are in a single chain of lovers, they all win.
`IdleRPG`: (based on Imbalanced mode) New roles are available: Paragon, Raider, Lawyer, Troublemaker, War Veteran, Wolf Shaman, Wolf Necromancer, Alpha Werewolf, Guardian Wolf, Superspreader, Red Lady, Priest, Pacifist, Grumpy Grandma, Nightmare Werewolf. (`Ritualist`, `Ghost Lady`, `Marksman`, `Forger`, `Serial Killer`, `Cannibal`, `Wolf Summoner`, `Sorcerer`, and `Voodoo Werewolf` are advanced unlocks.)
`Custom`: Use `{prefix}nww custom <role1, role2, ...>` to seed exact roles (duplicates allowed). Remaining slots are filled with normal balance."""
                ).format(prefix=ctx.clean_prefix),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )

    @newwerewolf.command(brief=_("See available werewolf game speeds"))
    @locale_doc
    async def speeds(self, ctx):
        _("""Used to see the list of available werewolf game speeds.""")
        return await ctx.send(
            embed=discord.Embed(
                title=_("Werewolf Game Speeds"),
                description=_(
                    """\
**Game speeds** (in seconds): `Normal`: 60 (default), `Extended`: 90, `Fast`: 45, `Blitz`: 30
`Normal`: All major action timers are limited to 60 seconds and number of days to play is unlimited.
`Extended`: All major action timers are limited to 90 seconds and number of days to play is unlimited.
`Fast`: All major action timers are limited to 45 seconds and number of days to play is dependent on the number of players plus 3 days. This means not killing anyone every night or every election will likely end the game with no winners.
`Blitz`: Warning: This is a faster game speed suitable for experienced players. All action timers are limited to 30 seconds and number of days to play is dependent on the number of players plus 3 days. This means not killing anyone every night or every election will likely end the game with no winners.
`Note`: Speed does not change the role roster. `Blitz` uses the same roster as the selected mode (for example, `Classic` roster on `Blitz`)."""
                ),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )

    @newwerewolf.command(brief=_("Check your werewolf role"))
    @locale_doc
    async def myrole(self, ctx):
        _(
            """Check your role in the Werewolf game and have the bot DM it to you.

            You must be part of the ongoing game to get your role."""
        )
        game = self.games.get(ctx.channel.id)
        if not game:
            return await ctx.send(
                _("There is no newwerewolf game in this channel! {author}").format(
                    author=ctx.author.mention
                )
            )
        if game == "forming":
            return await ctx.send(
                _("The game has yet to be started {author}.").format(
                    author=ctx.author.mention
                )
            )
        if ctx.author not in [player.user for player in game.players]:
            return await ctx.send(
                _("You're not in the game {author}.").format(author=ctx.author.mention)
            )
        else:
            player = discord.utils.get(game.players, user=ctx.author)
            if player is None:
                return await ctx.send(
                    _(
                        "You asked for your role in {channel} but your info couldn't be"
                        " found."
                    ).format(channel=ctx.channel.mention)
                )
            else:
                try:
                    if player.role != player.initial_roles[0]:
                        initial_role_info = _(
                            " A **{initial_roles}** initially"
                        ).format(
                            initial_roles=", ".join(
                                [
                                    game.get_role_name(initial_role)
                                    for initial_role in player.initial_roles
                                ]
                            )
                        )
                    else:
                        initial_role_info = ""
                    await ctx.author.send(
                        _(
                            "Checking your role in {ww_channel}... You are a"
                            " **{role_name}**!{initial_role_info}\n\n{description}"
                        ).format(
                            ww_channel=ctx.channel.mention,
                            role_name=player.role_name,
                            initial_role_info=initial_role_info,
                            description=ROLE_DESC[player.role],
                        )
                    )
                    return await ctx.send(
                        _("I sent a DM containing your role info, {author}.").format(
                            author=ctx.author.mention
                        )
                    )
                except discord.Forbidden:
                    return await ctx.send(
                        _("I couldn't send a DM to you {author}.").format(
                            author=ctx.author.mention
                        )
                    )

    @newwerewolf.command(
        name="progress",
        aliases=["xp", "levels"],
        brief=_("View role XP and advanced unlock progress"),
    )
    @locale_doc
    async def progress(self, ctx, *, role: str = None):
        _(
            """View your NewWerewolf role XP progress and advanced unlock status.

            `{prefix}nww progress`
            `{prefix}nww progress bodyguard`
            """
        )
        if not hasattr(self.bot, "pool"):
            return await ctx.send(
                _("Role XP is unavailable right now (no database connection).")
            )

        xp_map = await self._fetch_user_role_xp_map(ctx.author.id)
        base_roles = sorted(
            ADVANCED_ROLE_TIERS_BY_BASE.keys(),
            key=lambda role_obj: self._role_display_name(role_obj).lower(),
        )
        if not base_roles:
            return await ctx.send(_("No advanced role progression is configured yet."))

        if role is not None:
            parsed_roles, invalid_tokens = parse_custom_roles(role)
            if invalid_tokens or not parsed_roles:
                return await ctx.send(
                    _(
                        "I couldn't recognize that role. Use `{prefix}nww roles` to"
                        " see valid role names."
                    ).format(prefix=ctx.clean_prefix)
                )
            if len(parsed_roles) != 1:
                return await ctx.send(_("Please specify exactly one role."))

            requested_role = parsed_roles[0]
            base_role = ADVANCED_BASE_ROLE_BY_ADVANCED.get(requested_role, requested_role)
            if base_role not in ADVANCED_ROLE_TIERS_BY_BASE:
                return await ctx.send(
                    _("**{role}** has no advanced unlock path configured.").format(
                        role=self._role_display_name(base_role)
                    )
                )

            base_role_name = self._role_display_name(base_role)
            xp = xp_map.get(base_role.name.casefold(), 0)
            level = role_level_from_xp(xp)
            max_level = max(1, int(MAX_ROLE_LEVEL))
            xp_per_level = max(1, int(ROLE_XP_PER_LEVEL))
            if level >= max_level:
                next_level_text = _("Max level reached.")
            else:
                xp_target = level * xp_per_level
                xp_to_next = max(0, xp_target - xp)
                next_level_text = _("{xp} XP to level {level}.").format(
                    xp=xp_to_next, level=level + 1
                )

            unlock_tiers = sorted(
                ADVANCED_ROLE_TIERS_BY_BASE.get(base_role, {}).items(),
                key=lambda pair: pair[0],
            )
            unlock_lines = []
            for unlock_level, advanced_role in unlock_tiers:
                status = _("Unlocked") if level >= unlock_level else _("Locked")
                unlock_lines.append(
                    _("Lv {level}: {role} - {status}").format(
                        level=unlock_level,
                        role=self._role_display_name(advanced_role),
                        status=status,
                    )
                )

            embed = discord.Embed(
                title=_("NewWerewolf Progress"),
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            if requested_role != base_role:
                embed.description = _(
                    "Showing base-role progression for **{base}** (requested role:"
                    " **{requested}**)."
                ).format(
                    base=base_role_name,
                    requested=self._role_display_name(requested_role),
                )
            else:
                embed.description = _("Showing progression for **{role}**.").format(
                    role=base_role_name
                )
            embed.add_field(
                name=_("XP"),
                value=_("{xp} XP | Level {level}/{max_level}").format(
                    xp=xp, level=level, max_level=max_level
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Next Level"),
                value=next_level_text,
                inline=False,
            )
            embed.add_field(
                name=_("Advanced Unlocks"),
                value="\n".join(unlock_lines) if unlock_lines else _("None"),
                inline=False,
            )
            return await ctx.send(embed=embed)

        summary_lines: list[str] = []
        for base_role in base_roles:
            role_name = self._role_display_name(base_role)
            xp = xp_map.get(base_role.name.casefold(), 0)
            level = role_level_from_xp(xp)
            unlock_tiers = sorted(
                ADVANCED_ROLE_TIERS_BY_BASE.get(base_role, {}).items(),
                key=lambda pair: pair[0],
            )
            unlocked_roles = [
                self._role_display_name(advanced_role)
                for unlock_level, advanced_role in unlock_tiers
                if level >= unlock_level
            ]
            next_unlock = next(
                (
                    (unlock_level, advanced_role)
                    for unlock_level, advanced_role in unlock_tiers
                    if level < unlock_level
                ),
                None,
            )
            unlocked_label = (
                ", ".join(unlocked_roles) if unlocked_roles else _("none")
            )
            if next_unlock is None:
                next_label = _("All unlock tiers reached")
            else:
                next_label = _("Lv {level} {role}").format(
                    level=next_unlock[0],
                    role=self._role_display_name(next_unlock[1]),
                )
            summary_lines.append(
                _(
                    "`{role}` - Lv {level} ({xp} XP) | Unlocked: {unlocked} | Next:"
                    " {next_unlock}"
                ).format(
                    role=role_name,
                    level=level,
                    xp=xp,
                    unlocked=unlocked_label,
                    next_unlock=next_label,
                )
            )

        chunks = self._chunk_lines(summary_lines)
        embeds = []
        for idx, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=_("NewWerewolf Progress"),
                description=chunk,
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            embed.set_footer(
                text=_("Page {page}/{total} | Use `{prefix}nww progress <role>` for details").format(
                    page=idx,
                    total=len(chunks),
                    prefix=ctx.clean_prefix,
                )
            )
            embeds.append(embed)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @newwerewolf.command(brief=_("View descriptions of game roles"))
    @locale_doc
    async def roles(self, ctx, *, role=None):
        _(
            """View the descriptions of roles in the Werewolf game.
            `{prefix}roles` to see all roles.
            `{prefix}roles <role name here>` to view info about a role.
            """
        )
        restriction = _("(IdleRPG mode only)")
        role_groups = [
            {
                "side": _("The Werewolves"),
                "members": (
                    "Werewolf, Junior Werewolf, Wolf Seer, Sorcerer - Advanced"
                    " unlock, White Wolf, Cursed Wolf"
                    " Father, Big Bad Wolf, Wolf"
                    f" Shaman - {restriction}, Wolf Necromancer - {restriction},"
                    f" Alpha Werewolf - {restriction}, Wolf Summoner - Advanced unlock,"
                    " Wolf Trickster - Advanced unlock,"
                    f" Guardian Wolf - {restriction}, Nightmare Werewolf - {restriction},"
                    " Voodoo Werewolf - Advanced unlock, Wolf Pacifist - Advanced"
                    " unlock"
                ),
                "goal": _("Must eliminate all other villagers"),
            },
            {
                "side": _("The Villagers"),
                "members": (
                    "Villager, Cursed, Pure Soul, Flower Child, Seer, Aura Seer,"
                    " Gambler - Advanced unlock, Witch,"
                    " Forger - Advanced unlock,"
                    " Doctor, Bodyguard, Sheriff, Jailer, Medium, Loudmouth, Avenger,"
                    f" Red Lady - {restriction}, Ghost Lady - Advanced unlock, Priest - {restriction}, Marksman - Advanced unlock, Pacifist -"
                    f" {restriction}, Grumpy Grandma - {restriction}, Detective,"
                    " Mortician - Advanced unlock, Warden -"
                    " Advanced unlock, Seer Apprentice - Advanced unlock, Tough Guy -"
                    " Advanced unlock,"
                    " Healer, Amor,"
                    " Knight, Fortune Teller, Hunter -"
                    " Huntergame only,"
                    f" Sister, Brother, The Old, Fox, Judge, Paragon - {restriction},"
                    " Ritualist - Advanced unlock,"
                    f" Troublemaker - {restriction}, Lawyer - {restriction},"
                    f" War Veteran - {restriction}"
                ),
                "goal": _("Must find and eliminate the werewolves"),
            },
            {
                "side": _("The Ambiguous"),
                "members": (
                    f"Thief, Maid, Wolfhound, Raider - {restriction}"
                ),
                "goal": _("Make their side win"),
            },
            {
                "side": _("The Loners"),
                "members": (
                    f"White Wolf - {_('Be the sole survivor')}, Flutist -"
                    f" {_('Must enchant every living inhabitants')}, Superspreader -"
                    f" {_('Infect all the players with your virus')} {restriction},"
                    f" Jester -"
                    f" {_('Die to win')}, Head Hunter -"
                    f" {_('Get your assigned target lynched')},"
                    f" Serial Killer - {_('Be the sole survivor')} (Advanced unlock),"
                    f" Cannibal - {_('Be the sole survivor')} (Advanced unlock)"
                ),
                "goal": _("Must complete their own objective"),
            },
        ]

        def has_role(group: dict[str, str], role_name: str) -> bool:
            normalized_members = [
                member.split(" - ")[0].strip().lower()
                for member in group["members"].split(",")
            ]
            return role_name.lower() in normalized_members

        if role is None:
            em = discord.Embed(
                title=_("Werewolf Roles"),
                description=_(
                    "Roles are grouped into \n1. the Werewolves,\n2. the Villagers,\n3."
                    " the Ambiguous, and\n4. the Loners.\n**The available roles are:**"
                ),
                url="https://wiki.idlerpg.xyz/index.php?title=Werewolf",
                colour=self.bot.config.game.primary_colour,
            ).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            tip = _(
                "Use `{prefix}nww roles <role>` to view the description on a specific"
                " role."
            ).format(prefix=ctx.clean_prefix)
            embeds = [
                em.copy().add_field(
                    name=f"{group['side']} - {_('Goal')}: {group['goal']}",
                    value=group["members"].replace(", ", "\n") + f"\n\n**Tip:** {tip}",
                    inline=True,
                )
                for group in role_groups
            ]
            return await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

        search_role = role.upper().replace(" ", "_")
        try:
            ROLES[search_role]
        except KeyError:
            return await ctx.send(
                _("{role}? I couldn't find that role.").format(role=role.title())
            )
        role_groups.reverse()
        return await ctx.send(
            embed=discord.Embed(
                title=search_role.title().replace("_", " "),
                description=ROLE_DESC[ROLES[search_role]],
                colour=self.bot.config.game.primary_colour,
            )
            .add_field(
                name=_("Side:"),
                value=", ".join(
                    [
                        group["side"]
                        for group in role_groups
                        if has_role(group, role.title())
                    ]
                ),
                inline=True,
            )
            .add_field(
                name=_("Goal:"),
                value=", ".join(
                    [
                        group["goal"]
                        for group in role_groups
                        if has_role(group, role.title())
                    ]
                ),
                inline=True,
            )
            .set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        )


async def setup(bot):
    await bot.add_cog(NewWerewolf(bot))
