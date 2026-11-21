"""Interactive gear shop: pick a listing, preview it, buy it, or take yours down."""
from __future__ import annotations

import io

import discord

from classes.equipment.access import menu_actor_ids
from classes.equipment.card import modifier_effect, piece_numbers, render_armory
from classes.equipment.definitions import (
    ARCHETYPE_NOUN,
    ARCHETYPES,
    MODIFIERS,
    PAPER_DOLL_SLOTS,
    RARITIES,
    RARITY_DOTS,
    SLOT_NOUN,
    quality_band,
)
from classes.equipment.repository import (
    buy_listing,
    fetch_market,
    gear_theme,
    withdraw_listing,
)


LINE_EMOJI = {"guardian": "🛡️", "slayer": "⚔️", "vanguard": "⚖️"}
STALL_WINDOW = 6
SORT_MODES = (
    ("newest", "Newest"),
    ("blessing", "Blessing: highest"),
    ("ward", "Ward: highest"),
    ("quality", "Quality: highest"),
    ("temper", "Temper: highest"),
    ("price_high", "Price: highest"),
    ("price_low", "Price: lowest"),
    ("name", "Name"),
)
FILTER_OPTIONS = (
    *[("line:" + line, ARCHETYPE_NOUN[line], LINE_EMOJI[line]) for line in ARCHETYPES],
    *[("slot:" + slot, SLOT_NOUN[slot], None) for slot in PAPER_DOLL_SLOTS],
    *[("rarity:" + rarity, rarity.title(), RARITY_DOTS[rarity]) for rarity in RARITIES],
    ("mine", "My listings", None),
)


def _gold(amount: int) -> str:
    return f"${int(amount):,}"


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _dot(rarity: str) -> str:
    return RARITY_DOTS.get(str(rarity).lower(), "⚪")


def _slot_name(item: dict) -> str:
    return SLOT_NOUN.get(item.get("slot"), str(item.get("slot") or "piece"))


def _line_name(item: dict) -> str:
    return ARCHETYPE_NOUN.get(item.get("archetype"), str(item.get("archetype") or "").title())


def _short_label(item: dict) -> str:
    rarity = str(item.get("rarity") or "").title()
    label = f"{rarity} {_slot_name(item)} · {_gold(item['price'])}"
    return label[:100]


def _option_description(item: dict) -> str:
    quality = int(item.get("quality") or 0)
    stars = int(item.get("refinement") or 0)
    text = f"{quality_band(quality)} {quality} · {_line_name(item)} · +{stars}"
    return text[:100]


def _enchant_line(item: dict) -> str:
    names = []
    for modifier in item.get("modifiers") or []:
        modifier_id = modifier.get("modifier_id") if isinstance(modifier, dict) else str(modifier)
        spec = MODIFIERS.get(str(modifier_id))
        label = spec["name"] if spec else str(modifier_id)
        effect = modifier_effect(str(modifier_id))
        names.append(f"{label} ({effect})" if effect else label)
    return ", ".join(names) or "None"


def _sort_key(item: dict, mode: str):
    numbers = piece_numbers(item)
    item_id = int(item.get("id") or 0)
    if mode == "blessing":
        return (-float(numbers["blessing"]), -item_id)
    if mode == "ward":
        return (-float(numbers["ward"]), -item_id)
    if mode == "quality":
        return (-int(item.get("quality") or 0), -item_id)
    if mode == "temper":
        return (-int(item.get("refinement") or 0), -item_id)
    if mode == "price_high":
        return (-int(item.get("price") or 0), -item_id)
    if mode == "price_low":
        return (int(item.get("price") or 0), -item_id)
    if mode == "name":
        return (str(item.get("name") or "").lower(), -item_id)
    published = item.get("published")
    stamp = published.timestamp() if hasattr(published, "timestamp") else 0
    return (-stamp, -item_id)


def filtered_listings(listings: list[dict], filters: set[str], author_id: int, sort_mode: str) -> list[dict]:
    items = list(listings)
    lines = {value.split(":", 1)[1] for value in filters if value.startswith("line:")}
    slots = {value.split(":", 1)[1] for value in filters if value.startswith("slot:")}
    rarities = {value.split(":", 1)[1] for value in filters if value.startswith("rarity:")}
    if lines:
        items = [item for item in items if str(item.get("archetype")) in lines]
    if slots:
        items = [item for item in items if str(item.get("slot")) in slots]
    if rarities:
        items = [item for item in items if str(item.get("rarity")) in rarities]
    if "mine" in filters:
        items = [item for item in items if int(item.get("seller_id") or 0) == int(author_id)]
    items.sort(key=lambda item: _sort_key(item, sort_mode))
    return items


