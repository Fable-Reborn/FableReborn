from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils import checks

from .service import (
    GOLD_PER_CROWN,
    LINK_CODE_TTL_MINUTES,
    convert_gold_to_crowns,
    fetch_rpg_profile,
    issue_link_code,
    revoke_link_code,
)


log = logging.getLogger(__name__)


def format_playtime(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, _seconds = divmod(remainder, 60)
    return f"{hours:,}h {minutes:02d}m"


def format_last_map(name: str | None) -> str:
    normalized = " ".join(str(name or "").split())
    return normalized or "Not visited yet"


class CrownConversionModal(discord.ui.Modal, title="Convert Fable gold to crowns"):
    crowns = discord.ui.TextInput(
        label="Crowns to receive",
        placeholder=f"Each crown costs {GOLD_PER_CROWN:,} Fable gold",
        min_length=1,
        max_length=10,
    )

    def __init__(self, view: "TiamatProfileView"):
        super().__init__()
        self.profile_view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            amount = int(str(self.crowns.value).replace(",", "").strip())
            result = await convert_gold_to_crowns(
                self.profile_view.cog.bot.pool, interaction.user.id, amount
            )
        except (ValueError, LookupError) as error:
            return await interaction.followup.send(str(error), ephemeral=True)
        except Exception:
            log.exception(
                "Unexpected Tiamat crown conversion failure for Discord user %s",
                interaction.user.id,
            )
            return await interaction.followup.send(
                "The conversion could not be completed. No balance was changed; "
                "the error has been logged.",
                ephemeral=True,
            )
        await interaction.followup.send(
            f"Converted **{result.crowns_added:,} crowns** for "
            f"**{result.crowns_added * GOLD_PER_CROWN:,} Fable gold**.\n"
            f"New balances: **{result.crown_balance:,} crowns** and "
            f"**${result.gold_balance:,} Fable gold**.",
            ephemeral=True,
        )


class TiamatProfileView(discord.ui.View):
    def __init__(self, cog: "Tiamat", profile_user: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.profile_user = profile_user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.profile_user:
            return True
        await interaction.response.send_message(
            "Open your own RPG profile with `$rpg` to use these controls.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Convert gold to crowns", style=discord.ButtonStyle.success, emoji="👑")
    async def convert(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(CrownConversionModal(self))

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        embed, linked = await self.cog.build_profile_embed(self.profile_user)
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Convert gold to crowns":
                child.disabled = not linked
        await interaction.response.edit_message(embed=embed, view=self)


class Tiamat(commands.Cog):
    """Verified FableReborn account linking and one-way Tiamat crowns."""

    def __init__(self, bot):
        self.bot = bot

    async def build_profile_embed(self, profile_user: int) -> tuple[discord.Embed, bool]:
        row = await fetch_rpg_profile(self.bot.pool, profile_user)
        if not row:
            return (
                discord.Embed(
                    title="Tiamat RPG",
                    description="Create a Fable profile before linking the RPG.",
                    colour=discord.Colour.red(),
                ),
                False,
            )
        gold = max(0, int(row["money"] or 0))
        linked = bool(row["game_username"])
        embed = discord.Embed(title="Tiamat RPG", colour=discord.Colour.blue())
        embed.add_field(name="Fable gold", value=f"${gold:,}")
        embed.add_field(name="Convertible now", value=f"{gold // GOLD_PER_CROWN:,} crowns")
        if not linked:
            embed.description = (
                "Not linked yet. Run `$link`, then enter the private code while "
                "creating your RPG account."
            )
            embed.add_field(name="Crown wallet", value="Not linked", inline=False)
            return embed, False
        embed.description = f"Linked to **{row['game_username']}** ({row['display_name']})."
        embed.add_field(name="Crown wallet", value=f"👑 {int(row['crowns']):,}")
        embed.add_field(
            name="Gold converted",
            value=f"${int(row['total_converted_gold']):,}",
        )
        embed.add_field(
            name="Last map",
            value=format_last_map(row["last_map_name"]),
        )
        embed.add_field(
            name="RPG character",
            value=(
                f"Level **{int(row['actor_level']):,}**\n"
                f"HP **{int(row['current_hp']):,}/{int(row['max_hp']):,}** · "
                f"MP **{int(row['current_mp']):,}/{int(row['max_mp']):,}**\n"
                f"EXP **{int(row['experience']):,}** · "
                f"Playtime **{format_playtime(row['playtime_seconds'])}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Battle record",
            value=(
                f"{int(row['battles']):,} battles · {int(row['wins']):,} wins · "
                f"{int(row['escapes']):,} escapes"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"One-way conversion: {GOLD_PER_CROWN:,} Fable gold = 1 crown · "
                "RPG stats are client-reported"
            )
        )
        return embed, True

    @checks.has_char()
    @commands.command(name="link", brief="Create a private Tiamat RPG link code")
    async def link(self, ctx) -> None:
        try:
            try:
                code, linked = await issue_link_code(self.bot.pool, ctx.author.id)
            except LookupError as error:
                return await ctx.send(str(error))
            if linked:
                return await ctx.send(
                    f"Your Fable profile is already linked to RPG account "
                    f"**{linked['game_username']}**. Use `$rpg` to view it."
                )
            try:
                await ctx.author.send(
                    "Your one-use Tiamat RPG account link code is:\n\n"
                    f"**`{code}`**\n\n"
                    f"Enter it when creating the RPG account. It expires in "
                    f"{LINK_CODE_TTL_MINUTES} minutes. Never give this code to another player."
                )
            except discord.Forbidden:
                await revoke_link_code(self.bot.pool, ctx.author.id, code)
                return await ctx.send(
                    "I could not DM you. Enable direct messages and run `$link` again."
                )
            await ctx.send("I sent your one-use RPG link code by DM.", delete_after=20)
        except Exception as e:
            print(f"Error in link command: {e}")
            await ctx.send("An error occurred while processing your request. {e}")

    @checks.has_char()
    @commands.command(
        name="rpg",
        aliases=["tiamat", "crowns"],
        brief="View your linked RPG profile and crown wallet",
    )
    async def rpg(self, ctx) -> None:
        embed, linked = await self.build_profile_embed(ctx.author.id)
        view = TiamatProfileView(self, ctx.author.id)
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "Convert gold to crowns":
                child.disabled = not linked
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Tiamat(bot))
