"""Thorne's Anvil. Garron Thorne refines, tempers, and inscribes the armor a player is wearing."""
from __future__ import annotations

import io
import logging
import random

import discord

from classes.equipment.attunement import ATTUNEMENT_CAP, refinement_cap
from classes.equipment.definitions import (
    INSCRIBE_RARITIES,
    MATERIAL_LINES,
    MATERIALS,
    MAX_REFINEMENT,
    MODIFIER_LINES,
    MODIFIERS,
    PAPER_DOLL_SLOTS,
    SLOT_NOUN,
    material_dot,
    quality_band,
)
from classes.equipment.economy import inscribe_step, refine_step, temper_step
from classes.equipment.forge_art import anvil_gif
from classes.equipment.forge_result import banner_text, plain_banner, strike_banner
from classes.equipment.forge_result import stars as _stars
from classes.equipment.repository import (
    fetch_loadout,
    fetch_materials,
    inscribe_piece,
    refine_piece,
    temper_piece,
)

GIF_NAME = "thorne_anvil.gif"
FORGE_COLOR = 0xC8642A
BANNER_COLOR = {"success": 0x3DDC97, "pity": 0xE8B84A, "miss": 0x8C8378, "blocked": 0xC45C4A}
BIND_WARNING = (
    "**Are you sure?** Garron's work binds **{name}** to you for good. "
    "After this you will no longer be able to trade, give, sell, or list it on the gear shop."
)

GREETINGS = (
    "\"Bench. Set it down.\"",
    "\"Steel remembers every blow. So do I.\"",
    "\"Armor shows who wears it. Let's see yours.\"",
    "\"Titles don't impress the anvil. Neither does coin.\"",
    "\"You're young for this. Stand back from the sparks.\"",
)
WIN = (
    "\"There. Tighter grain, truer edge.\"",
    "\"It took. Good metal.\"",
    "\"Better. Wear it well.\"",
)
MISS = (
    "\"The steel fought me. No worse. No better.\"",
    "\"Cooled too fast. Again.\"",
    "\"Not today. The fire never sleeps. Come back.\"",
)
PITY = "\"Enough. This time it holds.\""


def anvil_file() -> discord.File:
    return discord.File(io.BytesIO(anvil_gif()), filename=GIF_NAME)


def _price(step: dict) -> str:
    parts = [f"{material_dot(material_id)} {MATERIALS[material_id]} x{amount}" for material_id, amount in step["cost"].items()]
    if step.get("gold"):
        parts.append(f"${int(step['gold']):,}")
    return ", ".join(parts)


def _odds(step: dict, fails: int) -> str:
    if not step["pity"]:
        return f"{int(step['chance'] * 100)}%"
    if fails >= step["pity"]:
        return "guaranteed (pity)"
    return f"{int(step['chance'] * 100)}% · pity {fails}/{step['pity']}"


def _offer(step: dict, fails: int) -> str:
    """Odds, then goods, then gold: three short lines that wrap well on a phone."""
    goods = " · ".join(
        f"{material_dot(material_id)} {MATERIALS[material_id]} {amount}" for material_id, amount in step["cost"].items()
    )
    lines = [f"**{_odds(step, fails)}**", goods]
    if step.get("gold"):
        lines.append(f"💰 ${int(step['gold']):,}")
    return "\n".join(line for line in lines if line)


