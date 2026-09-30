"""GM Possession: a Game Master secretly drives a raid boss in real time.

The GM receives each turn's options in DMs, voiced by the vessel's underling,
and anything they type there is spoken aloud by the vessel. Raiders guard and
mend each other, spend one class signature per fight, and keep acting as
spirits after they fall. When the fight ends, the raiders vote on which Game
Master it was before the identity is revealed; correct guesses earn a crate
the Possessor picks.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands
from discord.http import handle_message_parameters

from classes.classes import from_string as class_from_string
from utils import misc as rpgtools
from utils.checks import is_gm

from . import ui
from .engine import (
    ABILITIES,
    DREAD_MAX,
    MAX_RAIDERS,
    MAX_ROUNDS,
    MIN_RAIDERS,
    PLAYER_ACTIONS,
    SIGNATURES,
    SPIRIT_ACTIONS,
    Encounter,
    Raider,
    signature_for,
    split_gold,
)
from .lore import (
    ABILITY_RULES,
    DOMINATE_OUTCOMES,
    PLAYER_ACTION_FLAVOR,
    SIGNATURE_LORE,
    SPIRIT_FLAVOR,
    VESSELS,
    line,
    render,
)

JOIN_SECONDS = 300
ROUND_SECONDS = 45
RESULT_PAUSE_SECONDS = 5
RELAY_COOLDOWN_SECONDS = 2.0
RELAY_MAX_CHARS = 400
GUESS_SECONDS = 60
GUESS_PICK_SECONDS = 120
GUESS_FALLBACK_CRATE = "rare"
CRATE_TYPES = ("common", "uncommon", "rare", "magic", "legendary", "mystery", "fortune", "divine")
DEFAULT_PING_ROLE_ID = 1404803970572226760
RAIDER_EMOJI_BUDGET = 2600  # Above this many characters, raider bars fall back to text.
PROMPT_EMOJI_BUDGET = 1800  # The Possessor's prompt also carries the powers list.
NO_MENTIONS = discord.AllowedMentions.none()

HOW_IT_WORKS = (
    "🏆 **Win:** destroy the vessel, or complete the 🕯️ **Severance**.\n"
    f"☠️ **Lose:** everyone falls, or {MAX_ROUNDS} turns pass.\n"
    "🎯 **Each turn:** ⚔️ Strike · 🛡️ Guard yourself or an ally · ✨ Mend · 🕯️ Rite · "
    "💫 your class **Signature**, once per fight.\n"
    "👻 **The fallen** fight on as spirits: Haunt, Echo or Foresee.\n"
    "⚠️ **Watch for omens.** Its Cataclysm gathers for a turn before it lands, "
    "and the vessel grows deadlier as it breaks.\n"
    "🎭 **Afterwards,** guess which GM was the Possessor for a crate."
)
OUTCOME_TITLES = {
    "slain": "The vessel is destroyed!",
    "exorcised": "The Severance is complete!",
    "wiped": "The raid has fallen.",
    "withdrawn": "The possession endures.",
}
PHASE_RULES = {
    2: "Its armor is gone, and the circle holds one more voice.",
    3: "It hits harder, its Dread builds faster, and it can now use **{execute}**. The circle holds one more voice.",
}


def upper_first(text):
    return text[:1].upper() + text[1:]


def clip(text, limit=1024):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def chunk_lines(lines, limit=1024):
    """Pack lines into as few embed field values as fit."""
    chunks, current = [], ""
    for text in lines:
        candidate = f"{current}\n{text}" if current else text
        if len(candidate) > limit and current:
            chunks.append(current)
            current = text
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def class_lines(names):
    lines = []
    for name in names or ():
        game_class = class_from_string(name)
        if game_class is not None:
            lines.append(game_class.get_class_line_name())
    return lines


# ---- joining ---------------------------------------------------------------
class PossessionJoinView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=JOIN_SECONDS + 30)
        self.session = session
        self.joined = []
        self.closed = False
        self.message = None
        self._lock = asyncio.Lock()

    @discord.ui.button(label="Stand against it", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def join(self, interaction, button):
        session = self.session
        user = interaction.user
        if user.id == session.gm.id:
            return await interaction.response.send_message(
                "You cannot fight yourself. *Your underling looks confused.*", ephemeral=True
            )
        profile = await session.bot.pool.fetchrow('SELECT "class" FROM profile WHERE "user" = $1', user.id)
        if not profile:
            return await interaction.response.send_message("You need a character to join.", ephemeral=True)
        async with self._lock:
            if self.closed:
                rejection = "The vessel has already turned its gaze upon those gathered."
            elif any(member.id == user.id for member in self.joined):
                rejection = "You already stand against it."
            elif len(self.joined) >= MAX_RAIDERS:
                rejection = f"The line is full ({MAX_RAIDERS} raiders)."
            else:
                rejection = None
                self.joined.append(user)
                session.remember(user)
                session.signatures[user.id] = signature_for(class_lines(profile["class"]))
        if rejection:
            return await interaction.response.send_message(rejection, ephemeral=True)
        name, emoji, rule, _story = SIGNATURE_LORE[session.signatures[user.id]]
        await interaction.response.send_message(
            "You step forward. The vessel's head turns toward you, slowly.\n\n"
            f"{emoji} Your signature is **{name}**: {rule} *(Once per fight.)*",
            ephemeral=True,
        )
        await self.refresh()

    async def refresh(self):
        if self.message is None:
            return
        try:
            await self.message.edit(embed=self.session.join_embed(self.joined))
        except discord.HTTPException:
            pass

    async def close(self):
        async with self._lock:
            self.closed = True
        self.stop()
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---- raider turn controls --------------------------------------------------
class RaiderActionButton(discord.ui.Button):
    STYLES = {
        "strike": discord.ButtonStyle.danger,
        "guard": discord.ButtonStyle.secondary,
        "mend": discord.ButtonStyle.success,
        "rite": discord.ButtonStyle.primary,
        "signature": discord.ButtonStyle.secondary,
    }

    def __init__(self, action):
        label, emoji, _confirm = PLAYER_ACTION_FLAVOR[action]
        super().__init__(label=label, emoji=emoji, style=self.STYLES[action], row=0)
        self.action = action

    async def callback(self, interaction):
        view = self.view
        session = view.session
        raider = await session.gate(interaction, view.token)
        if raider is None:
            return
        uid = raider.user_id
        if self.action in ("strike", "rite"):
            session.choose(uid, self.action)
            return await interaction.response.send_message(PLAYER_ACTION_FLAVOR[self.action][2], ephemeral=True)
        if self.action in ("guard", "mend"):
            session.choose(uid, self.action, pending=True)
            picker = AllyPicker(session, view.token, uid, self.action)
            return await interaction.response.send_message(picker.prompt, view=picker, ephemeral=True)

        name, emoji, rule, _story = SIGNATURE_LORE[raider.signature]
        if raider.signature_used:
            return await interaction.response.send_message(
                f"{emoji} Your **{name}** is spent for this fight.", ephemeral=True
            )
        if not session.encounter.signature_ready(raider):
            return await interaction.response.send_message(
                f"{emoji} No one has fallen yet, so **{name}** has no one to call back.", ephemeral=True
            )
        picker = SignaturePicker(session, view.token, raider)
        embed = discord.Embed(
            title=f"{emoji} {name}",
            description=f"{rule}\n\n*Once per fight. It replaces your action this turn.*",
            color=session.vessel["color"],
        )
        await interaction.response.send_message(embed=embed, view=picker, ephemeral=True)


class SpiritButton(discord.ui.Button):
    def __init__(self, action):
        label, emoji, _rule, _confirm = SPIRIT_FLAVOR[action]
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, row=1)
        self.action = action

    async def callback(self, interaction):
        session = self.view.session
        spirit = await session.gate(interaction, self.view.token, spirit=True)
        if spirit is None:
            return
        uid = spirit.user_id
        if self.action == "foresee":
            vision = session.vision()
            if vision is None:
                return await interaction.response.send_message(
                    "👁️ The will behind the vessel has not decided yet. Look again soon.", ephemeral=True
                )
            session.spirit_choices[uid] = "foresee"
            session.foreseen.add(uid)
            return await interaction.response.send_message(
                f"👁️ {vision}\n*Warn the living before the turn ends.*", ephemeral=True
            )
        if uid in session.foreseen:
            return await interaction.response.send_message(
                "You spent this turn watching. Your warning is all you have left to give.", ephemeral=True
            )
        session.spirit_choices[uid] = self.action
        await interaction.response.send_message(SPIRIT_FLAVOR[self.action][3], ephemeral=True)


class RaiderActionView(discord.ui.View):
    def __init__(self, session, token):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        self.token = token
        for action in PLAYER_ACTIONS:
            self.add_item(RaiderActionButton(action))
        if session.encounter.fallen():
            for action in SPIRIT_ACTIONS:
                self.add_item(SpiritButton(action))


class AllyPicker(discord.ui.View):
    """Ephemeral follow-up to Guard or Mend: whom to protect or heal."""

    def __init__(self, session, token, uid, action):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        self.token = token
        self.action = action
        enc = session.encounter
        if action == "guard":
            self.prompt = "🛡️ Whom will you protect? Blows aimed at an ally land on you instead, halved."
            first = discord.SelectOption(label="Myself", value="self", emoji="🛡️",
                                         description="Take half damage this turn")
            pool = [r for r in enc.living() if r.user_id != uid]
        else:
            self.prompt = "✨ Whom will you mend?"
            first = discord.SelectOption(label="The most wounded", value="auto", emoji="✨",
                                         description="Decided when the turn ends")
            pool = enc.living()
        pool = sorted(pool, key=lambda r: r.hp_ratio)[:24]
        self.select = discord.ui.Select(
            placeholder="Choose an ally…",
            options=[first] + [session.raider_option(raider) for raider in pool],
        )
        self.select.callback = self.pick
        self.add_item(self.select)

    async def pick(self, interaction):
        raider = await self.session.gate(interaction, self.token)
        if raider is None:
            return
        value = self.select.values[0]
        target = None if value in ("self", "auto") else int(value)
        self.session.choose(raider.user_id, self.action, target)
        if target is not None:
            who = f"**{self.session.name(target)}**"
        else:
            who = "yourself" if self.action == "guard" else "whoever is most wounded"
        await interaction.response.edit_message(
            content=PLAYER_ACTION_FLAVOR[self.action][2].format(target=who), view=None
        )


class SignaturePicker(discord.ui.View):
    """Ephemeral confirmation (and target choice) for a raider's signature."""

    def __init__(self, session, token, raider):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        self.token = token
        self.name, self.emoji, _rule, _story = SIGNATURE_LORE[raider.signature]
        kind = SIGNATURES[raider.signature]["target"]
        if kind is None:
            button = discord.ui.Button(label=f"Unleash {self.name}", emoji=self.emoji,
                                       style=discord.ButtonStyle.primary)
            button.callback = self.unleash
            self.add_item(button)
            return
        enc = session.encounter
        pool = enc.living() if kind == "ally" else enc.fallen()
        pool = sorted(pool, key=lambda r: r.hp_ratio)[:25]
        self.select = discord.ui.Select(
            placeholder="Choose an ally…" if kind == "ally" else "Choose whom to raise…",
            options=[session.raider_option(raider) for raider in pool],
        )
        self.select.callback = self.pick
        self.add_item(self.select)

    async def unleash(self, interaction):
        await self._commit(interaction, None)

    async def pick(self, interaction):
        await self._commit(interaction, int(self.select.values[0]))

    async def _commit(self, interaction, target):
        raider = await self.session.gate(interaction, self.token)
        if raider is None:
            return
        if not self.session.encounter.signature_ready(raider):
            return await interaction.response.send_message("That power is beyond you now.", ephemeral=True)
        self.session.choose(raider.user_id, "signature", target)
        aimed = f" for **{self.session.name(target)}**" if target is not None else ""
        await interaction.response.edit_message(
            content=f"{self.emoji} **{self.name}** is ready{aimed}. It fires when the turn ends. "
                    "Pick another action to change your mind.",
            embed=None,
            view=None,
        )


