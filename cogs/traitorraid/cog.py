from __future__ import annotations

import asyncio
import math
import random
from collections import deque
from datetime import datetime

import discord
from discord.ext import commands

from utils import misc as rpgtools
from utils.checks import is_gm

from .engine import TraitorRaidEngine, estimated_round_damage
from .models import ActionChoice, ActionKind, PlayerState
from .presentation import hp_bar, hp_color
from .settings import (
    PRESETS,
    RaidSettings,
    normalize_setting_key,
    update_boss_name,
    update_setting,
)


RULES_TEXT = (
    "**Goal**\n"
    "Loyal raiders must defeat the boss or expose the Traitor. The Traitor wins "
    "if the boss survives the round limit, every loyal raider falls, or the "
    "Traitor reaches parity with one remaining loyal raider.\n\n"
    "**Every round**\n"
    "The boss marks its targets, then each living raider privately chooses an "
    "action. Choices resolve together. Missing choices automatically Guard.\n\n"
    "⚔️ **Assault** — full raid damage.\n"
    "🛡️ **Guard** — reduced damage, but heavily reduces the marked hit.\n"
    "🔎 **Investigate** — reduced damage and a private reading on one raider.\n"
    "✨ **Rally** — reduced damage and heals the most wounded living raider.\n\n"
    "The Traitor also has secret sabotage and a one-use Frame. Public corruption "
    "traces narrow the suspects; private readings are useful but not infallible. "
    "Votes occur every few rounds and the complete ballot is revealed afterward.\n\n"
    "**Pets are completely excluded.** Character raid damage, defence and HP are used; "
    "there are no separate pet turns or pet stats."
)


def _channel_key(source) -> tuple[int, int]:
    guild = getattr(source, "guild", None)
    channel = getattr(source, "channel", None)
    return (getattr(guild, "id", 0) or 0, getattr(channel, "id", 0) or 0)


class SettingsEditModal(discord.ui.Modal):
    def __init__(self, panel, title, definitions):
        super().__init__(title=title)
        self.panel = panel
        self.definitions = definitions
        current = panel.cog.get_settings(panel.key)
        for key, label in definitions:
            self.add_item(
                discord.ui.TextInput(
                    label=label,
                    default=str(getattr(current, key)),
                    required=True,
                    max_length=20,
                )
            )

    async def on_submit(self, interaction: discord.Interaction):
        settings = self.panel.cog.get_settings(self.panel.key)
        try:
            for (key, _label), child in zip(self.definitions, self.children):
                settings = update_setting(settings, key, child.value)
        except ValueError as error:
            return await interaction.response.send_message(str(error), ephemeral=True)

        self.panel.cog.settings_by_channel[self.panel.key] = settings
        await interaction.response.defer(ephemeral=True)
        await self.panel.refresh()
        await interaction.followup.send("Traitor Raid settings updated.", ephemeral=True)