class BindConfirm(discord.ui.View):
    def __init__(self, forge: "ForgeView", action: str):
        super().__init__(timeout=60)
        self.forge = forge
        self.action = action

    @discord.ui.button(label="Yes, bind it", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await self.forge.perform(self.action)
        except Exception:
            logging.getLogger(__name__).exception("Forge attempt failed")
            await interaction.response.edit_message(content="Garron's hammer slips. Try that again.", view=None)
            return
        text = banner_text(self.forge.banner) if self.forge.banner else "Garron sets the hammer down."
        await interaction.response.edit_message(content=text[:2000], view=None)
        if self.forge.message is not None:
            await self.forge.message.edit(embed=self.forge.embed(), view=self.forge)

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Garron sets the piece back on the rack.", view=None)


class ForgeView(discord.ui.View):
    def __init__(self, bot, author, loadout: dict, balances: dict, money: int, slot: str | None = None, prefix: str = "$"):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.prefix = prefix
        self.loadout = loadout
        self.balances = balances
        self.money = int(money or 0)
        worn = [name for name in PAPER_DOLL_SLOTS if name in loadout]
        self.slot = slot if slot in worn else worn[0]
        self.enchant: str | None = None
        self.line = random.choice(GREETINGS)
        self.banner: dict | None = None
        self.message: discord.Message | None = None
        self._build_selects()

    @property
    def piece(self) -> dict:
        return self.loadout[self.slot]

    def _current_enchants(self) -> list[str]:
        return [row["modifier_id"] for row in self.piece.get("modifiers") or []]

    def _build_selects(self) -> None:
        self.choose.options = [
            discord.SelectOption(
                label=f"{SLOT_NOUN[slot]}: {self.loadout[slot]['name']}"[:100],
                description=(
                    f"Quality {self.loadout[slot]['quality']} · tempered +{int(self.loadout[slot]['refinement'] or 0)}"
                )[:100],
                value=slot,
                default=slot == self.slot,
            )
            for slot in PAPER_DOLL_SLOTS
            if slot in self.loadout
        ]
        current = self._current_enchants()
        options = [
            discord.SelectOption(
                label=MODIFIERS[modifier_id]["name"],
                value=modifier_id,
                default=modifier_id == self.enchant,
                description="Already on this piece" if modifier_id in current else None,
            )
            for modifier_id in MODIFIER_LINES[self.piece["archetype"]]
        ]
        self.pick_enchant.options = options
        self.pick_enchant.disabled = not self._can_inscribe()

    def _can_inscribe(self) -> bool:
        return self.piece["rarity"] in INSCRIBE_RARITIES and not self.piece.get("fully_rolled")

    def _piece_block(self) -> str:
        """The worn piece, one stat per line. The stat a strike just changed shows its before and after."""
        piece = self.piece
        quality = int(piece["quality"])
        stars = int(piece["refinement"] or 0)
        enchants = ", ".join(MODIFIERS[m]["name"] for m in self._current_enchants() if m in MODIFIERS) or "None"
        lock = "🔒 Bound" if piece["bound"] else "🔓 Tradable"
        lines = {
            "quality": f"Quality {quality} · {quality_band(quality)}",
            "temper": f"Temper +{stars} {_stars(stars)}",
            "enchant": f"Enchant {enchants}",
        }
        banner = self.banner or {}
        if banner.get("stat") in lines:
            lines[banner["stat"]] = f"▸ {banner['delta']}"
        return "\n".join(
            (
                f"**{piece['name']}**",
                f"{piece['rarity'].title()} {piece['archetype'].title()} {SLOT_NOUN[self.slot].lower()} · {lock}",
                lines["quality"],
                lines["temper"],
                lines["enchant"],
                f"Attuned {int(piece.get('attunement') or 0):,}/{ATTUNEMENT_CAP:,}",
            )
        )

    def embed(self) -> discord.Embed:
        piece = self.piece
        archetype = piece["archetype"]
        quality = int(piece["quality"])
        stars = int(piece["refinement"] or 0)
        banner = self.banner
        if banner:
            title = f"{banner['mark']} {banner['title']}"
            color = BANNER_COLOR[banner["tone"]]
            note = f"\n\n{banner['note']}" if banner.get("note") else ""
        else:
            title, color, note = "⚒️ Thorne's Anvil", FORGE_COLOR, ""
        description = f"{self._piece_block()}{note}\n\n> *{self.line.strip(chr(34))}*\n> — Garron Thorne"
        embed = discord.Embed(title=title[:256], description=description[:4096], color=color)
        embed.set_image(url=f"attachment://{GIF_NAME}")

        step = refine_step(archetype, quality)
        if step is None:
            embed.add_field(name="⚒️ Refine", value="Quality 100. Nothing left to refine.", inline=False)
        else:
            embed.add_field(
                name=f"⚒️ Refine → {quality + 1}",
                value=_offer(step, int(piece.get("refine_fails") or 0)),
                inline=False,
            )

        cap = refinement_cap(int(piece.get("attunement") or 0))
        if stars >= MAX_REFINEMENT:
            embed.add_field(name="🔥 Temper", value="+7. Every star is set.", inline=False)
        elif stars >= cap:
            embed.add_field(
                name="🔥 Temper",
                value=f"Capped at +{cap}.\nReach {ATTUNEMENT_CAP:,} attunement for +6 and +7.",
                inline=False,
            )
        else:
            step = temper_step(archetype, stars + 1)
            embed.add_field(
                name=f"🔥 Temper → +{stars + 1}",
                value=_offer(step, int(piece.get("temper_fails") or 0)),
                inline=False,
            )

        if piece.get("fully_rolled"):
            embed.add_field(name="✒️ Inscribe", value="A fully rolled discovery keeps its two enchantments.", inline=False)
        elif piece["rarity"] not in INSCRIBE_RARITIES:
            embed.add_field(name="✒️ Inscribe", value="Magic and Legendary pieces only.", inline=False)
        else:
            step = inscribe_step(archetype)
            chosen = MODIFIERS[self.enchant]["name"] if self.enchant else "pick one below"
            embed.add_field(
                name=f"✒️ Inscribe → {chosen}",
                value=_offer(step, int(piece.get("inscribe_fails") or 0)) + "\nReplaces the current enchant.",
                inline=False,
            )

        goods = " · ".join(
            f"{material_dot(material_id)} {MATERIALS[material_id]} {self.balances.get(material_id, 0):,}"
            for material_id in MATERIAL_LINES[archetype]
        )
        embed.add_field(name="🎒 You have", value=f"{goods}\n💰 ${self.money:,}", inline=False)
        embed.set_footer(text="The Fire Never Sleeps · A failed try still costs its price.")
        return embed

    async def _reload(self) -> None:
        async with self.bot.pool.acquire() as conn:
            self.loadout = await fetch_loadout(conn, self.author.id)
            self.balances = await fetch_materials(conn, self.author.id)
            self.money = int(await conn.fetchval('SELECT money FROM profile WHERE "user" = $1', self.author.id) or 0)
        if self.slot not in self.loadout:
            remaining = [name for name in PAPER_DOLL_SLOTS if name in self.loadout]
            self.slot = remaining[0] if remaining else None
        if self.slot:
            self._build_selects()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Garron is working on someone else's armor.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def _redraw(self, interaction: discord.Interaction) -> None:
        if self.slot is None:
            self.stop()
            await interaction.response.edit_message(content="You are no longer wearing any armor.", embed=None, view=None, attachments=[])
            return
        await interaction.response.edit_message(embed=self.embed(), view=self)

    def _short_line(self, result: dict) -> str:
        if result.get("short") == "gold":
            return f"\"Coal isn't free. That costs ${int(result['gold']):,}.\""
        return f"\"I'll need {_price(result)} for that.\""

    async def perform(self, action: str) -> None:
        piece = self.piece
        before = {
            "name": piece["name"],
            "quality": int(piece["quality"]),
            "stars": int(piece["refinement"] or 0),
            "enchants": [MODIFIERS[m]["name"] for m in self._current_enchants() if m in MODIFIERS],
        }
        enchant = MODIFIERS[self.enchant]["name"] if self.enchant in MODIFIERS else None
        piece_id = int(piece["id"])
        async with self.bot.pool.acquire() as conn:
            if action == "temper":
                status, result = await temper_piece(conn, self.author.id, piece_id)
            elif action == "refine":
                status, result = await refine_piece(conn, self.author.id, piece_id)
            else:
                status, result = await inscribe_piece(conn, self.author.id, piece_id, self.enchant)
        if status in ("tempered", "refined", "inscribed", "poor"):
            if status == "poor":
                quote = self._short_line(result)
            elif result.get("pity_used"):
                quote = PITY
            elif result["success"]:
                quote = random.choice(WIN)
            else:
                quote = random.choice(MISS)
            self.banner = strike_banner(action, status, result, before, quote=quote, enchant=enchant)
            if status == "tempered" and result["success"] and int(result["refinement"]) >= MAX_REFINEMENT:
                quote = "\"Seven stars. Few hands ever earn that. Carry my mark.\""
                self.banner["quote"] = quote
                extra = await self._seven_star_reward()
                if extra:
                    self.banner["note"] = "\n".join(part for part in (self.banner["note"], extra) if part)
        else:
            self.banner = plain_banner("blocked", *self._refusal(action, status))
        self.line = self.banner["quote"]
        await self._reload()

    def _refusal(self, action: str, status: str) -> tuple[str, str, str]:
        """Title, note, and Garron's line when the hammer never falls."""
        name = self.piece["name"]
        if status == "missing":
            return "NOT ON THE ANVIL", f"{name} is no longer worn.", "\"You've taken that off. Wear it and bring it back.\""
        if status == "maxed" and action == "refine":
            return "QUALITY 100", f"{name} cannot be refined further.", "\"It's as fine as steel gets. Quality 100.\""
        if status == "maxed" and int(self.piece["refinement"] or 0) >= MAX_REFINEMENT:
            return "TEMPERED +7", f"{name} holds every star.", "\"Seven stars. That's all the steel will hold.\""
        if status == "maxed":
            return "TEMPER CAPPED", f"{name} needs attunement before another star.", "\"It won't take another star until it knows you better. Attune it first.\""
        if status == "same":
            return "ALREADY INSCRIBED", f"{name} already carries that enchantment.", "\"It already carries that one.\""
        return "CANNOT INSCRIBE", f"Garron will not put that on {name}.", "\"I can't put that on this piece.\""

    async def _seven_star_reward(self) -> str:
        from cogs.profile.theme_unlocks import sync_theme_unlocks

        try:
            state = await sync_theme_unlocks(self.bot.pool, self.author.id)
        except Exception:
            logging.getLogger(__name__).exception("Thorne's Anvil theme unlock failed")
            return ""
        if state is None or "thornesanvil" not in state.newly_unlocked:
            return ""
        return (
            "🔥 **Profile theme unlocked: Thorne's Anvil**\n"
            f"`{self.prefix}prpg preview thornesanvil`\n"
            f"`{self.prefix}prpg theme thornesanvil`"
        )

    async def _act(self, interaction: discord.Interaction, action: str) -> None:
        if action == "inscribe" and not self.enchant:
            self.banner = None
            self.line = "\"Pick the enchantment first, from the list under the buttons.\""
            return await self._redraw(interaction)
        if not self.piece["bound"]:
            await interaction.response.send_message(
                BIND_WARNING.format(name=self.piece["name"]), view=BindConfirm(self, action), ephemeral=True
            )
            return
        await self.perform(action)
        await self._redraw(interaction)

    @discord.ui.select(placeholder="Choose a worn piece", row=0)
    async def choose(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.slot = select.values[0]
        self.enchant = None
        self.banner = None
        self.line = random.choice(GREETINGS)
        self._build_selects()
        await self._redraw(interaction)

    @discord.ui.button(label="Refine", style=discord.ButtonStyle.primary, row=1)
    async def refine(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._act(interaction, "refine")

    @discord.ui.button(label="Temper", style=discord.ButtonStyle.primary, row=1)
    async def temper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._act(interaction, "temper")

    @discord.ui.button(label="Inscribe", style=discord.ButtonStyle.success, row=1)
    async def inscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._act(interaction, "inscribe")

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, row=1)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.select(placeholder="Enchantment to inscribe", row=2)
    async def pick_enchant(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.enchant = select.values[0]
        self._build_selects()
        await self._redraw(interaction)