# ---- the Possessor's panel -------------------------------------------------
class TargetSelect(discord.ui.Select):
    def __init__(self, session):
        enc = session.encounter
        options = []
        for raider in sorted(enc.living(), key=lambda r: r.hp_ratio)[:25]:
            last = PLAYER_ACTION_FLAVOR.get(enc.last_actions.get(raider.user_id), ("unknown",))[0]
            ready = " · signature ready" if not raider.signature_used else ""
            options.append(discord.SelectOption(
                label=session.plain_name(raider.user_id)[:100],
                value=str(raider.user_id),
                emoji=SIGNATURE_LORE[raider.signature][1],
                description=f"{ui.percent(raider.hp, raider.max_hp)}% health · last: {last}{ready}"[:100],
            ))
        super().__init__(placeholder="Choose whom to afflict…", options=options, row=0)

    async def callback(self, interaction):
        session = self.view.session
        self.view.target_id = int(self.values[0])
        await interaction.response.send_message(
            f"*{session.underling['name']} nods.* **{session.name(self.view.target_id)}**. Now choose the power.",
            ephemeral=True,
        )


class AbilityButton(discord.ui.Button):
    def __init__(self, session, ability, row):
        name, emoji, _narration = session.vessel["abilities"][ability]
        super().__init__(
            label=name,
            emoji=emoji,
            style=discord.ButtonStyle.danger if ability in ("cataclysm", "execute") else discord.ButtonStyle.secondary,
            disabled=not session.encounter.ability_ready(ability),
            row=row,
        )
        self.ability = ability

    async def callback(self, interaction):
        view = self.view
        session = view.session
        if view.is_finished():
            return await interaction.response.send_message("The moment has passed.", ephemeral=True)
        target_id = None
        if ABILITIES[self.ability]["target"]:
            target_id = view.target_id
            if target_id is None or not session.encounter.raiders[target_id].alive:
                target_id = session.encounter.weakest().user_id
        session.gm_choice = (self.ability, target_id)
        view.stop()
        for child in view.children:
            child.disabled = True
        name = session.vessel["abilities"][self.ability][0]
        aimed = f" upon **{session.name(target_id)}**" if target_id else ""
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"*{session.underling['name']}:* It will be done, {session.underling['master']}. **{name}**{aimed}."
        )
        session.check_turn_ready()


