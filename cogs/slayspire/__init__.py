from __future__ import annotations

import asyncio
import io

from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont

from discord.ext import commands

from .content import CARD_LIBRARY, CHARACTER_LIBRARY, POTION_LIBRARY, RELIC_LIBRARY
from .engine import SpireEngine
from .models import EnemyState, RunState
from .storage import SpireStorage
from .views import CharacterPickerView, SpireRunView


class SlayTheSpire(commands.Cog):
    CHARACTER_BANNERS = {
        "ironclad": "https://slaythespire.wiki.gg/images/IroncladBanner.jpg?f18bb6",
        "silent": "https://slaythespire.wiki.gg/images/SilentBanner.jpg?dd84d6",
        "defect": "https://slaythespire.wiki.gg/images/DefectBanner.jpg?a68a4e",
        "watcher": "https://slaythespire.wiki.gg/images/WatcherBanner.jpg?8f4a7c",
        "necrobinder": "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/295173706496475136_slay-the-spire-2-necrobinder-1.jpg",
    }
    CHARACTER_BLURBS = {
        "ironclad": "Durable brawler built around Strength, Exhaust, self-damage, and sustain.",
        "silent": "Agile rogue built around Poison, Shivs, discard, and draw control.",
        "defect": "Orb caster built around Lightning, Frost, Focus, and scaling engine turns.",
        "watcher": "Stance dancer built around Wrath, Calm, Divinity, and explosive turn planning.",
        "necrobinder": "Osty-driven summoner built around Doom, Ethereal sequencing, and Soul generation.",
    }
    CHARACTER_HIGHLIGHTS = {
        "ironclad": "High max HP, post-combat healing, strong frontloaded attacks.",
        "silent": "Starts with extra draw, strong defense tools, excels in long scaling fights.",
        "defect": "Starts channeling Lightning, scales hard with orb slots and Focus.",
        "watcher": "Highest burst ceiling, but Wrath punishes sloppy sequencing.",
        "necrobinder": "Osty intercepts attacks, Doom executes at end of turns, and Souls fuel late scaling.",
    }

    def __init__(self, bot):
        self.bot = bot
        self.engine = SpireEngine()
        self.storage = SpireStorage(Path("data") / "slayspire_runs")
        self.runs: dict[int, RunState] = {}
        self.locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, user_id: int) -> asyncio.Lock:
        lock = self.locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[user_id] = lock
        return lock

    async def get_run(self, user_id: int) -> RunState | None:
        run = self.runs.get(user_id)
        if run is not None:
            return run
        run = await self.storage.load_run(user_id)
        if run is not None:
            self.runs[user_id] = run
        return run

    async def save_run(self, run: RunState) -> None:
        self.runs[run.user_id] = run
        await self.storage.save_run(run)

    async def delete_run(self, user_id: int) -> None:
        self.runs.pop(user_id, None)
        await self.storage.delete_run(user_id)

    async def create_run(
        self,
        *,
        user_id: int,
        guild_id: int,
        channel_id: int,
        character: str,
    ) -> RunState:
        async with self._lock_for(user_id):
            existing = await self.get_run(user_id)
            if existing is not None and existing.phase not in {"victory", "defeat"}:
                raise ValueError("You already have an active run. Use `spire abandon` first.")
            run = self.engine.start_new_run(
                user_id=user_id,
                guild_id=guild_id,
                channel_id=channel_id,
                character=character,
            )
            await self.save_run(run)
            return run

    async def start_run_from_picker(self, interaction: discord.Interaction, character: str) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Use this in a server channel.", ephemeral=True)
            return
        try:
            run = await self.create_run(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                character=character,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=f"Starting as {self.character_display_name(character)}.",
            **self.build_edit_kwargs(run, view=SpireRunView(self, run)),
        )

    @commands.hybrid_group(name="spire", invoke_without_command=True)
    async def spire(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("Use this in a server channel.")
            return
        run = await self.get_run(ctx.author.id)
        if run is None:
            await ctx.send("No active run. Use `spire start`.")
            return
        await ctx.send(**self.build_send_kwargs(run, view=SpireRunView(self, run)))

    @spire.command(name="start")
    async def spire_start(self, ctx: commands.Context, character: str | None = None):
        if ctx.guild is None:
            await ctx.send("Use this in a server channel.")
            return
        async with self._lock_for(ctx.author.id):
            existing = await self.get_run(ctx.author.id)
            if existing is not None and existing.phase not in {"victory", "defeat"}:
                await ctx.send("You already have an active run. Use `spire abandon` first.")
                return
        if character is None:
            await ctx.send(
                embed=self.build_character_picker_embed("ironclad"),
                view=CharacterPickerView(self, ctx.author.id),
            )
            return
        try:
            run = await self.create_run(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id,
                channel_id=ctx.channel.id,
                character=character,
            )
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await ctx.send(**self.build_send_kwargs(run, view=SpireRunView(self, run)))

    @spire.command(name="resume")
    async def spire_resume(self, ctx: commands.Context):
        run = await self.get_run(ctx.author.id)
        if run is None:
            await ctx.send("No active run. Use `spire start`.")
            return
        await ctx.send(**self.build_send_kwargs(run, view=SpireRunView(self, run)))

    @spire.command(name="status")
    async def spire_status(self, ctx: commands.Context):
        await self.spire_resume(ctx)

    @spire.command(name="deck")
    async def spire_deck(self, ctx: commands.Context):
        run = await self.get_run(ctx.author.id)
        if run is None:
            await ctx.send("No active run. Use `spire start`.")
            return
        await ctx.send(self.render_deck(run))

    @spire.command(name="abandon")
    async def spire_abandon(self, ctx: commands.Context):
        async with self._lock_for(ctx.author.id):
            run = await self.get_run(ctx.author.id)
            if run is None:
                await ctx.send("No active run.")
                return
            self.engine.abandon_run(run)
            await self.delete_run(ctx.author.id)
        await ctx.send(**self.build_send_kwargs(run))

    async def handle_view_action(
        self,
        interaction: discord.Interaction,
        action: str,
        value: str | None,
    ):
        user_id = interaction.user.id
        async with self._lock_for(user_id):
            run = await self.get_run(user_id)
            if run is None:
                await interaction.response.send_message(
                    "No active run. Use `spire start`.",
                    ephemeral=True,
                )
                return

            if action in {"show_deck", "show_discard", "show_draw"}:
                if action == "show_deck":
                    payload = self.render_deck(run)
                elif action == "show_discard":
                    payload = self.render_discard(run)
                else:
                    payload = self.render_draw_pile(run)
                await interaction.response.send_message(payload, ephemeral=True)
                return

            try:
                notice = self._dispatch_action(run, action, value)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return

            if action == "abandon":
                await self.delete_run(user_id)
                await interaction.response.edit_message(
                    content=notice,
                    **self.build_edit_kwargs(run),
                )
                return

            await self.save_run(run)
            await interaction.response.edit_message(
                content=notice,
                **self.build_edit_kwargs(
                    run,
                    view=SpireRunView(self, run) if run.phase not in {"victory", "defeat"} else None,
                ),
            )

    def _dispatch_action(self, run: RunState, action: str, value: str | None) -> str:
        if action == "map_choice":
            return self.engine.choose_map_node(run, int(value))
        if action == "neow_choice":
            return self.engine.choose_neow_option(run, str(value))
        if action == "play_card":
            card = next(
                (entry for entry in run.combat.hand if entry.instance_id == value),
                None,
            ) if run.combat else None
            if card is None:
                raise ValueError("Card not found.")
            if self.engine.card_needs_target(run, card):
                run.selection_context = f"card:{value}"
                return "Choose a target."
            return self.engine.play_card(run, str(value))
        if action == "gambling_chip_discard":
            return self.engine.discard_gambling_chip_card(run, str(value))
        if action == "finish_gambling_chip":
            return self.engine.finish_gambling_chip(run)
        if action == "end_turn":
            return self.engine.end_turn(run)
        if action == "use_potion":
            potion_key = str(value).split(":", 1)[-1]
            if self.engine.potion_needs_target(run, potion_key):
                run.selection_context = f"potion:{potion_key}"
                return "Choose a target."
            return self.engine.use_potion(run, potion_key)
        if action == "target_enemy":
            if not run.selection_context:
                raise ValueError("No targeting action is pending.")
            if run.selection_context.startswith("card:"):
                card_id = run.selection_context.split(":", 1)[1]
                run.selection_context = None
                return self.engine.play_card(run, card_id, str(value))
            if run.selection_context.startswith("potion:"):
                potion_key = run.selection_context.split(":", 1)[1]
                run.selection_context = None
                return self.engine.use_potion(run, potion_key, str(value))
            raise ValueError("Targeting state is invalid.")
        if action == "reward_choice":
            return self.engine.choose_reward_card(run, int(value))
        if action == "skip_reward":
            return self.engine.choose_reward_card(run, None)
        if action == "singing_bowl":
            return self.engine.take_singing_bowl(run)
        if action == "boss_relic_choice":
            return self.engine.choose_boss_relic(run, int(value))
        if action == "treasure_relic":
            return self.engine.choose_treasure_relic(run)
        if action == "treasure_key":
            return self.engine.choose_sapphire_key(run)
        if action == "rest":
            return self.engine.rest(run)
        if action == "dig":
            return self.engine.dig(run)
        if action == "lift":
            return self.engine.lift(run)
        if action == "toke":
            self.engine.begin_toke(run)
            return "Choose a card to remove."
        if action == "recall":
            return self.engine.recall(run)
        if action == "smith":
            self.engine.begin_upgrade(run, "rest")
            return "Choose a card to upgrade."
        if action == "shop_buy":
            return self.engine.buy_shop_offer(run, str(value))
        if action == "shop_remove":
            self.engine.begin_shop_remove(run)
            return "Choose a card to remove."
        if action == "leave_shop":
            return self.engine.leave_shop(run)
        if action == "event_choice":
            return self.engine.choose_event_option(run, str(value))
        if action == "upgrade_choice":
            return self.engine.upgrade_card(run, str(value))
        if action == "remove_choice":
            return self.engine.remove_card(run, str(value))
        if action == "cancel_selection":
            return self.cancel_selection(run)
        if action == "abandon":
            return self.engine.abandon_run(run)
        raise ValueError("Unsupported action.")

    def cancel_selection(self, run: RunState) -> str:
        context = run.selection_context
        if run.phase in {"remove", "upgrade"} and (
            context in {"event", "transform", "bonfire"}
            or (context or "").startswith(("transform:", "astrolabe:", "empty_cage:", "bottle:"))
            or context in {"dollys_mirror", "duplicator"}
        ):
            raise ValueError("This event choice must be completed.")
        run.selection_context = None
        if run.phase == "combat" and context and context.startswith(("card:", "potion:")):
            return "Targeting cancelled."
        if run.phase == "remove" and context == "shop":
            run.phase = "shop"
            return "Card removal cancelled."
        if run.phase == "remove" and (context or "").startswith("forbidden_grimoire:"):
            resume_phase = str(run.meta.pop("forbidden_grimoire_resume_phase", "map"))
            if resume_phase == "map":
                self.engine._advance_after_noncombat(run)
            else:
                run.phase = resume_phase
            return "Card removal skipped."
        if run.phase == "upgrade" and context == "rest":
            run.phase = "rest"
            return "Upgrade cancelled."
        run.phase = "map"
        return "Selection cancelled."

    def node_label(self, node: str, run: RunState | None = None) -> str:
        if run is not None:
            return self.engine.map_choice_label(run, node)
        return self.engine._node_label(node)

    def map_choice_description(self, node: str, run: RunState) -> str:
        return self.engine.map_choice_description(run, node)

    def _map_choice_badges(
        self,
        run: RunState,
        nodes: list[dict[str, object]],
    ) -> dict[str, int]:
        available_ids = {
            str(node["id"])
            for node in nodes
            if isinstance(node, dict) and "id" in node
        }
        badges: dict[str, int] = {}
        for index, entry in enumerate(run.map_choices, start=1):
            node = self.engine.map_node_data(run, str(entry))
            if node is None:
                continue
            node_id = str(node.get("id", entry))
            if node_id in available_ids and node_id not in badges:
                badges[node_id] = index
        return badges

    def enemy_target_label(self, run: RunState, enemy: EnemyState) -> str:
        if run.combat is None:
            return enemy.name
        alive = [entry for entry in run.combat.enemies if entry.hp > 0]
        try:
            slot = alive.index(enemy) + 1
        except ValueError:
            slot = 0
        if slot > 0:
            return f"#{slot} {enemy.name}"
        return enemy.name

    def enemy_target_description(self, enemy: EnemyState) -> str:
        parts = [f"{enemy.hp}/{enemy.max_hp} HP"]
        if enemy.block > 0:
            parts.append(f"Block {enemy.block}")
        statuses = self.format_statuses(enemy.statuses)
        if statuses:
            parts.append(statuses)
        return " | ".join(parts)

    def character_display_name(self, character_key: str) -> str:
        return str(CHARACTER_LIBRARY[character_key]["name"])

    def character_picker_blurb(self, character_key: str) -> str:
        return self.CHARACTER_BLURBS.get(character_key, "")

    def build_character_picker_embed(self, character_key: str) -> discord.Embed:
        character = CHARACTER_LIBRARY[character_key]
        starter_relic_key = str(character["starter_relic"])
        starting_deck = list(character["starting_deck"])
        deck_counts: dict[str, int] = {}
        for card_key in starting_deck:
            card_name = CARD_LIBRARY[card_key].name
            deck_counts[card_name] = deck_counts.get(card_name, 0) + 1
        deck_summary = ", ".join(
            f"{count}x {name}" for name, count in deck_counts.items()
        )

        embed = discord.Embed(
            title=f"Choose Your Character: {character['name']}",
            description=self.CHARACTER_BLURBS.get(character_key, ""),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Overview",
            value=(
                f"Max HP: **{character['max_hp']}**\n"
                f"Starter Relic: **{RELIC_LIBRARY[starter_relic_key].name}**\n"
                f"Card Pool: **{len(character['card_pool'])}** class cards"
            ),
            inline=False,
        )
        embed.add_field(
            name="Starter Relic",
            value=RELIC_LIBRARY[starter_relic_key].description,
            inline=False,
        )
        embed.add_field(
            name="Starting Deck",
            value=deck_summary,
            inline=False,
        )
        embed.add_field(
            name="Highlights",
            value=self.CHARACTER_HIGHLIGHTS.get(character_key, "Climb the Spire."),
            inline=False,
        )
        banner_url = self.CHARACTER_BANNERS.get(character_key)
        if banner_url:
            embed.set_image(url=banner_url)
        embed.set_footer(text="Use the dropdown or arrows to browse, then press Start Run.")
        return embed

    def build_send_kwargs(
        self,
        run: RunState,
        *,
        view: discord.ui.View | None = None,
    ) -> dict[str, object]:
        embed, file = self.build_embed_payload(run)
        kwargs: dict[str, object] = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        if file is not None:
            kwargs["file"] = file
        return kwargs

    def build_edit_kwargs(
        self,
        run: RunState,
        *,
        view: discord.ui.View | None = None,
    ) -> dict[str, object]:
        embed, file = self.build_embed_payload(run)
        kwargs: dict[str, object] = {"embed": embed, "attachments": [file] if file is not None else []}
        kwargs["view"] = view
        return kwargs

    def build_embed_payload(self, run: RunState) -> tuple[discord.Embed, discord.File | None]:
        embed = self.build_embed(run)
        map_file = self.render_map_file(run)
        if map_file is not None:
            embed.set_image(url=f"attachment://{map_file.filename}")
        return embed, map_file

    def _map_symbol(self, node_type: str) -> str:
        return {
            "combat": "C",
            "elite": "E",
            "elite_key": "K",
            "rest": "R",
            "shop": "$",
            "event": "?",
            "treasure": "T",
            "boss": "M",
        }.get(node_type, "?")

    def _map_colors(self, node_type: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        palette = {
            "combat": ((168, 74, 50), (250, 214, 196)),
            "elite": ((132, 44, 44), (255, 225, 225)),
            "elite_key": ((70, 118, 150), (235, 248, 255)),
            "rest": ((66, 121, 79), (230, 249, 234)),
            "shop": ((176, 132, 58), (255, 245, 210)),
            "event": ((93, 72, 135), (240, 233, 255)),
            "treasure": ((173, 111, 35), (255, 244, 205)),
            "boss": ((92, 36, 36), (255, 234, 234)),
        }
        return palette.get(node_type, ((80, 80, 80), (245, 245, 245)))

    def _load_map_font(self, size: int):
        for font_name in ("DejaVuSansMono.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(font_name, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def render_map_file(self, run: RunState) -> discord.File | None:
        if run.phase != "map":
            return None

        width, height = 1320, 1760
        image = Image.new("RGBA", (width, height), (17, 15, 19, 255))
        draw = ImageDraw.Draw(image)
        title_font = self._load_map_font(40)
        label_font = self._load_map_font(22)
        symbol_font = self._load_map_font(26)
        small_font = self._load_map_font(15)

        draw.rectangle((0, 0, width, height), fill=(17, 15, 19, 255))
        for y in range(height):
            shade = 17 + min(28, y // 55)
            draw.line((0, y, width, y), fill=(shade, shade - 2, shade + 4, 255))

        draw.text((54, 34), f"Act {run.act} Map", font=title_font, fill=(248, 236, 214))
        draw.text(
            (56, 88),
            "Bright rings are reachable. Gold rings are visited. Blue badges match the dropdown.",
            font=label_font,
            fill=(194, 188, 180),
        )

        if run.act == 4:
            nodes = [
                {"id": "act4-rest", "row": 1, "col": 3, "node_type": "rest", "next_ids": ["act4-shop"]},
                {"id": "act4-shop", "row": 2, "col": 3, "node_type": "shop", "next_ids": ["act4-elite"]},
                {"id": "act4-elite", "row": 3, "col": 3, "node_type": "elite_key", "next_ids": ["act4-boss"]},
                {"id": "act4-boss", "row": 4, "col": 3, "node_type": "boss", "next_ids": []},
            ]
            visited = {
                node["id"]
                for index, node in enumerate(nodes)
                if index < run.act_floor
            }
            reachable = {
                node["id"]
                for index, node in enumerate(nodes)
                if index == min(run.act_floor, len(nodes) - 1)
            }
            max_row = 4
        else:
            act_map = self.engine._current_act_map(run)
            if act_map is None:
                return None
            nodes = [
                node
                for node in list(act_map.get("nodes", []))
                if isinstance(node, dict) and "id" in node
            ]
            visited = {str(entry) for entry in list(act_map.get("visited", []))}
            reachable = {str(entry) for entry in list(act_map.get("reachable", []))}
            boss_row = self.engine.MAP_BOSS_FLOOR
            nodes.append(
                {
                    "id": f"act{run.act}-boss",
                    "row": boss_row,
                    "col": self.engine.MAP_COLUMNS // 2,
                    "node_type": "boss",
                    "next_ids": [],
                }
            )
            max_row = boss_row

        choice_badges = self._map_choice_badges(run, nodes)
        selectable_nodes = reachable | set(choice_badges)

        left = 170
        right = width - 130
        top = 190
        bottom = height - 255
        col_step = (right - left) / max(1, self.engine.MAP_COLUMNS - 1)
        row_step = (bottom - top) / max(1, max_row - 1)
        node_positions: dict[str, tuple[float, float]] = {}
        for node in nodes:
            node_id = str(node["id"])
            row = int(node.get("row", 1))
            col = int(node.get("col", self.engine.MAP_COLUMNS // 2))
            stagger = (col_step * 0.18) if row % 2 == 0 else 0.0
            node_positions[node_id] = (
                left + (col_step * col) + stagger,
                top + (row_step * (row - 1)),
            )

        for row in range(1, max_row + 1):
            y = top + (row_step * (row - 1))
            draw.text((64, y - 12), f"{row:02d}", font=label_font, fill=(152, 146, 142))

        for node in nodes:
            node_id = str(node["id"])
            start = node_positions[node_id]
            for next_id in list(node.get("next_ids", [])):
                end = node_positions.get(str(next_id))
                if end is None:
                    continue
                if node_id in visited and str(next_id) in visited:
                    edge_color = (208, 176, 106)
                elif str(next_id) in selectable_nodes:
                    edge_color = (152, 216, 255)
                else:
                    edge_color = (84, 84, 90)
                draw.line((start[0], start[1], end[0], end[1]), fill=edge_color, width=4)

        node_radius = 24
        for node in nodes:
            node_id = str(node["id"])
            node_type = str(node.get("node_type", "combat"))
            x, y = node_positions[node_id]
            fill_color, text_color = self._map_colors(node_type)
            outline = (84, 84, 90)
            outline_width = 4
            if node_id in visited:
                outline = (214, 181, 116)
                outline_width = 6
            elif node_id in selectable_nodes:
                outline = (151, 220, 255)
                outline_width = 6

            draw.ellipse(
                (x - node_radius, y - node_radius, x + node_radius, y + node_radius),
                fill=fill_color,
                outline=outline,
                width=outline_width,
            )
            symbol = self._map_symbol(node_type)
            bbox = draw.textbbox((0, 0), symbol, font=symbol_font)
            draw.text(
                (x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 1),
                symbol,
                font=symbol_font,
                fill=text_color,
            )

            badge = choice_badges.get(node_id)
            if badge is not None:
                badge_radius = 14
                badge_x = x + node_radius - 6
                badge_y = y - node_radius + 6
                draw.ellipse(
                    (
                        badge_x - badge_radius,
                        badge_y - badge_radius,
                        badge_x + badge_radius,
                        badge_y + badge_radius,
                    ),
                    fill=(42, 92, 138),
                    outline=(196, 232, 255),
                    width=3,
                )
                badge_text = str(badge)
                badge_bbox = draw.textbbox((0, 0), badge_text, font=small_font)
                draw.text(
                    (
                        badge_x - (badge_bbox[2] - badge_bbox[0]) / 2,
                        badge_y - (badge_bbox[3] - badge_bbox[1]) / 2 - 1,
                    ),
                    badge_text,
                    font=small_font,
                    fill=(245, 250, 255),
                )

        legend_items = [
            ("C", "Combat"),
            ("E", "Elite"),
            ("K", "Burning Elite"),
            ("R", "Rest"),
            ("$", "Shop"),
            ("?", "Unknown"),
            ("T", "Treasure"),
            ("M", "Boss"),
        ]
        legend_top = height - 122
        draw.text((54, legend_top - 36), "Legend", font=label_font, fill=(248, 236, 214))
        for index, (symbol, label) in enumerate(legend_items):
            column = index % 4
            row = index // 4
            box_x = 54 + (column * 304)
            box_y = legend_top + (row * 42)
            draw.rounded_rectangle(
                (box_x, box_y, box_x + 30, box_y + 30),
                radius=9,
                fill=(38, 36, 44),
                outline=(106, 102, 120),
                width=2,
            )
            bbox = draw.textbbox((0, 0), symbol, font=small_font)
            draw.text(
                (box_x + 15 - (bbox[2] - bbox[0]) / 2, box_y + 15 - (bbox[3] - bbox[1]) / 2),
                symbol,
                font=small_font,
                fill=(244, 236, 224),
            )
            draw.text((box_x + 42, box_y + 5), label, font=small_font, fill=(210, 206, 198))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="spire_map.png")

    def render_map(self, run: RunState) -> str:
        act_map = self.engine._current_act_map(run)
        if act_map is None:
            return "No map generated."
        nodes = {
            str(node["id"]): node
            for node in list(act_map.get("nodes", []))
            if isinstance(node, dict) and "id" in node
        }
        reachable = {str(entry) for entry in list(act_map.get("reachable", []))}
        visited = {str(entry) for entry in list(act_map.get("visited", []))}
        symbol_map = {
            "combat": "C",
            "elite": "E",
            "elite_key": "K",
            "rest": "R",
            "shop": "$",
            "event": "?",
            "treasure": "T",
        }
        lines: list[str] = []
        for row in range(1, self.engine.MAP_NODE_ROWS + 1):
            cells: list[str] = []
            for col in range(self.engine.MAP_COLUMNS):
                node = next(
                    (
                        entry
                        for entry in nodes.values()
                        if int(entry.get("row", 0)) == row and int(entry.get("col", 0)) == col
                    ),
                    None,
                )
                if node is None:
                    cells.append(" . ")
                    continue
                symbol = symbol_map.get(str(node.get("node_type", "combat")), "?")
                node_id = str(node["id"])
                if node_id in visited:
                    cells.append(f"<{symbol}>")
                elif node_id in reachable:
                    cells.append(f"[{symbol}]")
                else:
                    cells.append(f" {symbol} ")
            lines.append(f"{row:02d} " + "".join(cells))
        lines.append(f"{self.engine.MAP_BOSS_FLOOR:02d}  M")
        return "```text\n" + "\n".join(lines) + "\n```"

    def potion_name(self, potion_key: str) -> str:
        return POTION_LIBRARY[potion_key].name

    def potion_description(self, potion_key: str) -> str:
        return POTION_LIBRARY[potion_key].description

    def build_embed(self, run: RunState) -> discord.Embed:
        title = f"Slay The Spire - {run.phase.replace('_', ' ').title()}"
        color = discord.Color.orange()
        if run.phase == "defeat":
            color = discord.Color.red()
        elif run.phase == "victory":
            color = discord.Color.green()
        embed = discord.Embed(title=title, color=color)
        embed.description = (
            f"Character: **{run.character.title()}** | HP: **{run.hp}/{run.max_hp}** | "
            f"Gold: **{run.gold}** | Act: **{run.act}** | "
            f"Floor: **{run.floor}/{self.engine.MAX_FLOORS}** | "
            f"Act Floor: **{run.act_floor}/{self.engine.FLOORS_PER_ACT}**"
        )
        keys = ", ".join(key.title() for key in run.keys) or "None"
        embed.add_field(name="Keys", value=keys, inline=False)

        if run.phase == "combat" and run.combat is not None:
            combat = run.combat
            enemy_lines = []
            for enemy in combat.enemies:
                enemy_lines.append(
                    f"**{enemy.name}** {enemy.hp}/{enemy.max_hp} HP | "
                    f"Block {enemy.block} | Intent: {self.render_intent(enemy, hidden='runic_dome' in run.relics)}"
                )
                statuses = self.format_statuses(enemy.statuses)
                if statuses:
                    enemy_lines.append(f"Statuses: {statuses}")
            embed.add_field(
                name="Enemy",
                value="\n".join(enemy_lines) or "No enemies remain.",
                inline=False,
            )
            embed.add_field(
                name="Player",
                value=(
                    f"Energy: {combat.energy}/{combat.max_energy}\n"
                    f"Block: {combat.player_block}\n"
                    + (
                        f"Osty: {combat.player_meta.get('osty_hp', 0)}/{combat.player_meta.get('osty_max_hp', 0)}\n"
                        if run.character == "necrobinder" or combat.player_meta.get("osty_max_hp", 0) > 0
                        else ""
                    )
                    + f"Stance: {combat.stance.title()}\n"
                    f"Orbs: {', '.join(orb.title() for orb in combat.orbs) or 'None'}\n"
                    f"Statuses: {self.format_statuses(combat.player_statuses) or 'None'}"
                ),
                inline=False,
            )
            hand = "\n".join(
                    f"- {self.engine.card_name(card)} [{self.engine.card_cost_label(card, combat)}]: "
                f"{self.engine.card_description(card)}"
                for card in combat.hand
            ) or "Hand is empty."
            embed.add_field(name="Hand", value=hand, inline=False)
            embed.add_field(
                name="Piles",
                value=(
                    f"Draw: {len(combat.draw_pile)} | "
                    f"Discard: {len(combat.discard_pile)} | "
                    f"Exhaust: {len(combat.exhaust_pile)}"
                ),
                inline=False,
            )
            log_text = "\n".join(combat.log[-6:]) or "Combat begins."
            embed.add_field(name="Log", value=log_text, inline=False)
            if run.potions:
                embed.add_field(
                    name="Potions",
                    value=", ".join(self.potion_name(key) for key in run.potions),
                    inline=False,
                )
        elif run.phase == "map":
            choices = "\n".join(
                f"{index + 1}. {self.node_label(choice, run)}"
                for index, choice in enumerate(run.map_choices)
            )
            embed.add_field(name="Reachable Nodes", value=choices or "No choices available.", inline=False)
            embed.add_field(
                name="Map",
                value="Rendered below. Bright rings are reachable, gold rings are visited, and blue badges match the dropdown order.",
                inline=False,
            )
        elif run.phase == "neow" and run.event is not None:
            embed.add_field(name=run.event.name, value=run.event.description, inline=False)
            options = "\n".join(
                f"- **{option.label}**: {option.description}" for option in run.event.options
            )
            embed.add_field(name="Choices", value=options or "No choices available.", inline=False)
        elif run.phase == "reward" and run.reward is not None:
            rewards = "\n".join(
                f"{index + 1}. {CARD_LIBRARY[key].name} - {CARD_LIBRARY[key].description}"
                for index, key in enumerate(run.reward.card_choices)
            )
            field_name = "Reward Cards" if run.reward.source != "event_forced" else "Choose A Card"
            if run.reward.source == "toolbox":
                field_name = "Toolbox"
            embed.add_field(name=field_name, value=rewards, inline=False)
            embed.add_field(name="Gold Won", value=str(run.reward.gold), inline=False)
        elif run.phase == "boss_relic" and run.reward is not None:
            relics = "\n".join(
                f"{index + 1}. {RELIC_LIBRARY[key].name} - {RELIC_LIBRARY[key].description}"
                for index, key in enumerate(run.reward.relic_choices)
            ) or "No boss relics available."
            embed.add_field(name="Boss Chest", value=relics, inline=False)
            embed.add_field(
                name="Transition",
                value=f"Choose a relic to begin Act {run.act + 1}.",
                inline=False,
            )
        elif run.phase == "treasure" and run.reward is not None:
            relic_name = RELIC_LIBRARY[run.reward.relic_choices[0]].name if run.reward.relic_choices else "Unknown Relic"
            relic_text = RELIC_LIBRARY[run.reward.relic_choices[0]].description if run.reward.relic_choices else ""
            embed.add_field(
                name="Treasure Chest",
                value=f"Relic: **{relic_name}**\n{relic_text}\nOr take the Sapphire Key instead.",
                inline=False,
            )
        elif run.phase == "rest":
            choices = []
            if "coffee_dripper" not in run.relics:
                choices.append("Rest to heal 30% max HP.")
            if "fusion_hammer" not in run.relics:
                choices.append("Smith to upgrade one card.")
            if "shovel" in run.relics:
                choices.append("Dig for a relic.")
            if "girya" in run.relics and int(run.meta.get("girya_lifts", 0)) < 3:
                choices.append("Lift with Girya to gain Strength.")
            if "peace_pipe" in run.relics:
                choices.append("Toke with Peace Pipe to remove a card.")
            if "ruby" not in run.keys and run.act < 4:
                choices.append("Recall the Ruby Key.")
            if not choices:
                choices.append("Your relics prevent both resting and smithing here.")
            embed.add_field(name="Choices", value=" ".join(choices), inline=False)
        elif run.phase == "shop" and run.shop is not None:
            offers = []
            for offer in run.shop.offers:
                if offer.kind == "card":
                    prefix = "Sale: " if offer.sale else ""
                    offers.append(f"- {prefix}{CARD_LIBRARY[offer.key].name}: {offer.cost}g")
                elif offer.kind == "potion":
                    offers.append(f"- {POTION_LIBRARY[offer.key].name}: {offer.cost}g")
                else:
                    offers.append(f"- {RELIC_LIBRARY[offer.key].name}: {offer.cost}g")
            offers.append(f"- Remove a card: {run.shop.remove_cost}g")
            embed.add_field(name="Merchant", value="\n".join(offers), inline=False)
        elif run.phase == "event" and run.event is not None:
            embed.add_field(name=run.event.name, value=run.event.description, inline=False)
            options = "\n".join(
                f"- {option.label}: {option.description}" for option in run.event.options
            )
            embed.add_field(name="Options", value=options, inline=False)
        elif run.phase == "upgrade":
            embed.add_field(name="Smith", value="Choose a card from your deck to upgrade.", inline=False)
        elif run.phase == "remove":
            if run.selection_context == "transform" or (run.selection_context or "").startswith("transform:"):
                value = "Choose a card from your deck to transform."
            elif run.selection_context == "bonfire":
                value = "Choose a card from your deck to offer to the bonfire."
            elif (run.selection_context or "").startswith("astrolabe:"):
                value = "Choose a card to transform and upgrade."
            elif (run.selection_context or "").startswith("empty_cage:"):
                value = "Choose a card to remove for Empty Cage."
            elif (run.selection_context or "").startswith("bottle:"):
                bottle_key = (run.selection_context or "").split(":", 1)[1]
                value = f"Choose a card for {RELIC_LIBRARY[bottle_key].name}."
            elif run.selection_context in {"dollys_mirror", "duplicator"}:
                value = "Choose a card to duplicate."
            elif run.selection_context == "peace_pipe":
                value = "Choose a card to remove with Peace Pipe."
            elif (run.selection_context or "").startswith("forbidden_grimoire:"):
                value = "Choose a card to remove with Forbidden Grimoire, or cancel to skip."
            else:
                value = "Choose a card from your deck to remove."
            embed.add_field(name="Removal", value=value, inline=False)
        elif run.phase == "victory":
            embed.add_field(name="Result", value="The boss is dead. This climb is complete.", inline=False)
        elif run.phase == "defeat":
            embed.add_field(name="Result", value="Your run has ended.", inline=False)

        relics = ", ".join(RELIC_LIBRARY[key].name for key in run.relics) or "None"
        embed.add_field(name="Relics", value=relics, inline=False)
        if run.log:
            embed.set_footer(text=" | ".join(run.log[-2:]))
        return embed

    def render_intent(self, enemy: EnemyState, *, hidden: bool = False) -> str:
        if enemy.asleep_turns > 0:
            return "Asleep"
        if hidden:
            return "Hidden"
        intent = self.engine._current_intent(enemy)
        parts: list[str] = []
        for action in intent.actions:
            action_type = action["type"]
            if action_type == "attack":
                hits = int(action.get("hits", 1))
                base = int(action["value"])
                if hits > 1:
                    parts.append(f"Attack {base}x{hits}")
                else:
                    parts.append(f"Attack {base}")
            elif action_type == "attack_turn_scaled_hits":
                parts.append(f"Attack {int(action['value'])}xT")
            elif action_type == "attack_hexaghost_divider":
                minimum = int(action.get("minimum", 1))
                maximum = int(action.get("maximum", 6))
                hits = int(action.get("hits", 6))
                parts.append(f"Attack {minimum}-{maximum}x{hits}")
            elif action_type == "block":
                parts.append(f"Block {int(action['value'])}")
            elif action_type == "block_target":
                target_key = action.get("target_key")
                if target_key:
                    parts.append(f"Grant {int(action['value'])} Block to {str(target_key).replace('_', ' ').title()}")
                else:
                    parts.append(f"Grant {int(action['value'])} Block")
            elif action_type == "apply_status":
                target = str(action["target"])
                status = str(action["status"]).replace("_", " ").title()
                value = int(action["value"])
                if target == "player":
                    parts.append(f"Apply {value} {status}")
                else:
                    parts.append(f"Gain {value} {status}")
            elif action_type == "modify_status":
                target = str(action["target"])
                status = str(action["status"]).replace("_", " ").title()
                value = int(action["value"])
                if target == "player":
                    parts.append(f"{'Apply' if value > 0 else 'Reduce'} {abs(value)} {status}")
                else:
                    verb = "Gain" if value > 0 else "Lose"
                    parts.append(f"{verb} {abs(value)} {status}")
            elif action_type == "create_card":
                parts.append(
                    f"Add {int(action.get('count', 1))} {str(action['key']).title()} to your {str(action['location'])}"
                )
            elif action_type == "attack_scaling":
                parts.append(f"Attack {int(action['value'])}+")
            elif action_type == "hexaghost_sear":
                parts.append(f"Attack {int(action.get('damage', 6))}; Add Burn")
            elif action_type == "hexaghost_inferno":
                parts.append(
                    f"Attack {int(action.get('damage', 2))}x{int(action.get('hits', 6))}; Add {int(action.get('burns', 3))} Burn+"
                )
            elif action_type == "explode":
                parts.append(f"Explode {int(action['value'])}")
            elif action_type == "summon":
                summons = ", ".join(str(entry).replace("_", " ").title() for entry in action.get("keys", []))
                parts.append(f"Summon {summons}")
            elif action_type == "buff_all_enemies":
                status = str(action["status"]).replace("_", " ").title()
                parts.append(f"All enemies gain {int(action['value'])} {status}")
            elif action_type == "heal_self":
                parts.append(f"Heal {int(action['value'])}")
            elif action_type == "heal_all_enemies":
                parts.append(f"Heal all {int(action['value'])}")
            elif action_type == "heal_to_half":
                parts.append("Heal to 50% HP")
            elif action_type == "clear_debuffs":
                parts.append("Clear debuffs")
            elif action_type == "heart_buff":
                parts.append("Gain Strength and escalate")
            elif action_type == "draw_next_turn":
                value = int(action["value"])
                if value >= 0:
                    parts.append(f"Draw +{value} next turn")
                else:
                    parts.append(f"Draw {value} next turn")
            elif action_type == "add_card_to_deck":
                parts.append(f"Add {str(action['key']).replace('_', ' ').title()} to deck")
        if not parts:
            return intent.name
        return f"{intent.name}: {'; '.join(parts)}"

    def format_statuses(self, statuses: dict[str, int]) -> str:
        parts = []
        for key, value in statuses.items():
            if key.startswith("temp_revert_"):
                continue
            if not value or key in {
                "temp_strength_loss",
                "akabeko_pending",
                "first_attack_bonus",
                "poison_bonus",
                "champion_belt",
                "paper_frog",
                "attacks_played_turn",
                "skills_played_turn",
                "cards_played_turn",
                "last_card_attack",
                "next_turn_draw",
                "next_turn_energy",
                "next_turn_block",
                "blue_candle",
                "red_skull_active",
                "retain_all",
                "happy_flower_counter",
                "incense_burner_counter",
                "ink_bottle_counter",
                "sundial_counter",
                "medical_kit",
                "emotion_chip_ready",
                "orange_pellets_attack",
                "orange_pellets_skill",
                "orange_pellets_power",
                "orange_pellets_used_turn",
            }:
                continue
            parts.append(f"{key.replace('_', ' ').title()} {value}")
        return ", ".join(parts)

    def render_deck(self, run: RunState) -> str:
        cards = "\n".join(
            f"- {self.engine.card_name(card)}: {self.engine.card_description(card)}"
            for card in run.deck
        )
        return f"**Deck ({len(run.deck)} cards)**\n{cards or 'Deck is empty.'}"

    def render_discard(self, run: RunState) -> str:
        if run.combat is None:
            return "No combat is active."
        cards = "\n".join(
            f"- {self.engine.card_name(card)}" for card in run.combat.discard_pile
        )
        return f"**Discard ({len(run.combat.discard_pile)})**\n{cards or 'Discard pile is empty.'}"

    def render_draw_pile(self, run: RunState) -> str:
        if run.combat is None:
            return "No combat is active."
        if "frozen_eye" not in run.relics:
            return "You need Frozen Eye to inspect the draw pile in order."
        cards = "\n".join(
            f"- {self.engine.card_name(card)}"
            for card in reversed(run.combat.draw_pile)
        )
        return f"**Draw Pile ({len(run.combat.draw_pile)})**\n{cards or 'Draw pile is empty.'}"


async def setup(bot):
    await bot.add_cog(SlayTheSpire(bot))