class BossSettingsModal(discord.ui.Modal):
    def __init__(self, panel):
        super().__init__(title="Edit Boss")
        self.panel = panel
        current = panel.cog.get_settings(panel.key)
        self.name_input = discord.ui.TextInput(
            label="Boss name",
            default=current.boss_name,
            required=True,
            max_length=60,
        )
        self.hp_input = discord.ui.TextInput(label="Boss HP", default=str(current.boss_hp))
        self.attack_input = discord.ui.TextInput(label="Boss attack", default=str(current.boss_attack))
        self.defense_input = discord.ui.TextInput(label="Boss defence", default=str(current.boss_defense))
        self.targets_input = discord.ui.TextInput(
            label="Targets per round",
            default=str(current.boss_targets),
        )
        for item in (
            self.name_input,
            self.hp_input,
            self.attack_input,
            self.defense_input,
            self.targets_input,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        settings = self.panel.cog.get_settings(self.panel.key)
        try:
            settings = update_boss_name(settings, self.name_input.value)
            settings = update_setting(settings, "boss_hp", self.hp_input.value)
            settings = update_setting(settings, "boss_attack", self.attack_input.value)
            settings = update_setting(settings, "boss_defense", self.defense_input.value)
            settings = update_setting(settings, "boss_targets", self.targets_input.value)
        except ValueError as error:
            return await interaction.response.send_message(str(error), ephemeral=True)
        self.panel.cog.settings_by_channel[self.panel.key] = settings
        await interaction.response.defer(ephemeral=True)
        await self.panel.refresh()
        await interaction.followup.send("Boss settings updated.", ephemeral=True)


class TraitorSettingsView(discord.ui.View):
    def __init__(self, cog, author_id, key):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.key = key
        self.message = None
        for index, preset in enumerate(("balanced", "quick", "brutal", "chaos")):
            button = discord.ui.Button(
                label=preset.title(),
                style=discord.ButtonStyle.secondary,
                row=0,
            )

            async def callback(interaction, selected=preset):
                self.cog.settings_by_channel[self.key] = PRESETS[selected]
                await interaction.response.defer(ephemeral=True)
                await self.refresh()
                await interaction.followup.send(
                    f"Applied the **{selected.title()}** preset.",
                    ephemeral=True,
                )

            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the host who opened this setup panel can edit it.",
            ephemeral=True,
        )
        return False

    async def refresh(self):
        if self.message:
            await self.message.edit(
                embed=self.cog.settings_embed(self.cog.get_settings(self.key)),
                view=self,
            )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Edit Boss", emoji="👹", style=discord.ButtonStyle.primary, row=1)
    async def edit_boss(self, interaction, button):
        await interaction.response.send_modal(BossSettingsModal(self))

    @discord.ui.button(label="Lobby & Timers", emoji="⏱️", style=discord.ButtonStyle.primary, row=1)
    async def edit_lobby(self, interaction, button):
        await interaction.response.send_modal(
            SettingsEditModal(
                self,
                "Lobby and Timers",
                (
                    ("min_players", "Minimum players"),
                    ("max_players", "Maximum players"),
                    ("join_seconds", "Lobby seconds"),
                    ("action_seconds", "Action seconds"),
                    ("vote_seconds", "Vote seconds"),
                ),
            )
        )

    @discord.ui.button(label="Betrayal", emoji="🕯️", style=discord.ButtonStyle.danger, row=1)
    async def edit_betrayal(self, interaction, button):
        await interaction.response.send_modal(
            SettingsEditModal(
                self,
                "Betrayal and Death Effects",
                (
                    ("traitor_heal_pct", "Traitor heal contribution %"),
                    ("traitor_death_damage_pct", "Traitor fall: boss HP damage %"),
                    ("innocent_death_enrage_pct", "Innocent death: boss ATK gain %"),
                    ("wrong_exile_enrage_pct", "Wrong exile: boss ATK gain %"),
                    ("clue_suspects", "Names in public clue"),
                ),
            )
        )

    @discord.ui.button(label="Round Rules", emoji="📜", style=discord.ButtonStyle.primary, row=2)
    async def edit_rules(self, interaction, button):
        await interaction.response.send_modal(
            SettingsEditModal(
                self,
                "Round Rules",
                (
                    ("max_rounds", "Maximum rounds"),
                    ("vote_every", "Vote every N rounds"),
                    ("investigate_accuracy_pct", "Investigation accuracy %"),
                    ("guard_reduction_pct", "Guard damage reduction %"),
                    ("rally_heal_pct", "Rally heal % max HP"),
                ),
            )
        )

    @discord.ui.button(label="Reset", emoji="↩️", style=discord.ButtonStyle.danger, row=2)
    async def reset(self, interaction, button):
        self.cog.settings_by_channel[self.key] = RaidSettings()
        await interaction.response.defer(ephemeral=True)
        await self.refresh()
        await interaction.followup.send("Settings reset to Balanced defaults.", ephemeral=True)

    @discord.ui.button(label="Done", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def done(self, interaction, button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=self.cog.settings_embed(self.cog.get_settings(self.key)),
            view=self,
        )
        self.stop()


class TraitorLobbyView(discord.ui.View):
    def __init__(self, cog, ctx, settings):
        super().__init__(timeout=settings.join_seconds)
        self.cog = cog
        self.ctx = ctx
        self.settings = settings
        self.host_id = ctx.author.id
        self.joined = []
        self.message = None
        self.closed = False
        self.started_early = False
        self.lock = asyncio.Lock()

    async def refresh(self):
        if self.message:
            try:
                await self.message.edit(embed=self.cog.lobby_embed(self), view=self)
            except discord.HTTPException:
                pass

    async def close(self):
        self.closed = True
        for child in self.children:
            child.disabled = True
        await self.refresh()

    @discord.ui.button(label="Join", emoji="⚔️", style=discord.ButtonStyle.success)
    async def join(self, interaction, button):
        async with self.lock:
            if self.closed:
                return await interaction.response.send_message("This lobby is closed.", ephemeral=True)
            if any(member.id == interaction.user.id for member in self.joined):
                return await interaction.response.send_message("You already joined.", ephemeral=True)
            if len(self.joined) >= self.settings.max_players:
                return await interaction.response.send_message("This raid is full.", ephemeral=True)
            async with self.cog.bot.pool.acquire() as conn:
                exists = await conn.fetchval(
                    'SELECT 1 FROM profile WHERE "user" = $1',
                    interaction.user.id,
                )
            if not exists:
                return await interaction.response.send_message(
                    "You need a character to join.", ephemeral=True
                )
            self.joined.append(interaction.user)
        await interaction.response.send_message(
            "You joined. Your role will be available privately when the raid begins.",
            ephemeral=True,
        )
        await self.refresh()

    @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction, button):
        async with self.lock:
            before = len(self.joined)
            self.joined = [member for member in self.joined if member.id != interaction.user.id]
            if len(self.joined) == before:
                return await interaction.response.send_message("You are not in this lobby.", ephemeral=True)
        await interaction.response.send_message("You left the Traitor Raid.", ephemeral=True)
        await self.refresh()

    @discord.ui.button(label="How to Play", emoji="📖", style=discord.ButtonStyle.primary)
    async def rules(self, interaction, button):
        await interaction.response.send_message(RULES_TEXT, ephemeral=True)

    @discord.ui.button(label="Start Now", emoji="▶️", style=discord.ButtonStyle.danger)
    async def start_now(self, interaction, button):
        if interaction.user.id != self.host_id:
            return await interaction.response.send_message("Only the host can start early.", ephemeral=True)
        if len(self.joined) < self.settings.min_players:
            needed = self.settings.min_players - len(self.joined)
            return await interaction.response.send_message(
                f"The raid needs {needed} more player(s).", ephemeral=True
            )
        self.started_early = True
        self.closed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=self.cog.lobby_embed(self), view=self)
        self.stop()

    @discord.ui.button(label="Cancel", emoji="✖️", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction, button):
        if interaction.user.id != self.host_id:
            return await interaction.response.send_message(
                "Only the host can cancel this lobby.", ephemeral=True
            )
        self.cog.cancelled_channels.add(_channel_key(self.ctx))
        self.closed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=self.cog.lobby_embed(self), view=self)
        self.stop()


