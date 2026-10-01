"""GM Possession: a Game Master secretly drives a raid boss in real time.

The GM receives each turn's options in DMs, voiced by the vessel's underling,
and anything they type there is spoken aloud by the vessel. Raiders guard and
mend each other, spend one class signature per fight, and keep acting as
spirits after they fall. When the fight ends, the raiders vote on which Game
Master it was before the identity is revealed; correct guesses earn a crate
the Possessor picks.

Each turn is shown as a rendered card (card.py), with the plain embed as a
fallback. The vessel speaks through an embed with its portrait; the Possessor
picks the face by starting a message with <anger>, <sinister> or <laugh>.
Art lives in assets/possession/<vessel>/ (sinister, anger, laugh, underling).
"""

import asyncio
import random
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

import discord
from discord.ext import commands
from discord.http import handle_message_parameters

from classes.classes import from_string as class_from_string
from utils import misc as rpgtools
from utils.checks import is_gm

from . import card, ui
from .engine import (
    ABILITIES,
    CLASS_SIGNATURES,
    DREAD_MAX,
    MAX_RAIDERS,
    MAX_ROUNDS,
    MIN_RAIDERS,
    PLAYER_ACTIONS,
    SIGNATURES,
    SINGLE_TARGET_HITS as SINGLE_TARGET,
    SPIRIT_ACTIONS,
    UNBROKEN_RITE,
    Encounter,
    Raider,
    signature_for,
    split_gold,
)
from .lore import (
    ABILITY_RULES,
    PLAYER_ACTION_FLAVOR,
    SIGNATURE_LORE,
    SPIRIT_FLAVOR,
    VESSELS,
    line,
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
CARD_FILENAME = "possession_turn.jpg"
EMOTION_TAG = re.compile(r"^\s*<\s*([a-z]+)\s*>\s*", re.IGNORECASE)
EMOTION_ALIASES = {
    "anger": "anger", "angry": "anger", "rage": "anger",
    "sinister": "sinister", "smirk": "sinister", "calm": "sinister",
    "laugh": "laugh", "laughing": "laugh", "lol": "laugh",
}
BAR_LENGTH = 10       # Same bar length as the battle cog.
BAR_RAIDER_LIMIT = 8  # Above this many living raiders, bars give way to a compact list.
NO_MENTIONS = discord.AllowedMentions.none()

HOW_TO_PLAY = (
    "Destroy the vessel or complete the 🕯️ **Severance** before "
    f"{MAX_ROUNDS} turns pass. Each turn, pick one action:\n"
    "⚔️ **Strike** · 🛡️ **Guard** you or an ally · ✨ **Mend** · 🕯️ **Rite** · "
    "💫 **Signature** (your class power, once per fight)\n"
    "The fallen keep helping as spirits. Afterwards, guess which GM was the Possessor."
)
OUTCOME_TITLES = {
    "slain": "The vessel is destroyed!",
    "exorcised": "The Severance is complete!",
    "wiped": "The raid has fallen.",
    "withdrawn": "The possession endures.",
}


def upper_first(text):
    return text[:1].upper() + text[1:]


def plural(count, word, suffix="s"):
    return f"{count} {word}{'' if count == 1 else suffix}"


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


def speech_emotion(content):
    """Split a leading <emotion> tag off the Possessor's message: (emotion, text)."""
    match = EMOTION_TAG.match(content)
    if match and match.group(1).lower() in EMOTION_ALIASES:
        return EMOTION_ALIASES[match.group(1).lower()], content[match.end():].strip()
    return card.DEFAULT_EMOTION, content


def image_file(data, filename):
    return discord.File(BytesIO(data), filename=filename)


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
    def __init__(self, session):
        options = [
            discord.SelectOption(
                label=f"{crate.title()} crate", value=crate,
                emoji=discord.PartialEmoji.from_str(session.crate_emoji(crate)),
            )
            for crate in CRATE_TYPES
        ]
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
            f"*{view.session.underling['name']}:* {view.session.crate_label(view.choice)} each. "
            f"How generous, {view.session.underling['master']}."
        )


