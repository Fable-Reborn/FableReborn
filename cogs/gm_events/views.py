"""Persistent buttons and modals for silent auctions and raffles.

The buttons are ``DynamicItem``s keyed by ``custom_id``, so they keep working after a restart
without re-attaching a view to each message. Every handler answers within Discord's 3 seconds:
the modal is sent first, and the modal submit defers before any database work.
"""
from __future__ import annotations

import discord

from utils.i18n import _

from . import logic

COG_NAME = "GMEvents"


def _cog(interaction: discord.Interaction):
    return interaction.client.get_cog(COG_NAME)


async def _unavailable(interaction: discord.Interaction) -> None:
    text = _("This feature is not available right now.")
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


class BidModal(discord.ui.Modal):
    def __init__(self, auction_id: int) -> None:
        super().__init__(title=_("Sealed Bid"), timeout=300)
        self.auction_id = auction_id
        self.amount = discord.ui.TextInput(
            label=_("Your bid in gold"),
            placeholder="1000, 1,000, 5k, 1.5m",
            min_length=1,
            max_length=24,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = _cog(interaction)
        if cog is None:
            return await _unavailable(interaction)
        try:
            amount = logic.parse_amount(self.amount.value)
        except ValueError as exc:
            return await interaction.followup.send(_(str(exc)), ephemeral=True)
        _ok, message = await cog.place_silent_bid(interaction.user.id, self.auction_id, amount)
        await interaction.followup.send(message, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        interaction.client.dispatch("gm_events_error", error)
        await _safe_followup(interaction)


class BuyModal(discord.ui.Modal):
    def __init__(self, raffle_id: int) -> None:
        super().__init__(title=_("Buy Raffle Tickets"), timeout=300)
        self.raffle_id = raffle_id
        self.quantity = discord.ui.TextInput(
            label=_("How many tickets?"), placeholder="1", min_length=1, max_length=5
        )
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = _cog(interaction)
        if cog is None:
            return await _unavailable(interaction)
        try:
            qty = logic.parse_quantity(self.quantity.value)
        except ValueError as exc:
            return await interaction.followup.send(_(str(exc)), ephemeral=True)
        _ok, message = await cog.buy_raffle_tickets(interaction.user.id, self.raffle_id, qty)
        await interaction.followup.send(message, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        interaction.client.dispatch("gm_events_error", error)
        await _safe_followup(interaction)


async def _safe_followup(interaction: discord.Interaction) -> None:
    text = _("Something went wrong. Your gold was not taken unless you saw a confirmation.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


class SilentBidButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"sa:bid:(?P<id>[0-9]+)"
):
    def __init__(self, auction_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=_("Place / Raise Bid"),
                emoji="🔒",
                style=discord.ButtonStyle.primary,
                custom_id=f"sa:bid:{auction_id}",
            )
        )
        self.auction_id = auction_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BidModal(self.auction_id))


class SilentMineButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"sa:mine:(?P<id>[0-9]+)"
):
    def __init__(self, auction_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=_("View My Bid"),
                style=discord.ButtonStyle.secondary,
                custom_id=f"sa:mine:{auction_id}",
            )
        )
        self.auction_id = auction_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = _cog(interaction)
        if cog is None:
            return await _unavailable(interaction)
        message = await cog.silent_bid_summary(interaction.user.id, self.auction_id)
        await interaction.followup.send(message, ephemeral=True)


class RaffleBuyButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"rf:buy:(?P<id>[0-9]+)"
):
    def __init__(self, raffle_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=_("Buy Tickets"),
                emoji="🎟️",
                style=discord.ButtonStyle.success,
                custom_id=f"rf:buy:{raffle_id}",
            )
        )
        self.raffle_id = raffle_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BuyModal(self.raffle_id))


class RaffleMineButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"rf:mine:(?P<id>[0-9]+)"
):
    def __init__(self, raffle_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=_("My Tickets"),
                style=discord.ButtonStyle.secondary,
                custom_id=f"rf:mine:{raffle_id}",
            )
        )
        self.raffle_id = raffle_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cog = _cog(interaction)
        if cog is None:
            return await _unavailable(interaction)
        message = await cog.raffle_ticket_summary(interaction.user.id, self.raffle_id)
        await interaction.followup.send(message, ephemeral=True)


DYNAMIC_ITEMS = (SilentBidButton, SilentMineButton, RaffleBuyButton, RaffleMineButton)


def silent_view(auction_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(SilentBidButton(auction_id))
    view.add_item(SilentMineButton(auction_id))
    return view


def raffle_view(raffle_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(RaffleBuyButton(raffle_id))
    view.add_item(RaffleMineButton(raffle_id))
    return view