class PossessorPanel(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        self.target_id = None
        self.add_item(TargetSelect(session))
        for index, ability in enumerate(ABILITIES):
            self.add_item(AbilityButton(session, ability, row=1 + index // 3))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.session.gm.id


# ---- the guessing game -----------------------------------------------------
class GuessSelect(discord.ui.Select):
    def __init__(self, candidates):
        options = [discord.SelectOption(label=name[:100], value=str(uid)) for uid, name in candidates]
        super().__init__(placeholder="Whose will drove the vessel?", options=options)

    async def callback(self, interaction):
        view = self.view
        if interaction.user.id not in view.voters:
            return await interaction.response.send_message(
                "Only those who stood against the vessel may name its master.", ephemeral=True
            )
        if view.is_finished():
            return await interaction.response.send_message("The guessing has closed.", ephemeral=True)
        choice = int(self.values[0])
        view.guesses[interaction.user.id] = choice
        await interaction.response.send_message(
            f"You name **{discord.utils.escape_markdown(view.names[choice])}**. "
            "You can change your guess until the vote closes.",
            ephemeral=True,
        )
        if view.voters.issubset(view.guesses):
            view.all_in.set()
        await view.update_counter()


class GuessView(discord.ui.View):
    def __init__(self, voters, candidates):
        super().__init__(timeout=GUESS_SECONDS + 15)
        self.voters = set(voters)
        self.names = dict(candidates)
        self.guesses = {}
        self.all_in = asyncio.Event()
        self.message = None
        self.embed = None
        self.add_item(GuessSelect(candidates))

    def counter_text(self):
        return f"🗳️ {len(self.guesses)}/{len(self.voters)} votes cast"

    async def update_counter(self):
        if self.message is None or self.embed is None or self.is_finished():
            return
        self.embed.set_footer(text=self.counter_text())
        try:
            await self.message.edit(embed=self.embed)
        except discord.HTTPException:
            pass


class CratePickSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=f"{crate.title()} Crate", value=crate) for crate in CRATE_TYPES]
        super().__init__(placeholder="Choose their reward…", options=options)

    async def callback(self, interaction):
        view = self.view
        if view.is_finished():
            return await interaction.response.send_message("The moment has passed.", ephemeral=True)
        view.choice = self.values[0]
        view.stop()
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"*{view.session.underling['name']}:* A **{view.choice.title()} Crate** each. "
            f"How generous, {view.session.underling['master']}."
        )


class CratePickView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=GUESS_PICK_SECONDS)
        self.session = session
        self.choice = None
        self.add_item(CratePickSelect())

    async def interaction_check(self, interaction):
        return interaction.user.id == self.session.gm.id