class CratePickView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=GUESS_PICK_SECONDS)
        self.session = session
        self.choice = None
        self.add_item(CratePickSelect(session))

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
        self.class_lines = {}     # user_id -> class line shown on the turn card
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

    def trait_label(self):
        trait = self.vessel["trait"]
        return f"{trait['emoji']} **{trait['name']}**"

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
    def crate_emoji(self, rarity):
        """The Crates cog's emoji for a rarity, so crates look the same everywhere."""
        emotes = getattr(self.bot.cogs.get("Crates"), "emotes", None)
        return getattr(emotes, rarity, "📦")

    def crate_label(self, rarity):
        return f"{self.crate_emoji(rarity)} **{rarity.title()} crate**"

    def hp_block(self, current, total, colour):
        """The battle cog's layout: an HP line over a 10-tile bar."""
        return (
            f"HP: {ui.compact(current)}/{ui.compact(total)} ({ui.percent(current, total)}%)\n"
            f"{ui.bar(current, total, BAR_LENGTH, colour)}"
        )

    def status_fields(self, embed):
        """Severance, Dread and the raid's damage bonus as three inline boxes."""
        enc = self.encounter
        embed.add_field(name="🕯️ Severance", value=f"{enc.rite}/{enc.rite_goal}", inline=True)
        dread = f"{enc.vessel.dread}/{DREAD_MAX}"
        if enc.charging:
            dread += " · gathering"
        elif enc.vessel.dread >= DREAD_MAX:
            dread += " · ready"
        embed.add_field(name="🌘 Dread", value=dread, inline=True)
        embed.add_field(name="⚔️ Damage bonus", value=f"+{enc.strike_bonus:.0%}", inline=True)

    def raider_title(self, raider):
        return f"{SIGNATURE_LORE[raider.signature][1]} {self.plain_name(raider.user_id)[:40]}"

    def compact_raider_line(self, raider, with_actions=False):
        """One raider as a single line; the Possessor also sees last actions and unused signatures."""
        line_ = (
            f"{SIGNATURE_LORE[raider.signature][1]} **{self.name(raider.user_id, 24)}** · "
            f"{ui.percent(raider.hp, raider.max_hp)}% ({ui.compact(raider.hp)})"
        )
        if with_actions and raider.user_id in self.encounter.last_actions:
            action = self.encounter.last_actions[raider.user_id]
            line_ += f" · last: {PLAYER_ACTION_FLAVOR.get(action, ('?',))[0]}"
        if with_actions and not raider.signature_used:
            line_ += " · 💫"
        return line_

    def add_raider_fields(self, embed):
        """One field per raider with an HP bar, like the battle cog; a compact list for big raids."""
        living = sorted(self.encounter.living(), key=lambda r: r.hp_ratio)
        if len(living) <= BAR_RAIDER_LIMIT:
            for raider in living:
                embed.add_field(
                    name=self.raider_title(raider),
                    value=self.hp_block(raider.hp, raider.max_hp, "blue"),
                    inline=False,
                )
            return
        lines = [self.compact_raider_line(raider) for raider in living]
        for index, chunk in enumerate(chunk_lines(lines)):
            embed.add_field(name=f"Raiders ({len(living)})" if index == 0 else "​", value=chunk, inline=False)

    def add_fallen_field(self, embed):
        fallen = self.encounter.fallen()
        if fallen:
            embed.add_field(
                name=f"👻 Fallen ({len(fallen)})",
                value=clip(", ".join(self.name(r.user_id, 24) for r in fallen)),
                inline=False,
            )

    # ---- art -----------------------------------------------------------
    def vessel_mood(self):
        enc = self.encounter
        if enc and enc.charging:
            return "laugh"
        if enc and enc.phase >= 3:
            return "anger"
        return card.DEFAULT_EMOTION

    def portrait_file(self, path, filename):
        """(attachment url, discord.File) for a portrait, or (None, None) if there's no art."""
        data = card.portrait_png(str(path)) if path else None
        if data is None:
            return None, None
        return f"attachment://{filename}", image_file(data, filename)

    def underling_embed(self, description, *, thumbnail=False):
        """An embed voiced by the underling, with their portrait when the art exists."""
        embed = discord.Embed(description=description, color=self.vessel["color"])
        url, file = self.portrait_file(card.underling_path(self.vessel_key), "underling.png")
        author = f"{self.underling['name']}, {self.underling['title']}"
        if url and thumbnail:
            embed.set_author(name=author)
            embed.set_thumbnail(url=url)
        else:
            embed.set_author(name=author, icon_url=url)
        return embed, file

    def speech_embed(self, text, emotion):
        """The vessel speaking aloud, with the matching portrait."""
        embed = discord.Embed(description=f"*{text}*", color=self.vessel["color"])
        embed.set_author(name=f"{self.vessel['emoji']} {self.vessel['voice']}")
        url, file = self.portrait_file(card.portrait_path(self.vessel_key, emotion), "speaker.png")
        if url:
            embed.set_thumbnail(url=url)
        return embed, file

    def card_data(self):
        enc = self.encounter
        vessel = enc.vessel
        warning = None
        if enc.charging:
            name = self.vessel["abilities"]["cataclysm"][0].upper()
            warning = f"{name} IS GATHERING  ·  {enc.interrupt_threshold:,.0f} damage breaks it, less weakens it"
        return {
            "accent": tuple(self.vessel["color"].to_bytes(3, "big")),
            "turn": enc.round_no,
            "max_turns": enc.max_rounds,
            "rite": enc.rite,
            "rite_goal": enc.rite_goal,
            "dread": vessel.dread,
            "dread_max": DREAD_MAX,
            "bonus": enc.strike_bonus,
            "warning": warning,
            "vessel": {
                "name": self.vessel["name"],
                "hp": vessel.hp,
                "max_hp": vessel.max_hp,
                "phase": ui.roman(enc.phase),
                "portrait": card.portrait_path(self.vessel_key, self.vessel_mood()),
            },
            "raiders": [
                {
                    "name": self.plain_name(raider.user_id),
                    "hp": raider.hp,
                    "max_hp": raider.max_hp,
                    "alive": raider.alive,
                    "portrait": card.class_art_path(self.class_lines.get(raider.user_id)),
                    "signature": SIGNATURE_LORE[raider.signature][0],
                    "signature_ready": not raider.signature_used,
                }
                for raider in enc.raiders.values()
            ],
        }

    def card_embed(self, deadline):
        """The slim embed that frames the rendered turn card."""
        enc = self.encounter
        description = f"Turn **{enc.round_no}/{enc.max_rounds}** · ends <t:{int(deadline.timestamp())}:R>"
        if enc.charging:
            name = self.vessel["abilities"]["cataclysm"][0]
            description += (
                f"\n⚠️ **{name} is gathering.** **{ui.compact(enc.interrupt_threshold)}** damage this turn "
                "breaks it; any less weakens it. Guard halves what lands."
            )
        embed = discord.Embed(description=description, color=self.vessel["color"])
        embed.set_image(url=f"attachment://{CARD_FILENAME}")
        footer = "No choice means Strike"
        if enc.fallen():
            footer += " · the fallen can Haunt, Echo or Foresee"
        embed.set_footer(text=footer)
        return embed

    async def send_turn(self, deadline, view):
        """Post the turn as a rendered card, or as the plain embed if rendering fails."""
        try:
            buffer = await asyncio.to_thread(card.render_turn_card, self.card_data())
        except Exception:
            self.bot.logger.exception("Possession turn card failed to render; using the embed")
            return await self.channel.send(embed=self.round_embed(deadline), view=view)
        return await self.channel.send(
            embed=self.card_embed(deadline), view=view, file=discord.File(buffer, filename=CARD_FILENAME)
        )

    # ---- embeds --------------------------------------------------------
    def join_embed(self, joined):
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])} has been possessed",
            description=f"{self.vessel['arrival']}\n\nThe vessel moves <t:{int(self.join_ends.timestamp())}:R>.",
            color=self.vessel["color"],
        )
        embed.add_field(name="How to play", value=HOW_TO_PLAY, inline=False)
        trait = self.vessel["trait"]
        embed.add_field(name=f"{trait['emoji']} This vessel: {trait['name']}", value=trait["rule"], inline=False)
        bounty = []
        if self.gold:
            bounty.append(f"💰 **${self.gold:,}** shared, more for survivors")
        if self.crate:
            bounty.append(f"{self.crate_label(self.crate)} for the most valiant")
        bounty.append("🎭 A crate for guessing the Possessor")
        embed.add_field(name="Bounty", value="\n".join(bounty), inline=False)
        roster = ", ".join(
            f"{SIGNATURE_LORE[self.signatures.get(member.id, 'last_stand')][1]} {self.name(member.id, 24)}"
            for member in joined
        )
        needed = MIN_RAIDERS - len(joined)
        if needed > 0:
            roster = f"{roster}\n*{needed} more needed.*" if roster else f"*{needed} more needed.*"
        embed.add_field(name=f"Raiders ({len(joined)}/{MAX_RAIDERS})", value=clip(roster), inline=False)
        embed.set_footer(text="Someone is watching through its eyes.")
        return embed

    def round_embed(self, deadline):
        enc = self.encounter
        phase = f" · Phase {ui.roman(enc.phase)}" if enc.phase > 1 else ""
        description = f"Turn **{enc.round_no}/{enc.max_rounds}**{phase} · ends <t:{int(deadline.timestamp())}:R>"
        if enc.charging:
            name = self.vessel["abilities"]["cataclysm"][0]
            description += (
                f"\n\n⚠️ **{name} is gathering.** It hits everyone when this turn ends.\n"
                f"**{ui.compact(enc.interrupt_threshold)}** damage this turn breaks it, and any less weakens it. "
                "Guard halves what lands."
            )
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])}",
            description=description,
            color=self.vessel["color"],
        )
        embed.add_field(name="Vessel", value=self.hp_block(enc.vessel.hp, enc.vessel.max_hp, "red"), inline=False)
        self.status_fields(embed)
        self.add_raider_fields(embed)
        self.add_fallen_field(embed)
        footer = "No choice means Strike"
        if enc.fallen():
            footer += " · the fallen can Haunt, Echo or Foresee"
        embed.set_footer(text=footer)
        return embed

    def prompt_embed(self, deadline):
        enc = self.encounter
        fields = self.fields()
        parts = [line(self.underling["prompt"], **fields)]
        if self.phase_note:
            parts.append(f"💥 *{self.vessel['phases'][self.phase_note]}*")
        for fallen in self.recent_deaths:
            parts.append(line(self.underling["kill"], fallen=f"**{self.name(fallen)}**"))
        if enc.charging:
            parts.append(
                f"{self.underling['charging']} They need **{ui.compact(enc.interrupt_threshold)}** "
                "damage this turn to break it; anything less only weakens it."
            )
        elif enc.rite >= enc.rite_goal / 2:
            parts.append(line(self.underling["rite_warning"], **fields))
        if enc.ability_ready("cataclysm"):
            parts.append(line(self.underling["dread_full"], **fields))
        embed = discord.Embed(description="\n\n".join(parts), color=self.vessel["color"])
        embed.set_author(name=f"{self.underling['name']}, {self.underling['title']}")
        embed.add_field(
            name=f"Vessel · Phase {ui.roman(enc.phase)}" if enc.phase > 1 else "Vessel",
            value=self.hp_block(enc.vessel.hp, enc.vessel.max_hp, "red"),
            inline=False,
        )
        self.status_fields(embed)
        lines = [self.compact_raider_line(r, with_actions=True) for r in sorted(enc.living(), key=lambda r: r.hp_ratio)]
        for index, chunk in enumerate(chunk_lines(lines)):
            embed.add_field(
                name=f"Raiders · answer <t:{int(deadline.timestamp())}:R>" if index == 0 else "​",
                value=chunk,
                inline=False,
            )
        if enc.charging:
            embed.set_footer(text="It falls on its own this turn. Type here to speak as the vessel.")
            return embed
        powers = []
        for ability, spec in ABILITIES.items():
            cooldown = enc.vessel.cooldowns.get(ability, 0)
            if cooldown:
                status = f" · *ready in {cooldown}*"
            elif enc.phase < spec.get("phase", 1):
                status = f" · *Phase {ui.roman(spec['phase'])}*"
            elif not enc.ability_ready(ability):
                status = f" · *needs {DREAD_MAX} Dread*"
            else:
                status = ""
            powers.append(f"{self.ability_label(ability)} · {ABILITY_RULES[ability]}{status}")
        powers.append(f"{self.trait_label()} · passive · {self.vessel['trait']['gm']}")
        embed.add_field(name="Powers", value=clip("\n".join(powers)), inline=False)
        embed.set_footer(
            text="Pick a target, then a power (no target = weakest) · 💫 = Signature unused · "
                 "type here to speak as the vessel; start with <anger>, <sinister> or <laugh> to change its face"
        )
        return embed

    def _signature_line(self, uid, key, target_id, amount):
        name, emoji, _rule, _story = SIGNATURE_LORE[key]
        who = self.name(uid)
        target = "themselves" if target_id == uid else self.name(target_id)
        detail = {
            "bulwark": "(everyone takes half damage)",
            "hunters_mark": "(+30% damage for 2 turns)",
            "unbroken_circle": f"(+{UNBROKEN_RITE} Severance, circle sealed)",
            "sunder": f"for **{ui.compact(amount)}** (+10% damage taken for the rest of the fight)",
            "pilfer": f"stealing **{ui.compact(amount)}** Dread",
            "ballad": f"healing the raid for **{ui.compact(amount)}**",
            "gift": f"healing {target} for **{ui.compact(amount)}**",
            "resurrection": f"raising **{target}**",
            "paragons_will": f"for **{ui.compact(amount)}**, plus a mend and a chant",
        }.get(key, f"for **{ui.compact(amount)}**")
        return f"{emoji} {who} used **{name}** {detail}"

    def _dominate_line(self, dom):
        name, emoji, _narration = self.vessel["abilities"]["dominate"]
        who = self.name(dom["target_id"])
        amount = dom.get("amount", 0)
        effect = {
            "strike": f"their strike hit {self.name(dom.get('victim_id'))} for **{ui.compact(amount or 0)}**",
            "mend": f"their heal went to the vessel (+{ui.compact(amount)})" if amount else "their heal fizzled",
            "rite": "their chant reversed the Severance (-1)" if amount else "their chant fell silent",
            "guard": "their guard dropped",
            "signature": "their Signature was wasted",
        }.get(dom.get("action"), "nothing happened")
        return f"{emoji} **{name}** seized {who}: {effect}."

    def report_embed(self, report, improvised):
        enc = self.encounter
        ability_name, emoji, _narration = self.vessel["abilities"][report.ability]
        raid, vessel = [], []

        if report.dominated:
            raid.append(self._dominate_line(report.dominated))
        if report.scrambled:
            raid.append(f"{self.trait_label()}: the strings tangle everyone, and every chosen action was shuffled!")
        for uid, key, target_id, amount in report.signatures:
            raid.append(self._signature_line(uid, key, target_id, amount))
        strikes = sorted(
            ((uid, amount) for uid, amount, tag in report.strikes if tag is None), key=lambda s: -s[1]
        )
        if strikes:
            total = ui.compact(sum(amount for _uid, amount in strikes))
            halved = " (halved by the ward)" if report.ward else ""
            if len(strikes) <= 4:
                named = " · ".join(f"{self.name(uid)} {ui.compact(amount)}" for uid, amount in strikes)
                raid.append(f"⚔️ {named}" + (f" (**{total}**)" if len(strikes) > 1 else "") + halved)
            else:
                top_uid, top = strikes[0]
                raid.append(
                    f"⚔️ {len(strikes)} strikes for **{total}**{halved} · top: {self.name(top_uid)} {ui.compact(top)}"
                )
        shields = [(guard, ward) for guard, ward in report.guards if guard != ward]
        braced = len(report.guards) - len(shields)
        guard_bits = [f"{self.name(guard)} guarded {self.name(ward)}" for guard, ward in shields[:3]]
        if len(shields) > 3:
            guard_bits.append(f"+{len(shields) - 3} more")
        if braced:
            guard_bits.append(f"{braced} braced")
        if guard_bits:
            raid.append("🛡️ " + " · ".join(guard_bits))
        mends = [(h, t, a) for h, t, a in report.mends if a > 0]
        if mends:
            bits = [
                f"{self.name(h)} healed {'themselves' if t == h else self.name(t)} for {ui.compact(a)}"
                for h, t, a in mends[:3]
            ]
            if len(mends) > 3:
                bits.append(f"+{len(mends) - 3} more")
            raid.append("✨ " + " · ".join(bits))
        if report.haunts:
            raid.append(f"👻 {plural(report.haunts, 'spirit')} drained **{report.haunt_drain}** Dread")
        if report.echoes:
            raid.append(f"🔔 {plural(report.echoes, 'spirit')} echoed the chant")
        if report.rite_veiled:
            ward_name, ward_emoji, _narration = self.vessel["abilities"]["ward"]
            raid.append(
                f"{ward_emoji} **{ward_name}** smothered the chant: **{report.rite_veiled}** Severance lost "
                f"({self.trait_label()})."
            )
        if report.total_rite:
            reached = enc.rite + (report.total_rite if report.rite_broken else 0)
            unheard = f" · {report.rite_unheard} unheard" if report.rite_unheard else ""
            raid.append(f"🕯️ Severance **+{report.total_rite}** ({reached}/{enc.rite_goal}){unheard}")
        if report.phase_change == 2:
            raid.append("💥 **Phase II:** the vessel's armor breaks.")
        elif report.phase_change == 3:
            raid.append(f"💥 **Phase III:** the vessel grows desperate and unlocks {self.ability_label('execute')}.")

        if report.charge_started:
            vessel.append(f"{emoji} **{ability_name}** is gathering. It hits everyone at the end of next turn.")
        elif report.releasing and report.interrupted:
            vessel.append(f"💥 **{ability_name}** was broken by {ui.compact(report.total_strike)} damage!")
        elif report.releasing and report.blast_scale < 1:
            pilfer = f" ({plural(report.pilfers, 'Pilfer')} halved it)" if report.pilfers else ""
            vessel.append(
                f"💥 The raid weakened **{ability_name}** to **{report.blast_scale:.0%}** strength{pilfer}."
            )
        elif report.ability == "ward" and not enc.victorious:
            vessel.append(f"{emoji} **{ability_name}** halved the raid's damage.")
        if report.hits:
            if report.ability in SINGLE_TARGET:
                uid, amount, halved, shielded = report.hits[0]
                note = f" (shielding {self.name(shielded)})" if shielded else " (guarded)" if halved else ""
                text = f"{emoji} **{ability_name}** hit {self.name(uid)} for **{ui.compact(amount)}**{note}"
                if report.vessel_healed:
                    text += f" and healed the vessel for {ui.compact(report.vessel_healed)}"
                vessel.append(text)
            else:
                total = sum(amount for _uid, amount, _h, _s in report.hits)
                vessel.append(f"{emoji} **{ability_name}** hit {plural(len(report.hits), 'raider')} for **{ui.compact(total)}**")
                parts = [
                    f"{self.name(uid, 16)} {ui.compact(amount)}{' 🛡️' if halved else ''}"
                    for uid, amount, halved, _shielded in report.hits[:8]
                ]
                more = f" · +{len(report.hits) - 8} more" if len(report.hits) > 8 else ""
                vessel.append("╰ " + " · ".join(parts) + more)
        if report.penance:
            parts = " · ".join(f"{self.name(uid, 16)} {ui.compact(amount)}" for uid, amount in report.penance[:8])
            vessel.append(f"{self.trait_label()}: the chanters are punished: {parts}")
        for uid in report.executed:
            vessel.append(f"⚰️ {self.name(uid)} was executed.")
        if report.rite_broken:
            names = ", ".join(self.name(uid) for uid in report.rite_broken)
            vessel.append(f"💥 The circle shattered on {names}. This turn's Severance was lost.")
        for uid in report.revived:
            vessel.append(f"🔆 {self.name(uid)} returned to the fight.")
        for uid in report.deaths:
            vessel.append(f"☠️ {self.name(uid)} fell.")
        if report.feasted:
            vessel.append(f"{self.trait_label()}: the vessel feeds on the fallen (+{ui.compact(report.feasted)} HP).")
        if not (report.dominated or report.hits or report.charge_started or report.releasing
                or report.ability == "ward" or report.penance) and not enc.outcome:
            vessel.append("The vessel falters.")

        if report.charge_started:
            title = f"{ability_name} gathers…"
        elif report.releasing:
            title = f"{ability_name}" + (" is broken!" if report.interrupted else "")
        else:
            title = ability_name
        embed = discord.Embed(
            title=f"Turn {report.round_no} · {emoji} {title}",
            description=clip("\n".join(raid + ([""] if raid and vessel else []) + vessel) or "Nothing happens.", 4000),
            color=self.vessel["color"],
        )
        vessel_state = enc.vessel
        footer = (
            f"Vessel {ui.percent(vessel_state.hp, vessel_state.max_hp)}% · "
            f"Severance {enc.rite}/{enc.rite_goal} · Dread {vessel_state.dread}"
        )
        if improvised:
            footer = f"{self.underling['name']} chose for the silent Possessor · {footer}"
        embed.set_footer(text=footer)
        return embed

    def honours(self):
        raiders = list(self.encounter.raiders.values())
        lines = []
        for attr, emoji, title, fmt in (
            ("dealt", "⚔️", "Top damage", lambda r: ui.compact(r.dealt)),
            ("healed", "✨", "Top healer", lambda r: ui.compact(r.healed)),
            ("rites", "🕯️", "Most chants", lambda r: str(r.rites)),
            ("absorbed", "🛡️", "Bodyguard", lambda r: f"{ui.compact(r.absorbed)} taken for others"),
            ("spirit_acts", "👻", "Restless spirit", lambda r: f"{r.spirit_acts} acts"),
        ):
            best = max(raiders, key=lambda r: getattr(r, attr))
            if getattr(best, attr) > 0:
                lines.append(f"{emoji} {title}: **{self.name(best.user_id, 24)}** ({fmt(best)})")
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
            trait=self.vessel["trait"]["key"],
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
                lines = class_lines(profile["class"])
                signature = signature_for(lines)
                self.class_lines[member.id] = next(
                    (line_ for line_ in lines if CLASS_SIGNATURES.get(line_) == signature), lines[0] if lines else None
                )
                raiders.append(Raider(
                    member.id, member.display_name, hp, hp, float(damage), float(armor), signature=signature,
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
        public = await self.send_turn(deadline, raider_view)
        panel = None if enc.charging else PossessorPanel(self)
        prompt = self.prompt_embed(deadline)
        url, file = self.portrait_file(card.underling_path(self.vessel_key), "underling.png")
        if url:
            prompt.set_author(name=prompt.author.name, icon_url=url)
        extras = {"view": panel} if panel else {}
        if file:
            extras["file"] = file
        private = await self.say_to_gm(embed=prompt, **extras)
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
            embed, file = self.underling_embed(line(self.underling["improvise_public"]))
            await self._safe_send(self.channel, embed=embed, **({"file": file} if file else {}))
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
            description=f"*{self.vessel['endings'][enc.outcome]}*",
            color=self.vessel["color"],
        )
        embed.add_field(name="Turns", value=str(enc.round_no), inline=True)
        embed.add_field(name="Survivors", value=f"{len(survivors)}/{len(participants)}", inline=True)
        embed.add_field(name="Vessel HP", value=f"{ui.percent(enc.vessel.hp, enc.vessel.max_hp)}%", inline=True)
        if mvp and mvp.valor(enc.vessel.attack) > 0:
            feats = [
                text for value, text in (
                    (mvp.dealt, f"{ui.compact(mvp.dealt)} damage"),
                    (mvp.healed, f"{ui.compact(mvp.healed)} healed"),
                    (mvp.rites, plural(mvp.rites, "chant")),
                    (mvp.absorbed, f"{ui.compact(mvp.absorbed)} taken for others"),
                    (mvp.revives, plural(mvp.revives, "revive")),
                ) if value
            ]
            embed.add_field(
                name="Most Valiant",
                value=f"{SIGNATURE_LORE[mvp.signature][1]} **{self.name(mvp.user_id)}** · " + " · ".join(feats),
                inline=False,
            )
        honours = self.honours()
        if honours:
            embed.add_field(name="Honours", value=clip("\n".join(honours)), inline=False)
        reward_lines = []
        if payouts:
            if survivors and min(payouts.values()) != max(payouts.values()):
                reward_lines.append(
                    f"💰 **${min(payouts.values()):,}** each, **${max(payouts.values()):,}** for survivors"
                )
            else:
                reward_lines.append(f"💰 **${max(payouts.values()):,}** each")
        if crate_winner:
            reward_lines.append(f"{self.crate_label(self.crate)} for **{self.name(crate_winner)}**")
        if reward_lines:
            embed.add_field(name="Rewards", value="\n".join(reward_lines), inline=False)
        embed.set_footer(text="Whose will was it? Vote below.")
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
                "One of these Game Masters was controlling the vessel. "
                f"Voting closes <t:{int(deadline.timestamp())}:R>.\n"
                "Guess right and you get a crate, picked by the Possessor. "
                "Only this fight's raiders can vote, and you can change your vote."
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
            mark = "" if hidden else "✅ " if candidate == self.gm.id else "❌ "
            label = discord.utils.escape_markdown(names.get(candidate, "someone"))
            who = ", ".join(self.name(uid, 20) for uid in voters) or "no one"
            lines.append(f"{mark}**{label}** · {plural(len(voters), 'vote')}: {who}")
        silent = [uid for uid in participants if uid not in guesses]
        if silent:
            lines.append(f"*Didn't vote: {', '.join(self.name(uid, 20) for uid in silent)}*")
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
                embed.add_field(name="Votes" if index == 0 else "​", value=chunk, inline=False)
            if correct:
                value = (
                    f"**{len(correct)}/{len(guesses)}** saw through the vessel.\n"
                    "📦 The Possessor is choosing their reward…"
                )
            else:
                value = f"None of the {plural(len(guesses), 'guess', 'es')} were right. The Possessor keeps their secret."
            embed.add_field(name="Verdict", value=value, inline=False)
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
                f"Choose within {GUESS_PICK_SECONDS // 60} minutes, or they each get a "
                f"{self.crate_label(GUESS_FALLBACK_CRATE)}."
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
            f"picked by {discord.utils.escape_markdown(self.gm.display_name)}" if chosen
            else "the Possessor didn't pick in time"
        )
        await self._safe_send(
            self.channel, clip(f"{self.crate_label(crate)} for {names} ({source}).", 2000)
        )
        return correct

    async def _log(self, enc, payouts, crate_winner, guesses, correct, guess_crate):
        crate_text = f", {self.crate} crate to {crate_winner}" if crate_winner else ""
        content = (
            f"**{self.gm}** possessed {self.vessel['name']} in <#{self.channel.id}>. "
            f"Outcome: **{enc.outcome}** after {plural(enc.round_no, 'turn')}, "
            f"{plural(len(enc.raiders), 'raider')}. "
            f"Paid **${sum(payouts.values()):,}** to {plural(len(payouts), 'player')}{crate_text}. "
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
            greeting, portrait = session.underling_embed(random.choice(session.underling["greeting"]), thumbnail=True)
            trait = session.vessel["trait"]
            greeting.add_field(name=f"{trait['emoji']} Your vessel's gift: {trait['name']}", value=trait["gm"], inline=False)
            greeting.add_field(
                name="Speaking as the vessel",
                value="Anything you type here, the vessel says aloud. Start a message with `<anger>`, "
                      "`<sinister>` or `<laugh>` to choose its face; with no tag it looks sinister.",
                inline=False,
            )
            await session.dm.send(embed=greeting, **({"file": portrait} if portrait else {}))
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
        emotion, content = speech_emotion(content)
        if not content:
            return
        text = discord.utils.escape_mentions(discord.utils.escape_markdown(content[:RELAY_MAX_CHARS]))
        embed, portrait = session.speech_embed(text, emotion)
        sent = await session._safe_send(session.channel, embed=embed, **({"file": portrait} if portrait else {}))
        try:
            await message.add_reaction("🗣️" if sent else "❌")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Possession(bot))
