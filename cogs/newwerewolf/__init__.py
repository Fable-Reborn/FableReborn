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

from classes.converters import IntGreaterThan, WerewolfMode
from utils import random
from utils.i18n import _, locale_doc
from utils.joins import JoinView
from .core import DESCRIPTIONS as ROLE_DESC
from .core import Game
from .core import Role as ROLES
from .core import parse_custom_roles
from .core import send_traceback

class NewWerewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}

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

        players = random.shuffle(players)
        try:
            game = Game(ctx, players, mode, speed, custom_roles=custom_roles)
            self.games[ctx.channel.id] = game
            await game.run()
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
        mode: WerewolfMode | None = "Classic",
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
        minimum_players = {
            "Classic": 5,
            "Imbalanced": 5,
            "Huntergame": 8,
            "Villagergame": 5,
            "Valentines": 8,
            "IdleRPG": 5,
        }

        if mode not in game_modes:
            return await ctx.send(
                _(
                    "Invalid game mode. Use `{prefix}help nww` to get help on this"
                    " command."
                ).format(prefix=ctx.clean_prefix)
            )
        if mode == "Idlerpg":
            mode = "IdleRPG"

        if not min_players:
            min_players = minimum_players.get(mode, 5)

        await self._start_multiplayer_game(
            ctx,
            mode=mode,
            speed=speed,
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
`IdleRPG`: (based on Imbalanced mode) New roles are available: Paragon, Raider, Ritualist, Lawyer, Troublemaker, War Veteran, Wolf Shaman, Wolf Necromancer, Superspreader.
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
`Blitz`: Warning: This is a faster game speed suitable for experienced players. All action timers are limited to 30 seconds and number of days to play is dependent on the number of players plus 3 days. This means not killing anyone every night or every election will likely end the game with no winners."""
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
                    "Werewolf, Junior Werewolf, Wolf Seer, White Wolf, Cursed Wolf"
                    " Father, Big Bad Wolf, Wolf"
                    f" Shaman - {restriction}, Wolf Necromancer - {restriction}"
                ),
                "goal": _("Must eliminate all other villagers"),
            },
            {
                "side": _("The Villagers"),
                "members": (
                    "Villager, Cursed, Pure Soul, Flower Child, Seer, Aura Seer, Witch,"
                    " Doctor, Bodyguard, Sheriff, Jailer, Medium, Loudmouth, Avenger,"
                    " Healer, Amor, Knight, Fortune Teller, Hunter - Huntergame only,"
                    f" Sister, Brother, The Old, Fox, Judge, Paragon - {restriction},"
                    f" Ritualist - {restriction}, Troublemaker - {restriction}, Lawyer"
                    f" - {restriction}, War Veteran - {restriction}"
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
                    f" {_('Get your assigned target lynched')}"
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
