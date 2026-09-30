"""The Theme Trade-In Contract: swap an owned collectible for a random unowned one of the same rarity."""

import discord

from .themes import THEMES, resolve_theme
from .theme_unlocks import (
    COLLECTIBLE_THEMES,
    RARITY_EMOJI,
    RARITY_WEIGHTS,
    TRADE_CONTRACT_NAME,
    TRADE_CONTRACT_TYPE,
    trade_in_options,
    trade_in_theme,
)

CONTRACT_EMOJI = "📜"
CONTRACT_COLOUR = 0xC9A227
# `$consume <alias>` names that open the contract (normalised: lowercase, spaces for _ and -).
CONTRACT_ALIASES = frozenset({
    "tradein", "trade in", "contract", "themecontract", "theme contract", "tradeincontract",
    "trade in contract", "theme trade in contract", "theme trade contract",
})


def normalise_alias(value):
    return " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())


def is_contract_alias(value):
    return normalise_alias(value) in CONTRACT_ALIASES


async def load_contract_state(pool, user_id):
    """(contracts held, owned collectible theme keys)."""
    async with pool.acquire() as conn:
        quantity = await conn.fetchval(
            'SELECT COALESCE(SUM(quantity), 0) FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;',
            user_id, TRADE_CONTRACT_TYPE,
        )
        rows = await conn.fetch('SELECT theme_key FROM profile_theme_unlocks WHERE user_id = $1;', user_id)
    owned = {row["theme_key"] for row in rows if row["theme_key"] in COLLECTIBLE_THEMES}
    return int(quantity or 0), owned


def _label(key):
    drop = COLLECTIBLE_THEMES[key]
    return f"{RARITY_EMOJI[drop.rarity]} **{THEMES[key].name}** ({drop.rarity})"


def complete_message(rarity):
    return (
        f"You already own every {RARITY_EMOJI[rarity]} **{rarity}** theme, so there is nothing to trade for. "
        "Your contract was **not** used."
    )


