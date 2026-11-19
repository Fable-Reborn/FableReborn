"""Development armory. Commands and combat stats stay dark outside FableDev."""
from __future__ import annotations

import io
import logging

import discord
from discord.ext import commands, tasks

from classes.equipment.definitions import (
    ARCHETYPES,
    MATERIAL_LINES,
    MATERIALS,
    OPEN_SLOTS,
    PAPER_DOLL_SLOTS,
    RARITIES,
    material_dot,
    quality_band,
    resolve_material,
    resolve_slot,
)
from classes.equipment.economy import craft_cost
from classes.equipment.repository import (
    add_materials,
    buy_listing,
    craft_chest,
    database_name,
    ensure_schema,
    equip_item,
    feature_enabled,
    set_feature_enabled,
    fetch_equipped_weapons,
    fetch_item,
    fetch_loadout,
    fetch_market,
    fetch_materials,
    gear_theme,
    grant_chest,
    list_piece,
    salvage_piece,
    set_gear_theme,
    spend_materials,
    unequip_item,
    withdraw_listing,
)
from classes.equipment.card import preview_loadout, render_armory
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

log = logging.getLogger(__name__)


def _file(png: bytes, name: str = "armory.png") -> discord.File:
    return discord.File(io.BytesIO(png), filename=name)