class TargetSelect(discord.ui.Select):
    def __init__(self, private_view, kind):
        self.private_view = private_view
        self.kind = kind
        engine = private_view.hub.engine
        actor_id = private_view.user_id
        candidates = [
            player
            for player in engine.living_players()
            if player.user_id != actor_id
            and not (kind == ActionKind.FRAME and player.user_id == engine.traitor_id)
        ]
        options = [
            discord.SelectOption(label=player.name[:100], value=str(player.user_id))
            for player in candidates
        ]
        super().__init__(
            placeholder="Choose a living raider…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        try:
            await self.private_view.hub.lock_action(
                interaction,
                self.private_view.user_id,
                ActionChoice(self.kind, target_id),
            )
        except ValueError as error:
            return await interaction.response.send_message(str(error), ephemeral=True)
        target = self.private_view.hub.engine.players[target_id]
        if self.kind == ActionKind.INVESTIGATE:
            text = f"🔎 **Investigate locked:** {target.name}. Your private reading arrives after resolution."
            self.private_view.hub.investigation_interactions[self.private_view.user_id] = interaction
        else:
            text = f"🕸️ **Frame locked:** the evidence will point toward {target.name}."
        await interaction.response.edit_message(content=text, view=None)
        await self.private_view.hub.refresh_dashboard()


class TargetSelectView(discord.ui.View):
    def __init__(self, private_view, kind):
        super().__init__(timeout=private_view.timeout)
        self.add_item(TargetSelect(private_view, kind))


class PrivateActionView(discord.ui.View):
    def __init__(self, hub, user_id):
        super().__init__(timeout=hub.settings.action_seconds)
        self.hub = hub
        self.user_id = user_id
        definitions = (
            ("Assault", "⚔️", discord.ButtonStyle.danger, ActionKind.ASSAULT, 0),
            ("Guard", "🛡️", discord.ButtonStyle.primary, ActionKind.GUARD, 0),
            ("Investigate", "🔎", discord.ButtonStyle.secondary, ActionKind.INVESTIGATE, 0),
            ("Rally", "✨", discord.ButtonStyle.success, ActionKind.RALLY, 0),
        )
        if user_id == hub.engine.traitor_id:
            definitions += (
                ("Sabotage", "🕯️", discord.ButtonStyle.danger, ActionKind.SABOTAGE, 1),
            )
            if not hub.engine.frame_used:
                definitions += (
                    ("Frame", "🕸️", discord.ButtonStyle.secondary, ActionKind.FRAME, 1),
                )
        for label, emoji, style, kind, row in definitions:
            button = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)

            async def callback(interaction, selected=kind):
                if selected in {ActionKind.INVESTIGATE, ActionKind.FRAME}:
                    return await interaction.response.edit_message(
                        content=(
                            "Choose whom to investigate."
                            if selected == ActionKind.INVESTIGATE
                            else "Choose an innocent to frame. Frame can be used once per game."
                        ),
                        view=TargetSelectView(self, selected),
                    )
                try:
                    await self.hub.lock_action(
                        interaction,
                        self.user_id,
                        ActionChoice(selected),
                    )
                except ValueError as error:
                    return await interaction.response.send_message(str(error), ephemeral=True)
                descriptions = {
                    ActionKind.ASSAULT: "⚔️ Assault locked. You will deal your full effective raid damage.",
                    ActionKind.GUARD: "🛡️ Guard locked. You trade damage for heavy protection if marked.",
                    ActionKind.RALLY: "✨ Rally locked. You will heal the most wounded living raider.",
                    ActionKind.SABOTAGE: "🕯️ Sabotage locked. Your contribution will secretly restore the boss.",
                }
                await interaction.response.edit_message(content=descriptions[selected], view=None)
                await self.hub.refresh_dashboard()

            button.callback = callback
            self.add_item(button)