class TradeInView(discord.ui.View):
    """Pick a rarity, pick the theme to give up, confirm. Only the contract holder can use it."""

    def __init__(self, ctx, contracts, owned, preselected=None):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.contracts = contracts
        self.owned = set(owned)
        self.rarity = COLLECTIBLE_THEMES[preselected].rarity if preselected else None
        self.theme = preselected
        self.equipped = None  # set by start_trade_in; warns when trading the worn theme
        self.message = None
        self.done = False

        self.rarity_select = discord.ui.Select(placeholder="1. Choose a rarity", row=0)
        self.rarity_select.callback = self.choose_rarity
        self.theme_select = discord.ui.Select(placeholder="2. Choose the theme to give up", row=1)
        self.theme_select.callback = self.choose_theme
        self.confirm_button = discord.ui.Button(
            label="Trade it in", emoji=CONTRACT_EMOJI, style=discord.ButtonStyle.success, row=2,
        )
        self.confirm_button.callback = self.confirm
        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=2)
        self.cancel_button.callback = self.cancel
        for item in (self.rarity_select, self.theme_select, self.confirm_button, self.cancel_button):
            self.add_item(item)
        self.refresh()

    # ---- state -------------------------------------------------------------
    def owned_in(self, rarity):
        return sorted(
            (key for key in self.owned if COLLECTIBLE_THEMES[key].rarity == rarity),
            key=lambda key: THEMES[key].name,
        )

    def refresh(self):
        rarities = [rarity for rarity in RARITY_WEIGHTS if self.owned_in(rarity)]
        self.rarity_select.options = [
            discord.SelectOption(
                label=rarity,
                value=rarity,
                emoji=RARITY_EMOJI[rarity],
                description=self._rarity_note(rarity),
                default=rarity == self.rarity,
            )
            for rarity in rarities
        ] or [discord.SelectOption(label="No collectible themes", value="none")]
        self.rarity_select.disabled = not rarities

        themes = self.owned_in(self.rarity) if self.rarity else []
        self.theme_select.options = [
            discord.SelectOption(
                label=THEMES[key].name[:100],
                value=key,
                emoji=THEMES[key].emoji,
                default=key == self.theme,
            )
            for key in themes[:25]
        ] or [discord.SelectOption(label="Choose a rarity first", value="none")]
        self.theme_select.disabled = not themes
        self.confirm_button.disabled = self.theme is None or not trade_in_options(self.owned, self.rarity)

    def _rarity_note(self, rarity):
        missing = len(trade_in_options(self.owned, rarity))
        owned = len(self.owned_in(rarity))
        if not missing:
            return f"Own {owned} · complete, nothing to receive"
        return f"Own {owned} · {missing} you don't have yet"

    def embed(self):
        embed = discord.Embed(
            title=f"{CONTRACT_EMOJI} {TRADE_CONTRACT_NAME}",
            description=(
                "Give up one theme you own and receive a **random theme of the same rarity** "
                "that you don't own yet.\n"
                f"You have **{self.contracts}** contract{'s' if self.contracts != 1 else ''}. One is used per trade."
            ),
            color=CONTRACT_COLOUR,
        )
        if self.theme:
            missing = len(trade_in_options(self.owned, self.rarity))
            if missing:
                lines = [
                    f"You give up {_label(self.theme)}.",
                    f"You receive 1 of **{missing}** {RARITY_EMOJI[self.rarity]} {self.rarity} theme"
                    f"{'s' if missing != 1 else ''} you don't own.",
                ]
                if self.theme == self.equipped:
                    lines.append("⚠️ This theme is equipped; your profile goes back to **Classic**.")
                embed.add_field(name="The trade", value="\n".join(lines), inline=False)
            else:
                embed.add_field(name="Nothing to trade for", value=complete_message(self.rarity), inline=False)
        elif self.rarity and not trade_in_options(self.owned, self.rarity):
            embed.add_field(name="Nothing to trade for", value=complete_message(self.rarity), inline=False)
        embed.set_footer(text="Traded themes are removed from your collection.")
        return embed

    # ---- interactions ------------------------------------------------------
    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This contract isn't yours.", ephemeral=True)
            return False
        return not self.done

    async def choose_rarity(self, interaction):
        value = self.rarity_select.values[0]
        if value != "none":
            self.rarity, self.theme = value, None
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def choose_theme(self, interaction):
        value = self.theme_select.values[0]
        if value != "none":
            self.theme = value
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def cancel(self, interaction):
        self.done = True
        self.stop()
        await interaction.response.edit_message(
            content="Trade-in cancelled. Your contract was kept.", embed=None, view=None,
        )

    async def confirm(self, interaction):
        self.done = True
        self.stop()
        result = await trade_in_theme(self.ctx.bot.pool, self.ctx.author.id, self.theme)
        await interaction.response.edit_message(content=None, embed=self.result_embed(result), view=None)

    def result_embed(self, result):
        prefix = self.ctx.clean_prefix
        if result.status == "traded":
            received = THEMES[result.received]
            lines = [
                f"You gave up {_label(result.given)}",
                f"and received {RARITY_EMOJI[result.rarity]} **{received.name}** ({result.rarity})!",
                "",
                f"Preview: `{prefix}prpg preview {received.key}`",
                f"Equip: `{prefix}prpg theme {received.key}`",
            ]
            if result.unequipped:
                lines.append("Your traded theme was equipped, so your profile is back on **Classic**.")
            return discord.Embed(title=f"{CONTRACT_EMOJI} Contract fulfilled", description="\n".join(lines),
                                 color=CONTRACT_COLOUR)
        message = {
            "no_contract": f"You don't have a **{TRADE_CONTRACT_NAME}**.",
            "not_owned": "You no longer own that theme. Your contract was not used.",
            "not_tradable": "Only collectible themes can be traded in. Your contract was not used.",
            "complete": complete_message(result.rarity) if result.rarity else "",
            "no_character": "You need a character to use this.",
        }[result.status]
        return discord.Embed(title=f"{CONTRACT_EMOJI} No trade made", description=message, color=CONTRACT_COLOUR)

    async def on_timeout(self):
        if self.message is not None and not self.done:
            try:
                await self.message.edit(content="The contract closed without a trade. It was kept.", view=None)
            except discord.HTTPException:
                pass


async def start_trade_in(ctx, theme_query=None):
    """Open the contract for ``ctx.author``; ``theme_query`` skips straight to that theme."""
    contracts, owned = await load_contract_state(ctx.bot.pool, ctx.author.id)
    if contracts < 1:
        return await ctx.send(
            f"You don't have a **{TRADE_CONTRACT_NAME}**. They can appear in the Trader's shop "
            f"(`{ctx.clean_prefix}trader`) or be traded from other players."
        )
    if not owned:
        return await ctx.send("You don't own any collectible themes to trade in. Your contract was kept.")

    preselected = None
    if theme_query:
        theme = resolve_theme(theme_query)
        if theme is None or theme.key not in COLLECTIBLE_THEMES:
            return await ctx.send("Only collectible themes can be traded in. Your contract was kept.")
        if theme.key not in owned:
            return await ctx.send(f"You don't own **{theme.name}**. Your contract was kept.")
        rarity = COLLECTIBLE_THEMES[theme.key].rarity
        if not trade_in_options(owned, rarity):
            return await ctx.send(complete_message(rarity))
        preselected = theme.key

    view = TradeInView(ctx, contracts, owned, preselected)
    async with ctx.bot.pool.acquire() as conn:
        view.equipped = await conn.fetchval('SELECT prpg_theme FROM profile WHERE "user" = $1;', ctx.author.id)
    view.message = await ctx.send(embed=view.embed(), view=view)
    return view.message