class Equipment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.available = False

    async def cog_load(self):
        self.bot.equipment_combat_enabled = False
        self.schema_ready = False
        try:
            async with self.bot.pool.acquire() as conn:
                name = await database_name(conn)
                await ensure_schema(conn)
                self.schema_ready = True
                self.available = await feature_enabled(conn)
            log.info("Equipment armory %s on database %s", "open" if self.available else "closed", name)
        except Exception:
            log.exception("Equipment armory failed to open")
            self.available = False
        self.bot.equipment_combat_enabled = self.available
        if self.schema_ready:
            self.refresh_switch.start()

    async def cog_unload(self):
        if self.refresh_switch.is_running():
            self.refresh_switch.cancel()

    @tasks.loop(seconds=60)
    async def refresh_switch(self):
        """Every cluster follows `$gear switch` within a minute."""
        try:
            async with self.bot.pool.acquire() as conn:
                enabled = await feature_enabled(conn)
        except Exception:
            log.exception("Equipment switch refresh failed")
            return
        if enabled != self.available:
            log.info("Equipment armory %s by switch", "opened" if enabled else "closed")
        self.available = enabled
        self.bot.equipment_combat_enabled = enabled

    async def _has_profile(self, conn, user_id: int) -> bool:
        return bool(await conn.fetchval('SELECT 1 FROM profile WHERE "user" = $1', int(user_id)))

    async def _closed(self, ctx) -> bool:
        if self.available:
            return False
        await ctx.send("The armory is closed on this realm.")
        return True

    def _embed(self, ctx, title: str, description: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=0x7EB6D6,
        )
        embed.set_image(url="attachment://armory.png")
        return embed

    @has_char()
    @commands.group(name="gear", invoke_without_command=True)
    @locale_doc
    async def gear(self, ctx, member: discord.Member = None):
        _(
            """Armor worn over your clothes. It does not use a weapon hand.

        `{prefix}gear` opens the armory card with your weapons and armor. The buttons open the totals, each armor slot, and each hand.
        `{prefix}gear @user` opens another character's armory card.
        `{prefix}gear chronicle` shows that card without the weapons or the buttons.
        `{prefix}gear theme <name>` picks the cover for your armory card. The menu on `{prefix}gear` does the same. Every cover is free.
        `{prefix}armory`, then the Gear button, lists the armor you own.
        `{prefix}gear info <id>` opens one piece on the chronicle card.
        `{prefix}help gear enchantments` lists every enchantment and which line can roll it.

        Smithing goods are separate for Guardian, Slayer, and Vanguard.
        Each line has a rough material, a worked material, and a relic.
        `{prefix}gear materials` shows what you hold.

        `{prefix}gear available` lists only the patterns you have discovered.
        Everyone starts with the common helm, cuirass, greaves, and sabatons of each line. Finding a stronger
        piece teaches that line and rarity for all four slots. `{prefix}gear craft <rarity> <line> [slot]` forges
        a known pattern. Leave the slot out to forge a cuirass. Quality is rolled. The new piece can be traded.

        `{prefix}forge` takes you to Garron Thorne, who works the pieces you are
        wearing. Refining raises quality. Tempering adds stars, up to +5. Inscribing
        sets one enchantment. Each costs materials and gold, can fail, and has pity.
        The first time binds the piece. `{prefix}forge trade` swaps goods between lines at 3 for 1.
        Party dragon kills pay smithing goods for the line you wear most.
        Higher dragon levels pay worked goods and sometimes a relic. `{prefix}gear salvage <id>` breaks one down for fewer
        materials than it cost.

        Bound pieces and fully rolled discoveries cannot be given, traded, or
        sold. `{prefix}gear give`, `{prefix}gear pay`, `{prefix}trade add gear`,
        `{prefix}trade add armory`, and `{prefix}gear shop` move the rest.

        A Slayer piece can roll Sunder. Sunder ignores enough armor that the
        Slayer wins the exchange against a reflect tank of similar strength.
        Breakthrough sometimes ignores more for that one hit. A Guardian piece
        rolls neither.         A much heavier wall still wins its exchange. Reflection's
        percentage is unchanged.

        Worn armor gains attunement from the same deeds as a soulbound
        weapon, for the same points: a finished adventure is 10, a battle-tower
        floor is 15, a raid victory is 20, and an ice-dragon kill is 25. A
        strong monster victory is 15. The piece is fully attuned at 2500.
        The first point binds it. A monster below half your health does not count.
        Battles against other players do not attune armor. Attunement 2500 lets tempering
        reach +7.

        Use `{prefix}help forge` to read how the forge works.
            """
        )
        if await self._closed(ctx):
            return
        from cogs.equipment.sheet import GearSheetView

        owner = member or ctx.author
        async with self.bot.pool.acquire() as conn:
            if owner.id != ctx.author.id and not await self._has_profile(conn, owner.id):
                return await ctx.send(f"{owner.display_name} does not have a character.")
            loadout = await fetch_loadout(conn, owner.id)
            weapons = await fetch_equipped_weapons(conn, owner.id)
            theme = await gear_theme(conn, owner.id)
        view = GearSheetView(ctx, loadout, weapons, owner=owner, theme=theme)
        await ctx.send(embed=view.embed(), file=view.file(), view=view)

    @gear.command(name="chronicle", brief="Show the original armory card")
    @locale_doc
    async def gear_chronicle(self, ctx):
        _(
            """Show the armory card without the weapon row or the buttons.

            `{prefix}gear` adds your weapons and the buttons. This command is the card alone.
            """
        )
        if await self._closed(ctx):
            return
        from classes.equipment.attunement import ATTUNEMENT_CAP

        async with self.bot.pool.acquire() as conn:
            loadout = await fetch_loadout(conn, ctx.author.id)
            theme = await gear_theme(conn, ctx.author.id)
        worn = [loadout[slot] for slot in PAPER_DOLL_SLOTS if slot in loadout]
        if not worn:
            description = (
                "No armor is worn. Helm, cuirass, greaves, and sabatons can all be equipped. "
                "Wearing a piece does not bind it."
            )
        else:
            description = "\n".join(
                f"**{piece['name']}** · {piece['rarity'].title()} {piece['archetype'].title()} · "
                f"{quality_band(piece['quality'])} {piece['quality']} · "
                f"tempered +{int(piece['refinement'])} · "
                f"attunement {int(piece.get('attunement') or 0)}/{ATTUNEMENT_CAP}"
                for piece in worn
            )
        png = render_armory(
            loadout,
            title=f"{ctx.author.display_name}'s Armory",
            subtitle="Helm, cuirass, greaves, and sabatons can be worn.",
            theme=theme,
        )
        await ctx.send(
            embed=self._embed(ctx, "Armory", description),
            file=_file(png),
        )

    @has_char()
    @commands.group(name="forge", aliases=["anvil"], invoke_without_command=True, brief="Garron Thorne works your worn armor")
    @locale_doc
    async def forge(self, ctx):
        _(
            """Visit Garron Thorne at Thorne's Anvil.

            Pick one of the armor pieces you are wearing. Only worn pieces appear.
            **Refine** raises quality by 1. **Temper** adds a star, up to +5, or +7 once the piece is fully attuned.
            **Inscribe** sets one enchantment from the piece's own line on a Magic or Legendary piece. A success replaces its current enchantment. Two enchantments only come from a fully rolled Legendary crate drop.
            Every attempt costs that line's materials and gold, even when it fails. Failures build pity, and after enough failures in a row the next attempt succeeds.
            The first refine, temper, or inscription binds the piece. Garron asks you to confirm before he does.
            `{prefix}forge trade <amount> <material> <line>` trades goods between lines.
            """
        )
        await self._open_forge(ctx)

    async def _open_forge(self, ctx, equipment_id: int | None = None):
        if await self._closed(ctx):
            return
        from cogs.equipment.forge import ForgeView, anvil_file

        async with self.bot.pool.acquire() as conn:
            loadout = await fetch_loadout(conn, ctx.author.id)
            balances = await fetch_materials(conn, ctx.author.id)
            money = await conn.fetchval('SELECT money FROM profile WHERE "user" = $1', ctx.author.id)
        if not any(slot in loadout for slot in PAPER_DOLL_SLOTS):
            return await ctx.send(
                f"Garron looks you over. \"You're not wearing any armor.\" Equip a piece with `{ctx.clean_prefix}gear equip <id>` first."
            )
        slot = None
        if equipment_id is not None:
            slot = next((name for name, item in loadout.items() if int(item["id"]) == int(equipment_id)), None)
            if slot is None:
                return await ctx.send(
                    f"Garron only works armor you are wearing. Equip it with `{ctx.clean_prefix}gear equip {equipment_id}` first."
                )
        view = ForgeView(self.bot, ctx.author, loadout, balances, money, slot=slot, prefix=ctx.clean_prefix)
        view.message = await ctx.send(embed=view.embed(), file=anvil_file(), view=view)

    @has_char()
    @forge.command(name="trade", brief="Trade smithing goods between lines")
    @locale_doc
    async def forge_trade(self, ctx, amount: int, *, material_and_line: str):
        _(
            """`<amount>` - How many of your material to hand over
            `<material>` - The material you give, for example Bog Iron
            `<line>` - The line you want, guardian, slayer, or vanguard

            Garron trades 3 of one line's material for 1 of another line's material of the same tier.
            Example: `{prefix}forge trade 9 Bog Iron slayer` gives 3 Cinder Ore. Leftovers that do not make a full 3 stay with you.
            """
        )
        if await self._closed(ctx):
            return
        from classes.equipment.definitions import TRADE_RATIO
        from classes.equipment.repository import trade_materials

        words = material_and_line.split()
        if amount < TRADE_RATIO or len(words) < 2:
            return await ctx.send(
                f"Use `{ctx.clean_prefix}forge trade <amount> <material> <line>`, with at least {TRADE_RATIO} goods."
            )
        line = words[-1].lower()
        material_id = resolve_material(" ".join(words[:-1]))
        if material_id is None or line not in ARCHETYPES:
            return await ctx.send("Name a material you hold and a line: guardian, slayer, or vanguard.")
        async with self.bot.pool.acquire() as conn:
            status, result = await trade_materials(conn, ctx.author.id, material_id, line, amount)
        if status == "invalid":
            return await ctx.send("Garron only trades between two different lines, at 3 for 1.")
        if status == "poor":
            return await ctx.send(f"You need {result['spent']} {MATERIALS[material_id]} for that trade.")
        await ctx.send(
            f"Garron takes {self._material_text({result['spent_id']: result['spent']})} "
            f"and hands you {self._material_text({result['received_id']: result['received']})}."
        )

    @has_char()
    @commands.command(name="gearlab", brief="Test the themed gear screen")
    @locale_doc
    async def gearlab(self, ctx):
        _(
            """Open the separate themed gear screen.

            Void, Royal, Frost, and Dusk recolor the chronicle. The slot buttons sit inside the box with the picture.
            `{prefix}gear` is unchanged.
            """
        )
        if await self._closed(ctx):
            return
        from cogs.equipment.layout import build_layout, render_lab, send_layout

        async with self.bot.pool.acquire() as conn:
            loadout = await fetch_loadout(conn, ctx.author.id)
            weapons = await fetch_equipped_weapons(conn, ctx.author.id)
        title = f"{ctx.author.display_name}'s Gear Lab"
        png = render_lab(loadout, weapons, focus="totals", theme="void", title=title)
        components = build_layout(ctx.author.id, loadout, weapons, focus="totals", theme="void", title=title)
        try:
            await send_layout(self.bot, ctx.channel.id, png, components)
        except discord.HTTPException as exc:
            await ctx.send(
                f"The gear lab could not be posted ({exc.status}). `{ctx.clean_prefix}gear` is unchanged."
            )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = ""
        if interaction.data:
            custom_id = str(interaction.data.get("custom_id") or "")
        if not custom_id.startswith("glb:"):
            return
        from cogs.equipment.layout import build_layout, edit_layout, parse_layout_id, render_lab

        parsed = parse_layout_id(custom_id, interaction.user.id)
        if parsed is None:
            if not interaction.response.is_done():
                await interaction.response.send_message("This screen belongs to someone else.", ephemeral=True)
            return
        if not getattr(self.bot, "equipment_combat_enabled", False):
            return
        focus, theme = parsed
        async with self.bot.pool.acquire() as conn:
            loadout = await fetch_loadout(conn, interaction.user.id)
            weapons = await fetch_equipped_weapons(conn, interaction.user.id)
        title = f"{interaction.user.display_name}'s Gear Lab"
        png = render_lab(loadout, weapons, focus=focus, theme=theme, title=title)
        components = build_layout(interaction.user.id, loadout, weapons, focus=focus, theme=theme, title=title)
        try:
            await edit_layout(self.bot, interaction, png, components)
        except discord.HTTPException:
            if not interaction.response.is_done():
                await interaction.response.send_message("That screen could not be updated.", ephemeral=True)

    @gear.command(name="preview", brief="Show a sample armory card")
    @locale_doc
    async def gear_preview(self, ctx):
        _("""Show the armory card with sample art, stars, and enchantment glow.""")
        if await self._closed(ctx):
            return
        png = render_armory(
            preview_loadout(),
            title="Armory preview",
            subtitle="Sample cuirass. The other slots are empty.",
        )
        await ctx.send(
            embed=self._embed(
                ctx,
                "Armory preview",
                "The cuirass shows temper stars and an enchantment glow. "
                "Helm, greaves, and sabatons are empty on this sample. "
                "This preview is not an item.",
            ),
            file=_file(png),
        )

    @has_char()
    @gear.command(name="enchantments", brief="List armor enchantments")
    @locale_doc
    async def gear_enchantments(self, ctx):
        _(
            """List every armor enchantment, what it does, and which line can roll it.

        About one crate piece in four gains a single enchantment from its own line.
        A fully rolled legendary discovery gains two. A crafted piece gains none.
        `{prefix}armory` shows the enchantments on each piece you own.

        Weapon Amplification adds 4% weapon damage.
        Fortified adds 6% ward.
        Vitality adds 75 health.
        Sunder ignores 55% of the foe's armor.
        Breakthrough has a 10% chance to ignore 15% more armor on that hit.

        Guardian rolls Fortified and Vitality.
        Slayer rolls Weapon Amplification, Vitality, Sunder, and Breakthrough.
        Vanguard rolls Weapon Amplification, Fortified, Vitality, and Breakthrough.
        A Guardian piece never rolls Sunder or Breakthrough. A Slayer piece never rolls Fortified.
            """
        )
        if await self._closed(ctx):
            return
        from classes.equipment.card import modifier_effect
        from classes.equipment.definitions import MODIFIER_LINES, MODIFIERS

        embed = discord.Embed(
            title="Armor enchantments",
            description=(
                "About one crate piece in four gains one enchantment from its line. "
                "A fully rolled legendary discovery gains two. Crafted pieces gain none."
            ),
            color=0x7EB6D6,
        )
        for modifier_id, spec in MODIFIERS.items():
            embed.add_field(
                name=spec["name"],
                value=modifier_effect(modifier_id) or "No listed effect.",
                inline=False,
            )
        for line, modifier_ids in MODIFIER_LINES.items():
            names = ", ".join(MODIFIERS[modifier_id]["name"] for modifier_id in modifier_ids)
            embed.add_field(name=line.title(), value=names, inline=False)
        await ctx.send(embed=embed)

    @has_char()
    @gear.command(name="materials", brief="Show your smithing goods")
    @locale_doc
    async def gear_materials(self, ctx):
        _(
            """Show your smithing goods.

        Guardian, Slayer, and Vanguard each have three materials. The dots match
        `{prefix}amulet resources`: white is the rough good, blue is worked, and
        gold is the relic. A balance of zero is still shown.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            balances = await fetch_materials(conn, ctx.author.id)
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Armory Materials",
            color=0x846236,
        )
        embed.add_field(
            name="Rarity Legend",
            value="⚪ Common • 🟢 Uncommon • 🔵 Rare • 🟣 Epic • 🟡 Legendary",
            inline=False,
        )
        for line, material_ids in MATERIAL_LINES.items():
            lines = [
                f"{material_dot(material_id)} {MATERIALS[material_id]}: {balances.get(material_id, 0):,}"
                for material_id in material_ids
            ]
            embed.add_field(name=line.title(), value="\n".join(lines), inline=False)
        await ctx.send(embed=embed)

    @has_char()
    @gear.command(name="theme", aliases=["cover"], brief="Pick the cover for your armory card")
    @locale_doc
    async def gear_theme_command(self, ctx, *, name: str = None):
        _(
            """`[name]` - The cover to use. Leave it out to list them.

            Every cover is free to pick and change. Others see your cover on `{prefix}gear @user`.
            """
        )
        if await self._closed(ctx):
            return
        from classes.equipment.chronicle import THEMES

        wanted = (name or "").strip().casefold().replace("'", "")
        choice = next(
            (key for key, spec in THEMES.items() if wanted in (key, spec.label.casefold().replace("'", ""))),
            None,
        )
        async with self.bot.pool.acquire() as conn:
            if choice is None:
                current = await gear_theme(conn, ctx.author.id)
                lines = "\n".join(
                    f"{'**' if key == current else ''}{spec.label}{'** (current)' if key == current else ''} · `{key}`"
                    for key, spec in THEMES.items()
                )
                note = f"No cover is called **{name}**.\n\n" if name else ""
                return await ctx.send(
                    embed=discord.Embed(
                        title="Armory covers",
                        description=f"{note}{lines}\n\nUse `{ctx.clean_prefix}gear theme <name>`.",
                        color=THEMES[current].accent,
                    )
                )
            await set_gear_theme(conn, ctx.author.id, choice)
        await ctx.send(f"Your armory card now uses the **{THEMES[choice].label}** cover.")

    @has_char()
    @gear.command(name="info", brief="Show one piece on the armory card")
    @locale_doc
    async def gear_info(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - The piece id from the Gear tab of `{prefix}armory`

            Show that piece on the armory card, including its quality, temper, and whether it is worn.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            item = await fetch_item(conn, ctx.author.id, equipment_id)
            theme = await gear_theme(conn, ctx.author.id)
        if item is None:
            return await ctx.send("You do not own a piece with that id.")
        state = "Worn" if item.get("equipped") else "Stored"
        png = render_armory(
            {item["slot"]: item} if item["slot"] in PAPER_DOLL_SLOTS else {},
            title=item["name"],
            subtitle=f"Id {item['id']} · {state}",
            theme=theme,
        )
        binding = "Bound" if item["bound"] else "Tradable until enhanced"
        await ctx.send(
            embed=self._embed(
                ctx,
                item["name"],
                f"{state} · {item['rarity'].title()} {item['archetype'].title()} {item['slot']} · "
                f"{quality_band(item['quality'])} {item['quality']} · {binding}.",
            ),
            file=_file(png),
        )

    @has_char()
    @gear.command(name="equip", brief="Wear a piece. This does not bind it")
    @locale_doc
    async def gear_equip(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - The piece id from the Gear tab of `{prefix}armory`

            Wear that piece in its slot. Equipping does not bind it.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            preview = await fetch_item(conn, ctx.author.id, equipment_id)
        if preview is not None and not preview.get("equipped") and not preview["bound"]:
            if not await ctx.confirm(
                f"**Are you sure?** Wearing **{preview['name']}** does not bind it by itself, but the first "
                "adventure, tower floor, monster battle, world raid, or dragon kill you finish while wearing it "
                "binds it to you. After that you will no longer be able to trade, give, sell, or list it."
            ):
                return await ctx.send("You leave it in your pack.")
        async with self.bot.pool.acquire() as conn:
            status, item = await equip_item(conn, ctx.author.id, equipment_id)
        if status == "missing":
            return await ctx.send("You do not own a piece with that id.")
        if status == "closed":
            return await ctx.send(
                f"The {item['slot']} slot is reserved. Open slots: {', '.join(OPEN_SLOTS)}."
            )
        if status == "already":
            return await ctx.send("That piece is already worn.")
        if status == "listed":
            return await ctx.send("Take it off the gear shop before wearing it.")
        await ctx.send(
            f"You wear **{item['name']}**. Equipping does not bind it."
        )

    @has_char()
    @gear.command(name="unequip", brief="Take off worn armor")
    @locale_doc
    async def gear_unequip(self, ctx, equipment_id: int = None):
        _(
            """`[equipment_id]` - Optional piece id. Leave it out to take off every worn piece.

            Take off one piece, or every piece you are wearing. This does not unbind them.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            status, removed_id = await unequip_item(conn, ctx.author.id, equipment_id)
        if status == "missing":
            return await ctx.send("Nothing came off.")
        if isinstance(removed_id, list):
            return await ctx.send(f"You put away {len(removed_id)} pieces.")
        await ctx.send(f"You put away piece `{removed_id}`.")

    def _material_text(self, amounts: dict) -> str:
        parts = [
            f"{material_dot(material_id)} {MATERIALS[material_id]} x{amount}"
            for material_id, amount in amounts.items()
            if int(amount) > 0 and material_id in MATERIALS
        ]
        return ", ".join(parts) or "nothing"

    @is_gm()
    @gear.command(name="switch", brief="GM: open or close the armory for everyone", hidden=True)
    @locale_doc
    async def gear_switch(self, ctx, state: str = None):
        _(
            """`[on|off]` - Open or close the armory. Leave it out to see the current state.

            Closing hides gear commands and removes armor from combat, crates, and trades on every cluster within a minute.
            Owned pieces and materials are kept.
            """
        )
        if not getattr(self, "schema_ready", False):
            return await ctx.send("The armory tables did not load. Check the bot log.")
        wanted = {"on": True, "open": True, "off": False, "close": False}.get(str(state or "").lower())
        if wanted is None:
            current = "open" if self.available else "closed"
            return await ctx.send(f"The armory is **{current}**. Use `{ctx.clean_prefix}gear switch on` or `off`.")
        async with self.bot.pool.acquire() as conn:
            await set_feature_enabled(conn, wanted)
        self.available = wanted
        self.bot.equipment_combat_enabled = wanted
        await ctx.send(
            f"The armory is now **{'open' if wanted else 'closed'}**. "
            "Other clusters follow within a minute."
        )

    @is_gm()
    @gear.command(name="uipreview", brief="GM: preview every crafting pattern", hidden=True)
    @locale_doc
    async def gear_uipreview(self, ctx):
        _(
            """Open the crafting menu with every pattern and a sample material wallet.

            The sample wallet does not spend materials, and the Craft button does not forge a piece.
            """
        )
        if await self._closed(ctx):
            return
        from cogs.equipment.available import GearCraftView
        from classes.equipment.economy import all_recipe_keys, preview_balances

        view = GearCraftView(
            self,
            ctx,
            preview_balances(),
            set(all_recipe_keys()),
            preview=True,
        )
        view.message = await ctx.send(embed=view.summary_embed(), view=view)

    @has_char()
    @gear.command(name="available", aliases=["craft"], brief="See discovered patterns, or craft one")
    @locale_doc
    async def gear_available(self, ctx, rarity: str = None, archetype: str = None, slot: str = None):
        _(
            """`[rarity]` - Optional. common, uncommon, rare, magic, or legendary
        `[line]` - Optional. guardian, slayer, or vanguard

        With no arguments, `{prefix}gear available` opens the crafting screen.
        It lists only patterns you have discovered and marks each one ready,
        close, or short. `{prefix}gear craft` opens the same screen.

        `{prefix}gear craft rare guardian` forges that cuirass when you know it.
        `{prefix}gear craft rare guardian helm` forges the helm. Quality is rolled.
        The piece is tradable until it is bound.
            """
        )
        if await self._closed(ctx):
            return
        if (rarity is None) != (archetype is None) or (slot is not None and rarity is None):
            return await ctx.send("Use `$gear craft <rarity> <line> [slot]`, or `$gear available` to browse.")
        if rarity is None or archetype is None:
            from cogs.equipment.available import GearCraftView
            from classes.equipment.repository import fetch_discovered_recipes

            async with self.bot.pool.acquire() as conn:
                balances = await fetch_materials(conn, ctx.author.id)
                discovered = await fetch_discovered_recipes(conn, ctx.author.id)
            view = GearCraftView(self, ctx, balances, discovered)
            view.message = await ctx.send(embed=view.summary_embed(), view=view)
            return
        rarity = rarity.lower()
        archetype = archetype.lower()
        piece_slot = resolve_slot(slot or "chest")
        if rarity not in RARITIES or archetype not in ARCHETYPES or piece_slot not in OPEN_SLOTS:
            return await ctx.send(
                f"Use a rarity ({', '.join(RARITIES)}), a line ({', '.join(ARCHETYPES)}), "
                "and optionally helm, cuirass, greaves, or sabatons."
            )
        cost = craft_cost(rarity, archetype)
        async with self.bot.pool.acquire() as conn:
            status, item = await craft_chest(conn, ctx.author.id, rarity, archetype, slot=piece_slot)
        if status == "unknown":
            return await ctx.send("You have not discovered that pattern yet. Find one first.")
        if status == "poor":
            return await ctx.send(f"You need {self._material_text(cost)}.")
        await ctx.send(
            f"You forge **{item['name']}** (`{item['id']}`). "
            f"{quality_band(item['quality'])} {item['quality']}. It is tradable until enhanced. "
            f"Spent {self._material_text(cost)}."
        )

    @has_char()
    @gear.command(name="refine", brief="Open the forge to refine a worn piece's quality")
    @locale_doc
    async def gear_refine(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - A piece you are wearing

            Open Thorne's Anvil on that piece. Refining raises quality by 1 for materials and gold, with a chance to fail and pity. The first time binds the piece.
            """
        )
        await self._open_forge(ctx, equipment_id)

    @has_char()
    @gear.command(name="temper", brief="Open the forge to temper a worn piece's stars")
    @locale_doc
    async def gear_temper(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - A piece you are wearing

            Open Thorne's Anvil on that piece. Tempering adds a star, up to +5, or +7 once the piece is fully attuned. It costs materials and gold, can fail, and has pity. The first time binds the piece.
            """
        )
        await self._open_forge(ctx, equipment_id)

    @has_char()
    @gear.command(name="salvage", brief="Break a piece into fewer materials")
    @locale_doc
    async def gear_salvage(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - The piece to destroy

        Break the piece down. You receive some of that line's materials, and
        always fewer than crafting the same piece would cost. Materials spent
        on refinement are not returned. A piece listed in `{prefix}gear shop`
        must be taken down first.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            status, result = await salvage_piece(conn, ctx.author.id, equipment_id)
        if status == "missing":
            return await ctx.send("You do not own that piece.")
        if status == "listed":
            return await ctx.send("Take it off the gear shop before salvaging it.")
        await ctx.send(
            f"You break down **{result['name']}** and recover {self._material_text(result['materials'])}."
        )

    @has_char()
    @gear.command(name="give", brief="Give a tradable piece to someone")
    @locale_doc
    async def gear_give(self, ctx, member: discord.Member, equipment_id: int):
        _(
            """`<member>` - Who receives the piece
            `<equipment_id>` - The piece id from the Gear tab of `{prefix}armory`

            Give a tradable piece to another character. Bound, refined, and fully rolled pieces cannot be given.
            """
        )
        if await self._closed(ctx):
            return
        if member.id == ctx.author.id:
            return await ctx.send("You already own that piece.")
        from classes.equipment.repository import move_piece

        async with self.bot.pool.acquire() as conn:
            if not await self._has_profile(conn, member.id):
                return await ctx.send(f"{member.display_name} does not have a character.")
            async with conn.transaction():
                status = await move_piece(conn, equipment_id, ctx.author.id, member.id)
        if status == "missing":
            return await ctx.send("You do not own that piece.")
        if status == "bound":
            return await ctx.send("That piece is bound and cannot be given.")
        await ctx.send(f"You give piece `{equipment_id}` to {member.mention}.")

    @has_char()
    @gear.command(name="pay", brief="Give smithing goods to someone")
    @locale_doc
    async def gear_pay(self, ctx, member: discord.Member, amount: int, *, material: str):
        _(
            """`<member>` - Who receives the materials
            `<amount>` - How many to give
            `<material>` - The material name, for example Bog Iron

            Give armory materials. Example: `{prefix}gear pay @user 10 Bog Iron`.
            """
        )
        if await self._closed(ctx):
            return
        if amount < 1 or member.id == ctx.author.id:
            return await ctx.send("Choose another character and a positive amount.")
        material_id = resolve_material(material)
        if material_id is None:
            return await ctx.send("That is not an armory material.")
        async with self.bot.pool.acquire() as conn:
            if not await self._has_profile(conn, member.id):
                return await ctx.send(f"{member.display_name} does not have a character.")
            async with conn.transaction():
                if not await spend_materials(conn, ctx.author.id, {material_id: amount}):
                    return await ctx.send("You do not have enough of that material.")
                await add_materials(conn, member.id, {material_id: amount})
        await ctx.send(
            f"You pay {member.mention} {material_dot(material_id)} {MATERIALS[material_id]} x{amount}."
        )

    @has_char()
    @gear.command(name="sell", brief="List a tradable piece on the gear shop")
    @locale_doc
    async def gear_sell(self, ctx, equipment_id: int, price: int):
        _(
            """`<equipment_id>` - The piece id from the Gear tab of `{prefix}armory`
            `<price>` - The price in gold, from 1 to 100,000,000

            List a tradable piece on `{prefix}gear shop`. Bound pieces cannot be listed.
            """
        )
        if await self._closed(ctx):
            return
        if price < 1 or price > 100_000_000:
            return await ctx.send("Price must be from 1 to 100,000,000.")
        async with self.bot.pool.acquire() as conn:
            status, item = await list_piece(conn, ctx.author.id, equipment_id, price)
        if status == "missing":
            return await ctx.send("You do not own that piece.")
        if status == "bound":
            return await ctx.send("That piece is bound and cannot be listed.")
        await ctx.send(f"You list **{item['name']}** for **${price:,}**. See `$gear shop`.")

    @gear.command(name="shop", brief="Browse the gear shop")
    @locale_doc
    async def gear_shop(self, ctx):
        _("""Show armor listed on the gear shop.""")
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            rows = await fetch_market(conn)
        if not rows:
            return await ctx.send("The gear shop is empty.")
        lines = [
            f"`{row['id']}` **{row['name']}** · {row['rarity'].title()} {row['archetype'].title()} · "
            f"{quality_band(row['quality'])} {row['quality']} · **${int(row['price']):,}**"
            for row in rows
        ]
        embed = discord.Embed(title="Gear shop", description="\n".join(lines), color=0x846236)
        await ctx.send(embed=embed)

    @has_char()
    @gear.command(name="buy", brief="Buy a piece from the gear shop")
    @locale_doc
    async def gear_buy(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - The listing id from `{prefix}gear shop`

            Buy that piece. The price is paid from your gold, and it stays tradable until it is refined.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            status, result = await buy_listing(conn, ctx.author.id, equipment_id)
        messages = {
            "missing": "That listing is gone.",
            "self": "You cannot buy your own listing.",
            "bound": "That listing was withdrawn because the piece can no longer be traded.",
            "poor": "You cannot afford that listing.",
        }
        if status != "bought":
            return await ctx.send(messages.get(status, "The purchase did not complete."))
        await ctx.send(f"You buy **{result['name']}** for **${result['price']:,}**.")

    @has_char()
    @gear.command(name="unsell", brief="Take your piece off the gear shop")
    @locale_doc
    async def gear_unsell(self, ctx, equipment_id: int):
        _(
            """`<equipment_id>` - Your listing id

            Take your piece off `{prefix}gear shop`.
            """
        )
        if await self._closed(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            status = await withdraw_listing(conn, ctx.author.id, equipment_id)
        if status == "missing":
            return await ctx.send("You do not have that listing.")
        await ctx.send(f"You take piece `{equipment_id}` back from the shop.")

    @is_gm()
    @gear.command(name="grant", brief="GM: create a tradable piece", hidden=True)
    @locale_doc
    async def gear_grant(
        self,
        ctx,
        member: discord.Member,
        rarity: str,
        archetype: str,
        quality: int = 70,
        slot: str = "chest",
    ):
        _(
            """`<member>` - Who receives the piece
            `<rarity>` - common, uncommon, rare, magic, or legendary
            `<archetype>` - guardian, slayer, or vanguard
            `[quality]` - Optional, from 1 to 100. Defaults to 70
            `[slot]` - Optional. helm, cuirass, greaves, or sabatons. Defaults to cuirass

            Create one tradable piece on the development realm. It is stored and unbound.
            """
        )
        if await self._closed(ctx):
            return
        rarity = rarity.lower()
        archetype = archetype.lower()
        if rarity not in RARITIES:
            return await ctx.send(f"Rarity must be one of: {', '.join(RARITIES)}.")
        if archetype not in ARCHETYPES:
            return await ctx.send(f"Archetype must be one of: {', '.join(ARCHETYPES)}.")
        piece_slot = resolve_slot(slot or "chest")
        if quality < 1 or quality > 100:
            return await ctx.send("Quality must be from 1 to 100.")
        if piece_slot not in OPEN_SLOTS:
            return await ctx.send("Slot must be helm, cuirass, greaves, or sabatons.")
        async with self.bot.pool.acquire() as conn:
            item = await grant_chest(conn, member.id, rarity, archetype, quality, slot=piece_slot)
        await ctx.send(
            f"Granted **{item['name']}** (`{item['id']}`) to {member.mention}. "
            f"Quality {item['quality']} ({quality_band(item['quality'])}). "
            "It is stored, tradable, and unbound."
        )

    async def _attune_from_deed(self, user_ids, amount, channel=None) -> None:
        if not getattr(self.bot, "equipment_combat_enabled", False):
            return
        from classes.equipment.attunement import attunement_message, crossed_milestone
        from classes.equipment.repository import attune_worn

        notes = []
        try:
            async with self.bot.pool.acquire() as conn:
                for user_id in dict.fromkeys(user_ids):
                    decision = await attune_worn(conn, int(user_id), amount=amount)
                    for item in (decision or {}).get("pieces") or ([] if not decision else [decision]):
                        if crossed_milestone(item):
                            notes.append(attunement_message(item))
        except Exception:
            return
        if notes and channel is not None:
            try:
                await channel.send("\n".join(notes))
            except Exception:
                return

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if not iscompleted:
            return
        from classes.equipment.attunement import XP_ADVENTURE

        await self._attune_from_deed([ctx.author.id], XP_ADVENTURE, getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_battletower_completion(self, ctx, success, *args):
        if not success:
            return
        from classes.equipment.attunement import XP_TOWER_FLOOR

        await self._attune_from_deed([ctx.author.id], XP_TOWER_FLOOR, getattr(ctx, "channel", None))

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if not success:
            return
        from classes.equipment.attunement import XP_RAID_WIN

        await self._attune_from_deed(
            participant_ids,
            XP_RAID_WIN,
            getattr(ctx, "channel", None),
        )

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        from classes.equipment.attunement import XP_DRAGON_KILL

        await self._attune_from_deed(
            [member.id for member in party_members],
            XP_DRAGON_KILL,
            getattr(ctx, "channel", None),
        )
        await self._dragon_materials(party_members, dragon_level, getattr(ctx, "channel", None))

    async def _dragon_materials(self, party_members, dragon_level, channel=None) -> None:
        if not getattr(self.bot, "equipment_combat_enabled", False):
            return
        import random

        from classes.equipment.economy import dragon_tier, roll_dragon_materials
        from classes.equipment.repository import worn_line

        rng = random.Random()
        lines = []
        try:
            async with self.bot.pool.acquire() as conn:
                for member in {member.id: member for member in party_members}.values():
                    if not await self._has_profile(conn, member.id):
                        continue
                    line = await worn_line(conn, member.id) or rng.choice(ARCHETYPES)
                    materials = roll_dragon_materials(dragon_level, line, rng)
                    await add_materials(conn, member.id, materials)
                    lines.append(f"{member.mention}: {self._material_text(materials)}")
        except Exception:
            log.exception("Dragon armory materials failed")
            return
        if lines and channel is not None:
            stage = dragon_tier(dragon_level)[1]
            try:
                await channel.send(f"**Armory goods from the {stage}:**\n" + "\n".join(lines))
            except Exception:
                return


async def setup(bot):
    await bot.add_cog(Equipment(bot))
