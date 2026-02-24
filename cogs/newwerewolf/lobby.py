from __future__ import annotations

import asyncio

import discord

from discord.enums import ButtonStyle
from discord.ui.button import Button

from utils.i18n import _
from utils.joins import JoinView


def _build_mode_label(mode: str) -> str:
    mode_emojis = {"Huntergame": "🔫", "Valentines": "💕", "Custom": "🧩"}
    mode_emoji = mode_emojis.get(mode, "")
    return mode_emoji + mode + mode_emoji


async def collect_players(
    ctx,
    *,
    mode: str,
    speed: str,
    min_players: int,
) -> list[discord.abc.User]:
    additional_text = _(
        "Use `{prefix}help nww` to get help on NewWerewolf commands. Use `{prefix}nww"
        " roles` to view descriptions of game roles and their goals to win. Use"
        " `{prefix}nww modes` and `{prefix}nww speeds` to see info about available"
        " game modes and speeds."
    ).format(prefix=ctx.clean_prefix)
    mode_label = _build_mode_label(mode)

    if (
        ctx.bot.config.game.official_tournament_channel_id
        and ctx.channel.id == ctx.bot.config.game.official_tournament_channel_id
    ):
        view = JoinView(
            Button(style=ButtonStyle.primary, label=_("Join the NewWerewolf game!")),
            message=_("You joined the NewWerewolf game."),
            timeout=60 * 10,
        )
        text = _(
            "**{author} started a mass-game of NewWerewolf!**\n**{mode}** mode on"
            " **{speed}** speed. You can join in the next 10 minutes."
            " **Minimum of {min_players} players are required.**"
        )
        await ctx.send(
            embed=discord.Embed(
                title=_("NewWerewolf Mass-game!"),
                description=text.format(
                    author=ctx.author.mention,
                    mode=mode_label,
                    speed=speed,
                    min_players=min_players,
                ),
                colour=ctx.bot.config.game.primary_colour,
            )
            .set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            .add_field(name=_("New to NewWerewolf?"), value=additional_text),
            view=view,
        )
        await asyncio.sleep(60)
        view.stop()
        return list(view.joined)

    view = JoinView(
        Button(style=ButtonStyle.primary, label=_("Join the NewWerewolf game!")),
        message=_("You joined the NewWerewolf game."),
        timeout=120,
    )
    view.joined.add(ctx.author)
    title = _("NewWerewolf game!")
    text = _(
        "**{author} started a game of NewWerewolf!**\n**{mode}** mode on"
        " **{speed}** speed. Minimum of **{min_players}** players are required."
        " Starting in 2 minutes."
    )
    await ctx.send(
        embed=discord.Embed(
            title=title,
            description=text.format(
                author=ctx.author.mention,
                mode=mode_label,
                speed=speed,
                min_players=min_players,
            ),
            colour=ctx.bot.config.game.primary_colour,
        )
        .set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        .add_field(name=_("New to NewWerewolf?"), value=additional_text),
        view=view,
    )

    await asyncio.sleep(60 * 2)
    view.stop()
    return list(view.joined)