# ---- the session -------------------------------------------------------------
class PossessionSession:
    def __init__(self, cog, gm, channel, vessel_key, gold, crate, hp_per_raider):
        self.cog = cog
        self.bot = cog.bot
        self.gm = gm
        self.channel = channel
        self.vessel_key = vessel_key
        self.vessel = VESSELS[vessel_key]
        self.underling = self.vessel["underling"]
        self.gold = gold
        self.crate = crate
        self.hp_per_raider = hp_per_raider
        self.dm = None
        self.encounter = None
        self.join_ends = None
        self.plain_names = {}
        self.signatures = {}
        self.raider_choices = {}   # user_id -> (action, target_id, pending)
        self.spirit_choices = {}   # user_id -> spirit action
        self.foreseen = set()
        self.gm_choice = None
        self.turn_token = 0
        self.turn_closed = True
        self.turn_ready = asyncio.Event()
        self.recent_deaths = []
        self.phase_note = None
        self.last_relay = 0.0
        self.task = None

    # ---- names and helpers ---------------------------------------------
    def remember(self, member):
        self.plain_names[member.id] = member.display_name

    def plain_name(self, user_id):
        return self.plain_names.get(user_id, "someone")

    def name(self, user_id, limit=32):
        """Display name, safe to drop into markdown."""
        return discord.utils.escape_markdown(self.plain_name(user_id)[:limit])

    def ability_label(self, ability):
        name, emoji, _narration = self.vessel["abilities"][ability]
        return f"{emoji} **{name}**"

    def raider_option(self, raider):
        return discord.SelectOption(
            label=self.plain_name(raider.user_id)[:100],
            value=str(raider.user_id),
            emoji=SIGNATURE_LORE[raider.signature][1],
            description=f"{ui.percent(raider.hp, raider.max_hp)}% health · "
                        f"{ui.compact(raider.hp)}/{ui.compact(raider.max_hp)}",
        )

    def fields(self):
        enc = self.encounter
        living = enc.living()
        strongest = max(living, key=lambda r: r.damage, default=None)
        weakest = enc.weakest()
        return {
            "round": enc.round_no,
            "max_rounds": enc.max_rounds,
            "weakest": f"**{self.name(weakest.user_id)}**" if weakest else "no one",
            "strongest": f"**{self.name(strongest.user_id)}**" if strongest else "no one",
            "rite": enc.rite,
            "goal": enc.rite_goal,
            "dread": enc.vessel.dread,
            "vessel_pct": ui.percent(enc.vessel.hp, enc.vessel.max_hp),
            "living": len(living),
        }

    def choose(self, user_id, action, target=None, pending=False):
        self.raider_choices[user_id] = (action, target, pending)
        self.check_turn_ready()

    def check_turn_ready(self):
        if self.encounter is None or self.gm_choice is None:
            return
        living = self.encounter.living()
        if all(
            r.user_id in self.raider_choices and not self.raider_choices[r.user_id][2] for r in living
        ):
            self.turn_ready.set()

    async def gate(self, interaction, token, *, spirit=False):
        """Return the acting raider, or answer the interaction with why they can't act."""
        enc = self.encounter
        raider = enc.raiders.get(interaction.user.id) if enc else None
        problem = None
        if token != self.turn_token or self.turn_closed:
            problem = "Too late. The turn has already ended."
        elif raider is None:
            problem = "You are not part of this fight."
        elif spirit and raider.alive:
            problem = "Only the fallen can do that. You still have a body to fight with."
        elif not spirit and not raider.alive:
            problem = "The dead cannot act, but your spirit can still 👻 Haunt, 🔔 Echo or 👁️ Foresee."
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return None
        return raider

    def vision(self):
        """What a Foreseeing spirit learns, or None if the Possessor hasn't chosen yet."""
        if self.encounter.charging:
            return f"{self.ability_label('cataclysm')} falls on everyone when this turn ends."
        if self.gm_choice is None:
            return None
        ability, target_id = self.gm_choice
        aimed = f" upon **{self.name(target_id)}**" if target_id else ""
        return f"The vessel will use {self.ability_label(ability)}{aimed}."

    async def say_to_gm(self, content=None, **kwargs):
        if self.dm is None:
            return None
        try:
            return await self.dm.send(content, **kwargs)
        except discord.HTTPException:
            return None

    async def _safe_send(self, destination, content=None, **kwargs):
        try:
            kwargs.setdefault("allowed_mentions", NO_MENTIONS)
            return await destination.send(content, **kwargs)
        except discord.HTTPException:
            return None

    # ---- shared embed pieces -------------------------------------------
    def effects_line(self):
        enc = self.encounter
        effects = []
        if enc.phase >= 2:
            effects.append(f"Phase {ui.roman(enc.phase)}: armor broken")
        if enc.mark_turns:
            effects.append("🏹 Marked: strikes +30%")
        if enc.vulnerability:
            effects.append(f"⚓ Sundered: strikes +{enc.vulnerability:.0%}")
        return " · ".join(effects)

    def vessel_field(self, embed, length=12):
        enc = self.encounter
        vessel = enc.vessel
        embed.add_field(
            name=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])} · Phase {ui.roman(enc.phase)}",
            value=f"{ui.bar(vessel.hp, vessel.max_hp, length, 'red')}\n"
                  f"**{ui.compact(vessel.hp)}** / {ui.compact(vessel.max_hp)} · "
                  f"{ui.percent(vessel.hp, vessel.max_hp)}%",
            inline=False,
        )

    def rite_field(self, embed, length=12):
        enc = self.encounter
        embed.add_field(
            name="🕯️ Severance",
            value=f"{ui.bar(enc.rite, enc.rite_goal, length, 'yellow')}\n"
                  f"**{enc.rite}** / {enc.rite_goal} · the circle holds **{enc.rite_capacity}** "
                  f"voice(s) · strikes **+{enc.grip_bonus:.0%}**",
            inline=False,
        )

    def dread_field(self, embed):
        enc = self.encounter
        cataclysm = self.vessel["abilities"]["cataclysm"][0]
        if enc.charging:
            status = f" · ⚠️ **{cataclysm} is gathering!**"
        elif enc.vessel.dread >= DREAD_MAX:
            status = f" · **{cataclysm} is ready!**"
        else:
            status = ""
        embed.add_field(
            name="🌘 Dread",
            value=f"{ui.pips(enc.vessel.dread, DREAD_MAX)} **{enc.vessel.dread}**/{DREAD_MAX}{status}",
            inline=False,
        )

    def raider_lines(self, with_actions=False, budget=RAIDER_EMOJI_BUDGET):
        """One line per living raider, with emoji bars when they fit the embed budget."""
        enc = self.encounter
        living = sorted(enc.living(), key=lambda r: r.hp_ratio)

        def build(emoji_bars):
            lines = []
            for raider in living:
                if emoji_bars:
                    bar = ui.bar(raider.hp, raider.max_hp, 6, "blue")
                else:
                    bar = f"`{ui.text_bar(raider.hp, raider.max_hp, 8)}`"
                extra = " 💫" if not raider.signature_used else ""
                if with_actions and raider.user_id in enc.last_actions:
                    last = PLAYER_ACTION_FLAVOR.get(enc.last_actions[raider.user_id], ("", "❔"))[1]
                    extra += f" · last {last}"
                lines.append(
                    f"{bar} {SIGNATURE_LORE[raider.signature][1]} **{self.name(raider.user_id, 20)}** "
                    f"`{ui.compact(raider.hp)}`{extra}"
                )
            return lines

        lines = build(True)
        if sum(len(text) + 1 for text in lines) > budget:
            lines = build(False)
        return lines or ["*No one is left standing.*"]

    def add_raider_fields(self, embed, title, with_actions=False, budget=RAIDER_EMOJI_BUDGET):
        for index, chunk in enumerate(chunk_lines(self.raider_lines(with_actions, budget))):
            embed.add_field(name=title if index == 0 else "​", value=chunk, inline=False)

    # ---- embeds --------------------------------------------------------
    def join_embed(self, joined):
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])} has been possessed",
            description=f"{self.vessel['arrival']}\n\n⏳ The vessel moves <t:{int(self.join_ends.timestamp())}:R>.",
            color=self.vessel["color"],
        )
        embed.add_field(name="📜 How it works", value=HOW_IT_WORKS, inline=False)
        rewards = []
        if self.gold:
            rewards.append(f"💰 **${self.gold:,}** split among those who stand, more for survivors")
        if self.crate:
            rewards.append(f"📦 a **{self.crate.title()} Crate** for the most valiant")
        if rewards:
            embed.add_field(name="🎁 Bounty", value="\n".join(rewards), inline=False)
        roster = [
            f"{SIGNATURE_LORE[self.signatures.get(member.id, 'last_stand')][1]} {self.name(member.id)}"
            for member in joined
        ]
        value = "\n".join(roster) if roster else "*No one has stepped forward yet…*"
        needed = MIN_RAIDERS - len(joined)
        if needed > 0:
            value += f"\n*{needed} more needed to begin.*"
        embed.add_field(
            name=f"⚔️ Standing against it ({len(joined)}/{MAX_RAIDERS})", value=clip(value), inline=False
        )
        embed.set_footer(text="Its will is not the vessel's own. Someone is watching through its eyes.")
        return embed

    def round_embed(self, deadline):
        enc = self.encounter
        lines = []
        if enc.charging:
            lines += [
                f"⚠️ {self.vessel['omen']}",
                f"It falls on the **whole raid** when this turn ends. Deal **{ui.compact(enc.interrupt_threshold)}** "
                "damage this turn to break it, 🛡️ Guard to halve it, or 🗝️ Pilfer it away.\n",
            ]
        lines.append(
            f"⏳ Choose your action. The turn ends <t:{int(deadline.timestamp())}:R>, or once everyone has chosen."
        )
        effects = self.effects_line()
        if effects:
            lines.append(f"*{effects}*")
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} Turn {enc.round_no}/{enc.max_rounds}",
            description="\n".join(lines),
            color=self.vessel["color"],
        )
        self.vessel_field(embed)
        self.rite_field(embed)
        self.dread_field(embed)
        self.add_raider_fields(embed, f"⚔️ Raiders ({len(enc.living())})")
        fallen = enc.fallen()
        if fallen:
            names = ", ".join(self.name(raider.user_id, 20) for raider in fallen)
            embed.add_field(
                name=f"👻 Spirits ({len(fallen)})",
                value=clip(f"{names}\n*The fallen can 👻 Haunt, 🔔 Echo or 👁️ Foresee.*"),
                inline=False,
            )
        embed.set_footer(text="No choice means Strike · 💫 signature still unused · 🛡️ and ✨ let you pick an ally")
        return embed

    def prompt_embed(self, deadline):
        enc = self.encounter
        fields = self.fields()
        parts = [line(self.underling["prompt"], **fields)]
        if self.phase_note:
            note = f"💥 *{self.vessel['phases'][self.phase_note]}*"
            if self.phase_note >= 3:
                note += f"\n**New power:** {self.ability_label('execute')}"
            parts.append(note)
        for fallen in self.recent_deaths:
            parts.append(line(self.underling["kill"], fallen=f"**{self.name(fallen)}**"))
        if enc.charging:
            parts.append(
                f"⚠️ {self.underling['charging']}\n"
                f"They need **{ui.compact(enc.interrupt_threshold)}** damage this turn to break it."
            )
        elif enc.rite >= enc.rite_goal / 2:
            parts.append(line(self.underling["rite_warning"], **fields))
        if enc.vessel.hp <= enc.vessel.max_hp * 0.3:
            parts.append(line(self.underling["vessel_low"], **fields))
        if enc.ability_ready("cataclysm"):
            parts.append(line(self.underling["dread_full"], **fields))
        embed = discord.Embed(description="\n\n".join(parts), color=self.vessel["color"])
        embed.set_author(name=f"{self.underling['name']}, {self.underling['title']}")
        self.vessel_field(embed, length=10)
        embed.add_field(
            name="🕯️ Severance",
            value=f"`{ui.text_bar(enc.rite, enc.rite_goal, 8)}` {enc.rite}/{enc.rite_goal} · holds {enc.rite_capacity}",
            inline=True,
        )
        embed.add_field(
            name="🌘 Dread",
            value=f"`{ui.text_bar(enc.vessel.dread, DREAD_MAX, 8)}` {enc.vessel.dread}/{DREAD_MAX}",
            inline=True,
        )
        self.add_raider_fields(
            embed, f"Raiders (answer <t:{int(deadline.timestamp())}:R>)", with_actions=True,
            budget=PROMPT_EMOJI_BUDGET,
        )
        if enc.charging:
            embed.set_footer(text="The gathered power falls on its own this turn. Your words still reach them.")
            return embed
        powers = []
        for ability in ABILITIES:
            spec = ABILITIES[ability]
            cooldown = enc.vessel.cooldowns.get(ability, 0)
            if cooldown:
                status = f" *(ready in {cooldown})*"
            elif enc.phase < spec.get("phase", 1):
                status = f" *(Phase {ui.roman(spec['phase'])})*"
            elif not enc.ability_ready(ability):
                status = f" *(needs {DREAD_MAX} Dread)*"
            else:
                status = ""
            powers.append(f"{self.ability_label(ability)}{status}: {ABILITY_RULES[ability]}")
        for index, chunk in enumerate(chunk_lines(powers)):
            embed.add_field(name="Your powers" if index == 0 else "​", value=chunk, inline=False)
        embed.set_footer(
            text=f"Pick a target, then a power. No target means the weakest. "
                 f"Anything you type here, the vessel speaks aloud. If you stay silent, "
                 f"{self.underling['name']} improvises. 💫 = signature unused."
        )
        return embed

    def report_embed(self, report, improvised):
        enc = self.encounter
        ability_name, emoji, narration = self.vessel["abilities"][report.ability]
        target = f"**{self.name(report.target_id)}**" if report.target_id else ""
        sections = []

        if report.dominated:
            dom = report.dominated
            amount = dom.get("amount", 0)
            action = "mend_wasted" if dom.get("action") == "mend" and not amount else dom.get("action")
            outcome = DOMINATE_OUTCOMES.get(action, DOMINATE_OUTCOMES[None])
            sections.append(
                f"{emoji} *{render(narration, target=target)}*\n" + render(
                    outcome,
                    target=target,
                    victim=f"**{self.name(dom.get('victim_id'))}**",
                    amount=ui.compact(amount) if isinstance(amount, float) else amount,
                )
            )

        spirits = []
        if report.haunts:
            spirits.append(f"👻 {report.haunts} spirit(s) haunt the vessel (**−{report.haunt_drain}** Dread)")
        if report.echoes:
            gained = f"**+{report.echo_gain}** Severance" if report.echo_gain else "the circle stirs"
            spirits.append(f"🔔 {report.echoes} echo(es) from beyond ({gained})")
        if spirits:
            sections.append("\n".join(spirits))

        raid = []
        for uid, key, target_id, amount in report.signatures:
            name, sig_emoji, _rule, story = SIGNATURE_LORE[key]
            raid.append(f"{sig_emoji} **{name}!** " + render(
                story,
                actor=f"**{self.name(uid)}**",
                target="themselves" if target_id == uid else f"**{self.name(target_id)}**" if target_id else "",
                amount=ui.compact(amount),
            ))
        strikes = [(uid, amount) for uid, amount, tag in report.strikes if tag is None]
        if strikes:
            top_uid, top = max(strikes, key=lambda s: s[1])
            warded = " *(halved by the ward)*" if report.ward else ""
            raid.append(
                f"⚔️ {len(strikes)} strike(s) land for **{ui.compact(sum(a for _u, a in strikes))}**{warded}. "
                f"Deepest cut: {self.name(top_uid)} ({ui.compact(top)})."
            )
        shields = [(guard, ward) for guard, ward in report.guards if guard != ward]
        braced = len(report.guards) - len(shields)
        guard_bits = [f"{self.name(guard)} shields {self.name(ward)}" for guard, ward in shields[:4]]
        if len(shields) > 4:
            guard_bits.append(f"{len(shields) - 4} more stand guard")
        if braced:
            guard_bits.append(f"{braced} brace themselves")
        if guard_bits:
            raid.append("🛡️ " + " · ".join(guard_bits) + ".")
        mends = [(h, t, a) for h, t, a in report.mends if a > 0]
        for healer, ally, amount in mends[:4]:
            who = "themselves" if ally == healer else self.name(ally)
            raid.append(f"✨ {self.name(healer)} mends {who} for **{ui.compact(amount)}**.")
        if len(mends) > 4:
            raid.append(f"✨ …and {len(mends) - 4} more mend(s).")
        if report.total_rite:
            reached = enc.rite + (report.total_rite if report.rite_broken else 0)
            raid.append(f"🕯️ The Severance advances **+{report.total_rite}** ({reached}/{enc.rite_goal}).")
        if report.rite_unheard:
            raid.append(f"🕯️ The circle is full. {report.rite_unheard} voice(s) go unheard.")
        if raid:
            sections.append("\n".join(raid))

        if report.phase_change:
            rule = PHASE_RULES[report.phase_change].format(execute=self.vessel["abilities"]["execute"][0])
            sections.append(
                f"💥 **PHASE {ui.roman(report.phase_change)}**\n*{self.vessel['phases'][report.phase_change]}*\n{rule}"
            )

        vessel = []
        acted = bool(report.dominated) or report.ability == "ward" or bool(report.hits)
        if report.charge_started:
            acted = True
            vessel.append(f"{emoji} {self.vessel['omen']}\n⚠️ It falls on the **whole raid** at the end of next turn!")
        elif report.releasing and report.interrupted:
            acted = True
            reason = "Pilfered away!" if report.pilfered else f"**{ui.compact(report.total_strike)}** damage broke it!"
            vessel.append(f"💥 *{self.vessel['interrupted']}* {reason}")
        elif report.ability == "ward":
            vessel.append(f"{emoji} *{render(narration, target=target)}*")
        elif report.hits:
            vessel.append(f"{emoji} *{render(narration, target=target)}*")
        for uid, amount, halved, shielded in report.hits[:10]:
            if shielded:
                note = f" *(shielding {self.name(shielded)})*"
            elif halved:
                note = " *(guarded)*"
            else:
                note = ""
            vessel.append(f"• {self.name(uid)} takes **{ui.compact(amount)}**{note}")
        if len(report.hits) > 10:
            vessel.append(f"• …and {len(report.hits) - 10} more.")
        for uid in report.executed:
            vessel.append(f"{emoji} **{self.name(uid)}** is executed where they stand!")
        if report.vessel_healed:
            vessel.append(f"🩸 The vessel restores **{ui.compact(report.vessel_healed)}**.")
        if report.rite_broken:
            names = ", ".join(self.name(uid) for uid in report.rite_broken)
            vessel.append(
                f"🕯️💥 **The circle shatters!** {names} was struck mid-chant. "
                f"This turn's Severance is lost ({enc.rite}/{enc.rite_goal})."
            )
        if vessel:
            sections.append("\n".join(vessel))

        fates = [f"🔆 **{self.name(uid)}** returns to the fight!" for uid in report.revived]
        fates += [f"☠️ **{self.name(uid)}** has fallen. Their spirit lingers." for uid in report.deaths]
        if not acted and enc.outcome in ("slain", "exorcised"):
            fates.append("*The vessel's final command dies unspoken.*")
        if fates:
            sections.append("\n".join(fates))

        if report.charge_started:
            title = f"{emoji} {ability_name} gathers…"
        elif report.releasing:
            title = f"{emoji} {ability_name}" + (" is broken!" if report.interrupted else "")
        elif acted:
            title = f"{emoji} {ability_name}"
        else:
            title = "The vessel falters!"
        if improvised:
            title += f" (chosen by {self.underling['name']})"
        embed = discord.Embed(
            title=f"Turn {report.round_no} · {title}",
            description=clip("\n\n".join(sections) or "*A tense stillness.*", 4000),
            color=self.vessel["color"],
        )
        vessel_state = enc.vessel
        embed.add_field(
            name="​",
            value=f"{ui.bar(vessel_state.hp, vessel_state.max_hp, 10, 'red')} "
                  f"**{ui.percent(vessel_state.hp, vessel_state.max_hp)}%** · "
                  f"🕯️ {enc.rite}/{enc.rite_goal} · 🌘 {vessel_state.dread}",
            inline=False,
        )
        return embed

    def honours(self):
        raiders = list(self.encounter.raiders.values())
        lines = []
        cutters = [r for r in sorted(raiders, key=lambda r: r.dealt, reverse=True)[:3] if r.dealt > 0]
        if cutters:
            lines.append("🗡️ **Deepest cuts:** " + " · ".join(
                f"{self.name(r.user_id, 20)} ({ui.compact(r.dealt)})" for r in cutters
            ))
        for attr, emoji, title, fmt in (
            ("healed", "✨", "Lifeline", lambda r: f"{ui.compact(r.healed)} mended"),
            ("rites", "🕯️", "Voice of the Severance", lambda r: f"{r.rites} rite(s)"),
            ("absorbed", "🛡️", "Bodyguard", lambda r: f"{ui.compact(r.absorbed)} taken for others"),
            ("revives", "🔆", "Miracle worker", lambda r: f"{r.revives} raised"),
            ("spirit_acts", "👻", "Restless spirit", lambda r: f"{r.spirit_acts} act(s) from beyond"),
        ):
            best = max(raiders, key=lambda r: getattr(r, attr))
            if getattr(best, attr) > 0:
                lines.append(f"{emoji} **{title}:** {self.name(best.user_id, 20)} ({fmt(best)})")
        return lines

    # ---- flow ----------------------------------------------------------
    async def run(self):
        try:
            await self._run()
        except asyncio.CancelledError:
            await self._safe_send(
                self.channel,
                f"{self.vessel['emoji']} *A higher power tears the will out of {self.vessel['name']}. "
                "The vessel collapses, and the possession is broken before it could finish.*",
            )
            raise
        except Exception:
            self.bot.logger.exception("Possession event failed")
            await self._safe_send(
                self.channel,
                "⚠️ The possession unraveled because of a technical problem. No rewards were paid.",
            )
        finally:
            self.cog.session = None

    async def _run(self):
        self.join_ends = datetime.now(timezone.utc) + timedelta(seconds=JOIN_SECONDS)
        join_view = PossessionJoinView(self)
        role = self.channel.guild.get_role(self.cog.ping_role_id) if self.cog.ping_role_id else None
        join_view.message = await self.channel.send(
            content=role.mention if role else None,
            embed=self.join_embed([]),
            view=join_view,
            allowed_mentions=discord.AllowedMentions(roles=[role]) if role else NO_MENTIONS,
        )
        await asyncio.sleep(JOIN_SECONDS)
        await join_view.close()

        raiders = await self._gather(join_view.joined)
        if len(raiders) < MIN_RAIDERS:
            await self._safe_send(
                self.channel,
                f"{self.vessel['emoji']} *{upper_first(self.vessel['name'])} surveys the few who came, "
                "finds them unworthy, and dissolves into nothing.* (Not enough raiders.)",
            )
            await self.say_to_gm(f"*{self.underling['name']}:* Too few came, {self.underling['master']}. Another time.")
            return

        self.encounter = Encounter(
            raiders,
            self.hp_per_raider,
            max_rounds=MAX_ROUNDS,
            cataclysm_variance=self.vessel["cataclysm_variance"],
        )
        await self.say_to_gm(
            f"*{self.underling['name']}:* {len(raiders)} of them, {self.underling['master']}. The vessel is yours."
        )
        while not self.encounter.outcome:
            await self._play_turn()
        await self._finish()

    async def _gather(self, members):
        raiders = []
        async with self.bot.pool.acquire() as conn:
            for member in members:
                profile = await conn.fetchrow(
                    'SELECT health, stathp, xp, "class" FROM profile WHERE "user" = $1', member.id
                )
                if not profile:
                    continue
                damage, armor = await self.bot.get_raidstats(member, conn=conn)
                level = rpgtools.xptolevel(profile["xp"])
                hp = float(
                    profile["health"] + 250 + level * 15
                    + profile["stathp"] * rpgtools.STAT_HEALTH_PER_POINT
                )
                self.remember(member)
                raiders.append(Raider(
                    member.id, member.display_name, hp, hp, float(damage), float(armor),
                    signature=signature_for(class_lines(profile["class"])),
                ))
        return raiders

    async def _play_turn(self):
        enc = self.encounter
        enc.start_round()
        self.turn_token += 1
        self.turn_closed = False
        self.raider_choices = {}
        self.spirit_choices = {}
        self.foreseen = set()
        self.gm_choice = ("cataclysm", None) if enc.charging else None
        self.turn_ready.clear()
        deadline = datetime.now(timezone.utc) + timedelta(seconds=ROUND_SECONDS)

        raider_view = RaiderActionView(self, self.turn_token)
        public = await self.channel.send(embed=self.round_embed(deadline), view=raider_view)
        panel = None if enc.charging else PossessorPanel(self)
        prompt = self.prompt_embed(deadline)
        private = await (self.say_to_gm(embed=prompt, view=panel) if panel else self.say_to_gm(embed=prompt))
        self.recent_deaths = []
        self.phase_note = None

        try:
            await asyncio.wait_for(self.turn_ready.wait(), ROUND_SECONDS)
        except asyncio.TimeoutError:
            pass
        self.turn_closed = True
        for view, message in ((raider_view, public), (panel, private)):
            if view is None:
                continue
            view.stop()
            for child in view.children:
                child.disabled = True
            if message is not None:
                try:
                    await message.edit(view=view)
                except discord.HTTPException:
                    pass

        improvised = self.gm_choice is None
        ability, target_id = self.gm_choice or enc.improvise()
        if improvised:
            await self._safe_send(self.channel, line(self.underling["improvise_public"]))
            await self.say_to_gm(f"*{self.underling['name']}:* {self.underling['improvise_private']}")
        actions = {uid: (action, target) for uid, (action, target, _pending) in self.raider_choices.items()}
        report = enc.resolve_round(actions, ability, target_id, dict(self.spirit_choices))
        self.recent_deaths = list(report.deaths)
        self.phase_note = report.phase_change
        await self._safe_send(self.channel, embed=self.report_embed(report, improvised))
        if not enc.outcome:
            await asyncio.sleep(RESULT_PAUSE_SECONDS)

    async def _finish(self):
        enc = self.encounter
        victorious = enc.victorious
        participants = list(enc.raiders)
        survivors = [r.user_id for r in enc.living()]
        mvp = enc.mvp()

        payouts, crate_winner = {}, None
        if victorious:
            payouts = split_gold(self.gold, participants, survivors)
            crate_winner = mvp.user_id if self.crate and mvp else None
            try:
                async with self.bot.pool.acquire() as conn:
                    async with conn.transaction():
                        for uid, amount in payouts.items():
                            await conn.execute(
                                'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2;', amount, uid
                            )
                        if crate_winner:
                            await conn.execute(
                                f'UPDATE profile SET "crates_{self.crate}" = "crates_{self.crate}" + 1 '
                                'WHERE "user" = $1;',
                                crate_winner,
                            )
            except Exception:
                self.bot.logger.exception("Possession reward transaction failed")
                payouts, crate_winner = {}, None
                await self._safe_send(
                    self.channel,
                    "⚠️ The rewards could not be paid, and no partial payout was kept. Please contact a Game Master.",
                )

        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {OUTCOME_TITLES[enc.outcome]}",
            description=(
                f"*{self.vessel['endings'][enc.outcome]}*\n\n"
                "The connection breaks, but whose will was it?"
            ),
            color=self.vessel["color"],
        )
        self.vessel_field(embed)
        if mvp and mvp.valor(enc.vessel.attack) > 0:
            embed.add_field(
                name="⭐ Most Valiant",
                value=f"{SIGNATURE_LORE[mvp.signature][1]} **{self.name(mvp.user_id)}**: "
                      f"{ui.compact(mvp.dealt)} dealt · {ui.compact(mvp.healed)} mended · {mvp.rites} rite(s)",
                inline=False,
            )
        honours = self.honours()
        if honours:
            embed.add_field(name="🏅 Honours", value=clip("\n".join(honours)), inline=False)
        embed.add_field(
            name="📜 Standing",
            value=f"**{len(survivors)}/{len(participants)}** raiders survived {enc.round_no} turn(s).",
            inline=False,
        )
        reward_lines = []
        if payouts:
            if survivors:
                reward_lines.append(
                    f"💰 Each raider received **${min(payouts.values()):,}**; "
                    f"survivors received **${max(payouts.values()):,}**."
                )
            else:
                reward_lines.append(f"💰 Each raider received **${max(payouts.values()):,}**.")
        if crate_winner:
            reward_lines.append(f"📦 **{self.name(crate_winner)}** claims a **{self.crate.title()} Crate**.")
        if reward_lines:
            embed.add_field(name="🎁 Rewards", value="\n".join(reward_lines), inline=False)
        await self._safe_send(self.channel, embed=embed)

        guesses, correct, names, held = await self._guess_vote(participants)
        hidden = held and not correct  # Nobody named them, so the Possessor stays secret.
        await self._reveal(participants, guesses, correct, names, hidden)
        guess_crate = None
        if correct:
            guess_crate, chosen = await self._pick_guess_reward(len(correct))
            correct = await self._pay_guessers(correct, guess_crate, chosen)

        farewell = self.underling["defeat"] if victorious else self.underling["victory"]
        await self.say_to_gm(f"*{self.underling['name']}:* {farewell}")
        if hidden:
            await self.say_to_gm(f"*{self.underling['name']}:* Not one of them named you, {self.underling['master']}. Your secret is safe.")
        await self._log(enc, payouts, crate_winner, guesses, correct, guess_crate)

    async def _gm_candidates(self):
        """The Possessor plus up to 24 other Game Masters, sorted by name."""
        rows = await self.bot.pool.fetch("SELECT user_id FROM game_masters")
        others = list(dict.fromkeys(row["user_id"] for row in rows if row["user_id"] != self.gm.id))
        random.shuffle(others)
        candidates = [(self.gm.id, self.gm.display_name)]
        for uid in others[:24]:
            user = self.channel.guild.get_member(uid) or self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except discord.HTTPException:
                    continue
            candidates.append((uid, user.display_name))
        return sorted(candidates, key=lambda c: c[1].lower())

    async def _guess_vote(self, participants):
        """Let the raiders name the Possessor.

        Returns (guesses, correct guessers, candidate names, whether the vote was held)."""
        try:
            candidates = await self._gm_candidates()
        except Exception:
            self.bot.logger.exception("Could not load Game Masters for the possession vote")
            return {}, [], {}, False
        if len(candidates) < 2:
            return {}, [], dict(candidates), False

        deadline = datetime.now(timezone.utc) + timedelta(seconds=GUESS_SECONDS)
        view = GuessView(participants, candidates)
        embed = discord.Embed(
            title="🎭 Who was the Possessor?",
            description=(
                "One of these Game Masters was watching through the vessel's eyes. "
                f"Name them before the vote closes <t:{int(deadline.timestamp())}:R>.\n\n"
                "Everyone who guesses right receives a crate, chosen by the Possessor themselves. "
                "Only raiders from this fight may guess, and you can change your guess until it closes."
            ),
            color=self.vessel["color"],
        )
        embed.set_footer(text=view.counter_text())
        view.embed = embed
        view.message = await self._safe_send(self.channel, embed=embed, view=view)
        if view.message is None:
            return {}, [], view.names, False
        try:
            await asyncio.wait_for(view.all_in.wait(), GUESS_SECONDS)
        except asyncio.TimeoutError:
            pass
        view.stop()
        for child in view.children:
            child.disabled = True
        embed.set_footer(text=f"{view.counter_text()} · voting closed")
        try:
            await view.message.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

        guesses = dict(view.guesses)
        correct = [uid for uid, guess in guesses.items() if guess == self.gm.id]
        return guesses, correct, view.names, True

    def vote_breakdown(self, participants, guesses, names, hidden=False):
        """Who voted for whom. Revealed: the Possessor first, marked right or wrong.
        Hidden: just the votes, most popular first, with nothing marking the Possessor."""
        by_candidate = {} if hidden else {self.gm.id: []}
        for voter, pick in guesses.items():
            by_candidate.setdefault(pick, []).append(voter)
        order = sorted(by_candidate, key=lambda c: (not hidden and c != self.gm.id, -len(by_candidate[c])))
        lines = []
        for candidate in order:
            voters = by_candidate[candidate]
            mark = "🗳️" if hidden else "✅" if candidate == self.gm.id else "❌"
            label = discord.utils.escape_markdown(names.get(candidate, "someone"))
            who = ", ".join(self.name(uid, 20) for uid in voters) or "*no one*"
            lines.append(f"{mark} **{label}** · {len(voters)} vote(s)\n╰ {who}")
        silent = [uid for uid in participants if uid not in guesses]
        if silent:
            lines.append(f"🤐 **Didn't vote:** {', '.join(self.name(uid, 20) for uid in silent)}")
        return lines

    async def _reveal(self, participants, guesses, correct, names, hidden=False):
        if hidden:
            embed = discord.Embed(
                title=f"{self.vessel['emoji']} The Possessor remains hidden",
                description=(
                    f"No one saw through {self.vessel['name']}. Whoever wore it slips away "
                    "unnamed… for now."
                    if guesses else
                    f"No one dared to name the will behind {self.vessel['name']}. It slips away unnamed."
                ),
                color=self.vessel["color"],
            )
        else:
            embed = discord.Embed(
                title=f"{self.vessel['emoji']} The Possessor is revealed",
                description=f"The will behind {self.vessel['name']} was **{self.gm.mention}**.",
                color=self.vessel["color"],
            )
        if guesses:
            breakdown = self.vote_breakdown(participants, guesses, names, hidden)
            for index, chunk in enumerate(chunk_lines(breakdown)):
                embed.add_field(name="🗳️ The votes" if index == 0 else "​", value=chunk, inline=False)
            if correct:
                value = (
                    f"**{len(correct)}/{len(guesses)}** saw through the vessel.\n"
                    "📦 The Possessor is choosing their reward…"
                )
            else:
                value = f"None of the {len(guesses)} guess(es) were right. The Possessor keeps their secret."
            embed.add_field(name="🎭 The verdict", value=value, inline=False)
        if correct:
            await self._safe_send(
                self.channel,
                f"{self.gm.mention}, check your DMs to choose the reward for those who saw through you.",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=[self.gm]),
            )
        else:
            await self._safe_send(self.channel, embed=embed)

    async def _pick_guess_reward(self, winners):
        """Ask the Possessor which crate the correct guessers earn. Returns (crate, chosen_by_gm)."""
        view = CratePickView(self)
        embed = discord.Embed(
            description=(
                f"*{self.underling['name']}:* {winners} of them saw through you, "
                f"{self.underling['master']}. What shall they be given?\n\n"
                f"Choose within {GUESS_PICK_SECONDS // 60} minutes, or they each receive a "
                f"**{GUESS_FALLBACK_CRATE.title()} Crate**."
            ),
            color=self.vessel["color"],
        )
        embed.set_author(name=f"{self.underling['name']}, {self.underling['title']}")
        message = await self.say_to_gm(embed=embed, view=view)
        if message is None:
            return GUESS_FALLBACK_CRATE, False
        try:
            await asyncio.wait_for(view.wait(), GUESS_PICK_SECONDS)
        except asyncio.TimeoutError:
            pass
        view.stop()
        if view.choice is None:
            for child in view.children:
                child.disabled = True
            try:
                await message.edit(view=view)
            except discord.HTTPException:
                pass
            return GUESS_FALLBACK_CRATE, False
        return view.choice, True

    async def _pay_guessers(self, correct, crate, chosen):
        """Pay the chosen crate to each correct guesser. Returns who was paid."""
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    for uid in correct:
                        await conn.execute(
                            f'UPDATE profile SET "crates_{crate}" = "crates_{crate}" + 1 WHERE "user" = $1;',
                            uid,
                        )
        except Exception:
            self.bot.logger.exception("Possession guess reward transaction failed")
            await self._safe_send(
                self.channel, "⚠️ The guessing rewards could not be paid. Please contact a Game Master."
            )
            return []
        names = ", ".join(f"**{self.name(uid)}**" for uid in correct)
        source = (
            f"chosen by {discord.utils.escape_markdown(self.gm.display_name)}" if chosen
            else "the Possessor didn't choose in time"
        )
        await self._safe_send(
            self.channel, clip(f"📦 {names} each receive a **{crate.title()} Crate** ({source}).", 2000)
        )
        return correct

    async def _log(self, enc, payouts, crate_winner, guesses, correct, guess_crate):
        crate_text = f", {self.crate} crate to {crate_winner}" if crate_winner else ""
        content = (
            f"**{self.gm}** possessed {self.vessel['name']} in <#{self.channel.id}>. "
            f"Outcome: **{enc.outcome}** after {enc.round_no} turn(s), {len(enc.raiders)} raider(s). "
            f"Paid **${sum(payouts.values()):,}** to {len(payouts)} player(s){crate_text}. "
            f"{len(correct)}/{len(guesses)} guessed the Possessor"
            f"{f' ({guess_crate} crate each)' if correct else ''}."
        )
        try:
            with handle_message_parameters(content=content, allowed_mentions=NO_MENTIONS) as params:
                await self.bot.http.send_message(self.bot.config.game.gm_log_channel, params=params)
        except Exception:
            self.bot.logger.exception("Could not log the possession to the GM log channel")