def filter_labels(filters: set[str]) -> str:
    if not filters:
        return "All listings"
    labels = []
    for value, label, _emoji in FILTER_OPTIONS:
        if value in filters:
            labels.append(label)
    return " · ".join(labels) or "All listings"


def sort_label(mode: str) -> str:
    return next((label for value, label in SORT_MODES if value == mode), "Newest")


class ShopBuyConfirm(discord.ui.View):
    def __init__(self, shop: "GearShopView", listing: dict):
        super().__init__(timeout=30)
        self.shop = shop
        self.listing_id = int(listing["id"])
        self.price = int(listing["price"])
        self.name = listing["name"]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) not in self.shop.allowed_ids:
            await interaction.response.send_message("This stall is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm buy", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.shop.bot.pool.acquire() as conn:
            status, result = await buy_listing(
                conn, self.shop.author_id, self.listing_id, expected_price=self.price
            )
        messages = {
            "missing": "That listing is gone.",
            "self": "You cannot buy your own listing.",
            "bound": "That listing was withdrawn because the piece can no longer be traded.",
            "poor": "You cannot afford that listing.",
        }
        try:
            if status == "changed":
                await interaction.response.edit_message(
                    content=(
                        f"That listing is now **{_gold(result['price'])}**. "
                        "The stall was refreshed — buy again if you still want it."
                    ),
                    view=None,
                )
            elif status != "bought":
                await interaction.response.edit_message(
                    content=messages.get(status, "The purchase did not complete."),
                    view=None,
                )
            else:
                await interaction.response.edit_message(
                    content=f"You buy **{result['name']}** for **{_gold(result['price'])}**.",
                    view=None,
                )
                self.shop.selected_id = None
        finally:
            await self.shop.reload()
            try:
                await self.shop.redraw(interaction, followup=True)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="You leave it on the stall.", view=None)


class ShopUnlistConfirm(discord.ui.View):
    def __init__(self, shop: "GearShopView", listing: dict):
        super().__init__(timeout=30)
        self.shop = shop
        self.listing_id = int(listing["id"])
        self.name = listing["name"]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) not in self.shop.allowed_ids:
            await interaction.response.send_message("This stall is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Take it down", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.shop.bot.pool.acquire() as conn:
            status = await withdraw_listing(conn, self.shop.author_id, self.listing_id)
        try:
            if status == "missing":
                await interaction.response.edit_message(content="You do not have that listing.", view=None)
            else:
                await interaction.response.edit_message(
                    content=f"You take **{self.name}** back from the shop.",
                    view=None,
                )
            self.shop.selected_id = None
        finally:
            await self.shop.reload()
            try:
                await self.shop.redraw(interaction, followup=True)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Keep listed", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="It stays on the stall.", view=None)


class GearShopSelect(discord.ui.Select):
    def __init__(self, shop: "GearShopView"):
        options = [
            discord.SelectOption(
                label=_short_label(item),
                value=str(item["id"]),
                description=_option_description(item),
                emoji=LINE_EMOJI.get(str(item.get("archetype")), "⚙️"),
                default=int(item["id"]) == shop.selected_id,
            )
            for item in shop.visible()[:25]
        ]
        super().__init__(placeholder="Choose a listing", options=options, row=0)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction):
        self.shop.selected_id = int(self.values[0])
        self.shop.rebuild()
        await self.shop.redraw(interaction)


class GearShopFilterSelect(discord.ui.Select):
    def __init__(self, shop: "GearShopView"):
        options = []
        for value, label, emoji in FILTER_OPTIONS:
            kwargs = {"label": label, "value": value, "default": value in shop.filters}
            if emoji:
                kwargs["emoji"] = emoji
            options.append(discord.SelectOption(**kwargs))
        super().__init__(
            placeholder="Filter by line, rarity, or slot",
            min_values=0,
            max_values=len(options),
            options=options,
            row=1,
        )
        self.shop = shop

    async def callback(self, interaction: discord.Interaction):
        self.shop.filters = set(self.values)
        shown = self.shop.visible()
        ids = {int(item["id"]) for item in shown}
        if self.shop.selected_id not in ids:
            self.shop.selected_id = int(shown[0]["id"]) if shown else None
            self.shop.show_card = False
        self.shop.rebuild()
        await self.shop.redraw(interaction)