class ActionHubView(discord.ui.View):
    def __init__(self, cog, engine, members, logs, evidence):
        super().__init__(timeout=engine.settings.action_seconds)
        self.cog = cog
        self.engine = engine
        self.members = members
        self.settings = engine.settings
        self.logs = logs
        self.evidence = evidence
        self.message = None
        self.closed = False
        self.lock = asyncio.Lock()
        self.all_locked = asyncio.Event()
        self.investigation_interactions = {}

    async def lock_action(self, interaction, user_id, choice):
        async with self.lock:
            if self.closed or self.engine.round_no <= 0:
                raise ValueError("This action window has closed.")
            self.engine.submit_action(user_id, choice)
            if len(self.engine.actions) >= len(self.engine.living_players()):
                self.all_locked.set()

    async def refresh_dashboard(self):
        if not self.message or self.closed:
            return
        try:
            await self.message.edit(
                embed=self.cog.battle_embed(
                    self.engine,
                    self.members,
                    self.logs,
                    self.evidence,
                    phase="ACTION PHASE",
                    locked=len(self.engine.actions),
                ),
                view=self,
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Choose Action", emoji="🎯", style=discord.ButtonStyle.danger)
    async def choose_action(self, interaction, button):
        player = self.engine.players.get(interaction.user.id)
        if not player or not player.alive:
            return await interaction.response.send_message(
                "Only living raiders in this game may act.", ephemeral=True
            )
        if interaction.user.id in self.engine.actions:
            choice = self.engine.actions[interaction.user.id]
            return await interaction.response.send_message(
                f"Your **{choice.kind.value.title()}** action is already locked.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            self.cog.private_action_text(self.engine, interaction.user.id),
            view=PrivateActionView(self, interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="My Role", emoji="🎭", style=discord.ButtonStyle.primary)
    async def my_role(self, interaction, button):
        if interaction.user.id not in self.engine.players:
            return await interaction.response.send_message("You are not in this raid.", ephemeral=True)
        await interaction.response.send_message(
            self.cog.role_text(self.engine, interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="How to Play", emoji="📖", style=discord.ButtonStyle.secondary)
    async def how_to_play(self, interaction, button):
        await interaction.response.send_message(RULES_TEXT, ephemeral=True)


class VoteSelect(discord.ui.Select):
    def __init__(self, vote_view):
        self.vote_view = vote_view
        options = [discord.SelectOption(label="Abstain", value="abstain", emoji="🤐")]
        options.extend(
            discord.SelectOption(label=player.name[:100], value=str(player.user_id), emoji="⚖️")
            for player in vote_view.engine.living_players()
        )
        super().__init__(
            placeholder="Accuse a raider or abstain…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.vote_view.record_vote(interaction, self.values[0])


class TraitorVoteView(discord.ui.View):
    def __init__(self, engine, members):
        super().__init__(timeout=engine.settings.vote_seconds)
        self.engine = engine
        self.members = members
        self.voter_ids = {player.user_id for player in engine.living_players()}
        self.ballots = {}
        self.lock = asyncio.Lock()
        self.all_voted = asyncio.Event()
        self.message = None
        self.closed = False
        self.add_item(VoteSelect(self))

    async def record_vote(self, interaction, raw_target):
        if interaction.user.id not in self.voter_ids:
            return await interaction.response.send_message(
                "Only living raiders may vote.", ephemeral=True
            )
        target = None if raw_target == "abstain" else int(raw_target)
        async with self.lock:
            if self.closed:
                return await interaction.response.send_message("Voting has closed.", ephemeral=True)
            self.ballots[interaction.user.id] = target
            if len(self.ballots) >= len(self.voter_ids):
                self.all_voted.set()
        target_text = "Abstain" if target is None else self.engine.players[target].name
        await interaction.response.send_message(
            f"Vote recorded: **{target_text}**. You may change it until voting closes.",
            ephemeral=True,
        )
        if self.message:
            try:
                await self.message.edit(embed=self.build_embed(), view=self)
            except discord.HTTPException:
                pass

    def build_embed(self):
        return discord.Embed(
            title=f"⚖️ Tribunal — Round {self.engine.round_no}",
            description=(
                "Discuss the evidence, then accuse one living raider or abstain. "
                "Targets stay hidden until the tribunal closes.\n\n"
                f"**Votes cast:** {len(self.ballots)}/{len(self.voter_ids)}\n"
                "A valid exile needs a unique plurality, at least two votes, and more support than Abstain."
            ),
            color=0xF1C40F,
        )


class TraitorRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_by_channel: dict[tuple[int, int], RaidSettings] = {}
        self.active_channels: set[tuple[int, int]] = set()
        self.cancelled_channels: set[tuple[int, int]] = set()
        self.active_views: dict[tuple[int, int], discord.ui.View] = {}

    def get_settings(self, key) -> RaidSettings:
        return self.settings_by_channel.get(key, RaidSettings())

    def settings_embed(self, settings):
        embed = discord.Embed(
            title="🕯️ Traitor Raid — Host Setup",
            description=(
                "Configure the game, then run `$spawntraitor`. Settings are isolated "
                "to this channel and freeze when the lobby opens.\n"
                "Use the buttons below or `$traitorsettings set <key> <value>`."
            ),
            color=0x7D3C98,
        )
        embed.add_field(
            name="👹 Boss",
            value=(
                f"**{settings.boss_name}**\n"
                f"HP `{settings.boss_hp:,}` • ATK `{settings.boss_attack:,}` • DEF `{settings.boss_defense:,}`\n"
                f"Targets `{settings.boss_targets}` per round"
            ),
            inline=False,
        )
        embed.add_field(
            name="🕯️ Betrayal",
            value=(
                f"Sabotage heals `{settings.traitor_heal_pct:g}%` of effective attack\n"
                f"Traitor falls: boss loses `{settings.traitor_death_damage_pct:g}%` max HP\n"
                f"Innocent combat death: boss ATK `+{settings.innocent_death_enrage_pct:g}%`\n"
                f"Wrong exile: boss ATK `+{settings.wrong_exile_enrage_pct:g}%`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⏱️ Flow",
            value=(
                f"Players `{settings.min_players}-{settings.max_players}` • Rounds `{settings.max_rounds}` • "
                f"Vote every `{settings.vote_every}`\n"
                f"Lobby `{settings.join_seconds}s` • Actions `{settings.action_seconds}s` • Votes `{settings.vote_seconds}s`\n"
                f"Clue size `{settings.clue_suspects}` • Investigation `{settings.investigate_accuracy_pct:g}%` accurate"
            ),
            inline=False,
        )
        embed.set_footer(text="Pets are excluded. Normal character raid stats are used.")
        return embed

    def lobby_embed(self, view):
        settings = view.settings
        roster = "\n".join(
            f"`{index:02}.` {member.mention}"
            for index, member in enumerate(view.joined, start=1)
        ) or "No raiders have joined yet."
        ready = len(view.joined) >= settings.min_players
        if view.closed:
            status = "**Lobby locked. Preparing roles…**" if ready else "**Lobby closed.**"
        elif ready:
            status = "✅ **Minimum party ready. The host may start now.**"
        else:
            status = f"Waiting for **{settings.min_players - len(view.joined)}** more raider(s)."
        embed = discord.Embed(
            title=f"🕯️ {settings.boss_name} Calls for Blood",
            description=(
                "One raider will secretly betray the party. Choose actions, study clues, "
                "survive the boss and expose the Traitor before time runs out.\n\n"
                f"{status}"
            ),
            color=0x7D3C98,
        )
        embed.add_field(
            name=f"Raiders ({len(view.joined)}/{settings.max_players})",
            value=roster[:1024],
            inline=False,
        )
        embed.add_field(
            name="Configured Threat",
            value=(
                f"❤️ `{settings.boss_hp:,}` HP  •  ⚔️ `{settings.boss_attack:,}` ATK  •  "
                f"🛡️ `{settings.boss_defense:,}` DEF\n"
                f"Rounds `{settings.max_rounds}` • Vote every `{settings.vote_every}` • "
                f"Sabotage `{settings.traitor_heal_pct:g}%`"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Hosted by {view.ctx.author} • Pets excluded • Settings locked for this lobby")
        return embed

    def role_text(self, engine, user_id):
        if user_id == engine.traitor_id:
            return (
                "## 🕯️ YOU ARE THE TRAITOR\n"
                "Keep the boss alive until the round limit or reduce the loyal party to parity. "
                "You may use normal actions to blend in. **Sabotage** heals the boss instead "
                "of damaging it and creates a real corruption trail. **Frame** is usable once: "
                "it performs a weaker sabotage and points the public trail toward an innocent.\n\n"
                "Your action is private. Lie, accuse and vote like everyone else."
            )
        return (
            "## 🛡️ YOU ARE LOYAL\n"
            "Defeat the boss and expose the Traitor before the party reaches parity. Public "
            "corruption trails always contain the source—or an innocent deliberately Framed "
            "by the Traitor. Investigations are private and usually accurate, so share carefully: "
            "any player can lie in chat."
        )

    def private_action_text(self, engine, user_id):
        settings = engine.settings
        text = (
            f"## Round {engine.round_no}: choose one action\n"
            "Your first choice locks for this round.\n\n"
            "⚔️ **Assault:** 100% effective raid damage.\n"
            f"🛡️ **Guard:** {settings.guard_damage_pct:g}% damage; if marked, reduce the boss hit by "
            f"{settings.guard_reduction_pct:g}%.\n"
            f"🔎 **Investigate:** {settings.investigate_damage_pct:g}% damage and privately read one raider.\n"
            f"✨ **Rally:** {settings.rally_damage_pct:g}% damage and heal the weakest raider for "
            f"{settings.rally_heal_pct:g}% max HP."
        )
        if user_id == engine.traitor_id:
            text += (
                f"\n\n🕯️ **Sabotage:** secretly heal the boss for {settings.traitor_heal_pct:g}% of your "
                "effective attack.\n🕸️ **Frame:** one-use half-strength sabotage that plants the public trail on an innocent."
            )
        return text

    def _raider_lines(self, engine, members):
        lines = []
        for player in engine.players.values():
            member = members[player.user_id]
            if player.exiled:
                icon, status = "⚖️", "EXILED"
            elif player.hp <= 0:
                icon, status = "💀", "FALLEN"
            elif player.hp_ratio <= 0.25:
                icon, status = "🔴", f"{player.hp:,.0f} HP"
            elif player.hp_ratio <= 0.60:
                icon, status = "🟡", f"{player.hp:,.0f} HP"
            else:
                icon, status = "🟢", f"{player.hp:,.0f} HP"
            marked = " 🎯" if player.user_id in engine.telegraphed_target_ids and player.alive else ""
            lines.append(f"{icon} {member.display_name[:24]} — **{status}**{marked}")
        return lines

    def battle_embed(self, engine, members, logs, evidence, *, phase, locked=None):
        boss = engine.boss
        pct = 0 if boss.max_hp <= 0 else max(0, min(100, boss.hp / boss.max_hp * 100))
        embed = discord.Embed(
            title=f"🕯️ TRAITOR RAID • ROUND {engine.round_no}/{engine.settings.max_rounds}",
            description=(
                f"### {boss.name}\n"
                f"`{hp_bar(boss.hp, boss.max_hp, 20)}` **{pct:.1f}%**\n"
                f"❤️ **{boss.hp:,.0f}/{boss.max_hp:,.0f} HP**  •  "
                f"⚔️ **{boss.damage:,.0f} ATK**  •  🛡️ **{boss.armor:,.0f} DEF**"
            ),
            color=0x3498DB if phase == "ACTION PHASE" else hp_color(boss.hp, boss.max_hp),
        )
        marked = [
            members[user_id].display_name
            for user_id in engine.telegraphed_target_ids
            if user_id in members and engine.players[user_id].alive
        ]
        phase_text = f"**{phase}**"
        if locked is not None:
            phase_text += f"\nActions locked: **{locked}/{len(engine.living_players())}**"
        if marked:
            phase_text += "\n🎯 Boss targets: **" + "**, **".join(marked) + "**"
        embed.add_field(name="Battlefield", value=phase_text, inline=False)

        raiders = self._raider_lines(engine, members)
        midpoint = math.ceil(len(raiders) / 2)
        embed.add_field(name="Raiders", value="\n".join(raiders[:midpoint]) or "None", inline=True)
        if len(raiders) > midpoint:
            embed.add_field(name="Raiders continued", value="\n".join(raiders[midpoint:]), inline=True)
        embed.add_field(
            name="Evidence",
            value=evidence or "No reliable corruption trail has formed yet.",
            inline=False,
        )
        embed.add_field(
            name="Recent Events",
            value="\n".join(f"• {line}" for line in list(logs)[-6:]) or "• The raid has begun.",
            inline=False,
        )
        if engine.traitor_revealed:
            embed.set_footer(text=f"THE TRAITOR WAS {members[engine.traitor_id].display_name.upper()} • Deduction phases disabled")
        else:
            next_vote = engine.settings.vote_every - (engine.round_no % engine.settings.vote_every)
            if next_vote == engine.settings.vote_every:
                next_vote = 0
            embed.set_footer(text=f"Next tribunal: {'this round' if next_vote == 0 else f'in {next_vote} round(s)'} • Pets excluded")
        return embed

    async def _member_stats(self, member, conn):
        profile = await conn.fetchrow(
            'SELECT health, stathp, xp FROM profile WHERE "user" = $1',
            member.id,
        )
        if not profile:
            return None
        damage, armor = await self.bot.get_raidstats(member, conn=conn)
        level = rpgtools.xptolevel(profile["xp"])
        hp = profile["health"] + 250 + level * 15 + profile["stathp"] * 50
        return PlayerState(
            user_id=member.id,
            name=member.display_name,
            hp=float(hp),
            max_hp=float(hp),
            damage=float(damage),
            armor=float(armor),
        )

    async def send_private_readings(self, result, hub, members, engine):
        for reading in result.investigations:
            target = engine.players[reading.target_id]
            verdict = "CORRUPTED" if reading.appears_corrupt else "LOYAL"
            emoji = "🕯️" if reading.appears_corrupt else "🛡️"
            text = (
                f"{emoji} **Private reading:** {target.name} appears **{verdict}**. "
                f"Readings are {engine.settings.investigate_accuracy_pct:g}% reliable; "
                "a Frame can also create false suspicion. You decide what to tell the channel."
            )
            interaction = hub.investigation_interactions.get(reading.investigator_id)
            delivered = False
            if interaction:
                try:
                    await interaction.followup.send(text, ephemeral=True)
                    delivered = True
                except (discord.HTTPException, discord.NotFound):
                    pass
            if not delivered:
                try:
                    await members[reading.investigator_id].send(text)
                except discord.HTTPException:
                    pass

    def _vote_ledger(self, result, members):
        lines = []
        for voter_id, target_id in result.ballots.items():
            target = "Abstain" if target_id is None else members[target_id].display_name
            lines.append(f"{members[voter_id].display_name} → **{target}**")
        return "\n".join(lines) or "No valid ballots were cast."

    async def run_vote(self, ctx, engine, members, key=None):
        vote_view = TraitorVoteView(engine, members)
        if key is not None:
            self.active_views[key] = vote_view
        message = await ctx.send(embed=vote_view.build_embed(), view=vote_view)
        vote_view.message = message
        try:
            await asyncio.wait_for(
                vote_view.all_voted.wait(),
                timeout=engine.settings.vote_seconds,
            )
        except asyncio.TimeoutError:
            pass
        vote_view.closed = True
        vote_view.stop()
        for child in vote_view.children:
            child.disabled = True
        result = engine.resolve_vote(vote_view.ballots)
        result_embed = discord.Embed(
            title=f"⚖️ Tribunal Result — Round {engine.round_no}",
            description=self._vote_ledger(result, members),
            color=0xF1C40F,
        )
        result_embed.add_field(name="Decision", value=result.reason, inline=False)
        await message.edit(embed=result_embed, view=vote_view)
        return result

    def result_embed(self, engine, members, duration):
        innocent_win = engine.outcome and engine.outcome.winner == "innocents"
        reasons = {
            "boss_defeated": "The boss was destroyed before the betrayal could succeed.",
            "all_innocents_fallen": "No loyal raiders remained standing.",
            "traitor_reached_parity": "The Traitor reached parity and seized control of the tribunal.",
            "round_limit": "Time expired while the boss still lived.",
        }
        boss = engine.boss
        embed = discord.Embed(
            title="🛡️ LOYAL RAIDERS WIN" if innocent_win else "🕯️ THE TRAITOR WINS",
            description=(
                f"{reasons.get(engine.outcome.reason, engine.outcome.reason)}\n\n"
                f"**The Traitor was {members[engine.traitor_id].mention}.**"
            ),
            color=0x2ECC71 if innocent_win else 0xC0392B,
        )
        pct = 0 if boss.max_hp <= 0 else max(0, boss.hp / boss.max_hp * 100)
        embed.add_field(
            name=boss.name,
            value=(
                f"`{hp_bar(boss.hp, boss.max_hp, 20)}` {pct:.1f}%\n"
                f"**{boss.hp:,.0f}/{boss.max_hp:,.0f} HP**"
            ),
            inline=False,
        )
        standing = [members[player.user_id].mention for player in engine.living_innocents()]
        embed.add_field(name="Loyal survivors", value=" ".join(standing) or "None", inline=False)
        embed.set_footer(text=f"{engine.round_no} round(s) • {duration}s • Pets excluded")
        return embed

    @commands.group(name="traitorsettings", aliases=["trsettings"], invoke_without_command=True)
    @is_gm()
    async def traitorsettings(self, ctx):
        """Configure the next Traitor Raid in this channel."""
        key = _channel_key(ctx)
        if key in self.active_channels:
            return await ctx.send("Settings are frozen while a Traitor Raid is active here.")
        view = TraitorSettingsView(self, ctx.author.id, key)
        message = await ctx.send(embed=self.settings_embed(self.get_settings(key)), view=view)
        view.message = message

    @traitorsettings.command(name="set")
    @is_gm()
    async def traitorsettings_set(self, ctx, key: str, value: str):
        channel_key = _channel_key(ctx)
        if channel_key in self.active_channels:
            return await ctx.send("Settings are frozen while a Traitor Raid is active here.")
        try:
            updated = update_setting(self.get_settings(channel_key), key, value)
        except ValueError as error:
            return await ctx.send(str(error))
        self.settings_by_channel[channel_key] = updated
        normalized = normalize_setting_key(key)
        await ctx.send(f"✅ `{normalized}` is now `{getattr(updated, normalized)}`.")

    @traitorsettings.command(name="name")
    @is_gm()
    async def traitorsettings_name(self, ctx, *, name: str):
        channel_key = _channel_key(ctx)
        if channel_key in self.active_channels:
            return await ctx.send("Settings are frozen while a Traitor Raid is active here.")
        try:
            updated = update_boss_name(self.get_settings(channel_key), name)
        except ValueError as error:
            return await ctx.send(str(error))
        self.settings_by_channel[channel_key] = updated
        await ctx.send(f"✅ The boss is now called **{updated.boss_name}**.")

    @traitorsettings.command(name="preset")
    @is_gm()
    async def traitorsettings_preset(self, ctx, preset: str):
        channel_key = _channel_key(ctx)
        if channel_key in self.active_channels:
            return await ctx.send("Settings are frozen while a Traitor Raid is active here.")
        preset = preset.lower()
        if preset not in PRESETS:
            return await ctx.send("Choose: `balanced`, `quick`, `brutal`, or `chaos`.")
        self.settings_by_channel[channel_key] = PRESETS[preset]
        await ctx.send(f"✅ Applied the **{preset.title()}** Traitor Raid preset.")

    @traitorsettings.command(name="reset")
    @is_gm()
    async def traitorsettings_reset(self, ctx):
        channel_key = _channel_key(ctx)
        if channel_key in self.active_channels:
            return await ctx.send("Settings are frozen while a Traitor Raid is active here.")
        self.settings_by_channel[channel_key] = RaidSettings()
        await ctx.send("✅ Traitor Raid settings reset to Balanced defaults.")

    @commands.command(name="traitorrules")
    async def traitorrules(self, ctx):
        await ctx.send(RULES_TEXT)

    @commands.command(name="stoptraitor", aliases=["canceltraitor"])
    @is_gm()
    async def stoptraitor(self, ctx):
        key = _channel_key(ctx)
        if key not in self.active_channels:
            return await ctx.send("There is no active Traitor Raid in this channel.")
        self.cancelled_channels.add(key)
        view = self.active_views.get(key)
        if view:
            if hasattr(view, "all_locked"):
                view.all_locked.set()
            if hasattr(view, "all_voted"):
                view.all_voted.set()
            view.stop()
        await ctx.send("🛑 The host has cancelled the Traitor Raid.")

    @commands.command(name="spawntraitor")
    @is_gm()
    async def spawntraitor(self, ctx, hp: int | None = None):
        """Open and run a complete social-deduction boss raid."""
        key = _channel_key(ctx)
        if key in self.active_channels:
            return await ctx.send("A Traitor Raid is already active in this channel.")

        settings = self.get_settings(key)
        if hp is not None:
            try:
                settings = update_setting(settings, "boss_hp", str(hp))
            except ValueError as error:
                return await ctx.send(str(error))

        self.active_channels.add(key)
        self.cancelled_channels.discard(key)
        engine = None
        members = {}
        try:
            lobby = TraitorLobbyView(self, ctx, settings)
            message = await ctx.send(embed=self.lobby_embed(lobby), view=lobby)
            lobby.message = message
            self.active_views[key] = lobby
            await lobby.wait()
            await lobby.close()

            if key in self.cancelled_channels:
                return
            if len(lobby.joined) < settings.min_players:
                return await ctx.send(
                    f"The raid disperses: only **{len(lobby.joined)}**/{settings.min_players} required players joined."
                )

            participants = []
            seen = set()
            async with self.bot.pool.acquire() as conn:
                for member in lobby.joined[: settings.max_players]:
                    if member.id in seen:
                        continue
                    seen.add(member.id)
                    state = await self._member_stats(member, conn)
                    if state:
                        participants.append(state)
                        members[member.id] = member
            if len(participants) < settings.min_players:
                return await ctx.send("Too many profiles became invalid; the raid could not begin.")

            traitor_id = random.choice(participants).user_id
            engine = TraitorRaidEngine(settings, participants, traitor_id)
            for user_id, member in members.items():
                try:
                    await member.send(self.role_text(engine, user_id))
                except discord.HTTPException:
                    pass

            estimate = estimated_round_damage(participants, settings.boss_defense)
            expected_rounds = math.ceil(settings.boss_hp / max(1, estimate))
            await ctx.send(
                embed=discord.Embed(
                    title="🎭 Roles Sealed — The Raid Begins",
                    description=(
                        "Use **My Role** on the battle board if your DMs are closed. "
                        "Nobody else can see your role or action panel.\n\n"
                        f"A full coordinated assault is estimated to need about **{expected_rounds} round(s)**. "
                        "Sabotage, recovery and deaths will change that."
                    ),
                    color=0x7D3C98,
                )
            )

            logs = deque(maxlen=8)
            evidence = "No corruption has been detected."
            started = datetime.utcnow()
            battle_message = await ctx.send(
                embed=self.battle_embed(
                    engine,
                    members,
                    logs,
                    evidence,
                    phase="PREPARING",
                )
            )

            while not engine.outcome and key not in self.cancelled_channels:
                engine.begin_round()
                targets = [members[user_id].display_name for user_id in engine.telegraphed_target_ids]
                logs.append("🎯 The boss marks " + ", ".join(targets) + " for its next attack.")

                hub = ActionHubView(self, engine, members, logs, evidence)
                hub.message = battle_message
                self.active_views[key] = hub
                await battle_message.edit(
                    embed=self.battle_embed(
                        engine,
                        members,
                        logs,
                        evidence,
                        phase="ACTION PHASE",
                        locked=0,
                    ),
                    view=hub,
                )
                try:
                    await asyncio.wait_for(
                        hub.all_locked.wait(),
                        timeout=settings.action_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
                hub.closed = True
                hub.stop()
                for child in hub.children:
                    child.disabled = True
                if key in self.cancelled_channels:
                    break

                before_hp = engine.boss.hp
                round_result = engine.resolve_player_phase()
                net = before_hp - engine.boss.hp
                counts = " • ".join(
                    f"{name} `{count}`" for name, count in sorted(round_result.action_counts.items())
                )
                logs.append(f"⚔️ Net pressure removes **{max(0, net):,.0f} HP**. {counts}")
                if round_result.boss_healing > 0:
                    logs.append("🕯️ Hidden corruption restores some of the boss's strength.")
                if round_result.rally_healing > 0:
                    logs.append(f"✨ Rally restores **{round_result.rally_healing:,.0f} HP** across the party.")
                if round_result.defaulted_ids:
                    logs.append(f"🛡️ {len(round_result.defaulted_ids)} silent raider(s) automatically Guard.")
                if round_result.evidence_ids:
                    names = [members[user_id].display_name for user_id in round_result.evidence_ids]
                    if round_result.evidence_kind == "tampered":
                        evidence = "🕸️ A **tampered trace** points toward: **" + " • ".join(names) + "**"
                    else:
                        evidence = "🔮 Corruption passed through one of: **" + " • ".join(names) + "**"
                else:
                    evidence = "✨ No corrupt action left a public trace this round."
                await self.send_private_readings(round_result, hub, members, engine)

                engine.determine_outcome()
                if not engine.outcome:
                    boss_result = engine.resolve_boss_phase()
                    for attack in boss_result.attacks:
                        target = members[attack.target_id]
                        guard_note = " after Guard" if attack.guarded else ""
                        death_note = " — **FALLEN**" if attack.killed else ""
                        logs.append(
                            f"👹 {target.display_name} takes **{attack.damage:,.0f}**{guard_note}{death_note}."
                        )
                    if boss_result.innocent_deaths:
                        logs.append(
                            f"🔥 {len(boss_result.innocent_deaths)} loyal death(s) enrage the boss to "
                            f"**{engine.boss.damage:,.0f} ATK**."
                        )
                    if boss_result.traitor_fell:
                        logs.append(
                            f"🕯️ **THE TRAITOR FALLS!** The broken pact tears "
                            f"**{boss_result.traitor_burst_damage:,.0f} HP** from the boss."
                        )
                        evidence = f"☠️ The Traitor was **{members[engine.traitor_id].display_name}**."
                    engine.determine_outcome()

                if not engine.outcome and engine.should_vote():
                    await battle_message.edit(
                        embed=self.battle_embed(
                            engine,
                            members,
                            logs,
                            evidence,
                            phase="TRIBUNAL",
                        ),
                        view=None,
                    )
                    vote_result = await self.run_vote(ctx, engine, members, key)
                    if vote_result.exile_id is not None:
                        correct, burst = engine.apply_exile(vote_result.exile_id)
                        exiled = members[vote_result.exile_id]
                        if correct:
                            logs.append(
                                f"⚖️ **{exiled.display_name} WAS THE TRAITOR!** The pact ruptures for "
                                f"**{burst:,.0f} boss damage**."
                            )
                            evidence = f"☠️ The Traitor was **{exiled.display_name}**."
                        else:
                            logs.append(
                                f"⚖️ **{exiled.display_name} was loyal.** The wrong exile enrages the boss."
                            )
                    else:
                        logs.append("⚖️ The tribunal ended without an exile.")
                    engine.determine_outcome()

                engine.determine_outcome(round_complete=True)
                await battle_message.edit(
                    embed=self.battle_embed(
                        engine,
                        members,
                        logs,
                        evidence,
                        phase="ROUND RESOLVED",
                    ),
                    view=None,
                )
                if not engine.outcome:
                    await asyncio.sleep(2)

            if key in self.cancelled_channels or not engine or not engine.outcome:
                if battle_message:
                    await battle_message.edit(view=None)
                return

            duration = (datetime.utcnow() - started).seconds
            await battle_message.edit(
                embed=self.result_embed(engine, members, duration),
                view=None,
            )
            await ctx.send(
                "🎁 **Rewards are host-managed.** This game does not automatically "
                "award money, crates, Legacy Points, feats, or win progress."
            )
        finally:
            self.active_channels.discard(key)
            self.cancelled_channels.discard(key)
            self.active_views.pop(key, None)