class Possession(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        possession_ids = getattr(getattr(bot.config, "ids", None), "possession", {}) or {}
        self.ping_role_id = possession_ids.get("ping_role_id", DEFAULT_PING_ROLE_ID)

    def cog_unload(self):
        if self.session and self.session.task:
            self.session.task.cancel()

    def _vessel_list(self):
        return "\n".join(
            f"{v['emoji']} `{key}`: **{upper_first(v['name'])}** ({v['god']}), "
            f"voiced to you by {v['underling']['name']}, {v['underling']['title']}"
            for key, v in VESSELS.items()
        )

    @is_gm()
    @commands.command(hidden=True, brief="Possess a vessel and fight the raiders yourself")
    async def possess(
        self,
        ctx,
        channel: Optional[discord.TextChannel] = None,
        vessel: str = None,
        gold: int = 0,
        crate: str = "none",
        hp_per_raider: int = 0,
    ):
        """`[channel]` - where the vessel appears; defaults to this channel
        `<vessel>` - sepulchure, drakath or elysia
        `[gold]` - gold pool paid on victory: half to everyone, half to survivors
        `[crate]` - crate rarity for the most valiant raider, or none
        `[hp_per_raider]` - fixed vessel health per raider; 0 (default) scales it to the raid's damage

        You secretly control the boss. Your underling DMs you each turn; pick a target and a power.
        Anything you type in that DM is spoken aloud by the vessel. You are revealed at the end.
        Run it from a private channel with a target channel so no one sees you start it.

        Only Game Masters can use this command."""
        target = channel or ctx.channel
        remote = target.id != ctx.channel.id
        key = (vessel or "").lower()
        crate = (crate or "none").lower()
        problem = None
        bot_perms = target.permissions_for(target.guild.me)
        if self.session:
            problem = "A vessel is already possessed. Use `$unpossess` to break it first."
        elif key not in VESSELS:
            problem = f"Choose a vessel:\n{self._vessel_list()}"
        elif gold < 0:
            problem = "The gold pool cannot be negative."
        elif crate not in CRATE_TYPES + ("none",):
            problem = f"Crate must be one of: {', '.join(CRATE_TYPES)}, or none."
        elif hp_per_raider and not 1_000 <= hp_per_raider <= 1_000_000:
            problem = "Vessel health per raider must be 0 (auto) or between 1,000 and 1,000,000."
        elif remote and not target.permissions_for(ctx.author).view_channel:
            problem = "You cannot see that channel."
        elif not (bot_perms.view_channel and bot_perms.send_messages and bot_perms.embed_links):
            problem = f"I need to view, send messages and embed links in {target.mention}."
        if problem:
            return await ctx.send(problem, allowed_mentions=NO_MENTIONS)

        session = PossessionSession(
            self, ctx.author, target, key, gold, None if crate == "none" else crate, hp_per_raider or None
        )
        try:
            session.dm = await ctx.author.create_dm()
            greeting = discord.Embed(
                description=random.choice(session.underling["greeting"]), color=session.vessel["color"]
            )
            greeting.set_author(name=f"{session.underling['name']}, {session.underling['title']}")
            await session.dm.send(embed=greeting)
            role = target.guild.get_role(self.ping_role_id) if self.ping_role_id else None
            if role and not role.mentionable and not bot_perms.mention_everyone:
                await session.dm.send(
                    f"⚠️ I can't ping **{role.name}** in {target.mention}: the role isn't mentionable "
                    "and I lack Mention Everyone there. The event will run without the ping."
                )
        except discord.HTTPException:
            return await ctx.send(
                "Your underling cannot reach you. Open your DMs to this bot and try again.",
                delete_after=15,
            )
        if remote:
            await ctx.send(f"{session.vessel['emoji']} The vessel awakens in {target.mention}. Your underling awaits in your DMs.")
        else:
            try:
                await ctx.message.delete()  # Keep the Possessor's identity hidden.
            except discord.HTTPException:
                pass
        self.session = session
        session.task = asyncio.create_task(session.run())

    @is_gm()
    @commands.command(hidden=True, brief="Forcibly end an active possession")
    async def unpossess(self, ctx):
        """Break the active possession. No rewards are paid.

        Only Game Masters can use this command."""
        if not self.session or not self.session.task:
            return await ctx.send("Nothing is possessed right now.")
        self.session.task.cancel()
        await ctx.send("The possession has been broken.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Relay the Possessor's DMs through the vessel's mouth."""
        session = self.session
        if (
            session is None
            or message.guild is not None
            or message.author.id != session.gm.id
            or session.dm is None
            or message.channel.id != session.dm.id
        ):
            return
        content = message.content.strip()
        if not content or content.startswith(self.bot.config.bot.global_prefix):
            return
        now = asyncio.get_running_loop().time()
        if now - session.last_relay < RELAY_COOLDOWN_SECONDS:
            try:
                await message.add_reaction("⏳")
            except discord.HTTPException:
                pass
            return
        session.last_relay = now
        text = discord.utils.escape_mentions(discord.utils.escape_markdown(content[:RELAY_MAX_CHARS]))
        sent = await session._safe_send(
            session.channel, f"{session.vessel['emoji']} **{session.vessel['voice']}:** *{text}*"
        )
        try:
            await message.add_reaction("🗣️" if sent else "❌")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Possession(bot))