class GearShopSortSelect(discord.ui.Select):
    def __init__(self, shop: "GearShopView"):
        options = [
            discord.SelectOption(label=label, value=value, default=shop.sort_mode == value)
            for value, label in SORT_MODES
        ]
        super().__init__(placeholder="Sort listings", options=options, row=2)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction):
        self.shop.sort_mode = self.values[0]
        shown = self.shop.visible()
        if shown and self.shop.selected_id not in {int(item["id"]) for item in shown}:
            self.shop.selected_id = int(shown[0]["id"])
        self.shop.rebuild()
        await self.shop.redraw(interaction)


class GearShopView(discord.ui.View):
    def __init__(self, ctx, listings: list[dict], gold: int, theme: str):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.bot = ctx.bot
        self.author_id = ctx.author.id
        self.allowed_ids = menu_actor_ids(ctx)
        self.listings = listings
        self.gold = int(gold or 0)
        self.theme = theme
        self.filters: set[str] = set()
        self.sort_mode = "newest"
        self.selected_id = int(self.visible()[0]["id"]) if self.visible() else None
        self.show_card = False
        self.message = None
        self.rebuild()

    def visible(self) -> list[dict]:
        return filtered_listings(self.listings, self.filters, self.author_id, self.sort_mode)

    def selected(self) -> dict | None:
        return next((item for item in self.visible() if int(item["id"]) == self.selected_id), None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) not in self.allowed_ids:
            await interaction.response.send_message("This stall is not yours.", ephemeral=True)
            return False
        return True

    async def reload(self) -> None:
        async with self.bot.pool.acquire() as conn:
            self.listings = await fetch_market(conn)
            self.gold = int(
                await conn.fetchval('SELECT money FROM profile WHERE "user" = $1', self.author_id) or 0
            )
            self.theme = await gear_theme(conn, self.author_id)
        shown = self.visible()
        ids = {int(item["id"]) for item in shown}
        if self.selected_id not in ids:
            self.selected_id = int(shown[0]["id"]) if shown else None
            self.show_card = False
        self.rebuild()

    def rebuild(self) -> None:
        self.clear_items()
        listing = self.selected()
        shown = self.visible()
        yours = bool(listing and int(listing["seller_id"]) == self.author_id)
        can_buy = bool(listing and not yours and self.gold >= int(listing["price"]))
        preview_label = "Hide card" if self.show_card else "Preview"
        if shown:
            self.add_item(GearShopSelect(self))
        self.add_item(GearShopFilterSelect(self))
        self.add_item(GearShopSortSelect(self))
        for label, style, callback, disabled, row in [
            (preview_label, discord.ButtonStyle.secondary, self.preview, listing is None, 3),
            ("Buy", discord.ButtonStyle.success, self.buy, not can_buy, 3),
            ("Unlist", discord.ButtonStyle.danger, self.unlist, not yours, 3),
            ("Refresh", discord.ButtonStyle.secondary, self.refresh, False, 4),
            ("Close", discord.ButtonStyle.secondary, self.close, False, 4),
        ]:
            button = discord.ui.Button(label=label, style=style, disabled=disabled, row=row)
            button.callback = callback
            self.add_item(button)

    def stall_lines(self) -> str:
        shown = self.visible()
        if not self.listings:
            return "The stall is empty."
        if not shown:
            return "No listings match these filters."
        selected_index = next(
            (index for index, item in enumerate(shown) if int(item["id"]) == self.selected_id),
            0,
        )
        start = max(0, selected_index - 2)
        end = min(len(shown), start + STALL_WINDOW)
        start = max(0, end - STALL_WINDOW)
        lines = []
        for item in shown[start:end]:
            marker = "▶" if int(item["id"]) == self.selected_id else "•"
            yours = " · yours" if int(item["seller_id"]) == self.author_id else ""
            lines.append(
                f"{marker} {_dot(item['rarity'])} **{_slot_name(item)}** · "
                f"{str(item['rarity']).title()} {_line_name(item)} · **{_gold(item['price'])}**{yours}"
            )
        if start > 0 or end < len(shown):
            lines.append(f"Showing {start + 1}–{end} of {len(shown)}")
        return "\n".join(lines)

    def selected_text(self) -> str:
        item = self.selected()
        if item is None:
            if self.filters:
                return "No listings match these filters."
            return "Choose a listing from the menu."
        numbers = piece_numbers(item)
        yours = int(item["seller_id"]) == self.author_id
        price = int(item["price"])
        quality = int(item["quality"])
        stars = int(item.get("refinement") or 0)
        if yours:
            purse = "This is your listing."
        elif self.gold >= price:
            purse = f"You can buy this. Gold left after: {_gold(self.gold - price)}"
        else:
            purse = f"Short {_gold(price - self.gold)}."
        return (
            f"**{item['name']}**\n"
            f"{str(item['rarity']).title()} · {_line_name(item)} · {_slot_name(item)}\n"
            f"Id `{item['id']}`\n"
            f"{quality_band(quality)} {quality} · tempered +{stars}\n"
            f"Blessing +{_trim(numbers['blessing'] * 100)}% · Ward +{_trim(numbers['ward'])}\n"
            f"Enchantment: {_enchant_line(item)[:180]}\n"
            f"Seller: <@{int(item['seller_id'])}>\n"
            f"Price: **{_gold(price)}**\n"
            f"Your gold: {_gold(self.gold)}\n"
            f"{purse}"
        )

    def embed(self) -> discord.Embed:
        listing = self.selected()
        embed = discord.Embed(
            title="Gear shop",
            description=(
                f"**{len(self.visible())}** shown of **{len(self.listings)}** · Your gold: **{_gold(self.gold)}**\n"
                f"Filter: {filter_labels(self.filters)} · Sort: {sort_label(self.sort_mode)}"
            ),
            color=0x846236,
        )
        embed.add_field(name="Stall", value=self.stall_lines()[:1024], inline=False)
        embed.add_field(name="Selected", value=self.selected_text()[:1024], inline=False)
        if self.show_card and listing and listing.get("slot") in PAPER_DOLL_SLOTS:
            embed.set_image(url="attachment://armory.png")
        embed.set_footer(text="$gear sell lists a piece · bound armor cannot be sold")
        return embed

    def card_file(self) -> discord.File | None:
        listing = self.selected()
        if not self.show_card or listing is None or listing.get("slot") not in PAPER_DOLL_SLOTS:
            return None
        png = render_armory(
            {listing["slot"]: listing},
            title=listing["name"],
            subtitle=f"{_gold(listing['price'])} · {quality_band(int(listing['quality']))} {int(listing['quality'])}",
            theme=self.theme,
        )
        return discord.File(io.BytesIO(png), filename="armory.png")

    async def redraw(self, interaction: discord.Interaction, *, followup: bool = False) -> None:
        file = self.card_file()
        kwargs = {"embed": self.embed(), "view": self, "attachments": [file] if file else []}
        if followup:
            if self.message:
                await self.message.edit(**kwargs)
            return
        if interaction.response.is_done():
            if interaction.message:
                await interaction.message.edit(**kwargs)
            return
        await interaction.response.edit_message(**kwargs)

    async def preview(self, interaction: discord.Interaction):
        if self.selected() is None:
            return await interaction.response.send_message("Choose a listing first.", ephemeral=True)
        self.show_card = not self.show_card
        self.rebuild()
        await self.redraw(interaction)

    async def buy(self, interaction: discord.Interaction):
        listing = self.selected()
        if listing is None:
            return await interaction.response.send_message("Choose a listing first.", ephemeral=True)
        asked = int(listing["price"])
        await self.reload()
        live = self.selected()
        self.rebuild()
        await self.redraw(interaction)
        if live is None:
            return await interaction.followup.send("That listing is gone.", ephemeral=True)
        if int(live["seller_id"]) == self.author_id:
            return await interaction.followup.send("That listing is yours. Unlist it instead.", ephemeral=True)
        price = int(live["price"])
        if self.gold < price:
            return await interaction.followup.send("You cannot afford that listing.", ephemeral=True)
        if price != asked:
            prompt = (
                f"That listing is now **{_gold(price)}** (was **{_gold(asked)}**). "
                f"Buy **{live['name']}** for **{_gold(price)}**?"
            )
        else:
            prompt = f"Buy **{live['name']}** for **{_gold(price)}**?"
        await interaction.followup.send(
            prompt,
            view=ShopBuyConfirm(self, live),
            ephemeral=True,
        )

    async def unlist(self, interaction: discord.Interaction):
        listing = self.selected()
        if listing is None or int(listing["seller_id"]) != self.author_id:
            return await interaction.response.send_message("That listing is not yours.", ephemeral=True)
        await interaction.response.send_message(
            f"Take **{listing['name']}** off the stall?",
            view=ShopUnlistConfirm(self, listing),
            ephemeral=True,
        )

    async def refresh(self, interaction: discord.Interaction):
        await self.reload()
        await self.redraw(interaction)

    async def close(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=None)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
