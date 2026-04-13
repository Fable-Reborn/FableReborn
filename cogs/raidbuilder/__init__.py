import asyncio
import copy
import json
import random as randomm
import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, View

from classes.converters import IntGreaterThan
from utils.checks import is_gm, is_god
from utils.i18n import _
from utils.joins import JoinView


@dataclass(frozen=True)
class SkeletonOptionGroup:
    title: str
    summary: str
    options: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RaidModeSpec:
    key: str
    display_name: str
    skeleton: str
    summary: str
    legacy_command: str
    legacy_usage: str
    option_groups: tuple[SkeletonOptionGroup, ...] = field(default_factory=tuple)


MODE_SPECS: dict[str, RaidModeSpec] = {
    "good": RaidModeSpec(
        key="good",
        display_name="Good",
        skeleton="trial",
        summary=(
            "Elysia-style elimination trials with rotating phases, themed events, "
            "and survivor pressure instead of a boss HP race."
        ),
        legacy_command="goodspawn",
        legacy_usage="$goodspawn",
        option_groups=(
            SkeletonOptionGroup(
                title="Phase Flow",
                summary="Trial skeletons rotate through ceremonial phases that define the event table.",
                options=("day", "night", "custom phases", "phase weights"),
            ),
            SkeletonOptionGroup(
                title="Resolution",
                summary="Each phase resolves one or more participant trials with survival-based outcomes.",
                options=("event pools", "success odds", "miracle saves", "elimination rules"),
            ),
            SkeletonOptionGroup(
                title="Escalation",
                summary="Later rounds can tighten the field without changing the skeleton itself.",
                options=("final showdown", "rarity events", "stacking danger", "blessings"),
            ),
        ),
    ),
    "evil": RaidModeSpec(
        key="evil",
        display_name="Evil",
        skeleton="ritual",
        summary=(
            "Sepulchure-style role raid with Champion, Priest, Followers, a Guardian, "
            "ritual progress, AI fallback, and takeover pressure."
        ),
        legacy_command="evilspawn",
        legacy_usage="$evilspawn",
        option_groups=(
            SkeletonOptionGroup(
                title="Roles",
                summary="Ritual skeletons are asymmetric and centered on leader/support jobs.",
                options=("leader slots", "follower roles", "AI fallback", "takeovers"),
            ),
            SkeletonOptionGroup(
                title="Turn Engine",
                summary="This framework resolves role turns, resource costs, and support synergy.",
                options=("turn order", "mana", "cooldowns", "directive control"),
            ),
            SkeletonOptionGroup(
                title="Enemy Pressure",
                summary="Guardian or boss phases react to ritual progress and player decisions.",
                options=("phase table", "progress rules", "punishments", "win conditions"),
            ),
        ),
    ),
    "chaos": RaidModeSpec(
        key="chaos",
        display_name="Chaos",
        skeleton="attrition",
        summary=(
            "Drakath-style attrition boss raid with a real boss HP pool, flat follower health, "
            "random events, taunts, and cinematic pressure."
        ),
        legacy_command="chaosspawn",
        legacy_usage="$chaosspawn <boss_hp>",
        option_groups=(
            SkeletonOptionGroup(
                title="Boss Loop",
                summary="Attrition skeletons revolve around repeated boss attack and raid retaliation cycles.",
                options=("boss HP", "attack tables", "crit tables", "phase thresholds"),
            ),
            SkeletonOptionGroup(
                title="Chaos Events",
                summary="Swing events add volatility without introducing asymmetric roles.",
                options=("heals", "pulses", "mutations", "random wipes"),
            ),
            SkeletonOptionGroup(
                title="Presentation",
                summary="This framework leans on atmosphere and pacing to sell the fight.",
                options=("taunts", "health bars", "survivor rewards", "chat reactions"),
            ),
        ),
    ),
}


GOOD_MEDIA_SLOTS = (
    ("intro", "Intro", "Opening join embed art."),
    ("phase", "Phase", "Phase transition embed art."),
    ("result", "Result", "Per-trial outcome embed art."),
    ("victory", "Victory", "Final winner embed art."),
)

CHAOS_MEDIA_SLOTS = (
    ("intro", "Intro", "Opening join embed art."),
    ("boss_turn", "Boss Turn", "Boss strike embed art."),
    ("raid_turn", "Raid Turn", "Raid retaliation embed art."),
    ("victory", "Victory", "Final victory embed art."),
)

EVIL_MEDIA_SLOTS = (
    ("intro", "Intro", "Opening ritual embed art."),
    ("prompts", "Prompts", "Leader and follower prompt embed art."),
    ("guardian", "Guardian", "Guardian phase and attack embed art."),
    ("status", "Status", "Turn summary embed art."),
    ("victory", "Victory", "Final ritual outcome embed art."),
)

RITUAL_PROMPT_SLOTS = (
    ("follower", "Follower Prompt", "Follower DM prompt title and description."),
    ("champion", "Champion Prompt", "Champion DM prompt title and description."),
    ("priest", "Priest Prompt", "Priest DM prompt title and description."),
)

RITUAL_COUNTDOWN_SLOTS = (
    ("ten_minutes", "10 Minutes", 600, "**The shadows deepen... The ritual begins in 10 minutes.**"),
    ("five_minutes", "5 Minutes", 300, "**Whispers fill the air... 5 minutes remain.**"),
    ("two_minutes", "2 Minutes", 120, "**Your heart pounds... 2 minutes until the ritual commences.**"),
    ("one_minute", "1 Minute", 60, "**A chill runs down your spine... 1 minute left.**"),
    ("thirty_seconds", "30 Seconds", 30, "**The ground trembles... 30 seconds.**"),
    ("ten_seconds", "10 Seconds", 10, "**Darkness engulfs you... 10 seconds.**"),
)


def _ritual_countdown_defaults() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "remaining": remaining,
            "message": message,
        }
        for key, label, remaining, message in RITUAL_COUNTDOWN_SLOTS
    ]


def _blank_media() -> dict[str, str]:
    return {"image_url": "", "thumbnail_url": ""}


def _good_presentation() -> dict[str, Any]:
    return {
        "colors": {
            "intro": "#3498DB",
            "phase": "#F1C40F",
            "success": "#2ECC71",
            "failure": "#E74C3C",
            "victory": "#5DADE2",
        },
        "media": {
            "intro": _blank_media(),
            "phase": _blank_media(),
            "result": _blank_media(),
            "victory": _blank_media(),
        },
    }


def _chaos_presentation() -> dict[str, Any]:
    return {
        "colors": {
            "intro": "#8E44AD",
            "boss_turn": "#C0392B",
            "raid_turn": "#F1C40F",
            "victory": "#F39C12",
            "defeat": "#7F1D1D",
        },
        "media": {
            "intro": _blank_media(),
            "boss_turn": _blank_media(),
            "raid_turn": _blank_media(),
            "victory": _blank_media(),
        },
    }


def _evil_presentation() -> dict[str, Any]:
    return {
        "colors": {
            "intro": "#992D22",
            "prompt": "#8E44AD",
            "status": "#7B241C",
            "victory": "#27AE60",
            "danger": "#C0392B",
        },
        "media": {
            "intro": _blank_media(),
            "prompts": _blank_media(),
            "guardian": _blank_media(),
            "status": _blank_media(),
            "victory": _blank_media(),
        },
        "labels": {
            "champion": "Champion",
            "priest": "Priest",
            "followers": "Followers",
            "guardian": "Guardian",
        },
        "prompts": {
            "follower": {
                "title": "Followers",
                "description": "Choose how you support the ritual this turn.",
            },
            "champion": {
                "title": "Champion",
                "description": "Choose how the Champion acts this turn.",
            },
            "priest": {
                "title": "Priest",
                "description": "Choose how the Priest shapes the ritual this turn.",
            },
        },
        "texts": {
            "no_valid": "No valid followers answered the ritual.",
            "collapse": "The {guardian_label} collapses and the ritual surges forward.",
            "respawn": "The {guardian_label} rises again as **{phase_name}**.",
            "champion_slain": "The {champion_label} is slain before the ritual can recover.",
            "champion_fall": "The {champion_label} falls, and the ritual collapses with them.",
            "success": "The ritual completes successfully. Sepulchure answers the call of **{definition_name}**.",
            "stall": "The ritual stalls at **{progress}/{win_progress}** progress and the {guardian_label} endures.",
            "turn_prompt": "It's {player}'s turn. Check DMs.",
            "followers_summary_empty": "No follower contributions this turn.",
        },
    }


def _champion_action_defaults() -> dict[str, dict[str, Any]]:
    return {
        "Smite": {
            "effect": "damage",
            "display_name": "Smite",
            "description": "Damage the Guardian.",
            "result_text": "The {champion_label} smites the {guardian_label} for **{damage}** damage.",
        },
        "Heal": {
            "effect": "heal",
            "display_name": "Heal",
            "description": "Recover HP.",
            "result_text": "The {champion_label} restores **{heal_amount}** HP.",
        },
        "Haste": {
            "effect": "haste",
            "display_name": "Haste",
            "description": "Advance ritual progress and become vulnerable.",
            "result_text": "The {champion_label} drives the ritual forward and leaves themselves exposed.",
        },
        "Defend": {
            "effect": "defend",
            "display_name": "Defend",
            "description": "Reduce incoming damage.",
            "result_text": "The {champion_label} braces for the next assault.",
        },
        "Sacrifice": {
            "effect": "sacrifice",
            "display_name": "Sacrifice",
            "description": "Trade HP for ritual progress.",
            "result_text": "The {champion_label} offers **{self_damage}** HP to advance the ritual.",
        },
    }


def _build_good_starter() -> dict[str, Any]:
    return {
        "id": "good_trial_remaster",
        "mode": "good",
        "skeleton": "trial",
        "runtime": "native",
        "status": "published",
        "name": "Elysian Trial Remaster",
        "description": "A data-driven Elysia trial that keeps the day and night elimination structure.",
        "config": {
            "join_timeout": 900,
            "min_survivors": 1,
            "max_rounds": 40,
            "phase_delay": 5,
            "result_delay": 3,
            "eligibility": {"god": "Elysia"},
            "announce": {
                "title": "Champions of Compassion",
                "description": (
                    "Champions of compassion, take your stand. Day and night will test the hearts "
                    "of Elysia's faithful until only the worthiest remain."
                ),
                "join_label": "Join the trial!",
                "joined_message": "You joined the trial.",
            },
            "presentation": _good_presentation(),
            "winner_text": "{winner} endure the final ordeal beneath Elysia's light.",
            "phases": [
                {
                    "key": "day",
                    "weight": 1,
                    "title": "It turns day",
                    "description": (
                        "As the sun's golden rays grace the horizon, renewal spreads across the land."
                    ),
                    "events": [
                        {
                            "text": "Extend a Healing Hand",
                            "success_rate": 80,
                            "win_text": "Your compassionate efforts brought healing and solace.",
                            "lose_text": "Your healing touch falters when the trial demands more of you.",
                        },
                        {
                            "text": "Ease Emotional Burdens",
                            "success_rate": 50,
                            "win_text": "Your empathy mends a wounded heart before the crowd.",
                            "lose_text": "Your words fail to bridge the pain before you.",
                        },
                        {
                            "text": "Kindness in Action",
                            "success_rate": 60,
                            "win_text": "Your selfless actions ripple outward with visible grace.",
                            "lose_text": "Your kindness does not fully land in the moment that mattered.",
                        },
                    ],
                },
                {
                    "key": "night",
                    "weight": 1,
                    "title": "It turns night",
                    "description": (
                        "The world is wrapped in quiet stars, and mercy must now survive the dark."
                    ),
                    "events": [
                        {
                            "text": "Guiding Light of Compassion",
                            "success_rate": 30,
                            "win_text": "You bring light to a darkened soul under the moon.",
                            "lose_text": "Your light does not reach far enough through the night.",
                            "mercy_chance": 10,
                        },
                        {
                            "text": "Healing Moon's Embrace",
                            "success_rate": 45,
                            "win_text": "The moon magnifies your healing touch.",
                            "lose_text": "Unseen forces hinder your attempt to heal.",
                        },
                        {
                            "text": "Stellar Harmonies of Renewal",
                            "success_rate": 20,
                            "win_text": "The stars answer and renewal pours through the sky.",
                            "lose_text": "The harmonies remain distant, and the chance is lost.",
                            "mercy_chance": 5,
                        },
                    ],
                },
            ],
        },
    }


def _build_evil_starter() -> dict[str, Any]:
    return {
        "id": "evil_ritual_remaster",
        "mode": "evil",
        "skeleton": "ritual",
        "runtime": "native",
        "status": "published",
        "name": "Infernal Ritual Remaster",
        "description": "A configurable Sepulchure ritual using shared leader AI and DM decision buttons.",
        "config": {
            "join_timeout": 900,
            "decision_timeout": 90,
            "allow_ai_fallback": True,
            "eligibility": {"god": "Sepulchure"},
            "announce": {
                "title": "The Eclipse Begins",
                "description": (
                    "The moon turns blood red as a forgotten temple rises from the dark. "
                    "Followers may serve as leaders or lend their will as ritualists."
                ),
                "leader_label": "Join as Champion/Priest",
                "follower_label": "Join as Follower Only",
                "leader_joined_message": "You joined as a potential leader.",
                "follower_joined_message": "You joined as a follower.",
                "countdown_messages": _ritual_countdown_defaults(),
                "start_message": "**💀 The ritual begins! The Guardian awakens from its slumber... 💀**",
                "eligibility_message": "**Gathering the faithful... checking dm eligibility this may take awhile**",
            },
            "presentation": _evil_presentation(),
            "ritual": {
                "start_progress": 0,
                "win_progress": 100,
                "max_turns": 15,
                "guardian_collapse_progress": 10,
            },
            "champion": {
                "max_hp": 1500,
                "base_damage": 700,
                "heal_amount": 200,
                "haste_progress": 15,
                "haste_cooldown": 3,
                "sacrifice_hp": 350,
                "sacrifice_progress": 18,
                "defend_multiplier": 0.6,
                "vulnerable_multiplier": 1.25,
                "actions": _champion_action_defaults(),
            },
            "priest": {
                "max_mana": 100,
                "mana_regen": 10,
                "actions": {
                    "Bless": {
                        "display_name": "Bless",
                        "description": "Empower the Champion with shadow-wreathed force.",
                        "result_text": "The {priest_label} invokes **{action_name}** and grants **{damage_boost}** bonus damage to the {champion_label}.",
                        "mana_cost": 20,
                        "damage_boost": 200,
                    },
                    "Barrier": {
                        "display_name": "Barrier",
                        "description": "Wrap the Champion in protective shadow.",
                        "result_text": "The {priest_label} casts **{action_name}**, raising **{shield}** shield around the {champion_label}.",
                        "mana_cost": 30,
                        "shield": 250,
                    },
                    "Curse": {
                        "display_name": "Curse",
                        "description": "Weaken the Guardian's damage output.",
                        "result_text": "The {priest_label} brands the {guardian_label} with **{action_name}**, reducing its fury.",
                        "mana_cost": 25,
                        "guardian_damage_down": 0.25,
                    },
                    "Revitalize": {
                        "display_name": "Revitalize",
                        "description": "Restore the Champion's vitality.",
                        "result_text": "The {priest_label} channels **{action_name}** to restore **{heal}** HP to the {champion_label}.",
                        "mana_cost": 20,
                        "heal": 300,
                    },
                    "Channel": {
                        "display_name": "Channel",
                        "description": "Direct raw darkness into the ritual.",
                        "result_text": "The {priest_label} pours **{action_name}** into the ritual for **{progress}** progress.",
                        "mana_cost": 15,
                        "progress": 12,
                    },
                },
            },
            "followers": {
                "actions": {
                    "Boost Ritual": {
                        "display_name": "Boost Ritual",
                        "description": "Push the ceremony forward in a coordinated surge.",
                        "progress": 2,
                        "cap_total": 8,
                    },
                    "Protect Champion": {
                        "display_name": "Protect Champion",
                        "description": "Wrap the Champion in protective shadow.",
                        "shield": 50,
                    },
                    "Empower Priest": {
                        "display_name": "Empower Priest",
                        "description": "Amplify the Priest's restorative arts.",
                        "healing_boost": 0.1,
                    },
                    "Sabotage Guardian": {
                        "display_name": "Sabotage Guardian",
                        "description": "Wear down the Guardian's assault.",
                        "guardian_damage_down": 0.1,
                    },
                    "Chant": {
                        "display_name": "Chant",
                        "description": "Add steady momentum to the ritual circle.",
                        "progress": 1,
                    },
                    "Heal Champion": {
                        "display_name": "Heal Champion",
                        "description": "Restore the Champion with lesser rites.",
                        "heal": 50,
                    },
                }
            },
            "guardian": {
                "max_hp": 5000,
                "respawn_hp_ratio": 0.45,
                "phases": [
                    {
                        "threshold": 0,
                        "name": "The Sentinel",
                        "description": "A towering sentinel steps from ancient shadow.",
                        "abilities": ["strike", "shield", "purify"],
                    },
                    {
                        "threshold": 35,
                        "name": "The Corrupted",
                        "description": "The Guardian twists into a darker and faster shape.",
                        "abilities": ["strike", "corrupting_blast", "fear_aura", "purify"],
                    },
                    {
                        "threshold": 70,
                        "name": "The Abyssal Horror",
                        "description": "Its final form is a screaming abyss wrapped in armor.",
                        "abilities": ["obliterate", "soul_drain", "dark_aegis", "apocalyptic_roar"],
                    },
                ],
                "abilities": {
                    "strike": {
                        "display_name": "Strike",
                        "description": "A brutal direct blow against the Champion.",
                        "damage_text": "The {guardian_label} uses **{ability_name}** for **{damage}** damage.",
                        "damage_range": [120, 220],
                    },
                    "shield": {
                        "display_name": "Shield",
                        "description": "Reinforce the Guardian with a shell of shadow.",
                        "shield_text": "The {guardian_label} reinforces itself with **{shield}** shield.",
                        "shield": 200,
                    },
                    "purify": {
                        "display_name": "Purify",
                        "description": "Push the ritual backwards through violent cleansing.",
                        "progress_text": "The ritual is driven back by **{progress_down}** progress.",
                        "progress_down": 18,
                    },
                    "corrupting_blast": {
                        "display_name": "Corrupting Blast",
                        "description": "Damage the Champion and sap their power.",
                        "damage_text": "The {guardian_label} unleashes **{ability_name}** for **{damage}** damage.",
                        "damage_range": [160, 260],
                        "damage_down": 100,
                    },
                    "fear_aura": {
                        "display_name": "Fear Aura",
                        "description": "Sow dread that disrupts ritual momentum.",
                        "progress_text": "Dread from **{ability_name}** tears away **{progress_down}** ritual progress.",
                        "progress_down": 6,
                    },
                    "obliterate": {
                        "display_name": "Obliterate",
                        "description": "A devastating finishing strike.",
                        "damage_text": "The {guardian_label} crashes down with **{ability_name}** for **{damage}** damage.",
                        "damage_range": [350, 700],
                    },
                    "soul_drain": {
                        "display_name": "Soul Drain",
                        "description": "Drain the Champion and restore the Guardian.",
                        "damage_text": "The {guardian_label} tears free essence with **{ability_name}** for **{damage}** damage.",
                        "damage_range": [180, 260],
                        "heal_ratio": 1.0,
                    },
                    "dark_aegis": {
                        "display_name": "Dark Aegis",
                        "description": "Raise a stronger shield of abyssal armor.",
                        "shield_text": "A **{shield}** point veil of darkness hardens around the {guardian_label}.",
                        "shield": 350,
                    },
                    "apocalyptic_roar": {
                        "display_name": "Apocalyptic Roar",
                        "description": "Damage the Champion and shake the ritual loose.",
                        "damage_text": "The {guardian_label} bellows **{ability_name}** for **{damage}** damage.",
                        "progress_text": "The roar rips away **{progress_down}** ritual progress.",
                        "damage_range": [150, 240],
                        "progress_down": 10,
                    },
                },
            },
        },
    }


def _build_chaos_starter() -> dict[str, Any]:
    return {
        "id": "chaos_attrition_remaster",
        "mode": "chaos",
        "skeleton": "attrition",
        "runtime": "native",
        "status": "published",
        "name": "Void Breach Remaster",
        "description": "A configurable Drakath attrition raid with boss HP, pulse events, and swarm damage.",
        "config": {
            "join_timeout": 900,
            "max_rounds": 30,
            "eligibility": {"god": "Drakath"},
            "boss_name": "Eclipse the Void Conqueror",
            "boss_hp": 5000,
            "player_hp": 250,
            "announce": {
                "title": "The Void Awakens",
                "description": (
                    "Reality bends as Eclipse claws at the edge of the realm. "
                    "The faithful of Drakath must survive long enough to drive it back."
                ),
                "join_label": "Sacrifice yourself to the raid!",
                "joined_message": "You've pledged your soul to the raid.",
            },
            "presentation": _chaos_presentation(),
            "boss_attack": {
                "critical_chance": 0.3,
                "normal_min": 100,
                "normal_max": 280,
                "critical_min": 160,
                "critical_max": 360,
            },
            "events": {
                "heal_chance": 0.2,
                "heal_min": 90,
                "heal_max": 140,
                "pulse_chance": 0.2,
                "pulse_damage": 100,
                "pulse_targets": 3,
            },
            "players": {
                "critical_chance": 0.15,
                "normal_min": 20,
                "normal_max": 45,
                "critical_min": 70,
                "critical_max": 150,
            },
            "messages": {
                "high_damage": [
                    "Eclipse howls as the raid tears through the void.",
                    "The abyss buckles beneath the force of Drakath's faithful.",
                ],
                "medium_damage": [
                    "Eclipse recoils, then steadies itself in the dark.",
                    "The void hisses at the pressure of the assault.",
                ],
                "low_damage": [
                    "Eclipse laughs at the shallow wound.",
                    "The void barely notices the glancing strike.",
                ],
                "victory": (
                    "{count} followers of Drakath survive as Eclipse is hurled back into the void."
                ),
                "defeat": "The last resistance collapses, and Eclipse feeds on the silence.",
                "retreat": "{boss_name} slips back into the void with **{boss_hp}** HP remaining.",
            },
        },
    }


STARTER_DEFINITIONS: dict[str, dict[str, Any]] = {
    definition["id"]: definition
    for definition in (
        _build_good_starter(),
        _build_evil_starter(),
        _build_chaos_starter(),
    )
}

STARTER_DEFINITION_IDS = {
    "good": "good_trial_remaster",
    "evil": "evil_ritual_remaster",
    "chaos": "chaos_attrition_remaster",
}

SKELETON_STARTER_DEFINITION_IDS = {
    definition["skeleton"]: definition_id
    for definition_id, definition in STARTER_DEFINITIONS.items()
}

DEFAULT_ACTIONS = {
    "follower": "Chant",
    "champion": "Smite",
    "priest": "Bless",
}


class RaidBuilderFormModal(Modal):
    def __init__(self, builder_view: "RaidBuilderPanelView", *, title: str, fields: list[dict], submit_handler):
        super().__init__(title=title[:45])
        self.builder_view = builder_view
        self.submit_handler = submit_handler
        self.inputs = {}
        for field in fields[:5]:
            widget = TextInput(
                label=str(field["label"])[:45],
                placeholder=str(field.get("placeholder") or "")[:100],
                default=str(field.get("default") or "")[:4000],
                required=bool(field.get("required", True)),
                style=field.get("style", discord.TextStyle.short),
                max_length=field.get("max_length"),
            )
            self.inputs[field["key"]] = widget
            self.add_item(widget)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.builder_view.author.id:
            return await interaction.response.send_message(
                "This raid builder panel is not for you.",
                ephemeral=True,
            )
        values = {key: widget.value for key, widget in self.inputs.items()}
        try:
            response_text = await self.submit_handler(values)
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.builder_view.refresh_message()
        if response_text:
            await interaction.followup.send(response_text, ephemeral=True)


class RaidBuilderNewDraftModal(Modal, title="Create Raid Draft"):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        super().__init__()
        suggested = f"{builder_view.selected_mode}_draft"
        self.builder_view = builder_view
        self.definition_id = TextInput(
            label="Definition ID",
            placeholder="my_custom_raid",
            default=suggested[:64],
            required=True,
            max_length=64,
        )
        default_skeleton = MODE_SPECS[builder_view.selected_mode].skeleton
        self.skeleton = TextInput(
            label="Skeleton Template",
            placeholder="trial, ritual, or attrition",
            default=default_skeleton,
            required=True,
            max_length=16,
        )
        self.add_item(self.definition_id)
        self.add_item(self.skeleton)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.builder_view.author.id:
            return await interaction.response.send_message(
                "This raid builder panel is not for you.",
                ephemeral=True,
            )

        normalized_definition_id = self.builder_view.cog._validate_definition_id(
            self.definition_id.value
        )
        if normalized_definition_id is None:
            return await interaction.response.send_message(
                "Definition ids must be 3-64 chars and use only lowercase letters, numbers, `_`, or `-`.",
                ephemeral=True,
            )
        if normalized_definition_id in self.builder_view.cog.registry["definitions"]:
            return await interaction.response.send_message(
                f"Definition `{normalized_definition_id}` already exists.",
                ephemeral=True,
            )
        skeleton_key = self.builder_view.cog._coerce_skeleton_key(self.skeleton.value)
        if skeleton_key is None:
            return await interaction.response.send_message(
                "Skeleton templates must be one of `good`, `evil`, `chaos`, `trial`, `ritual`, or `attrition`.",
                ephemeral=True,
            )

        self.builder_view.cog.registry["definitions"][normalized_definition_id] = (
            self.builder_view.cog.build_draft_from_starter(
                self.builder_view.selected_mode,
                normalized_definition_id,
                skeleton_key=skeleton_key,
            )
        )
        self.builder_view.cog._save_registry()
        self.builder_view.selected_definition_id = normalized_definition_id
        self.builder_view.current_page_key = None
        self.builder_view.current_item_key = None
        await interaction.response.defer(ephemeral=True)
        await self.builder_view.refresh_message()
        await interaction.followup.send(
            f"Created draft `{normalized_definition_id}` from the `{skeleton_key}` skeleton.",
            ephemeral=True,
        )


class RaidBuilderModeSelect(Select):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        self.builder_view = builder_view
        options = [
            discord.SelectOption(
                label=spec.display_name,
                value=spec.key,
                description=f"Definitions owned by {spec.display_name}"[:100],
                default=spec.key == builder_view.selected_mode,
            )
            for spec in MODE_SPECS.values()
        ]
        super().__init__(
            placeholder="Choose a raid owner",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.builder_view.selected_mode = self.values[0]
        self.builder_view.selected_definition_id = None
        self.builder_view.current_page_key = None
        self.builder_view.current_item_key = None
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class RaidBuilderDefinitionSelect(Select):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        self.builder_view = builder_view
        definitions = builder_view._definitions_for_selected_mode()
        options = []
        for definition in definitions[:25]:
            definition_id = definition["id"]
            status = definition.get("status", "draft")
            active = (
                builder_view.cog._get_active_definition_id(builder_view.selected_mode)
                == definition_id
            )
            skeleton = builder_view.cog._definition_skeleton_key(definition) or "unknown"
            description = f"{status} • {skeleton}"
            if active:
                description += " • active"
            options.append(
                discord.SelectOption(
                    label=definition.get("name", definition_id)[:100],
                    value=definition_id,
                    description=description[:100],
                    default=definition_id == builder_view.selected_definition_id,
                )
            )
        if not options:
            options.append(
                discord.SelectOption(
                    label="No definitions",
                    value="__none__",
                    description="Create a draft to begin.",
                    default=True,
                )
            )
        super().__init__(
            placeholder="Choose a raid definition",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
            disabled=not definitions,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] != "__none__":
            self.builder_view.selected_definition_id = self.values[0]
            self.builder_view.current_page_key = None
            self.builder_view.current_item_key = None
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class RaidBuilderPageSelect(Select):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        self.builder_view = builder_view
        options = []
        for page in builder_view._page_specs():
            options.append(
                discord.SelectOption(
                    label=page["label"][:100],
                    value=page["key"],
                    description=page["description"][:100],
                    default=page["key"] == builder_view.current_page_key,
                )
            )
        super().__init__(
            placeholder="Choose a builder page",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.builder_view.current_page_key = self.values[0]
        self.builder_view.current_item_key = None
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class RaidBuilderItemSelect(Select):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        self.builder_view = builder_view
        options = []
        for item in builder_view._item_options():
            options.append(
                discord.SelectOption(
                    label=item["label"][:100],
                    value=item["key"],
                    description=item["description"][:100],
                    default=item["key"] == builder_view.current_item_key,
                )
            )
        super().__init__(
            placeholder="Choose the page item",
            min_values=1,
            max_values=1,
            options=options,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        self.builder_view.current_item_key = self.values[0]
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class RaidBuilderStructureView(View):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        super().__init__(timeout=300)
        self.builder_view = builder_view
        self._sync_buttons()

    def _state(self) -> dict[str, Any]:
        return self.builder_view.structure_state()

    def _build_embed(self) -> discord.Embed:
        state = self._state()
        definition = self.builder_view.current_definition()
        embed = discord.Embed(
            title="Builder Structure",
            color=discord.Color.orange(),
        )
        if not state.get("supported"):
            embed.description = state.get("reason", "This page does not support structural editing.")
            return embed

        embed.description = (
            "Create placeholder items, duplicate the current one, delete it, or change its order. "
            "The main builder panel will refresh after each change."
        )
        embed.add_field(name="Owner", value=self.builder_view.selected_mode, inline=True)
        embed.add_field(name="Definition", value=definition["id"] if definition else "none", inline=True)
        embed.add_field(name="Target", value=state["entity_label"].title(), inline=True)
        embed.add_field(name="Selected", value=state["selected_label"], inline=False)
        if state.get("scope_label"):
            embed.add_field(name="Scope", value=str(state["scope_label"]), inline=True)
        embed.add_field(
            name="Position",
            value=f"{state.get('position', 0)}/{state.get('total', 0)}",
            inline=True,
        )
        return embed

    def _sync_buttons(self) -> None:
        state = self._state()
        supported = bool(state.get("supported"))
        add_label = "Add"
        if supported:
            add_label = f"Add {state['entity_label'].title()}"[:80]
        self.add_button.label = add_label
        self.add_button.disabled = not supported
        self.duplicate_button.disabled = not supported
        self.delete_button.disabled = not supported or not state.get("can_delete")
        self.move_up_button.disabled = not supported or not state.get("can_move_up")
        self.move_down_button.disabled = not supported or not state.get("can_move_down")

    async def _run_action(self, interaction: discord.Interaction, action: str, *, delta: int = 0):
        if interaction.user.id != self.builder_view.author.id:
            return await interaction.response.send_message(
                "This structure panel is not for you.",
                ephemeral=True,
            )
        definition = self.builder_view.current_definition()
        if definition is None or self.builder_view.current_page_key is None:
            return await interaction.response.send_message(
                "No editable list is selected.",
                ephemeral=True,
            )
        try:
            page_key, item_key, message = self.builder_view.cog._builder_structure_action(
                definition,
                self.builder_view.current_page_key,
                self.builder_view.current_item_key,
                action,
                delta=delta,
            )
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)

        self.builder_view.current_page_key = page_key
        self.builder_view.current_item_key = item_key
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)
        await self.builder_view.refresh_message()
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Add", style=discord.ButtonStyle.primary)
    async def add_button(self, interaction: discord.Interaction, button: Button):
        await self._run_action(interaction, "add")

    @discord.ui.button(label="Duplicate", style=discord.ButtonStyle.secondary)
    async def duplicate_button(self, interaction: discord.Interaction, button: Button):
        await self._run_action(interaction, "duplicate")

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await self._run_action(interaction, "delete")

    @discord.ui.button(label="Up", style=discord.ButtonStyle.secondary)
    async def move_up_button(self, interaction: discord.Interaction, button: Button):
        await self._run_action(interaction, "move", delta=-1)

    @discord.ui.button(label="Down", style=discord.ButtonStyle.secondary)
    async def move_down_button(self, interaction: discord.Interaction, button: Button):
        await self._run_action(interaction, "move", delta=1)


class RaidBuilderDeleteDefinitionView(View):
    def __init__(self, builder_view: "RaidBuilderPanelView"):
        super().__init__(timeout=120)
        self.builder_view = builder_view

    def _build_embed(self) -> discord.Embed:
        definition = self.builder_view.current_definition()
        embed = discord.Embed(
            title="Delete Raid Definition",
            color=discord.Color.red(),
        )
        if definition is None:
            embed.description = "No definition is selected."
            return embed

        skeleton = self.builder_view.cog._definition_skeleton_key(definition) or "unknown"
        active_modes = self.builder_view.cog._definition_active_modes(definition["id"])
        starter = definition["id"] in STARTER_DEFINITIONS
        embed.description = (
            "Delete this definition from the registry. "
            "Starter templates cannot be deleted."
        )
        embed.add_field(name="Owner", value=definition.get("mode", "unknown"), inline=True)
        embed.add_field(name="Skeleton", value=skeleton, inline=True)
        embed.add_field(name="Definition", value=definition["id"], inline=True)
        embed.add_field(
            name="Active On",
            value=", ".join(active_modes) if active_modes else "none",
            inline=True,
        )
        embed.add_field(
            name="Protected",
            value="yes" if starter else "no",
            inline=True,
        )
        return embed

    async def _deny_foreign_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.builder_view.author.id:
            await interaction.response.send_message(
                "This delete panel is not for you.",
                ephemeral=True,
            )
            return True
        return False

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        if await self._deny_foreign_user(interaction):
            return
        definition = self.builder_view.current_definition()
        if definition is None:
            return await interaction.response.send_message(
                "No definition is selected.",
                ephemeral=True,
            )
        try:
            cleared_modes = self.builder_view.cog._delete_definition(definition["id"])
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)

        self.builder_view.selected_definition_id = None
        self.builder_view.current_page_key = None
        self.builder_view.current_item_key = None
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Raid Definition Deleted",
                description=f"Deleted `{definition['id']}`.",
                color=discord.Color.red(),
            ),
            view=None,
        )
        await self.builder_view.refresh_message()

        if cleared_modes:
            await interaction.followup.send(
                f"Cleared active routing for: {', '.join(f'`{mode_key}`' for mode_key in cleared_modes)}.",
                ephemeral=True,
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if await self._deny_foreign_user(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Delete Raid Definition",
                description="Deletion canceled.",
                color=discord.Color.blurple(),
            ),
            view=None,
        )


class RaidBuilderPanelView(View):
    def __init__(
        self,
        *,
        cog: "RaidBuilder",
        ctx,
        initial_mode: str | None = None,
        initial_definition_id: str | None = None,
    ):
        super().__init__(timeout=900)
        self.cog = cog
        self.ctx = ctx
        self.author = ctx.author
        self.selected_mode = initial_mode or "good"
        self.selected_definition_id = initial_definition_id
        self.current_page_key: str | None = None
        self.current_item_key: str | None = None
        self.message: discord.Message | None = None
        self.mode_select: RaidBuilderModeSelect | None = None
        self.definition_select: RaidBuilderDefinitionSelect | None = None
        self.page_select: RaidBuilderPageSelect | None = None
        self.item_select: RaidBuilderItemSelect | None = None
        self._sync_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This raid builder panel is not for you.",
                ephemeral=True,
            )
            return False
        return True

    def _definitions_for_selected_mode(self) -> list[dict[str, Any]]:
        definitions = [
            definition
            for definition in self.cog.registry["definitions"].values()
            if definition.get("mode") == self.selected_mode
        ]
        return sorted(
            definitions,
            key=lambda definition: (
                definition.get("status") != "published",
                definition.get("id", ""),
            ),
        )

    def _default_definition_id(self) -> str | None:
        active_definition_id = self.cog._get_active_definition_id(self.selected_mode)
        if active_definition_id:
            active_definition = self.cog._get_definition(active_definition_id)
            if active_definition and active_definition.get("mode") == self.selected_mode:
                return active_definition_id

        definitions = self._definitions_for_selected_mode()
        starter_definition_id = STARTER_DEFINITION_IDS.get(self.selected_mode)
        for definition in definitions:
            if definition.get("id") != starter_definition_id:
                return definition["id"]

        if starter_definition_id and self.cog._get_definition(starter_definition_id):
            return starter_definition_id
        if definitions:
            return definitions[0]["id"]
        return None

    def _page_specs(self) -> list[dict[str, str]]:
        definition = self.current_definition()
        skeleton_key = self.cog._definition_skeleton_key(definition)
        if skeleton_key is None:
            skeleton_key = MODE_SPECS[self.selected_mode].skeleton
        return self.cog._builder_page_specs(skeleton_key)

    def _item_options(self) -> list[dict[str, str]]:
        definition = self.current_definition()
        if definition is None or self.current_page_key is None:
            return []
        return self.cog._builder_item_options(definition, self.current_page_key)

    def structure_state(self) -> dict[str, Any]:
        return self.cog._builder_structure_state(
            self.current_definition(),
            self.current_page_key,
            self.current_item_key,
        )

    def _current_page_index(self) -> int:
        page_specs = self._page_specs()
        for index, page in enumerate(page_specs):
            if page["key"] == self.current_page_key:
                return index
        return 0

    def current_definition(self) -> dict[str, Any] | None:
        if self.selected_definition_id is None:
            return None
        definition = self.cog._get_definition(self.selected_definition_id)
        if definition is None or definition.get("mode") != self.selected_mode:
            return None
        return definition

    def _ensure_state(self) -> None:
        if self.selected_mode not in MODE_SPECS:
            self.selected_mode = "good"

        if self.current_definition() is None:
            self.selected_definition_id = self._default_definition_id()

        page_specs = self._page_specs()
        page_keys = [page["key"] for page in page_specs]
        if not page_keys:
            self.current_page_key = None
        elif self.current_page_key not in page_keys:
            self.current_page_key = page_keys[0]

        item_options = self._item_options()
        item_keys = [item["key"] for item in item_options]
        if item_keys:
            if self.current_item_key not in item_keys:
                self.current_item_key = item_keys[0]
        else:
            self.current_item_key = None

    def _clear_dynamic_controls(self) -> None:
        for control_name in ("mode_select", "definition_select", "page_select", "item_select"):
            control = getattr(self, control_name)
            if control is not None:
                self.remove_item(control)
                setattr(self, control_name, None)

    def _sync_controls(self) -> None:
        self._ensure_state()
        self._clear_dynamic_controls()

        self.mode_select = RaidBuilderModeSelect(self)
        self.definition_select = RaidBuilderDefinitionSelect(self)
        self.page_select = RaidBuilderPageSelect(self)
        self.add_item(self.mode_select)
        self.add_item(self.definition_select)
        self.add_item(self.page_select)

        if self._item_options():
            self.item_select = RaidBuilderItemSelect(self)
            self.add_item(self.item_select)

        self.structure_button.disabled = (
            self.current_definition() is None or not self.structure_state().get("supported")
        )
        self.edit_page_button.disabled = self.current_definition() is None
        self.delete_definition_button.disabled = (
            self.current_definition() is None
            or not self.cog._can_delete_definition(self.current_definition()["id"])
        )

        definition = self.current_definition()
        if definition is None:
            self.state_button.disabled = True
            self.state_button.label = "State"
            self.state_button.style = discord.ButtonStyle.secondary
            return

        self.state_button.disabled = False
        is_active = self.cog._get_active_definition_id(self.selected_mode) == definition["id"]
        status = definition.get("status", "draft")
        if is_active:
            self.state_button.label = "Deactivate"
            self.state_button.style = discord.ButtonStyle.secondary
        elif status != "published":
            self.state_button.label = "Publish"
            self.state_button.style = discord.ButtonStyle.success
        else:
            self.state_button.label = "Activate"
            self.state_button.style = discord.ButtonStyle.success

    def _current_payload(self) -> dict[str, Any]:
        definition = self.current_definition()
        if definition is None:
            return {
                "title": "Raid Builder",
                "description": "No definition is selected.",
                "fields": [],
                "form_fields": [],
                "form_title": "Edit",
                "submit_handler": None,
            }
        return self.cog._builder_page_payload(
            definition,
            self.current_page_key,
            self.current_item_key,
        )

    def _build_embed(self) -> discord.Embed:
        definition = self.current_definition()
        payload = self._current_payload()
        embed = discord.Embed(
            title=payload["title"],
            description=payload["description"],
            color=discord.Color.blurple(),
        )
        for field in payload.get("fields", []):
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False),
            )

        if definition is not None:
            active_definition_id = self.cog._get_active_definition_id(self.selected_mode)
            skeleton_key = self.cog._definition_skeleton_key(definition) or "unknown"
            footer_bits = [
                f"Owner: {self.selected_mode}",
                f"Skeleton: {skeleton_key}",
                f"Definition: {definition['id']}",
                f"Status: {definition.get('status', 'draft')}",
                f"Route: {'active' if active_definition_id == definition['id'] else 'inactive'}",
            ]
        else:
            footer_bits = [f"Owner: {self.selected_mode}", "Definition: none"]
        embed.set_footer(text=" • ".join(footer_bits))
        return embed

    async def start(self):
        self._sync_controls()
        self.message = await self.ctx.send(embed=self._build_embed(), view=self)

    async def refresh_message(self):
        self._sync_controls()
        if self.message is not None:
            await self.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="Structure", style=discord.ButtonStyle.secondary, row=4)
    async def structure_button(self, interaction: discord.Interaction, button: Button):
        structure_view = RaidBuilderStructureView(self)
        await interaction.response.send_message(
            embed=structure_view._build_embed(),
            view=structure_view,
            ephemeral=True,
        )

    @discord.ui.button(label="New Draft", style=discord.ButtonStyle.primary, row=4)
    async def new_draft_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RaidBuilderNewDraftModal(self))

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary, row=4)
    async def edit_page_button(self, interaction: discord.Interaction, button: Button):
        payload = self._current_payload()
        submit_handler = payload.get("submit_handler")
        form_fields = payload.get("form_fields") or []
        if submit_handler is None or not form_fields:
            return await interaction.response.send_message(
                "This page does not expose editable fields yet.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            RaidBuilderFormModal(
                self,
                title=payload.get("form_title", "Edit Raid Definition"),
                fields=form_fields,
                submit_handler=submit_handler,
            )
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, row=4)
    async def delete_definition_button(self, interaction: discord.Interaction, button: Button):
        definition = self.current_definition()
        if definition is None:
            return await interaction.response.send_message(
                "No definition is selected.",
                ephemeral=True,
            )
        delete_view = RaidBuilderDeleteDefinitionView(self)
        await interaction.response.send_message(
            embed=delete_view._build_embed(),
            view=delete_view,
            ephemeral=True,
        )

    @discord.ui.button(label="State", style=discord.ButtonStyle.success, row=4)
    async def state_button(self, interaction: discord.Interaction, button: Button):
        definition = self.current_definition()
        if definition is None:
            return await interaction.response.send_message(
                "No definition is selected.",
                ephemeral=True,
            )

        is_active = self.cog._get_active_definition_id(self.selected_mode) == definition["id"]
        if is_active:
            self.cog.registry["modes"][self.selected_mode]["active_definition_id"] = None
            self.cog._save_registry()
            await interaction.response.defer(ephemeral=True)
            await self.refresh_message()
            await interaction.followup.send(
                f"Deactivated `{definition['id']}` for `{self.selected_mode}`.",
                ephemeral=True,
            )
            return

        if definition.get("status") != "published":
            definition["status"] = "published"
            self.cog._save_registry()
            await interaction.response.defer(ephemeral=True)
            await self.refresh_message()
            await interaction.followup.send(
                f"Published `{definition['id']}`.",
                ephemeral=True,
            )
            return

        self.cog.registry["modes"][self.selected_mode]["active_definition_id"] = definition["id"]
        self.cog._save_registry()
        await interaction.response.defer(ephemeral=True)
        await self.refresh_message()
        await interaction.followup.send(
            f"Activated `{definition['id']}` for `{self.selected_mode}`.",
            ephemeral=True,
        )


class RaidBuilder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.registry_path = Path("assets/data/raid_builder_registry.json")
        self.registry = self._load_registry()

    @classmethod
    def default_registry(cls) -> dict[str, Any]:
        return {
            "modes": {
                mode_key: {"active_definition_id": None}
                for mode_key in MODE_SPECS
            },
            "definitions": copy.deepcopy(STARTER_DEFINITIONS),
        }

    @classmethod
    def _fill_missing(cls, current: Any, defaults: Any) -> Any:
        if not isinstance(current, dict) or not isinstance(defaults, dict):
            return current
        for key, default_value in defaults.items():
            if key not in current:
                current[key] = copy.deepcopy(default_value)
                continue
            if isinstance(current[key], dict) and isinstance(default_value, dict):
                cls._fill_missing(current[key], default_value)
        return current

    @classmethod
    def _upgrade_definition_schema(
        cls,
        definition_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        definition.setdefault("id", definition_id)
        mode = definition.get("mode")
        if isinstance(mode, str):
            mode = mode.casefold()
            definition["mode"] = mode
        skeleton = cls._normalize_skeleton_key(definition.get("skeleton"), mode_key=mode)
        if skeleton is not None:
            definition["skeleton"] = skeleton

        starter_id = SKELETON_STARTER_DEFINITION_IDS.get(skeleton)
        if starter_id:
            cls._fill_missing(definition, copy.deepcopy(STARTER_DEFINITIONS[starter_id]))

        config = definition.setdefault("config", {})
        announce = config.setdefault("announce", {})
        if skeleton == "trial":
            cls._fill_missing(config.setdefault("presentation", {}), _good_presentation())
            announce.setdefault("join_label", "Join the trial!")
            announce.setdefault("joined_message", "You joined the trial.")
        elif skeleton == "attrition":
            cls._fill_missing(config.setdefault("presentation", {}), _chaos_presentation())
            announce.setdefault("join_label", "Join the raid!")
            announce.setdefault("joined_message", "You joined the raid.")
            messages = config.setdefault("messages", {})
            messages.setdefault(
                "retreat",
                "{boss_name} slips back into the void with **{boss_hp}** HP remaining.",
            )
        elif skeleton == "ritual":
            cls._fill_missing(config.setdefault("presentation", {}), _evil_presentation())
            announce.setdefault("leader_label", "Join as Champion/Priest")
            announce.setdefault("follower_label", "Join as Follower Only")
            announce.setdefault("leader_joined_message", "You joined as a potential leader.")
            announce.setdefault("follower_joined_message", "You joined as a follower.")
            announce.setdefault("start_message", "**💀 The ritual begins! The Guardian awakens from its slumber... 💀**")
            announce.setdefault(
                "eligibility_message",
                "**Gathering the faithful... checking dm eligibility this may take awhile**",
            )
            countdown_messages = announce.get("countdown_messages")
            default_countdown_entries = _ritual_countdown_defaults()
            default_countdown_map = {
                entry["key"]: entry
                for entry in default_countdown_entries
            }
            if not isinstance(countdown_messages, list) or not countdown_messages:
                announce["countdown_messages"] = default_countdown_entries
            else:
                normalized_countdown_messages = []
                seen_keys = set()
                for index, entry in enumerate(countdown_messages):
                    if not isinstance(entry, dict):
                        continue
                    raw_key = str(entry.get("key") or f"countdown_{index + 1}").casefold().strip()
                    default_entry = default_countdown_map.get(raw_key, {})
                    label = str(entry.get("label") or default_entry.get("label") or raw_key.replace("_", " ").title())
                    try:
                        remaining = int(entry.get("remaining", default_entry.get("remaining", 0)))
                    except (TypeError, ValueError):
                        remaining = int(default_entry.get("remaining", 0))
                    message = str(entry.get("message") or default_entry.get("message") or "").strip()
                    if not message:
                        continue
                    normalized_countdown_messages.append(
                        {
                            "key": raw_key,
                            "label": label,
                            "remaining": max(0, remaining),
                            "message": message,
                        }
                    )
                    seen_keys.add(raw_key)
                for default_entry in default_countdown_entries:
                    if default_entry["key"] not in seen_keys:
                        normalized_countdown_messages.append(copy.deepcopy(default_entry))
                announce["countdown_messages"] = normalized_countdown_messages

            champion = config.setdefault("champion", {})
            champion_actions = champion.get("actions")
            if not isinstance(champion_actions, dict) or not champion_actions:
                champion["actions"] = copy.deepcopy(_champion_action_defaults())
                champion_actions = champion["actions"]
            for action_name, action in champion_actions.items():
                if not isinstance(action, dict):
                    champion_actions[action_name] = {
                        "display_name": action_name,
                        "description": "Champion action.",
                        "result_text": "The {champion_label} acts.",
                    }
                    continue
                defaults = _champion_action_defaults().get(
                    action_name,
                    {
                        "effect": "damage",
                        "display_name": action_name,
                        "description": "Champion action.",
                        "result_text": "The {champion_label} acts.",
                    },
                )
                cls._fill_missing(action, defaults)

            priest_actions = config.setdefault("priest", {}).setdefault("actions", {})
            for action_name, action in priest_actions.items():
                if not isinstance(action, dict):
                    priest_actions[action_name] = {"mana_cost": 0}
                    action = priest_actions[action_name]
                action.setdefault("display_name", action_name)
                action.setdefault("description", "Priest spell.")
                action.setdefault(
                    "result_text",
                    "The {priest_label} invokes **{action_name}**.",
                )

            follower_actions = config.setdefault("followers", {}).setdefault("actions", {})
            for action_name, action in follower_actions.items():
                if not isinstance(action, dict):
                    follower_actions[action_name] = {}
                    action = follower_actions[action_name]
                action.setdefault("display_name", action_name)
                action.setdefault("description", "Follower support action.")

            guardian = config.setdefault("guardian", {})
            guardian.setdefault("phases", [])
            guardian_abilities = guardian.setdefault("abilities", {})
            for ability_name, ability in guardian_abilities.items():
                if not isinstance(ability, dict):
                    guardian_abilities[ability_name] = {}
                    ability = guardian_abilities[ability_name]
                ability.setdefault("display_name", ability_name.replace("_", " ").title())
                ability.setdefault("description", "Guardian ability.")
                if "damage_range" in ability:
                    ability.setdefault(
                        "damage_text",
                        "The {guardian_label} uses **{ability_name}** for **{damage}** damage.",
                    )
                if "shield" in ability:
                    ability.setdefault(
                        "shield_text",
                        "The {guardian_label} reinforces itself with **{shield}** shield.",
                    )
                if "progress_down" in ability:
                    ability.setdefault(
                        "progress_text",
                        "The ritual is driven back by **{progress_down}** progress.",
                    )

        return definition

    @classmethod
    def normalize_registry(cls, raw: Any) -> dict[str, Any]:
        registry = cls.default_registry()
        if not isinstance(raw, dict):
            return registry

        definitions = raw.get("definitions", {})
        if isinstance(definitions, dict):
            for definition_id, definition in definitions.items():
                if not isinstance(definition_id, str) or not isinstance(definition, dict):
                    continue
                merged_definition = cls._upgrade_definition_schema(
                    definition_id,
                    copy.deepcopy(definition),
                )
                registry["definitions"][definition_id] = merged_definition

        modes = raw.get("modes", {})
        if isinstance(modes, dict):
            for mode_key in MODE_SPECS:
                mode_state = modes.get(mode_key, {})
                if not isinstance(mode_state, dict):
                    continue
                active_definition_id = mode_state.get("active_definition_id")
                if active_definition_id is None or isinstance(active_definition_id, str):
                    registry["modes"][mode_key]["active_definition_id"] = active_definition_id

        return registry

    @classmethod
    def build_draft_from_starter(
        cls,
        mode_key: str,
        definition_id: str,
        *,
        skeleton_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = mode_key.casefold()
        normalized_skeleton = cls._normalize_skeleton_key(skeleton_key, mode_key=normalized_mode)
        if normalized_skeleton is None:
            raise ValueError(f"Unknown skeleton `{skeleton_key}`.")
        starter_definition_id = SKELETON_STARTER_DEFINITION_IDS[normalized_skeleton]
        starter_definition = copy.deepcopy(STARTER_DEFINITIONS[starter_definition_id])
        starter_definition["mode"] = normalized_mode
        starter_definition["skeleton"] = normalized_skeleton
        starter_definition = cls._upgrade_definition_schema(definition_id, starter_definition)
        starter_definition["id"] = definition_id
        starter_definition["status"] = "draft"
        starter_definition["name"] = f"{starter_definition['name']} ({definition_id})"
        starter_definition["source_definition_id"] = starter_definition_id
        return starter_definition

    def _load_registry(self) -> dict[str, Any]:
        raw: Any = None
        if self.registry_path.exists():
            try:
                raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None

        registry = self.normalize_registry(raw)
        self._save_registry(registry)
        return registry

    def _save_registry(self, registry: dict[str, Any] | None = None) -> None:
        data = registry or self.registry
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _get_mode_spec(self, mode_key: str) -> RaidModeSpec | None:
        return MODE_SPECS.get(mode_key.casefold())

    @staticmethod
    def _default_skeleton_for_mode(mode_key: str | None) -> str | None:
        if not isinstance(mode_key, str):
            return None
        spec = MODE_SPECS.get(mode_key.casefold())
        if spec is None:
            return None
        return spec.skeleton

    @staticmethod
    def _coerce_skeleton_key(value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.casefold().strip()
        if normalized in SKELETON_STARTER_DEFINITION_IDS:
            return normalized
        spec = MODE_SPECS.get(normalized)
        if spec is not None:
            return spec.skeleton
        return None

    @classmethod
    def _normalize_skeleton_key(
        cls,
        skeleton_key: str | None,
        *,
        mode_key: str | None = None,
    ) -> str | None:
        return cls._coerce_skeleton_key(skeleton_key) or cls._default_skeleton_for_mode(mode_key)

    @classmethod
    def _definition_skeleton_key(cls, definition: dict[str, Any] | None) -> str | None:
        if not isinstance(definition, dict):
            return None
        return cls._normalize_skeleton_key(
            definition.get("skeleton"),
            mode_key=definition.get("mode"),
        )

    def _definition_active_modes(self, definition_id: str) -> list[str]:
        return [
            mode_key
            for mode_key, mode_state in self.registry["modes"].items()
            if mode_state.get("active_definition_id") == definition_id
        ]

    def _can_delete_definition(self, definition_id: str) -> bool:
        return definition_id not in STARTER_DEFINITION_IDS.values()

    def _delete_definition(self, definition_id: str) -> list[str]:
        normalized_definition_id = definition_id.casefold()
        if normalized_definition_id not in self.registry["definitions"]:
            raise ValueError(f"Definition `{normalized_definition_id}` does not exist.")
        if not self._can_delete_definition(normalized_definition_id):
            raise ValueError("Starter templates cannot be deleted.")

        cleared_modes = self._definition_active_modes(normalized_definition_id)
        for mode_key in cleared_modes:
            self.registry["modes"][mode_key]["active_definition_id"] = None

        del self.registry["definitions"][normalized_definition_id]
        self._save_registry()
        return cleared_modes

    def _get_definition(self, definition_id: str) -> dict[str, Any] | None:
        definition = self.registry["definitions"].get(definition_id)
        if isinstance(definition, dict):
            return definition
        return None

    def _get_active_definition_id(self, mode_key: str) -> str | None:
        mode_state = self.registry["modes"].get(mode_key, {})
        active_definition_id = mode_state.get("active_definition_id")
        if isinstance(active_definition_id, str):
            return active_definition_id
        return None

    def _get_active_definition(self, mode_key: str) -> dict[str, Any] | None:
        active_definition_id = self._get_active_definition_id(mode_key)
        if active_definition_id is None:
            return None

        definition = self._get_definition(active_definition_id)
        if definition is None:
            return None
        if definition.get("mode") != mode_key:
            return None
        if definition.get("status") != "published":
            return None
        if self._definition_skeleton_key(definition) is None:
            return None
        return definition

    def _get_route_text(self, mode_key: str) -> str:
        spec = MODE_SPECS[mode_key]
        active_definition = self._get_active_definition(mode_key)
        if active_definition is not None:
            return f"custom runtime `{active_definition['id']}`"

        active_definition_id = self._get_active_definition_id(mode_key)
        if active_definition_id:
            return (
                f"selected `{active_definition_id}` is not runnable; "
                f"fallback stays `{spec.legacy_command}`"
            )
        return f"legacy fallback `{spec.legacy_command}`"

    @staticmethod
    def _validate_definition_id(definition_id: str) -> str | None:
        normalized = definition_id.casefold()
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", normalized) is None:
            return None
        return normalized

    @staticmethod
    def _dedupe_users(users: list[discord.abc.User]) -> list[discord.abc.User]:
        deduped = []
        seen_ids = set()
        for user in users:
            user_id = getattr(user, "id", None)
            if user_id is None or user_id in seen_ids:
                continue
            seen_ids.add(user_id)
            deduped.append(user)
        return deduped

    @staticmethod
    def _format_mentions(users: list[discord.abc.User]) -> str:
        mentions = [
            getattr(user, "mention", getattr(user, "display_name", str(user)))
            for user in users
        ]
        if not mentions:
            return "nobody"
        return ", ".join(mentions)

    @staticmethod
    def _progress_bar(current: int | float, total: int | float, bar_length: int = 10) -> str:
        if total <= 0:
            return "[----------]"
        ratio = max(0.0, min(float(current) / float(total), 1.0))
        filled = int(round(ratio * bar_length))
        return "[" + ("#" * filled) + ("-" * (bar_length - filled)) + "]"

    @staticmethod
    def _weighted_choice(entries: list[dict[str, Any]]) -> dict[str, Any]:
        weights = [max(1, int(entry.get("weight", 1))) for entry in entries]
        return randomm.choices(entries, weights=weights, k=1)[0]

    async def _safe_get_player_decision(
        self,
        raid_cog,
        player,
        options: list[str],
        role: str,
        timeout: int,
        embed: discord.Embed | None = None,
        option_labels: dict[str, str] | None = None,
    ) -> tuple[str | None, bool]:
        if not options:
            return None, False

        fallback = DEFAULT_ACTIONS.get(role) or options[0]
        if fallback not in options:
            fallback = options[0]
        display_to_option = {}
        display_options = options
        if option_labels:
            display_options = []
            for option in options:
                display_label = option_labels.get(option, option)
                display_to_option[display_label] = option
                display_options.append(display_label)

        try:
            decision, used_default = await asyncio.wait_for(
                raid_cog.get_player_decision(
                    player=player,
                    options=display_options,
                    role=role,
                    embed=embed,
                ),
                timeout=timeout,
            )
            mapped_decision = display_to_option.get(decision, decision)
            if mapped_decision not in options:
                mapped_decision = fallback
            return mapped_decision, used_default
        except (asyncio.TimeoutError, discord.Forbidden, discord.HTTPException):
            return fallback, True

    async def _filter_eligible_users(
        self,
        users: list[discord.abc.User],
        god_name: str | None,
    ) -> list[discord.abc.User]:
        users = self._dedupe_users(users)
        if god_name is None:
            return users

        eligible_users = []
        async with self.bot.pool.acquire() as conn:
            for user in users:
                profile = await conn.fetchrow(
                    'SELECT god FROM profile WHERE "user"=$1;',
                    user.id,
                )
                if profile and profile["god"] == god_name:
                    eligible_users.append(user)
        return eligible_users

    async def _invoke_legacy_command(self, ctx, spec: RaidModeSpec, **kwargs: Any) -> None:
        command = self.bot.get_command(spec.legacy_command)
        if command is None:
            await ctx.send(f"Legacy raid command `{spec.legacy_command}` is not loaded.")
            return

        await command.can_run(ctx)

        if spec.key == "chaos":
            boss_hp = kwargs.get("boss_hp")
            if boss_hp is None:
                await ctx.send(
                    "Chaos mode still needs a boss HP while it routes to the current horror raid."
                )
                return
            await ctx.invoke(command, boss_hp=boss_hp)
            return

        await ctx.invoke(command)

    async def _launch_mode(self, ctx, mode_key: str, **kwargs: Any) -> None:
        spec = self._get_mode_spec(mode_key)
        if spec is None:
            await ctx.send(f"Unknown raid mode `{mode_key}`.")
            return

        definition = self._get_active_definition(mode_key)
        if definition is None:
            active_definition_id = self._get_active_definition_id(mode_key)
            if active_definition_id:
                await ctx.send(
                    f"Mode `{spec.display_name}` points at `{active_definition_id}`, but it is not a published "
                    f"custom definition. Falling back to `{spec.legacy_command}`."
                )
            await self._invoke_legacy_command(ctx, spec, **kwargs)
            return

        try:
            await self._run_custom_definition(ctx, definition, **kwargs)
        except Exception as exc:
            await ctx.send(
                f"Custom raid definition `{definition['id']}` failed before completion: {exc}"
            )

    async def _run_custom_definition(
        self,
        ctx,
        definition: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        skeleton = self._definition_skeleton_key(definition)
        if skeleton == "trial":
            await self._run_trial_definition(ctx, definition)
            return
        if skeleton == "ritual":
            await self._run_ritual_definition(ctx, definition)
            return
        if skeleton == "attrition":
            await self._run_attrition_definition(ctx, definition, kwargs.get("boss_hp"))
            return

        raise ValueError(f"Unsupported custom skeleton `{definition.get('skeleton', 'unknown')}`.")

    async def _run_trial_definition(self, ctx, definition: dict[str, Any]) -> None:
        config = definition["config"]
        announce = config["announce"]
        join_timeout = int(config.get("join_timeout", 900))
        join_view = JoinView(
            Button(style=ButtonStyle.primary, label=announce.get("join_label", "Join")),
            message=announce.get("joined_message", "You joined the raid."),
            timeout=join_timeout,
        )

        intro_embed = discord.Embed(
            title=announce.get("title", definition["name"]),
            description=announce.get("description", definition.get("description", "")),
            color=discord.Color.blue(),
        )
        self._apply_presentation(
            intro_embed,
            definition,
            color_key="intro",
            media_key="intro",
            default_color=discord.Color.blue(),
        )
        intro_embed.set_footer(text=f"Skeleton: {definition['skeleton']}")
        await ctx.send(embed=intro_embed, view=join_view)

        await asyncio.sleep(join_timeout)
        join_view.stop()

        phase_delay = max(0, int(config.get("phase_delay", 5)))
        result_delay = max(0, int(config.get("result_delay", 3)))
        min_survivors = max(1, int(config.get("min_survivors", 1)))
        max_rounds = max(1, int(config.get("max_rounds", 40)))
        eligible_god = config.get("eligibility", {}).get("god")
        participants = await self._filter_eligible_users(list(join_view.joined), eligible_god)

        if len(participants) < min_survivors:
            await ctx.send(
                f"No valid followers of {eligible_god or 'the required faith'} answered the trial."
            )
            return

        await ctx.send(f"**{len(participants)}** participants enter `{definition['name']}`.")

        rounds_played = 0
        phases = config.get("phases", [])
        if not phases:
            await ctx.send("This trial definition has no phases configured.")
            return

        while len(participants) > min_survivors and rounds_played < max_rounds:
            rounds_played += 1
            phase = self._weighted_choice(phases)
            phase_embed = discord.Embed(
                title=phase.get("title", phase.get("key", "Phase").title()),
                description=phase.get("description", ""),
                color=discord.Color.gold(),
            )
            self._apply_presentation(
                phase_embed,
                definition,
                color_key="phase",
                media_key="phase",
                default_color=discord.Color.gold(),
            )
            phase_embed.set_footer(text=f"Round {rounds_played}")
            await ctx.send(embed=phase_embed)
            if phase_delay:
                await asyncio.sleep(phase_delay)

            target_count = min(
                int(phase.get("targets_per_round", 1)),
                max(1, len(participants) - min_survivors),
            )
            targets = randomm.sample(participants, target_count)
            events = phase.get("events", [])
            if not events:
                await ctx.send(f"Phase `{phase.get('key', 'unknown')}` has no events configured.")
                return

            for target in targets:
                event = randomm.choice(events)
                success_rate = max(0, min(100, int(event.get("success_rate", 50))))
                success = randomm.randint(1, 100) <= success_rate
                if not success:
                    mercy_chance = max(0, min(100, int(event.get("mercy_chance", 0))))
                    if mercy_chance and randomm.randint(1, 100) <= mercy_chance:
                        success = True

                result_embed = discord.Embed(
                    title=event.get("text", "Trial"),
                    description=(
                        event.get("win_text", "The test is overcome.")
                        if success
                        else event.get("lose_text", "The trial claims another soul.")
                    ),
                    color=discord.Color.green() if success else discord.Color.red(),
                )
                self._apply_presentation(
                    result_embed,
                    definition,
                    color_key="success" if success else "failure",
                    media_key="result",
                    default_color=discord.Color.green() if success else discord.Color.red(),
                )
                result_embed.set_author(
                    name=getattr(target, "display_name", str(target)),
                    icon_url=target.display_avatar.url,
                )

                if not success and target in participants:
                    participants.remove(target)

                result_embed.set_footer(text=f"{len(participants)} followers remain")
                await ctx.send(embed=result_embed)
                if result_delay:
                    await asyncio.sleep(result_delay)

                if len(participants) <= min_survivors:
                    break

        if participants:
            winners = self._format_mentions(participants)
            winner_text = config.get("winner_text", "{winner} remain standing.").format(
                winner=winners,
                count=len(participants),
            )
            winner_embed = discord.Embed(
                title="Trial Complete",
                description=winner_text,
                color=discord.Color.blue(),
            )
            self._apply_presentation(
                winner_embed,
                definition,
                color_key="victory",
                media_key="victory",
                default_color=discord.Color.blue(),
            )
            await ctx.send(embed=winner_embed)
            return

        await ctx.send("The trial ends with no survivors.")

    async def _run_attrition_definition(
        self,
        ctx,
        definition: dict[str, Any],
        boss_hp_override: int | None,
    ) -> None:
        config = definition["config"]
        announce = config["announce"]
        join_timeout = int(config.get("join_timeout", 900))
        join_view = JoinView(
            Button(style=ButtonStyle.danger, label=announce.get("join_label", "Join")),
            message=announce.get("joined_message", "You joined the raid."),
            timeout=join_timeout,
        )

        boss_name = config.get("boss_name", "The Boss")
        initial_boss_hp = int(boss_hp_override or config.get("boss_hp", 5000))
        if initial_boss_hp <= 0:
            raise ValueError("Custom attrition definitions require a positive boss HP.")

        intro_embed = discord.Embed(
            title=announce.get("title", definition["name"]),
            description=announce.get("description", definition.get("description", "")),
            color=discord.Color.dark_purple(),
        )
        self._apply_presentation(
            intro_embed,
            definition,
            color_key="intro",
            media_key="intro",
            default_color=discord.Color.dark_purple(),
        )
        intro_embed.add_field(name="Boss", value=boss_name, inline=True)
        intro_embed.add_field(name="HP", value=f"{initial_boss_hp}", inline=True)
        intro_embed.set_footer(text=f"Skeleton: {definition['skeleton']}")
        await ctx.send(embed=intro_embed, view=join_view)

        await asyncio.sleep(join_timeout)
        join_view.stop()

        participants = await self._filter_eligible_users(
            list(join_view.joined),
            config.get("eligibility", {}).get("god"),
        )
        if not participants:
            await ctx.send("The void finds no worthy followers to consume.")
            return

        raid = {
            participant: int(config.get("player_hp", 250))
            for participant in participants
        }
        messages = config.get("messages", {})
        attack_config = config.get("boss_attack", {})
        events_config = config.get("events", {})
        players_config = config.get("players", {})
        max_rounds = max(1, int(config.get("max_rounds", 30)))
        boss_hp = initial_boss_hp

        await ctx.send(f"**{len(raid)}** followers stand against **{boss_name}**.")

        round_number = 0
        while boss_hp > 0 and raid and round_number < max_rounds:
            round_number += 1
            target = randomm.choice(list(raid.keys()))
            critical = randomm.random() < float(attack_config.get("critical_chance", 0.3))
            if critical:
                damage = randomm.randint(
                    int(attack_config.get("critical_min", 160)),
                    int(attack_config.get("critical_max", 360)),
                )
            else:
                damage = randomm.randint(
                    int(attack_config.get("normal_min", 100)),
                    int(attack_config.get("normal_max", 280)),
                )
            raid[target] -= damage

            boss_embed = discord.Embed(
                title="Critical Hit!" if critical else f"{boss_name} Strikes!",
                description=(
                    f"{boss_name} tears into {target.mention} for **{damage}** damage."
                    if raid[target] > 0
                    else f"{boss_name} devours {target.mention} and leaves only silence behind."
                ),
                color=discord.Color.red() if critical or raid[target] <= 0 else discord.Color.dark_purple(),
            )
            self._apply_presentation(
                boss_embed,
                definition,
                color_key="boss_turn",
                media_key="boss_turn",
                default_color=discord.Color.red() if critical or raid[target] <= 0 else discord.Color.dark_purple(),
            )
            boss_embed.add_field(name="Target HP", value=max(0, raid[target]), inline=True)
            boss_embed.add_field(name="Round", value=round_number, inline=True)
            await ctx.send(embed=boss_embed)

            if raid[target] <= 0:
                del raid[target]
                if not raid:
                    break

            heal_chance = float(events_config.get("heal_chance", 0.2))
            if raid and randomm.random() < heal_chance:
                healed_target = randomm.choice(list(raid.keys()))
                heal_amount = randomm.randint(
                    int(events_config.get("heal_min", 90)),
                    int(events_config.get("heal_max", 140)),
                )
                raid[healed_target] += heal_amount
                await ctx.send(
                    f"Drakath's warped favor restores **{heal_amount} HP** to {healed_target.mention}."
                )

            pulse_chance = float(events_config.get("pulse_chance", 0.2))
            if raid and randomm.random() < pulse_chance:
                pulse_targets = min(
                    int(events_config.get("pulse_targets", 3)),
                    len(raid),
                )
                pulse_damage = int(events_config.get("pulse_damage", 100))
                selected_targets = randomm.sample(list(raid.keys()), pulse_targets)
                for selected_target in selected_targets:
                    raid[selected_target] -= pulse_damage
                await ctx.send(
                    f"A void pulse slams into {self._format_mentions(selected_targets)} for **{pulse_damage}** damage each."
                )
                for selected_target in selected_targets:
                    if raid[selected_target] <= 0:
                        del raid[selected_target]
                if not raid:
                    break

            combined_damage = 0
            for _participant in list(raid.keys()):
                if randomm.random() < float(players_config.get("critical_chance", 0.15)):
                    combined_damage += randomm.randint(
                        int(players_config.get("critical_min", 70)),
                        int(players_config.get("critical_max", 150)),
                    )
                else:
                    combined_damage += randomm.randint(
                        int(players_config.get("normal_min", 20)),
                        int(players_config.get("normal_max", 45)),
                    )

            boss_hp = max(0, boss_hp - combined_damage)
            raid_embed = discord.Embed(
                title=f"{boss_name} Under Siege",
                description="The swarm drives forward through fear and wreckage.",
                color=discord.Color.gold(),
            )
            self._apply_presentation(
                raid_embed,
                definition,
                color_key="raid_turn",
                media_key="raid_turn",
                default_color=discord.Color.gold(),
            )
            raid_embed.add_field(name="Combined Damage", value=combined_damage, inline=True)
            raid_embed.add_field(
                name=f"{boss_name} HP",
                value=f"{boss_hp} {self._progress_bar(boss_hp, initial_boss_hp)}",
                inline=True,
            )
            await ctx.send(embed=raid_embed)

            if boss_hp > 0:
                if combined_damage >= 300 and messages.get("high_damage"):
                    await ctx.send(randomm.choice(messages["high_damage"]))
                elif combined_damage >= 150 and messages.get("medium_damage"):
                    await ctx.send(randomm.choice(messages["medium_damage"]))
                elif messages.get("low_damage"):
                    await ctx.send(randomm.choice(messages["low_damage"]))

        if boss_hp <= 0 and raid:
            victory_text = messages.get(
                "victory",
                "{count} survivors remain as the boss is cast down.",
            ).format(
                count=len(raid),
                survivors=self._format_mentions(list(raid.keys())),
            )
            victory_embed = discord.Embed(
                title="Victory",
                description=victory_text,
                color=discord.Color.gold(),
            )
            self._apply_presentation(
                victory_embed,
                definition,
                color_key="victory",
                media_key="victory",
                default_color=discord.Color.gold(),
            )
            victory_embed.add_field(
                name="Survivors",
                value=self._format_mentions(list(raid.keys())),
                inline=False,
            )
            await ctx.send(embed=victory_embed)
            return

        if not raid:
            defeat_embed = discord.Embed(
                title="Defeat",
                description=messages.get("defeat", "The raid is wiped out."),
                color=self._resolve_color(
                    config.get("presentation", {}).get("colors", {}).get("defeat"),
                    discord.Color.red(),
                ),
            )
            await ctx.send(embed=defeat_embed)
            return

        await ctx.send(
            messages.get(
                "retreat",
                "{boss_name} slips back into the void with **{boss_hp}** HP remaining.",
            ).format(
                boss_name=boss_name,
                boss_hp=boss_hp,
            )
        )

    async def _run_ritual_definition(self, ctx, definition: dict[str, Any]) -> None:
        from cogs.raid import ShadowChampionAI, ShadowPriestAI

        raid_cog = self.bot.get_cog("Raid")
        if raid_cog is None:
            raise ValueError("The Raid cog must be loaded to run ritual definitions.")

        config = definition["config"]
        announce = config["announce"]
        presentation = config.get("presentation", {})
        role_labels = presentation.get("labels", {})
        prompt_copy = presentation.get("prompts", {})
        ritual_texts = presentation.get("texts", {})
        join_timeout = int(config.get("join_timeout", 900))
        decision_timeout = int(config.get("decision_timeout", 90))
        allow_ai_fallback = bool(config.get("allow_ai_fallback", True))
        champion_label = role_labels.get("champion", "Champion")
        priest_label = role_labels.get("priest", "Priest")
        followers_label = role_labels.get("followers", "Followers")
        guardian_label = role_labels.get("guardian", "Guardian")

        class DualJoinView(View):
            def __init__(self):
                super().__init__(timeout=join_timeout)
                self.follower_joined = []
                self.leader_joined = []

            @discord.ui.button(label=announce.get("follower_label", "Join as Follower"), style=ButtonStyle.secondary)
            async def follower_button(self, interaction: discord.Interaction, button: Button):
                if interaction.user in self.follower_joined or interaction.user in self.leader_joined:
                    await interaction.response.send_message("You already joined this ritual.", ephemeral=True)
                    return
                self.follower_joined.append(interaction.user)
                await interaction.response.send_message(
                    announce.get("follower_joined_message", "You joined as a follower."),
                    ephemeral=True,
                )

            @discord.ui.button(label=announce.get("leader_label", "Join as Leader"), style=ButtonStyle.primary)
            async def leader_button(self, interaction: discord.Interaction, button: Button):
                if interaction.user in self.follower_joined or interaction.user in self.leader_joined:
                    await interaction.response.send_message("You already joined this ritual.", ephemeral=True)
                    return
                self.leader_joined.append(interaction.user)
                await interaction.response.send_message(
                    announce.get("leader_joined_message", "You joined as a potential leader."),
                    ephemeral=True,
                )

        join_view = DualJoinView()
        intro_embed = discord.Embed(
            title=announce.get("title", definition["name"]),
            description=announce.get("description", definition.get("description", "")),
            color=discord.Color.dark_red(),
        )
        self._apply_presentation(
            intro_embed,
            definition,
            color_key="intro",
            media_key="intro",
            default_color=discord.Color.dark_red(),
        )
        intro_embed.set_footer(text=f"Skeleton: {definition['skeleton']}")
        await ctx.send(embed=intro_embed, view=join_view)

        countdown_messages = sorted(
            (
                entry
                for entry in announce.get("countdown_messages", [])
                if isinstance(entry, dict)
            ),
            key=lambda entry: int(entry.get("remaining", 0)),
            reverse=True,
        )
        countdown_context = {
            "definition_name": definition["name"],
            "champion_label": champion_label,
            "priest_label": priest_label,
            "followers_label": followers_label,
            "guardian_label": guardian_label,
        }
        remaining_time = join_timeout
        for countdown_entry in countdown_messages:
            checkpoint = max(0, int(countdown_entry.get("remaining", 0)))
            if checkpoint >= remaining_time:
                continue
            await asyncio.sleep(remaining_time - checkpoint)
            remaining_time = checkpoint
            countdown_text = self._format_template(
                countdown_entry.get("message", ""),
                **countdown_context,
            ).strip()
            if countdown_text:
                await ctx.send(countdown_text)

        await asyncio.sleep(remaining_time)
        join_view.stop()

        start_message = self._format_template(
            announce.get("start_message", ""),
            **countdown_context,
        ).strip()
        if start_message:
            await ctx.send(start_message)

        eligibility_message = self._format_template(
            announce.get("eligibility_message", ""),
            **countdown_context,
        ).strip()
        if eligibility_message:
            await ctx.send(eligibility_message)

        eligible_god = config.get("eligibility", {}).get("god")
        follower_participants = await self._filter_eligible_users(
            join_view.follower_joined,
            eligible_god,
        )
        leader_participants = await self._filter_eligible_users(
            join_view.leader_joined,
            eligible_god,
        )
        participants = self._dedupe_users(follower_participants + leader_participants)

        if not participants:
            await ctx.send(
                ritual_texts.get("no_valid", "No valid followers answered the ritual.")
            )
            return

        if not leader_participants:
            champion = ShadowChampionAI()
            priest = ShadowPriestAI()
            followers = participants
        else:
            champion = randomm.choice(leader_participants)
            leader_participants.remove(champion)
            if leader_participants:
                priest = randomm.choice(leader_participants)
                leader_participants.remove(priest)
            elif allow_ai_fallback:
                priest = ShadowPriestAI()
            else:
                priest = None
            followers = self._dedupe_users(follower_participants + leader_participants)

        await ctx.send(f"{champion_label}: **{getattr(champion, 'mention', champion)}**")
        if priest is not None:
            await ctx.send(f"{priest_label}: **{getattr(priest, 'mention', priest)}**")
        await ctx.send(
            f"{followers_label}: {self._format_mentions(followers) if followers else 'none'}"
        )

        champion_config = config["champion"]
        champion_actions = champion_config["actions"]
        priest_config = config["priest"]
        follower_actions = config["followers"]["actions"]
        guardian_config = config["guardian"]
        ritual_config = config["ritual"]
        follower_prompt = prompt_copy.get("follower", {})
        champion_prompt = prompt_copy.get("champion", {})
        priest_prompt = prompt_copy.get("priest", {})
        champion_action_labels = {
            action_name: self._action_display_name(action_name, action_config)
            for action_name, action_config in champion_actions.items()
        }
        priest_action_labels = {
            action_name: self._action_display_name(action_name, action_config)
            for action_name, action_config in priest_config["actions"].items()
        }
        follower_action_labels = {
            action_name: self._action_display_name(action_name, action_config)
            for action_name, action_config in follower_actions.items()
        }

        champion_stats = {
            "hp": int(champion_config["max_hp"]),
            "max_hp": int(champion_config["max_hp"]),
            "damage": int(champion_config["base_damage"]),
            "base_damage": int(champion_config["base_damage"]),
            "haste_cooldown": 0,
            "defending": False,
            "vulnerable": False,
            "shield_points": 0,
        }
        priest_stats = {
            "mana": int(priest_config["max_mana"]),
            "max_mana": int(priest_config["max_mana"]),
            "healing_boost": 1.0,
        }
        guardians_stats = {
            "hp": int(guardian_config["max_hp"]),
            "max_hp": int(guardian_config["max_hp"]),
            "damage_multiplier": 1.0,
            "shield_points": 0,
            "cursed": False,
            "incapacitated_turns": 0,
        }
        progress = int(ritual_config.get("start_progress", 0))
        max_turns = int(ritual_config.get("max_turns", 15))
        win_progress = int(ritual_config.get("win_progress", 100))
        guardian_collapse_progress = int(ritual_config.get("guardian_collapse_progress", 10))

        follower_embed = discord.Embed(
            title=follower_prompt.get("title", followers_label),
            description=follower_prompt.get(
                "description",
                "Choose how you support the ritual this turn.",
            ),
            color=discord.Color.purple(),
        )
        self._apply_presentation(
            follower_embed,
            definition,
            color_key="prompt",
            media_key="prompts",
            default_color=discord.Color.purple(),
        )
        for action_name, action_config in follower_actions.items():
            fragments = []
            if action_config.get("progress"):
                fragments.append(f"+{action_config['progress']} progress")
            if action_config.get("shield"):
                fragments.append(f"+{action_config['shield']} shield")
            if action_config.get("heal"):
                fragments.append(f"+{action_config['heal']} heal")
            if action_config.get("healing_boost"):
                fragments.append(f"+{action_config['healing_boost']} priest boost")
            if action_config.get("guardian_damage_down"):
                fragments.append(f"-{action_config['guardian_damage_down']} guardian damage")
            follower_embed.add_field(
                name=self._action_display_name(action_name, action_config),
                value=action_config.get("description", ", ".join(fragments) if fragments else "Support action"),
                inline=False,
            )

        champion_embed = discord.Embed(
            title=champion_prompt.get("title", champion_label),
            description=champion_prompt.get(
                "description",
                f"Choose how the {champion_label} acts this turn.",
            ),
            color=discord.Color.red(),
        )
        self._apply_presentation(
            champion_embed,
            definition,
            color_key="prompt",
            media_key="prompts",
            default_color=discord.Color.red(),
        )
        for action_name, action_config in champion_actions.items():
            champion_embed.add_field(
                name=self._action_display_name(action_name, action_config),
                value=action_config.get("description", "Champion action."),
                inline=False,
            )

        priest_embed = discord.Embed(
            title=priest_prompt.get("title", priest_label),
            description=priest_prompt.get(
                "description",
                f"Choose how the {priest_label} shapes the ritual this turn.",
            ),
            color=discord.Color.dark_purple(),
        )
        self._apply_presentation(
            priest_embed,
            definition,
            color_key="prompt",
            media_key="prompts",
            default_color=discord.Color.dark_purple(),
        )
        for action_name, action_config in priest_config["actions"].items():
            priest_embed.add_field(
                name=self._action_display_name(action_name, action_config),
                value=(
                    f"{action_config.get('description', 'Priest spell.')}\n"
                    f"Cost: {action_config.get('mana_cost', 0)} mana"
                ),
                inline=False,
            )

        async def get_follower_decisions() -> dict[str, int]:
            combined = {action_name: 0 for action_name in follower_actions}
            if not followers:
                return combined

            async def get_single_decision(follower):
                decision, _used_default = await self._safe_get_player_decision(
                    raid_cog,
                    follower,
                    list(follower_actions.keys()),
                    "follower",
                    decision_timeout,
                    follower_embed,
                    option_labels=follower_action_labels,
                )
                return decision

            tasks = [get_single_decision(follower) for follower in followers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    continue
                if result in combined:
                    combined[result] += 1
            return combined

        def clamp_progress(value: int) -> int:
            return max(0, min(value, win_progress))

        def apply_damage_to_champion(raw_damage: float) -> int:
            damage = raw_damage
            if champion_stats["defending"]:
                damage *= float(champion_config.get("defend_multiplier", 0.6))
                champion_stats["defending"] = False
            if champion_stats["vulnerable"]:
                damage *= float(champion_config.get("vulnerable_multiplier", 1.25))
                champion_stats["vulnerable"] = False

            damage = int(round(damage))
            if champion_stats["shield_points"] > 0:
                absorbed = min(damage, champion_stats["shield_points"])
                champion_stats["shield_points"] -= absorbed
                damage -= absorbed
            champion_stats["hp"] -= damage
            return damage

        def current_guardian_phase() -> dict[str, Any]:
            phases = sorted(
                guardian_config.get("phases", []),
                key=lambda item: int(item.get("threshold", 0)),
            )
            current = phases[0]
            for phase in phases:
                if progress >= int(phase.get("threshold", 0)):
                    current = phase
            return current

        def choose_guardian_action(abilities: list[str]) -> str:
            if guardians_stats["shield_points"] <= 0 and "shield" in abilities and guardians_stats["hp"] < guardians_stats["max_hp"] * 0.5:
                return "shield"
            if progress >= int(win_progress * 0.75) and "purify" in abilities:
                return "purify"
            if champion_stats["hp"] < champion_stats["max_hp"] * 0.4 and "obliterate" in abilities:
                return "obliterate"
            if guardians_stats["cursed"] and "soul_drain" in abilities:
                return "soul_drain"
            return randomm.choice(abilities)

        for turn_number in range(1, max_turns + 1):
            if champion_stats["hp"] <= 0:
                await ctx.send(
                    self._format_template(
                        ritual_texts.get(
                            "champion_fall",
                            "The {champion_label} falls, and the ritual collapses with them.",
                        ),
                        champion_label=champion_label,
                    )
                )
                return
            if progress >= win_progress:
                break

            follower_combined_decision = {action_name: 0 for action_name in follower_actions}
            priest_decision = None
            champion_decision = None

            if priest is not None:
                valid_priest_options = [
                    action_name
                    for action_name, action_config in priest_config["actions"].items()
                    if priest_stats["mana"] >= int(action_config.get("mana_cost", 0))
                ]
                if isinstance(priest, ShadowPriestAI):
                    fallback_priest_decision = await priest.make_decision(
                        priest_stats,
                        champion_stats,
                        guardians_stats,
                        progress,
                        follower_combined_decision,
                    )
                    priest_decision = (
                        fallback_priest_decision
                        if fallback_priest_decision in valid_priest_options
                        else (valid_priest_options[0] if valid_priest_options else None)
                    )
                    if priest_decision is not None:
                        await priest.announce_decision(
                            ctx,
                            priest_decision,
                            priest_stats,
                            champion_stats,
                            guardians_stats,
                            progress,
                        )
                else:
                    if valid_priest_options:
                        await ctx.send(
                            self._format_template(
                                ritual_texts.get("turn_prompt", "It's {player}'s turn. Check DMs."),
                                player=priest.mention,
                            )
                        )
                        priest_decision, _used_default = await self._safe_get_player_decision(
                            raid_cog,
                            priest,
                            valid_priest_options,
                            "priest",
                            decision_timeout,
                            priest_embed,
                            option_labels=priest_action_labels,
                        )

                if priest_decision is not None:
                    action_config = priest_config["actions"][priest_decision]
                    priest_stats["mana"] -= int(action_config.get("mana_cost", 0))
                    champion_stats["damage"] += int(action_config.get("damage_boost", 0))
                    champion_stats["shield_points"] += int(action_config.get("shield", 0))
                    champion_stats["hp"] = min(
                        champion_stats["max_hp"],
                        champion_stats["hp"] + int(action_config.get("heal", 0) * priest_stats["healing_boost"]),
                    )
                    guardians_stats["damage_multiplier"] = max(
                        0.5,
                        guardians_stats["damage_multiplier"] - float(action_config.get("guardian_damage_down", 0.0)),
                    )
                    guardians_stats["cursed"] = bool(action_config.get("guardian_damage_down", 0.0))
                    progress = clamp_progress(
                        progress + int(action_config.get("progress", 0) * priest_stats["healing_boost"])
                    )
                    await ctx.send(
                        self._format_template(
                            action_config.get(
                                "result_text",
                                "The {priest_label} invokes **{action_name}**.",
                            ),
                            priest_label=priest_label,
                            champion_label=champion_label,
                            guardian_label=guardian_label,
                            action_name=self._action_display_name(priest_decision, action_config),
                            damage_boost=action_config.get("damage_boost", 0),
                            shield=action_config.get("shield", 0),
                            heal=int(action_config.get("heal", 0) * priest_stats["healing_boost"]),
                            progress=int(action_config.get("progress", 0) * priest_stats["healing_boost"]),
                        )
                    )

            if guardians_stats["hp"] <= 0 and guardians_stats["incapacitated_turns"] == 0:
                guardians_stats["incapacitated_turns"] = 1
                progress = clamp_progress(progress + guardian_collapse_progress)
                await ctx.send(
                    self._format_template(
                        ritual_texts.get(
                            "collapse",
                            "The {guardian_label} collapses and the ritual surges forward.",
                        ),
                        guardian_label=guardian_label,
                    )
                )

            phase_info = current_guardian_phase()
            if guardians_stats["incapacitated_turns"] > 0:
                guardians_stats["incapacitated_turns"] -= 1
                if guardians_stats["incapacitated_turns"] == 0:
                    guardians_stats["hp"] = int(
                        guardians_stats["max_hp"] * float(guardian_config.get("respawn_hp_ratio", 0.45))
                    )
                    await ctx.send(
                        self._format_template(
                            ritual_texts.get(
                                "respawn",
                                "The {guardian_label} rises again as **{phase_name}**.",
                            ),
                            guardian_label=guardian_label,
                            phase_name=phase_info["name"],
                        )
                    )
            else:
                ability_name = choose_guardian_action(list(phase_info.get("abilities", [])))
                ability_config = guardian_config["abilities"][ability_name]
                display_ability_name = self._guardian_ability_display_name(
                    ability_name,
                    ability_config,
                )
                if "damage_range" in ability_config:
                    low, high = ability_config["damage_range"]
                    raw_damage = randomm.randint(int(low), int(high)) * guardians_stats["damage_multiplier"]
                    dealt_damage = apply_damage_to_champion(raw_damage)
                    if ability_config.get("heal_ratio"):
                        guardians_stats["hp"] = min(
                            guardians_stats["max_hp"],
                            guardians_stats["hp"] + int(dealt_damage * float(ability_config["heal_ratio"])),
                        )
                    if ability_config.get("damage_down"):
                        champion_stats["damage"] = max(
                            0,
                            champion_stats["damage"] - int(ability_config["damage_down"]),
                        )
                    await ctx.send(
                        self._format_template(
                            ability_config.get(
                                "damage_text",
                                "The {guardian_label} uses **{ability_name}** for **{damage}** damage.",
                            ),
                            guardian_label=guardian_label,
                            ability_name=display_ability_name,
                            damage=dealt_damage,
                        )
                    )
                if ability_config.get("shield"):
                    guardians_stats["shield_points"] += int(ability_config["shield"])
                    await ctx.send(
                        self._format_template(
                            ability_config.get(
                                "shield_text",
                                "The {guardian_label} reinforces itself with **{shield}** shield.",
                            ),
                            guardian_label=guardian_label,
                            ability_name=display_ability_name,
                            shield=ability_config["shield"],
                        )
                    )
                if ability_config.get("progress_down"):
                    progress = clamp_progress(progress - int(ability_config["progress_down"]))
                    await ctx.send(
                        self._format_template(
                            ability_config.get(
                                "progress_text",
                                "The ritual is driven back by **{progress_down}** progress.",
                            ),
                            guardian_label=guardian_label,
                            ability_name=display_ability_name,
                            progress_down=ability_config["progress_down"],
                        )
                    )

            if champion_stats["hp"] <= 0:
                await ctx.send(
                    self._format_template(
                        ritual_texts.get(
                            "champion_slain",
                            "The {champion_label} is slain before the ritual can recover.",
                        ),
                        champion_label=champion_label,
                    )
                )
                return

            follower_combined_decision = await get_follower_decisions()
            for action_name, count in follower_combined_decision.items():
                if count <= 0:
                    continue
                action_config = follower_actions[action_name]
                progress_gain = int(action_config.get("progress", 0) * count)
                cap_total = action_config.get("cap_total")
                if cap_total is not None:
                    progress_gain = min(progress_gain, int(cap_total))
                progress = clamp_progress(progress + progress_gain)
                champion_stats["shield_points"] += int(action_config.get("shield", 0) * count)
                champion_stats["hp"] = min(
                    champion_stats["max_hp"],
                    champion_stats["hp"] + int(action_config.get("heal", 0) * count),
                )
                priest_stats["healing_boost"] += float(action_config.get("healing_boost", 0.0) * count)
                guardians_stats["damage_multiplier"] = max(
                    0.5,
                    guardians_stats["damage_multiplier"] - float(action_config.get("guardian_damage_down", 0.0) * count),
                )

            valid_champion_options = self._valid_champion_action_names(
                champion_actions,
                champion_stats,
            )

            if isinstance(champion, ShadowChampionAI):
                fallback_champion_decision = await champion.make_decision(
                    champion_stats,
                    guardians_stats,
                    progress,
                    follower_combined_decision,
                )
                champion_decision = self._resolve_champion_ai_choice(
                    fallback_champion_decision,
                    champion_actions,
                    valid_champion_options,
                )
                await champion.announce_decision(
                    ctx,
                    champion_decision,
                    champion_stats,
                    guardians_stats,
                    progress,
                )
            else:
                await ctx.send(
                    self._format_template(
                        ritual_texts.get("turn_prompt", "It's {player}'s turn. Check DMs."),
                        player=champion.mention,
                    )
                )
                champion_decision, _used_default = await self._safe_get_player_decision(
                    raid_cog,
                    champion,
                    valid_champion_options,
                    "champion",
                    decision_timeout,
                    champion_embed,
                    option_labels=champion_action_labels,
                )

            champion_action_config = champion_actions.get(champion_decision, {})
            champion_effect = self._champion_action_effect(
                champion_decision or "",
                champion_action_config,
            )
            if champion_effect == "damage":
                damage = champion_stats["damage"]
                if guardians_stats["shield_points"] > 0:
                    absorbed = min(damage, guardians_stats["shield_points"])
                    guardians_stats["shield_points"] -= absorbed
                    damage -= absorbed
                guardians_stats["hp"] -= damage
                await ctx.send(
                    self._format_template(
                        champion_action_config.get(
                            "result_text",
                            "The {champion_label} smites the {guardian_label} for **{damage}** damage.",
                        ),
                        champion_label=champion_label,
                        guardian_label=guardian_label,
                        action_name=self._action_display_name(champion_decision, champion_action_config),
                        damage=damage,
                    )
                )
            elif champion_effect == "heal":
                heal_amount = int(champion_config.get("heal_amount", 200))
                champion_stats["hp"] = min(champion_stats["max_hp"], champion_stats["hp"] + heal_amount)
                await ctx.send(
                    self._format_template(
                        champion_action_config.get(
                            "result_text",
                            "The {champion_label} restores **{heal_amount}** HP.",
                        ),
                        champion_label=champion_label,
                        guardian_label=guardian_label,
                        action_name=self._action_display_name(champion_decision, champion_action_config),
                        heal_amount=heal_amount,
                    )
                )
            elif champion_effect == "haste":
                progress = clamp_progress(progress + int(champion_config.get("haste_progress", 15)))
                champion_stats["haste_cooldown"] = int(champion_config.get("haste_cooldown", 3))
                champion_stats["vulnerable"] = True
                await ctx.send(
                    self._format_template(
                        champion_action_config.get(
                            "result_text",
                            "The {champion_label} drives the ritual forward and leaves themselves exposed.",
                        ),
                        champion_label=champion_label,
                        guardian_label=guardian_label,
                        action_name=self._action_display_name(champion_decision, champion_action_config),
                    )
                )
            elif champion_effect == "defend":
                champion_stats["defending"] = True
                await ctx.send(
                    self._format_template(
                        champion_action_config.get(
                            "result_text",
                            "The {champion_label} braces for the next assault.",
                        ),
                        champion_label=champion_label,
                        guardian_label=guardian_label,
                        action_name=self._action_display_name(champion_decision, champion_action_config),
                    )
                )
            elif champion_effect == "sacrifice":
                self_damage = int(champion_config.get("sacrifice_hp", 350))
                champion_stats["hp"] -= self_damage
                progress = clamp_progress(progress + int(champion_config.get("sacrifice_progress", 18)))
                await ctx.send(
                    self._format_template(
                        champion_action_config.get(
                            "result_text",
                            "The {champion_label} offers **{self_damage}** HP to advance the ritual.",
                        ),
                        champion_label=champion_label,
                        guardian_label=guardian_label,
                        action_name=self._action_display_name(champion_decision, champion_action_config),
                        self_damage=self_damage,
                    )
                )

            if champion_stats["haste_cooldown"] > 0:
                champion_stats["haste_cooldown"] -= 1

            status_embed = discord.Embed(
                title=f"{definition['name']} - Turn {turn_number}",
                color=discord.Color.dark_red(),
            )
            self._apply_presentation(
                status_embed,
                definition,
                color_key="status",
                media_key="status",
                default_color=discord.Color.dark_red(),
            )
            status_embed.add_field(
                name="Ritual Progress",
                value=f"{self._progress_bar(progress, win_progress)} {progress}/{win_progress}",
                inline=False,
            )
            status_embed.add_field(
                name=champion_label,
                value=f"{max(0, int(champion_stats['hp']))}/{champion_stats['max_hp']} HP",
                inline=True,
            )
            status_embed.add_field(
                name=guardian_label,
                value=(
                    f"{phase_info['name']}\n"
                    f"{max(0, int(guardians_stats['hp']))}/{guardians_stats['max_hp']} HP"
                ),
                inline=True,
            )
            if priest is not None:
                status_embed.add_field(
                    name=f"{priest_label} Mana",
                    value=f"{priest_stats['mana']}/{priest_stats['max_mana']}",
                    inline=True,
                )
            if champion_decision is not None:
                status_embed.add_field(
                    name=f"{champion_label} Action",
                    value=champion_action_labels.get(champion_decision, champion_decision),
                    inline=False,
                )
            if priest_decision is not None:
                status_embed.add_field(
                    name=f"{priest_label} Action",
                    value=priest_action_labels.get(priest_decision, priest_decision),
                    inline=False,
                )
            follower_summary = ", ".join(
                f"{follower_action_labels.get(action, action)}: {count}"
                for action, count in follower_combined_decision.items()
                if count
            ) or ritual_texts.get("followers_summary_empty", "No follower contributions this turn.")
            status_embed.add_field(name=followers_label, value=follower_summary, inline=False)
            await ctx.send(embed=status_embed)

            champion_stats["damage"] = champion_stats["base_damage"]
            priest_stats["mana"] = min(
                priest_stats["max_mana"],
                priest_stats["mana"] + int(priest_config.get("mana_regen", 10)),
            )
            priest_stats["healing_boost"] = 1.0
            guardians_stats["damage_multiplier"] = 1.0
            guardians_stats["cursed"] = False

        if champion_stats["hp"] <= 0:
            await ctx.send(
                self._format_template(
                    ritual_texts.get(
                        "champion_fall",
                        "The {champion_label} falls, and the ritual collapses with them.",
                    ),
                    champion_label=champion_label,
                )
            )
            return
        if progress >= win_progress:
            victory_embed = discord.Embed(
                title="Ritual Complete",
                description=self._format_template(
                    ritual_texts.get(
                        "success",
                        "The ritual completes successfully. Sepulchure answers the call of **{definition_name}**.",
                    ),
                    definition_name=definition["name"],
                ),
                color=discord.Color.green(),
            )
            self._apply_presentation(
                victory_embed,
                definition,
                color_key="victory",
                media_key="victory",
                default_color=discord.Color.green(),
            )
            await ctx.send(embed=victory_embed)
            return
        await ctx.send(
            self._format_template(
                ritual_texts.get(
                    "stall",
                    "The ritual stalls at **{progress}/{win_progress}** progress and the {guardian_label} endures.",
                ),
                progress=progress,
                win_progress=win_progress,
                guardian_label=guardian_label,
            )
        )

    @staticmethod
    def _require_text(value: str, field_name: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field_name} cannot be empty.")
        return cleaned

    @staticmethod
    def _parse_int(value: str, field_name: str, *, min_value: int | None = None, max_value: int | None = None) -> int:
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an integer.") from exc
        if min_value is not None and parsed < min_value:
            raise ValueError(f"{field_name} must be at least {min_value}.")
        if max_value is not None and parsed > max_value:
            raise ValueError(f"{field_name} must be at most {max_value}.")
        return parsed

    @staticmethod
    def _parse_float(value: str, field_name: str, *, min_value: float | None = None, max_value: float | None = None) -> float:
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a number.") from exc
        if min_value is not None and parsed < min_value:
            raise ValueError(f"{field_name} must be at least {min_value}.")
        if max_value is not None and parsed > max_value:
            raise ValueError(f"{field_name} must be at most {max_value}.")
        return parsed

    @staticmethod
    def _parse_bool(value: str, field_name: str) -> bool:
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "no", "n", "0", "off"}:
            return False
        raise ValueError(f"{field_name} must be true/false.")

    @staticmethod
    def _parse_csv_list(value: str) -> list[str]:
        return [entry.strip() for entry in value.split(",") if entry.strip()]

    @staticmethod
    def _parse_message_lines(value: str) -> list[str]:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if not lines:
            raise ValueError("At least one message line is required.")
        return lines

    @staticmethod
    def _parse_optional_text(value: str) -> str:
        return value.strip()

    @staticmethod
    def _parse_hex_color(value: str, field_name: str) -> str:
        cleaned = value.strip()
        if re.fullmatch(r"#?[0-9A-Fa-f]{6}", cleaned) is None:
            raise ValueError(f"{field_name} must be a hex color like `#A1B2C3`.")
        return f"#{cleaned.lstrip('#').upper()}"

    @staticmethod
    def _resolve_color(raw_color: str | None, default: discord.Color) -> discord.Color:
        if not raw_color:
            return default
        cleaned = raw_color.strip().lstrip("#")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", cleaned) is None:
            return default
        return discord.Color(int(cleaned, 16))

    @staticmethod
    def _format_template(template: str, **kwargs: Any) -> str:
        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        return str(template).format_map(_SafeDict(kwargs))

    @staticmethod
    def _action_display_name(action_name: str, action_config: dict[str, Any]) -> str:
        return str(action_config.get("display_name") or action_name)

    @staticmethod
    def _guardian_ability_display_name(ability_name: str, ability_config: dict[str, Any]) -> str:
        return str(ability_config.get("display_name") or ability_name.replace("_", " ").title())

    @staticmethod
    def _champion_action_effect(action_name: str, action_config: dict[str, Any]) -> str:
        effect = str(action_config.get("effect") or "").strip().casefold()
        if effect:
            return effect
        legacy_map = {
            "smite": "damage",
            "heal": "heal",
            "haste": "haste",
            "defend": "defend",
            "sacrifice": "sacrifice",
        }
        return legacy_map.get(action_name.casefold(), "damage")

    @staticmethod
    def _slugify_builder_key(text: str, *, fallback: str = "item") -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
        return cleaned or fallback

    def _unique_builder_key(self, existing_keys: list[str] | set[str], base: str) -> str:
        normalized = self._slugify_builder_key(base)
        existing = {str(key).casefold() for key in existing_keys}
        if normalized.casefold() not in existing:
            return normalized
        counter = 2
        while f"{normalized}_{counter}".casefold() in existing:
            counter += 1
        return f"{normalized}_{counter}"

    @staticmethod
    def _reordered_dict(data: dict[str, Any], move_key: str, delta: int) -> dict[str, Any]:
        items = list(data.items())
        index = next((index for index, (key, _value) in enumerate(items) if key == move_key), None)
        if index is None:
            return data
        target_index = max(0, min(len(items) - 1, index + delta))
        if target_index == index:
            return data
        item = items.pop(index)
        items.insert(target_index, item)
        return dict(items)

    @staticmethod
    def _insert_after_dict_item(data: dict[str, Any], after_key: str, new_key: str, new_value: Any) -> dict[str, Any]:
        items = list(data.items())
        index = next((index for index, (key, _value) in enumerate(items) if key == after_key), len(items) - 1)
        items.insert(index + 1, (new_key, new_value))
        return dict(items)

    @staticmethod
    def _delete_dict_item(data: dict[str, Any], delete_key: str) -> dict[str, Any]:
        return {key: value for key, value in data.items() if key != delete_key}

    @staticmethod
    def _new_good_event() -> dict[str, Any]:
        return {
            "text": "New Trial Event",
            "success_rate": 50,
            "mercy_chance": 0,
            "win_text": "The test is overcome.",
            "lose_text": "The trial claims another soul.",
        }

    def _new_good_phase(self, phase_key: str) -> dict[str, Any]:
        return {
            "key": phase_key,
            "weight": 1,
            "title": phase_key.replace("_", " ").title(),
            "description": "Describe the atmosphere and stakes of this phase.",
            "events": [self._new_good_event()],
        }

    @staticmethod
    def _new_priest_action(action_name: str) -> dict[str, Any]:
        display_name = action_name.replace("_", " ").title()
        return {
            "display_name": display_name,
            "description": "Describe the ritual magic this action represents.",
            "result_text": "The {priest_label} invokes **{action_name}**.",
            "mana_cost": 15,
            "progress": 8,
        }

    @staticmethod
    def _new_follower_action(action_name: str) -> dict[str, Any]:
        display_name = action_name.replace("_", " ").title()
        return {
            "display_name": display_name,
            "description": "Describe how followers support the ritual with this action.",
            "progress": 1,
        }

    @staticmethod
    def _new_guardian_ability(ability_name: str) -> dict[str, Any]:
        display_name = ability_name.replace("_", " ").title()
        return {
            "display_name": display_name,
            "description": "Describe the Guardian's attack pattern.",
            "damage_text": "The {guardian_label} uses **{ability_name}** for **{damage}** damage.",
            "damage_range": [120, 220],
        }

    def _new_guardian_phase(
        self,
        phase_name: str,
        available_abilities: list[str],
        threshold: int,
    ) -> dict[str, Any]:
        return {
            "threshold": threshold,
            "name": phase_name,
            "description": "Describe how the Guardian changes in this phase.",
            "abilities": available_abilities[:1] if available_abilities else [],
        }

    def _new_champion_action(
        self,
        action_name: str,
        *,
        effect: str = "damage",
    ) -> dict[str, Any]:
        display_name = action_name.replace("_", " ").title()
        effect_map = {
            "damage": {
                "result_text": "The {champion_label} smites the {guardian_label} for **{damage}** damage.",
                "description": "Damage the Guardian.",
            },
            "heal": {
                "result_text": "The {champion_label} restores **{heal_amount}** HP.",
                "description": "Recover HP.",
            },
            "haste": {
                "result_text": "The {champion_label} drives the ritual forward and leaves themselves exposed.",
                "description": "Advance ritual progress and become vulnerable.",
            },
            "defend": {
                "result_text": "The {champion_label} braces for the next assault.",
                "description": "Reduce incoming damage.",
            },
            "sacrifice": {
                "result_text": "The {champion_label} offers **{self_damage}** HP to advance the ritual.",
                "description": "Trade HP for ritual progress.",
            },
        }
        effect_defaults = effect_map.get(effect, effect_map["damage"])
        return {
            "effect": effect,
            "display_name": display_name,
            "description": effect_defaults["description"],
            "result_text": effect_defaults["result_text"],
        }

    def _valid_champion_action_names(
        self,
        champion_actions: dict[str, dict[str, Any]],
        champion_stats: dict[str, Any],
    ) -> list[str]:
        valid_actions = []
        for action_name, action_config in champion_actions.items():
            effect = self._champion_action_effect(action_name, action_config)
            if effect == "haste" and champion_stats.get("haste_cooldown", 0) > 0:
                continue
            valid_actions.append(action_name)
        return valid_actions

    def _resolve_champion_ai_choice(
        self,
        ai_choice: str | None,
        champion_actions: dict[str, dict[str, Any]],
        valid_options: list[str],
    ) -> str | None:
        if not valid_options:
            return None
        if ai_choice in valid_options:
            return ai_choice
        requested_effect = {
            "Smite": "damage",
            "Heal": "heal",
            "Haste": "haste",
            "Defend": "defend",
            "Sacrifice": "sacrifice",
        }.get(str(ai_choice))
        if requested_effect:
            for action_name in valid_options:
                if self._champion_action_effect(action_name, champion_actions[action_name]) == requested_effect:
                    return action_name
        return valid_options[0]

    def _builder_structure_state(
        self,
        definition: dict[str, Any] | None,
        page_key: str | None,
        item_key: str | None,
    ) -> dict[str, Any]:
        if definition is None or page_key is None:
            return {"supported": False, "reason": "Choose a list page first."}

        config = definition["config"]
        skeleton = self._definition_skeleton_key(definition)
        if skeleton == "trial":
            if page_key == "phase":
                phases = config.get("phases", [])
                if not phases:
                    return {"supported": False, "reason": "No phases are configured."}
                phase_keys = [phase["key"] for phase in phases]
                selected_key = item_key if item_key in phase_keys else phase_keys[0]
                index = phase_keys.index(selected_key)
                return {
                    "supported": True,
                    "entity_label": "phase",
                    "selected_label": selected_key,
                    "position": index + 1,
                    "total": len(phase_keys),
                    "can_delete": len(phase_keys) > 1,
                    "can_move_up": index > 0,
                    "can_move_down": index < len(phase_keys) - 1,
                }
            if page_key == "event":
                phase_key, raw_index = (item_key or "day:0").split(":")
                phase = next((phase for phase in config.get("phases", []) if phase["key"] == phase_key), None)
                if phase is None or not phase.get("events"):
                    return {"supported": False, "reason": "This phase has no events."}
                event_index = int(raw_index)
                events = phase["events"]
                event_index = max(0, min(event_index, len(events) - 1))
                event = events[event_index]
                return {
                    "supported": True,
                    "entity_label": "event",
                    "selected_label": event.get("text", f"{phase_key} event {event_index + 1}"),
                    "position": event_index + 1,
                    "total": len(events),
                    "scope_label": phase_key,
                    "can_delete": len(events) > 1,
                    "can_move_up": event_index > 0,
                    "can_move_down": event_index < len(events) - 1,
                }
            return {"supported": False, "reason": "This page is not a list editor."}

        if skeleton == "ritual":
            if page_key in {"champion_action", "priest_action", "follower_action", "guardian_ability", "guardian_ability_copy"}:
                if page_key == "champion_action":
                    container = config["champion"]["actions"]
                    labeler = self._action_display_name
                    entity_label = "champion action"
                elif page_key == "priest_action":
                    container = config["priest"]["actions"]
                    labeler = self._action_display_name
                    entity_label = "priest action"
                elif page_key == "follower_action":
                    container = config["followers"]["actions"]
                    labeler = self._action_display_name
                    entity_label = "follower action"
                else:
                    container = config["guardian"]["abilities"]
                    labeler = self._guardian_ability_display_name
                    entity_label = "guardian ability"
                keys = list(container.keys())
                if not keys:
                    return {"supported": False, "reason": "No items are configured."}
                selected_key = item_key if item_key in keys else keys[0]
                index = keys.index(selected_key)
                return {
                    "supported": True,
                    "entity_label": entity_label,
                    "selected_label": labeler(selected_key, container[selected_key]),
                    "position": index + 1,
                    "total": len(keys),
                    "can_delete": len(keys) > 1,
                    "can_move_up": index > 0,
                    "can_move_down": index < len(keys) - 1,
                }
            if page_key == "guardian_phase":
                phases = config["guardian"].get("phases", [])
                if not phases:
                    return {"supported": False, "reason": "No guardian phases are configured."}
                phase_index = int(item_key or "0")
                phase_index = max(0, min(phase_index, len(phases) - 1))
                phase = phases[phase_index]
                return {
                    "supported": True,
                    "entity_label": "guardian phase",
                    "selected_label": phase.get("name", f"Phase {phase_index + 1}"),
                    "position": phase_index + 1,
                    "total": len(phases),
                    "can_delete": len(phases) > 1,
                    "can_move_up": phase_index > 0,
                    "can_move_down": phase_index < len(phases) - 1,
                }
            return {"supported": False, "reason": "This page is not a list editor."}

        return {"supported": False, "reason": "This skeleton does not expose structural editing here."}

    def _builder_structure_action(
        self,
        definition: dict[str, Any],
        page_key: str,
        item_key: str | None,
        action: str,
        *,
        delta: int = 0,
    ) -> tuple[str | None, str | None, str]:
        config = definition["config"]
        normalized_page = "guardian_ability" if page_key == "guardian_ability_copy" else page_key
        skeleton = self._definition_skeleton_key(definition)

        if skeleton == "trial" and normalized_page == "phase":
            phases = config.get("phases", [])
            phase_keys = [phase["key"] for phase in phases]
            current_key = item_key if item_key in phase_keys else phase_keys[0]
            current_index = phase_keys.index(current_key)

            if action == "add":
                new_key = self._unique_builder_key(phase_keys, "phase")
                phases.append(self._new_good_phase(new_key))
                self._save_registry()
                return "phase", new_key, f"Added phase `{new_key}`. Use `Edit` to customize it."
            if action == "duplicate":
                source = copy.deepcopy(phases[current_index])
                source["key"] = self._unique_builder_key(phase_keys, f"{current_key}_copy")
                phases.insert(current_index + 1, source)
                self._save_registry()
                return "phase", source["key"], f"Duplicated phase `{current_key}`."
            if action == "delete":
                if len(phases) <= 1:
                    raise ValueError("At least one phase must remain.")
                del phases[current_index]
                next_index = max(0, min(current_index, len(phases) - 1))
                self._save_registry()
                return "phase", phases[next_index]["key"], f"Deleted phase `{current_key}`."
            if action == "move":
                target_index = max(0, min(len(phases) - 1, current_index + delta))
                if target_index == current_index:
                    raise ValueError("That phase cannot move any further.")
                phase = phases.pop(current_index)
                phases.insert(target_index, phase)
                self._save_registry()
                return "phase", phase["key"], f"Moved phase `{phase['key']}`."

        if skeleton == "trial" and normalized_page == "event":
            phase_key, raw_index = (item_key or "day:0").split(":")
            phase = next((phase for phase in config.get("phases", []) if phase["key"] == phase_key), None)
            if phase is None:
                raise ValueError("Selected phase no longer exists.")
            events = phase.setdefault("events", [])
            if not events:
                events.append(self._new_good_event())
            event_index = max(0, min(int(raw_index), len(events) - 1))
            if action == "add":
                events.insert(event_index + 1, self._new_good_event())
                self._save_registry()
                return "event", f"{phase_key}:{event_index + 1}", f"Added a new event to `{phase_key}`."
            if action == "duplicate":
                events.insert(event_index + 1, copy.deepcopy(events[event_index]))
                self._save_registry()
                return "event", f"{phase_key}:{event_index + 1}", f"Duplicated an event in `{phase_key}`."
            if action == "delete":
                if len(events) <= 1:
                    raise ValueError("At least one event must remain in a phase.")
                del events[event_index]
                next_index = max(0, min(event_index, len(events) - 1))
                self._save_registry()
                return "event", f"{phase_key}:{next_index}", f"Deleted an event from `{phase_key}`."
            if action == "move":
                target_index = max(0, min(len(events) - 1, event_index + delta))
                if target_index == event_index:
                    raise ValueError("That event cannot move any further.")
                event = events.pop(event_index)
                events.insert(target_index, event)
                self._save_registry()
                return "event", f"{phase_key}:{target_index}", f"Moved an event within `{phase_key}`."

        if skeleton == "ritual" and normalized_page in {
            "champion_action",
            "priest_action",
            "follower_action",
            "guardian_ability",
        }:
            if normalized_page == "champion_action":
                container = config["champion"]["actions"]
                base_name = "champion_action"
                factory = lambda key: self._new_champion_action(key)
            elif normalized_page == "priest_action":
                container = config["priest"]["actions"]
                base_name = "priest_action"
                factory = self._new_priest_action
            elif normalized_page == "follower_action":
                container = config["followers"]["actions"]
                base_name = "follower_action"
                factory = self._new_follower_action
            else:
                container = config["guardian"]["abilities"]
                base_name = "guardian_ability"
                factory = self._new_guardian_ability
            keys = list(container.keys())
            current_key = item_key if item_key in keys else keys[0]
            current_index = keys.index(current_key)
            entity_name = normalized_page.replace("_", " ")

            if action == "add":
                new_key = self._unique_builder_key(keys, base_name)
                new_value = factory(new_key)
                rebuilt = self._insert_after_dict_item(container, keys[-1], new_key, new_value)
                container.clear()
                container.update(rebuilt)
                self._save_registry()
                return page_key, new_key, f"Added {entity_name} `{new_key}`."
            if action == "duplicate":
                new_key = self._unique_builder_key(keys, f"{current_key}_copy")
                new_value = copy.deepcopy(container[current_key])
                new_value["display_name"] = new_key.replace("_", " ").title()
                rebuilt = self._insert_after_dict_item(container, current_key, new_key, new_value)
                container.clear()
                container.update(rebuilt)
                self._save_registry()
                return page_key, new_key, f"Duplicated {entity_name} `{current_key}`."
            if action == "delete":
                if len(keys) <= 1:
                    raise ValueError("At least one item must remain.")
                rebuilt = self._delete_dict_item(container, current_key)
                container.clear()
                container.update(rebuilt)
                next_keys = list(container.keys())
                next_index = max(0, min(current_index, len(next_keys) - 1))
                self._save_registry()
                return page_key, next_keys[next_index], f"Deleted {entity_name} `{current_key}`."
            if action == "move":
                rebuilt = self._reordered_dict(container, current_key, delta)
                if list(rebuilt.keys()) == list(container.keys()):
                    raise ValueError("That item cannot move any further.")
                container.clear()
                container.update(rebuilt)
                self._save_registry()
                return page_key, current_key, f"Moved {entity_name} `{current_key}`."

        if skeleton == "ritual" and normalized_page == "guardian_phase":
            phases = config["guardian"].setdefault("phases", [])
            if not phases:
                phases.append(self._new_guardian_phase("New Phase", list(config["guardian"]["abilities"].keys()), 0))
            phase_index = max(0, min(int(item_key or "0"), len(phases) - 1))

            if action == "add":
                next_threshold = int(phases[-1].get("threshold", 0)) + 10
                phases.insert(
                    phase_index + 1,
                    self._new_guardian_phase(
                        f"Guardian Phase {len(phases) + 1}",
                        list(config["guardian"]["abilities"].keys()),
                        next_threshold,
                    ),
                )
                self._save_registry()
                return "guardian_phase", str(phase_index + 1), "Added a guardian phase."
            if action == "duplicate":
                phases.insert(phase_index + 1, copy.deepcopy(phases[phase_index]))
                self._save_registry()
                return "guardian_phase", str(phase_index + 1), "Duplicated a guardian phase."
            if action == "delete":
                if len(phases) <= 1:
                    raise ValueError("At least one guardian phase must remain.")
                del phases[phase_index]
                next_index = max(0, min(phase_index, len(phases) - 1))
                self._save_registry()
                return "guardian_phase", str(next_index), "Deleted a guardian phase."
            if action == "move":
                target_index = max(0, min(len(phases) - 1, phase_index + delta))
                if target_index == phase_index:
                    raise ValueError("That guardian phase cannot move any further.")
                phase = phases.pop(phase_index)
                phases.insert(target_index, phase)
                self._save_registry()
                return "guardian_phase", str(target_index), "Moved a guardian phase."

        raise ValueError("This page does not support structural editing yet.")

    def _media_slot_specs(self, mode: str) -> tuple[tuple[str, str, str], ...]:
        if mode == "trial":
            return GOOD_MEDIA_SLOTS
        if mode == "ritual":
            return EVIL_MEDIA_SLOTS
        return CHAOS_MEDIA_SLOTS

    def _media_slot_meta(self, mode: str, slot_key: str) -> tuple[str, str]:
        for key, label, description in self._media_slot_specs(mode):
            if key == slot_key:
                return label, description
        return slot_key.replace("_", " ").title(), "Media slot"

    def _apply_presentation(
        self,
        embed: discord.Embed,
        definition: dict[str, Any],
        *,
        color_key: str,
        media_key: str,
        default_color: discord.Color,
    ) -> discord.Embed:
        presentation = definition.get("config", {}).get("presentation", {})
        colors = presentation.get("colors", {})
        media = presentation.get("media", {}).get(media_key, {})
        embed.color = self._resolve_color(colors.get(color_key), default_color)
        image_url = media.get("image_url")
        thumbnail_url = media.get("thumbnail_url")
        if image_url:
            embed.set_image(url=image_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        return embed

    def _builder_page_specs(self, skeleton_key: str) -> list[dict[str, str]]:
        if skeleton_key == "trial":
            return [
                {"key": "overview", "label": "Overview", "description": "Name, description, join settings"},
                {"key": "announce", "label": "Announce", "description": "Join title, intro text, and button copy"},
                {"key": "theme", "label": "Theme", "description": "Embed colors for this raid mode"},
                {"key": "media_slot", "label": "Media", "description": "Attach images and thumbnails to embed slots"},
                {"key": "timings", "label": "Timing", "description": "Faith, pacing, and victory text"},
                {"key": "phase", "label": "Phase", "description": "Edit a phase shell like day or night"},
                {"key": "event", "label": "Event", "description": "Edit a specific event inside a phase"},
            ]
        if skeleton_key == "ritual":
            return [
                {"key": "overview", "label": "Overview", "description": "Name, description, faith, timers"},
                {"key": "announce", "label": "Announce", "description": "Intro copy and join button text"},
                {"key": "countdown_copy", "label": "Countdown", "description": "Edit countdown, start, and eligibility text"},
                {"key": "theme", "label": "Theme", "description": "Embed colors for the ritual"},
                {"key": "media_slot", "label": "Media", "description": "Attach images and thumbnails to ritual embeds"},
                {"key": "role_labels", "label": "Role Labels", "description": "Rename Champion, Priest, Followers, and Guardian"},
                {"key": "prompt_copy", "label": "Prompt Copy", "description": "Edit one DM prompt title and description"},
                {"key": "ritual_core", "label": "Ritual Core", "description": "Progress thresholds and turn count"},
                {"key": "champion_core", "label": "Champion Core", "description": "Champion health, damage, and haste"},
                {"key": "champion_action", "label": "Champion Action", "description": "Edit one champion action"},
                {"key": "champion_risk", "label": "Champion Risk", "description": "Sacrifice and damage multipliers"},
                {"key": "priest_core", "label": "Priest Core", "description": "Priest mana and regeneration"},
                {"key": "priest_action", "label": "Priest Action", "description": "Edit one priest action"},
                {"key": "follower_action", "label": "Follower Action", "description": "Edit one follower action"},
                {"key": "guardian_core", "label": "Guardian Core", "description": "Guardian HP and respawn"},
                {"key": "guardian_phase", "label": "Guardian Phase", "description": "Edit one guardian phase"},
                {"key": "guardian_ability_copy", "label": "Guardian Copy", "description": "Edit one guardian ability's label and narration"},
                {"key": "guardian_ability", "label": "Guardian Ability", "description": "Edit one guardian ability"},
            ]
        return [
            {"key": "overview", "label": "Overview", "description": "Name, description, faith, pacing"},
            {"key": "announce", "label": "Announce", "description": "Join title, intro text, and button copy"},
            {"key": "theme", "label": "Theme", "description": "Embed colors for the attrition loop"},
            {"key": "media_slot", "label": "Media", "description": "Attach images and thumbnails to embed slots"},
            {"key": "boss_core", "label": "Boss Core", "description": "Boss name, boss HP, follower HP"},
            {"key": "boss_attack", "label": "Boss Attack", "description": "Critical and normal boss damage"},
            {"key": "heal_event", "label": "Heal Event", "description": "Random heal event tuning"},
            {"key": "pulse_event", "label": "Pulse Event", "description": "Void pulse tuning"},
            {"key": "player_damage", "label": "Player Damage", "description": "Follower damage bands"},
            {"key": "message_bucket", "label": "Message Bucket", "description": "High/medium/low and end messages"},
        ]

    def _builder_item_options(self, definition: dict[str, Any], page_key: str) -> list[dict[str, str]]:
        config = definition["config"]
        skeleton = self._definition_skeleton_key(definition)
        if skeleton == "trial":
            if page_key == "media_slot":
                return [
                    {"key": key, "label": label, "description": description}
                    for key, label, description in self._media_slot_specs("trial")
                ]
            if page_key == "phase":
                return [
                    {
                        "key": phase["key"],
                        "label": phase["key"].title(),
                        "description": f"{len(phase.get('events', []))} events",
                    }
                    for phase in config.get("phases", [])
                ]
            if page_key == "event":
                options = []
                for phase in config.get("phases", []):
                    for index, event in enumerate(phase.get("events", []), start=1):
                        options.append(
                            {
                                "key": f"{phase['key']}:{index - 1}",
                                "label": f"{phase['key'].title()} {index}",
                                "description": event.get("text", "Event")[:100],
                            }
                        )
                return options
            return []

        if skeleton == "ritual":
            if page_key == "media_slot":
                return [
                    {"key": key, "label": label, "description": description}
                    for key, label, description in self._media_slot_specs("ritual")
                ]
            if page_key == "countdown_copy":
                countdown_options = [
                    {
                        "key": f"countdown:{entry['key']}",
                        "label": str(entry.get("label") or entry.get("key", "Countdown")),
                        "description": f"{int(entry.get('remaining', 0))}s remaining",
                    }
                    for entry in sorted(
                        config["announce"].get("countdown_messages", []),
                        key=lambda entry: int(entry.get("remaining", 0)),
                        reverse=True,
                    )
                    if isinstance(entry, dict)
                ]
                countdown_options.extend(
                    (
                        {
                            "key": "start_message",
                            "label": "Start Message",
                            "description": "Posted when the ritual begins",
                        },
                        {
                            "key": "eligibility_message",
                            "label": "Eligibility Check",
                            "description": "Posted before eligibility filtering starts",
                        },
                    )
                )
                return countdown_options
            if page_key == "prompt_copy":
                return [
                    {"key": key, "label": label, "description": description}
                    for key, label, description in RITUAL_PROMPT_SLOTS
                ]
            if page_key == "champion_action":
                return [
                    {
                        "key": action_name,
                        "label": self._action_display_name(action_name, action_config),
                        "description": "Champion action",
                    }
                    for action_name, action_config in definition["config"]["champion"]["actions"].items()
                ]
            if page_key == "priest_action":
                return [
                    {
                        "key": action_name,
                        "label": self._action_display_name(action_name, action_config),
                        "description": "Priest spell",
                    }
                    for action_name, action_config in config["priest"]["actions"].items()
                ]
            if page_key == "follower_action":
                return [
                    {
                        "key": action_name,
                        "label": self._action_display_name(action_name, action_config),
                        "description": "Follower support action",
                    }
                    for action_name, action_config in config["followers"]["actions"].items()
                ]
            if page_key == "guardian_phase":
                return [
                    {
                        "key": str(index),
                        "label": phase.get("name", f"Phase {index + 1}"),
                        "description": f"Threshold {phase.get('threshold', 0)}",
                    }
                    for index, phase in enumerate(config["guardian"].get("phases", []))
                ]
            if page_key in {"guardian_ability", "guardian_ability_copy"}:
                return [
                    {
                        "key": ability_name,
                        "label": self._guardian_ability_display_name(ability_name, ability_config),
                        "description": "Guardian ability",
                    }
                    for ability_name, ability_config in config["guardian"]["abilities"].items()
                ]
            return []

        if page_key == "media_slot":
            return [
                {"key": key, "label": label, "description": description}
                for key, label, description in self._media_slot_specs("attrition")
            ]
        if page_key == "message_bucket":
            options = []
            for key in ("high_damage", "medium_damage", "low_damage", "victory", "defeat", "retreat"):
                label = key.replace("_", " ").title()
                options.append({"key": key, "label": label, "description": "Message content"})
            return options
        return []

    def _builder_page_payload(
        self,
        definition: dict[str, Any],
        page_key: str | None,
        item_key: str | None,
    ) -> dict[str, Any]:
        if page_key is None:
            return {
                "title": "Raid Builder",
                "description": "Choose a page to edit.",
                "fields": [],
                "form_fields": [],
                "form_title": "Edit",
                "submit_handler": None,
            }
        skeleton = self._definition_skeleton_key(definition)
        if skeleton == "trial":
            return self._good_builder_page_payload(definition, page_key, item_key)
        if skeleton == "ritual":
            return self._evil_builder_page_payload(definition, page_key, item_key)
        return self._chaos_builder_page_payload(definition, page_key, item_key)

    def _media_slot_payload(
        self,
        definition: dict[str, Any],
        slot_key: str,
    ) -> dict[str, Any]:
        presentation = definition["config"].setdefault("presentation", {})
        media = presentation.setdefault("media", {})
        slot = media.setdefault(slot_key, _blank_media())
        skeleton = self._definition_skeleton_key(definition) or "attrition"
        slot_label, slot_description = self._media_slot_meta(skeleton, slot_key)

        async def submit(values):
            slot["image_url"] = self._parse_optional_text(values["image_url"])
            slot["thumbnail_url"] = self._parse_optional_text(values["thumbnail_url"])
            self._save_registry()
            return f"Updated media slot `{slot_key}`."

        return {
            "title": f"{definition['name']} • Media • {slot_label}",
            "description": slot_description,
            "fields": [
                {"name": "Image URL", "value": slot.get("image_url") or "None", "inline": False},
                {"name": "Thumbnail URL", "value": slot.get("thumbnail_url") or "None", "inline": False},
            ],
            "form_title": f"Edit {slot_label} Media",
            "form_fields": [
                {
                    "key": "image_url",
                    "label": "Image URL",
                    "default": slot.get("image_url", ""),
                    "required": False,
                    "placeholder": "Leave blank to clear",
                },
                {
                    "key": "thumbnail_url",
                    "label": "Thumbnail URL",
                    "default": slot.get("thumbnail_url", ""),
                    "required": False,
                    "placeholder": "Leave blank to clear",
                },
            ],
            "submit_handler": submit,
        }

    def _theme_payload(
        self,
        definition: dict[str, Any],
        *,
        title_suffix: str,
        description: str,
        fields_spec: tuple[tuple[str, str], ...],
    ) -> dict[str, Any]:
        colors = definition["config"].setdefault("presentation", {}).setdefault("colors", {})

        async def submit(values):
            for key, label in fields_spec:
                colors[key] = self._parse_hex_color(values[key], label)
            self._save_registry()
            return "Updated theme colors."

        return {
            "title": f"{definition['name']} • {title_suffix}",
            "description": description,
            "fields": [
                {"name": label, "value": colors.get(key, "unset"), "inline": True}
                for key, label in fields_spec
            ],
            "form_title": f"Edit {title_suffix}",
            "form_fields": [
                {"key": key, "label": label, "default": str(colors.get(key, ""))}
                for key, label in fields_spec
            ],
            "submit_handler": submit,
        }

    def _good_builder_page_payload(
        self,
        definition: dict[str, Any],
        page_key: str,
        item_key: str | None,
    ) -> dict[str, Any]:
        config = definition["config"]
        announce = config["announce"]
        phases = {phase["key"]: phase for phase in config.get("phases", [])}

        if page_key == "overview":
            async def submit(values):
                definition["name"] = self._require_text(values["name"], "Name")
                definition["description"] = self._require_text(values["description"], "Description")
                config["join_timeout"] = self._parse_int(values["join_timeout"], "Join timeout", min_value=30)
                config["min_survivors"] = self._parse_int(values["min_survivors"], "Minimum survivors", min_value=1)
                config["max_rounds"] = self._parse_int(values["max_rounds"], "Maximum rounds", min_value=1)
                self._save_registry()
                return "Updated good raid overview."

            return {
                "title": f"{definition['name']} • Overview",
                "description": definition.get("description", ""),
                "fields": [
                    {"name": "Join Timeout", "value": f"{config.get('join_timeout', 0)}s", "inline": True},
                    {"name": "Min Survivors", "value": f"{config.get('min_survivors', 1)}", "inline": True},
                    {"name": "Max Rounds", "value": f"{config.get('max_rounds', 0)}", "inline": True},
                    {"name": "Status", "value": f"`{definition.get('status', 'draft')}`", "inline": True},
                ],
                "form_title": "Edit Good Overview",
                "form_fields": [
                    {"key": "name", "label": "Name", "default": definition.get("name", "")},
                    {"key": "description", "label": "Description", "default": definition.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "join_timeout", "label": "Join Timeout", "default": str(config.get("join_timeout", 900))},
                    {"key": "min_survivors", "label": "Min Survivors", "default": str(config.get("min_survivors", 1))},
                    {"key": "max_rounds", "label": "Max Rounds", "default": str(config.get("max_rounds", 40))},
                ],
                "submit_handler": submit,
            }

        if page_key == "announce":
            async def submit(values):
                announce["title"] = self._require_text(values["title"], "Title")
                announce["description"] = self._require_text(values["description"], "Description")
                announce["join_label"] = self._require_text(values["join_label"], "Join label")
                announce["joined_message"] = self._require_text(values["joined_message"], "Joined message")
                self._save_registry()
                return "Updated good raid announce copy."

            return {
                "title": f"{definition['name']} • Announce",
                "description": "Opening copy and join button text.",
                "fields": [
                    {"name": "Title", "value": announce.get("title", "None"), "inline": False},
                    {"name": "Join Label", "value": announce.get("join_label", "Join"), "inline": True},
                    {"name": "Joined Message", "value": announce.get("joined_message", "None"), "inline": False},
                ],
                "form_title": "Edit Good Announce",
                "form_fields": [
                    {"key": "title", "label": "Title", "default": announce.get("title", "")},
                    {"key": "description", "label": "Description", "default": announce.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "join_label", "label": "Join Label", "default": announce.get("join_label", "")},
                    {"key": "joined_message", "label": "Joined Message", "default": announce.get("joined_message", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "theme":
            return self._theme_payload(
                definition,
                title_suffix="Theme",
                description="Control the main embed colors for the trial flow.",
                fields_spec=(
                    ("intro", "Intro Color"),
                    ("phase", "Phase Color"),
                    ("success", "Success Color"),
                    ("failure", "Failure Color"),
                    ("victory", "Victory Color"),
                ),
            )

        if page_key == "media_slot":
            return self._media_slot_payload(definition, item_key or "intro")

        if page_key == "timings":
            async def submit(values):
                config["phase_delay"] = self._parse_int(values["phase_delay"], "Phase delay", min_value=0)
                config["result_delay"] = self._parse_int(values["result_delay"], "Result delay", min_value=0)
                config["eligibility"]["god"] = self._require_text(values["eligibility_god"], "Eligibility god")
                config["winner_text"] = self._require_text(values["winner_text"], "Winner text")
                self._save_registry()
                return "Updated good raid timing settings."

            return {
                "title": f"{definition['name']} • Timing",
                "description": "Faith, pacing, and final narration.",
                "fields": [
                    {"name": "Faith", "value": config.get("eligibility", {}).get("god", "Any"), "inline": True},
                    {"name": "Phase Delay", "value": f"{config.get('phase_delay', 0)}s", "inline": True},
                    {"name": "Result Delay", "value": f"{config.get('result_delay', 0)}s", "inline": True},
                    {"name": "Winner Text", "value": config.get("winner_text", "None"), "inline": False},
                ],
                "form_title": "Edit Good Timing",
                "form_fields": [
                    {"key": "eligibility_god", "label": "Eligibility God", "default": config.get("eligibility", {}).get("god", "Elysia")},
                    {"key": "phase_delay", "label": "Phase Delay", "default": str(config.get("phase_delay", 5))},
                    {"key": "result_delay", "label": "Result Delay", "default": str(config.get("result_delay", 3))},
                    {"key": "winner_text", "label": "Winner Text", "default": config.get("winner_text", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "phase":
            phase = phases[item_key] if item_key in phases else next(iter(phases.values()))

            async def submit(values, phase=phase):
                phase["title"] = self._require_text(values["title"], "Phase title")
                phase["description"] = self._require_text(values["description"], "Phase description")
                phase["weight"] = self._parse_int(values["weight"], "Phase weight", min_value=1)
                self._save_registry()
                return f"Updated phase `{phase['key']}`."

            return {
                "title": f"{definition['name']} • Phase • {phase['key'].title()}",
                "description": phase.get("description", ""),
                "fields": [
                    {"name": "Title", "value": phase.get("title", "Untitled"), "inline": False},
                    {"name": "Weight", "value": str(phase.get("weight", 1)), "inline": True},
                    {"name": "Events", "value": str(len(phase.get("events", []))), "inline": True},
                ],
                "form_title": f"Edit {phase['key'].title()} Phase",
                "form_fields": [
                    {"key": "title", "label": "Title", "default": phase.get("title", "")},
                    {"key": "description", "label": "Description", "default": phase.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "weight", "label": "Weight", "default": str(phase.get("weight", 1))},
                ],
                "submit_handler": submit,
            }

        phase_key, raw_index = (item_key or "day:0").split(":")
        phase = phases[phase_key]
        event = phase["events"][int(raw_index)]

        async def submit(values, event=event, phase=phase):
            event["text"] = self._require_text(values["text"], "Event text")
            event["success_rate"] = self._parse_int(values["success_rate"], "Success rate", min_value=0, max_value=100)
            event["mercy_chance"] = self._parse_int(values["mercy_chance"], "Mercy chance", min_value=0, max_value=100)
            event["win_text"] = self._require_text(values["win_text"], "Win text")
            event["lose_text"] = self._require_text(values["lose_text"], "Lose text")
            self._save_registry()
            return f"Updated `{phase['key']}` event `{event['text']}`."

        return {
            "title": f"{definition['name']} • Event • {phase['key'].title()}",
            "description": event.get("text", ""),
            "fields": [
                {"name": "Success Rate", "value": f"{event.get('success_rate', 0)}%", "inline": True},
                {"name": "Mercy Chance", "value": f"{event.get('mercy_chance', 0)}%", "inline": True},
                {"name": "Win Text", "value": event.get("win_text", "None"), "inline": False},
                {"name": "Lose Text", "value": event.get("lose_text", "None"), "inline": False},
            ],
            "form_title": "Edit Trial Event",
            "form_fields": [
                {"key": "text", "label": "Event Text", "default": event.get("text", "")},
                {"key": "success_rate", "label": "Success Rate", "default": str(event.get("success_rate", 50))},
                {"key": "mercy_chance", "label": "Mercy Chance", "default": str(event.get("mercy_chance", 0))},
                {"key": "win_text", "label": "Win Text", "default": event.get("win_text", ""), "style": discord.TextStyle.paragraph},
                {"key": "lose_text", "label": "Lose Text", "default": event.get("lose_text", ""), "style": discord.TextStyle.paragraph},
            ],
            "submit_handler": submit,
        }

    def _chaos_builder_page_payload(
        self,
        definition: dict[str, Any],
        page_key: str,
        item_key: str | None,
    ) -> dict[str, Any]:
        config = definition["config"]
        announce = config["announce"]

        if page_key == "overview":
            async def submit(values):
                definition["name"] = self._require_text(values["name"], "Name")
                definition["description"] = self._require_text(values["description"], "Description")
                config["eligibility"]["god"] = self._require_text(values["eligibility_god"], "Eligibility god")
                config["join_timeout"] = self._parse_int(values["join_timeout"], "Join timeout", min_value=30)
                config["max_rounds"] = self._parse_int(values["max_rounds"], "Max rounds", min_value=1)
                self._save_registry()
                return "Updated chaos raid overview."

            return {
                "title": f"{definition['name']} • Overview",
                "description": definition.get("description", ""),
                "fields": [
                    {"name": "Faith", "value": config.get("eligibility", {}).get("god", "Any"), "inline": True},
                    {"name": "Join Timeout", "value": f"{config.get('join_timeout', 0)}s", "inline": True},
                    {"name": "Max Rounds", "value": str(config.get("max_rounds", 0)), "inline": True},
                ],
                "form_title": "Edit Chaos Overview",
                "form_fields": [
                    {"key": "name", "label": "Name", "default": definition.get("name", "")},
                    {"key": "description", "label": "Description", "default": definition.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "eligibility_god", "label": "Eligibility God", "default": config.get("eligibility", {}).get("god", "Drakath")},
                    {"key": "join_timeout", "label": "Join Timeout", "default": str(config.get("join_timeout", 900))},
                    {"key": "max_rounds", "label": "Max Rounds", "default": str(config.get("max_rounds", 30))},
                ],
                "submit_handler": submit,
            }

        if page_key == "announce":
            async def submit(values):
                announce["title"] = self._require_text(values["title"], "Title")
                announce["description"] = self._require_text(values["description"], "Description")
                announce["join_label"] = self._require_text(values["join_label"], "Join label")
                announce["joined_message"] = self._require_text(values["joined_message"], "Joined message")
                self._save_registry()
                return "Updated chaos raid announce copy."

            return {
                "title": f"{definition['name']} • Announce",
                "description": "Opening copy and join button text.",
                "fields": [
                    {"name": "Title", "value": announce.get("title", "None"), "inline": False},
                    {"name": "Join Label", "value": announce.get("join_label", "Join"), "inline": True},
                    {"name": "Joined Message", "value": announce.get("joined_message", "None"), "inline": False},
                ],
                "form_title": "Edit Chaos Announce",
                "form_fields": [
                    {"key": "title", "label": "Title", "default": announce.get("title", "")},
                    {"key": "description", "label": "Description", "default": announce.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "join_label", "label": "Join Label", "default": announce.get("join_label", "")},
                    {"key": "joined_message", "label": "Joined Message", "default": announce.get("joined_message", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "theme":
            return self._theme_payload(
                definition,
                title_suffix="Theme",
                description="Control the main embed colors for the chaos attrition flow.",
                fields_spec=(
                    ("intro", "Intro Color"),
                    ("boss_turn", "Boss Turn Color"),
                    ("raid_turn", "Raid Turn Color"),
                    ("victory", "Victory Color"),
                    ("defeat", "Defeat Color"),
                ),
            )

        if page_key == "media_slot":
            return self._media_slot_payload(definition, item_key or "intro")

        if page_key == "boss_core":
            async def submit(values):
                config["boss_name"] = self._require_text(values["boss_name"], "Boss name")
                config["boss_hp"] = self._parse_int(values["boss_hp"], "Boss HP", min_value=1)
                config["player_hp"] = self._parse_int(values["player_hp"], "Player HP", min_value=1)
                self._save_registry()
                return "Updated chaos boss core."

            return {
                "title": f"{definition['name']} • Boss Core",
                "description": "Main boss and participant durability settings.",
                "fields": [
                    {"name": "Boss", "value": config.get("boss_name", "Unknown"), "inline": False},
                    {"name": "Boss HP", "value": str(config.get("boss_hp", 0)), "inline": True},
                    {"name": "Follower HP", "value": str(config.get("player_hp", 0)), "inline": True},
                ],
                "form_title": "Edit Chaos Boss Core",
                "form_fields": [
                    {"key": "boss_name", "label": "Boss Name", "default": config.get("boss_name", "")},
                    {"key": "boss_hp", "label": "Boss HP", "default": str(config.get("boss_hp", 5000))},
                    {"key": "player_hp", "label": "Follower HP", "default": str(config.get("player_hp", 250))},
                ],
                "submit_handler": submit,
            }

        if page_key == "boss_attack":
            attack = config["boss_attack"]

            async def submit(values):
                attack["critical_chance"] = self._parse_float(values["critical_chance"], "Critical chance", min_value=0.0, max_value=1.0)
                attack["normal_min"] = self._parse_int(values["normal_min"], "Normal min", min_value=0)
                attack["normal_max"] = self._parse_int(values["normal_max"], "Normal max", min_value=attack["normal_min"])
                attack["critical_min"] = self._parse_int(values["critical_min"], "Critical min", min_value=0)
                attack["critical_max"] = self._parse_int(values["critical_max"], "Critical max", min_value=attack["critical_min"])
                self._save_registry()
                return "Updated chaos boss attack tuning."

            return {
                "title": f"{definition['name']} • Boss Attack",
                "description": "Boss damage bands and critical chance.",
                "fields": [
                    {"name": "Critical Chance", "value": str(attack.get("critical_chance", 0.0)), "inline": True},
                    {"name": "Normal", "value": f"{attack.get('normal_min', 0)}-{attack.get('normal_max', 0)}", "inline": True},
                    {"name": "Critical", "value": f"{attack.get('critical_min', 0)}-{attack.get('critical_max', 0)}", "inline": True},
                ],
                "form_title": "Edit Boss Attack",
                "form_fields": [
                    {"key": "critical_chance", "label": "Critical Chance", "default": str(attack.get("critical_chance", 0.3))},
                    {"key": "normal_min", "label": "Normal Min", "default": str(attack.get("normal_min", 100))},
                    {"key": "normal_max", "label": "Normal Max", "default": str(attack.get("normal_max", 280))},
                    {"key": "critical_min", "label": "Critical Min", "default": str(attack.get("critical_min", 160))},
                    {"key": "critical_max", "label": "Critical Max", "default": str(attack.get("critical_max", 360))},
                ],
                "submit_handler": submit,
            }

        if page_key == "heal_event":
            event = config["events"]

            async def submit(values):
                event["heal_chance"] = self._parse_float(values["heal_chance"], "Heal chance", min_value=0.0, max_value=1.0)
                event["heal_min"] = self._parse_int(values["heal_min"], "Heal min", min_value=0)
                event["heal_max"] = self._parse_int(values["heal_max"], "Heal max", min_value=event["heal_min"])
                self._save_registry()
                return "Updated chaos heal event."

            return {
                "title": f"{definition['name']} • Heal Event",
                "description": "Random healing event frequency and amount.",
                "fields": [
                    {"name": "Heal Chance", "value": str(event.get("heal_chance", 0.0)), "inline": True},
                    {"name": "Heal Range", "value": f"{event.get('heal_min', 0)}-{event.get('heal_max', 0)}", "inline": True},
                ],
                "form_title": "Edit Heal Event",
                "form_fields": [
                    {"key": "heal_chance", "label": "Heal Chance", "default": str(event.get("heal_chance", 0.2))},
                    {"key": "heal_min", "label": "Heal Min", "default": str(event.get("heal_min", 90))},
                    {"key": "heal_max", "label": "Heal Max", "default": str(event.get("heal_max", 140))},
                ],
                "submit_handler": submit,
            }

        if page_key == "pulse_event":
            event = config["events"]

            async def submit(values):
                event["pulse_chance"] = self._parse_float(values["pulse_chance"], "Pulse chance", min_value=0.0, max_value=1.0)
                event["pulse_damage"] = self._parse_int(values["pulse_damage"], "Pulse damage", min_value=0)
                event["pulse_targets"] = self._parse_int(values["pulse_targets"], "Pulse targets", min_value=1)
                self._save_registry()
                return "Updated chaos pulse event."

            return {
                "title": f"{definition['name']} • Pulse Event",
                "description": "Void pulse frequency, damage, and target count.",
                "fields": [
                    {"name": "Pulse Chance", "value": str(event.get("pulse_chance", 0.0)), "inline": True},
                    {"name": "Pulse Damage", "value": str(event.get("pulse_damage", 0)), "inline": True},
                    {"name": "Pulse Targets", "value": str(event.get("pulse_targets", 0)), "inline": True},
                ],
                "form_title": "Edit Pulse Event",
                "form_fields": [
                    {"key": "pulse_chance", "label": "Pulse Chance", "default": str(event.get("pulse_chance", 0.2))},
                    {"key": "pulse_damage", "label": "Pulse Damage", "default": str(event.get("pulse_damage", 100))},
                    {"key": "pulse_targets", "label": "Pulse Targets", "default": str(event.get("pulse_targets", 3))},
                ],
                "submit_handler": submit,
            }

        if page_key == "player_damage":
            player_damage = config["players"]

            async def submit(values):
                player_damage["critical_chance"] = self._parse_float(values["critical_chance"], "Critical chance", min_value=0.0, max_value=1.0)
                player_damage["normal_min"] = self._parse_int(values["normal_min"], "Normal min", min_value=0)
                player_damage["normal_max"] = self._parse_int(values["normal_max"], "Normal max", min_value=player_damage["normal_min"])
                player_damage["critical_min"] = self._parse_int(values["critical_min"], "Critical min", min_value=0)
                player_damage["critical_max"] = self._parse_int(values["critical_max"], "Critical max", min_value=player_damage["critical_min"])
                self._save_registry()
                return "Updated follower damage tuning."

            return {
                "title": f"{definition['name']} • Player Damage",
                "description": "Follower damage bands against the boss.",
                "fields": [
                    {"name": "Critical Chance", "value": str(player_damage.get("critical_chance", 0.0)), "inline": True},
                    {"name": "Normal", "value": f"{player_damage.get('normal_min', 0)}-{player_damage.get('normal_max', 0)}", "inline": True},
                    {"name": "Critical", "value": f"{player_damage.get('critical_min', 0)}-{player_damage.get('critical_max', 0)}", "inline": True},
                ],
                "form_title": "Edit Player Damage",
                "form_fields": [
                    {"key": "critical_chance", "label": "Critical Chance", "default": str(player_damage.get("critical_chance", 0.15))},
                    {"key": "normal_min", "label": "Normal Min", "default": str(player_damage.get("normal_min", 20))},
                    {"key": "normal_max", "label": "Normal Max", "default": str(player_damage.get("normal_max", 45))},
                    {"key": "critical_min", "label": "Critical Min", "default": str(player_damage.get("critical_min", 70))},
                    {"key": "critical_max", "label": "Critical Max", "default": str(player_damage.get("critical_max", 150))},
                ],
                "submit_handler": submit,
            }

        bucket_key = item_key or "high_damage"
        messages = config["messages"]
        bucket_value = messages.get(bucket_key, [])
        is_list_bucket = isinstance(bucket_value, list)
        default_value = "\n".join(bucket_value) if is_list_bucket else str(bucket_value)

        async def submit(values):
            if is_list_bucket:
                messages[bucket_key] = self._parse_message_lines(values["messages"])
            else:
                messages[bucket_key] = self._require_text(values["messages"], "Message text")
            self._save_registry()
            return f"Updated message bucket `{bucket_key}`."

        return {
            "title": f"{definition['name']} • Messages • {bucket_key.replace('_', ' ').title()}",
            "description": "Edit the narration bucket used by this chaos raid.",
            "fields": [
                {"name": "Bucket", "value": bucket_key, "inline": True},
                {"name": "Type", "value": "List" if is_list_bucket else "Single", "inline": True},
                {"name": "Content", "value": default_value or "None", "inline": False},
            ],
            "form_title": "Edit Message Bucket",
            "form_fields": [
                {"key": "messages", "label": "Messages", "default": default_value, "style": discord.TextStyle.paragraph},
            ],
            "submit_handler": submit,
        }

    def _evil_builder_page_payload(
        self,
        definition: dict[str, Any],
        page_key: str,
        item_key: str | None,
    ) -> dict[str, Any]:
        config = definition["config"]
        announce = config["announce"]
        presentation = config["presentation"]

        if page_key == "overview":
            async def submit(values):
                definition["name"] = self._require_text(values["name"], "Name")
                definition["description"] = self._require_text(values["description"], "Description")
                config["eligibility"]["god"] = self._require_text(values["eligibility_god"], "Eligibility god")
                config["join_timeout"] = self._parse_int(values["join_timeout"], "Join timeout", min_value=30)
                config["decision_timeout"] = self._parse_int(values["decision_timeout"], "Decision timeout", min_value=10)
                self._save_registry()
                return "Updated evil raid overview."

            return {
                "title": f"{definition['name']} • Overview",
                "description": definition.get("description", ""),
                "fields": [
                    {"name": "Faith", "value": config.get("eligibility", {}).get("god", "Any"), "inline": True},
                    {"name": "Join Timeout", "value": f"{config.get('join_timeout', 0)}s", "inline": True},
                    {"name": "Decision Timeout", "value": f"{config.get('decision_timeout', 0)}s", "inline": True},
                ],
                "form_title": "Edit Evil Overview",
                "form_fields": [
                    {"key": "name", "label": "Name", "default": definition.get("name", "")},
                    {"key": "description", "label": "Description", "default": definition.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "eligibility_god", "label": "Eligibility God", "default": config.get("eligibility", {}).get("god", "Sepulchure")},
                    {"key": "join_timeout", "label": "Join Timeout", "default": str(config.get("join_timeout", 900))},
                    {"key": "decision_timeout", "label": "Decision Timeout", "default": str(config.get("decision_timeout", 90))},
                ],
                "submit_handler": submit,
            }

        if page_key == "announce":
            async def submit(values):
                announce["title"] = self._require_text(values["title"], "Title")
                announce["description"] = self._require_text(values["description"], "Description")
                announce["leader_label"] = self._require_text(values["leader_label"], "Leader button label")
                announce["follower_label"] = self._require_text(values["follower_label"], "Follower button label")
                announce["leader_joined_message"] = self._require_text(values["leader_joined_message"], "Leader joined message")
                self._save_registry()
                return "Updated ritual announce copy."

            return {
                "title": f"{definition['name']} • Announce",
                "description": "Opening copy and main ritual join labels.",
                "fields": [
                    {"name": "Title", "value": announce.get("title", "None"), "inline": False},
                    {"name": "Leader Label", "value": announce.get("leader_label", "Join"), "inline": True},
                    {"name": "Follower Label", "value": announce.get("follower_label", "Join"), "inline": True},
                    {"name": "Leader Joined Message", "value": announce.get("leader_joined_message", "None"), "inline": False},
                    {"name": "Follower Joined Message", "value": announce.get("follower_joined_message", "None"), "inline": False},
                ],
                "form_title": "Edit Ritual Announce",
                "form_fields": [
                    {"key": "title", "label": "Title", "default": announce.get("title", "")},
                    {"key": "description", "label": "Description", "default": announce.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "leader_label", "label": "Leader Label", "default": announce.get("leader_label", "")},
                    {"key": "follower_label", "label": "Follower Label", "default": announce.get("follower_label", "")},
                    {"key": "leader_joined_message", "label": "Leader Joined Message", "default": announce.get("leader_joined_message", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "countdown_copy":
            countdown_messages = announce.get("countdown_messages", [])
            countdown_map = {
                entry.get("key"): entry
                for entry in countdown_messages
                if isinstance(entry, dict)
            }

            if item_key == "start_message":
                async def submit(values):
                    announce["start_message"] = self._require_text(values["message"], "Start message")
                    self._save_registry()
                    return "Updated ritual start message."

                return {
                    "title": f"{definition['name']} • Countdown • Start Message",
                    "description": "Sent immediately after the join window closes and the ritual starts.",
                    "fields": [
                        {"name": "Message", "value": announce.get("start_message", "None"), "inline": False},
                    ],
                    "form_title": "Edit Start Message",
                    "form_fields": [
                        {
                            "key": "message",
                            "label": "Message",
                            "default": announce.get("start_message", ""),
                            "style": discord.TextStyle.paragraph,
                        },
                    ],
                    "submit_handler": submit,
                }

            if item_key == "eligibility_message":
                async def submit(values):
                    announce["eligibility_message"] = self._require_text(values["message"], "Eligibility message")
                    self._save_registry()
                    return "Updated ritual eligibility check message."

                return {
                    "title": f"{definition['name']} • Countdown • Eligibility Check",
                    "description": "Sent before the ritual filters players by eligibility and DMs leaders.",
                    "fields": [
                        {"name": "Message", "value": announce.get("eligibility_message", "None"), "inline": False},
                    ],
                    "form_title": "Edit Eligibility Check Message",
                    "form_fields": [
                        {
                            "key": "message",
                            "label": "Message",
                            "default": announce.get("eligibility_message", ""),
                            "style": discord.TextStyle.paragraph,
                        },
                    ],
                    "submit_handler": submit,
                }

            countdown_key = (item_key or "countdown:ten_minutes").split(":", 1)[-1]
            countdown_entry = countdown_map.get(countdown_key)
            if countdown_entry is None and countdown_messages:
                countdown_entry = countdown_messages[0]
                countdown_key = countdown_entry.get("key", countdown_key)
            if countdown_entry is None:
                raise ValueError("No countdown entries are configured.")

            async def submit(values, countdown_entry=countdown_entry):
                countdown_entry["label"] = self._require_text(values["label"], "Label")
                countdown_entry["remaining"] = self._parse_int(
                    values["remaining"],
                    "Seconds remaining",
                    min_value=1,
                )
                countdown_entry["message"] = self._require_text(values["message"], "Message")
                self._save_registry()
                return f"Updated countdown `{countdown_entry.get('label', countdown_key)}`."

            return {
                "title": f"{definition['name']} • Countdown • {countdown_entry.get('label', countdown_key)}",
                "description": "Edit one pre-ritual countdown checkpoint.",
                "fields": [
                    {"name": "Label", "value": countdown_entry.get("label", countdown_key), "inline": True},
                    {"name": "Seconds Remaining", "value": str(countdown_entry.get("remaining", 0)), "inline": True},
                    {"name": "Message", "value": countdown_entry.get("message", "None"), "inline": False},
                ],
                "form_title": f"Edit {countdown_entry.get('label', countdown_key)}",
                "form_fields": [
                    {"key": "label", "label": "Label", "default": countdown_entry.get("label", countdown_key)},
                    {"key": "remaining", "label": "Seconds Remaining", "default": str(countdown_entry.get("remaining", 0))},
                    {
                        "key": "message",
                        "label": "Message",
                        "default": countdown_entry.get("message", ""),
                        "style": discord.TextStyle.paragraph,
                    },
                ],
                "submit_handler": submit,
            }

        if page_key == "theme":
            return self._theme_payload(
                definition,
                title_suffix="Theme",
                description="Control the main embed colors for the ritual.",
                fields_spec=(
                    ("intro", "Intro Color"),
                    ("prompt", "Prompt Color"),
                    ("status", "Status Color"),
                    ("victory", "Victory Color"),
                    ("danger", "Danger Color"),
                ),
            )

        if page_key == "media_slot":
            return self._media_slot_payload(definition, item_key or "intro")

        if page_key == "role_labels":
            labels = presentation["labels"]

            async def submit(values):
                labels["champion"] = self._require_text(values["champion"], "Champion label")
                labels["priest"] = self._require_text(values["priest"], "Priest label")
                labels["followers"] = self._require_text(values["followers"], "Followers label")
                labels["guardian"] = self._require_text(values["guardian"], "Guardian label")
                self._save_registry()
                return "Updated ritual role labels."

            return {
                "title": f"{definition['name']} • Role Labels",
                "description": "Rename the main ritual roles without changing the engine.",
                "fields": [
                    {"name": "Champion", "value": labels.get("champion", "Champion"), "inline": True},
                    {"name": "Priest", "value": labels.get("priest", "Priest"), "inline": True},
                    {"name": "Followers", "value": labels.get("followers", "Followers"), "inline": True},
                    {"name": "Guardian", "value": labels.get("guardian", "Guardian"), "inline": True},
                ],
                "form_title": "Edit Role Labels",
                "form_fields": [
                    {"key": "champion", "label": "Champion", "default": labels.get("champion", "")},
                    {"key": "priest", "label": "Priest", "default": labels.get("priest", "")},
                    {"key": "followers", "label": "Followers", "default": labels.get("followers", "")},
                    {"key": "guardian", "label": "Guardian", "default": labels.get("guardian", "")},
                ],
                "submit_handler": submit,
            }

        if page_key == "prompt_copy":
            prompt_key = item_key or "follower"
            prompt = presentation["prompts"][prompt_key]
            prompt_label = dict((key, label) for key, label, _description in RITUAL_PROMPT_SLOTS).get(
                prompt_key,
                prompt_key.title(),
            )

            async def submit(values, prompt=prompt):
                prompt["title"] = self._require_text(values["title"], "Title")
                prompt["description"] = self._require_text(values["description"], "Description")
                self._save_registry()
                return f"Updated ritual prompt `{prompt_key}`."

            return {
                "title": f"{definition['name']} • Prompt Copy • {prompt_label}",
                "description": "Rename and retheme the DM prompt players receive.",
                "fields": [
                    {"name": "Title", "value": prompt.get("title", "None"), "inline": False},
                    {"name": "Description", "value": prompt.get("description", "None"), "inline": False},
                ],
                "form_title": f"Edit {prompt_label}",
                "form_fields": [
                    {"key": "title", "label": "Title", "default": prompt.get("title", "")},
                    {"key": "description", "label": "Description", "default": prompt.get("description", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "ritual_core":
            ritual = config["ritual"]

            async def submit(values):
                ritual["start_progress"] = self._parse_int(values["start_progress"], "Start progress", min_value=0)
                ritual["win_progress"] = self._parse_int(values["win_progress"], "Win progress", min_value=1)
                ritual["max_turns"] = self._parse_int(values["max_turns"], "Max turns", min_value=1)
                ritual["guardian_collapse_progress"] = self._parse_int(values["guardian_collapse_progress"], "Guardian collapse progress", min_value=0)
                config["allow_ai_fallback"] = self._parse_bool(values["allow_ai_fallback"], "Allow AI fallback")
                self._save_registry()
                return "Updated ritual core."

            return {
                "title": f"{definition['name']} • Ritual Core",
                "description": "Progress, turn cap, and AI fallback.",
                "fields": [
                    {"name": "Start Progress", "value": str(ritual.get("start_progress", 0)), "inline": True},
                    {"name": "Win Progress", "value": str(ritual.get("win_progress", 0)), "inline": True},
                    {"name": "Max Turns", "value": str(ritual.get("max_turns", 0)), "inline": True},
                    {"name": "Guardian Collapse", "value": str(ritual.get("guardian_collapse_progress", 0)), "inline": True},
                    {"name": "AI Fallback", "value": str(config.get("allow_ai_fallback", False)), "inline": True},
                ],
                "form_title": "Edit Ritual Core",
                "form_fields": [
                    {"key": "start_progress", "label": "Start Progress", "default": str(ritual.get("start_progress", 0))},
                    {"key": "win_progress", "label": "Win Progress", "default": str(ritual.get("win_progress", 100))},
                    {"key": "max_turns", "label": "Max Turns", "default": str(ritual.get("max_turns", 15))},
                    {"key": "guardian_collapse_progress", "label": "Guardian Collapse Progress", "default": str(ritual.get("guardian_collapse_progress", 10))},
                    {"key": "allow_ai_fallback", "label": "Allow AI Fallback", "default": str(config.get("allow_ai_fallback", True))},
                ],
                "submit_handler": submit,
            }

        if page_key == "champion_core":
            champion = config["champion"]

            async def submit(values):
                champion["max_hp"] = self._parse_int(values["max_hp"], "Max HP", min_value=1)
                champion["base_damage"] = self._parse_int(values["base_damage"], "Base damage", min_value=0)
                champion["heal_amount"] = self._parse_int(values["heal_amount"], "Heal amount", min_value=0)
                champion["haste_progress"] = self._parse_int(values["haste_progress"], "Haste progress", min_value=0)
                champion["haste_cooldown"] = self._parse_int(values["haste_cooldown"], "Haste cooldown", min_value=0)
                self._save_registry()
                return "Updated champion core."

            return {
                "title": f"{definition['name']} • Champion Core",
                "description": "Base durability and haste settings.",
                "fields": [
                    {"name": "Max HP", "value": str(champion.get("max_hp", 0)), "inline": True},
                    {"name": "Base Damage", "value": str(champion.get("base_damage", 0)), "inline": True},
                    {"name": "Heal Amount", "value": str(champion.get("heal_amount", 0)), "inline": True},
                    {"name": "Haste Progress", "value": str(champion.get("haste_progress", 0)), "inline": True},
                    {"name": "Haste Cooldown", "value": str(champion.get("haste_cooldown", 0)), "inline": True},
                ],
                "form_title": "Edit Champion Core",
                "form_fields": [
                    {"key": "max_hp", "label": "Max HP", "default": str(champion.get("max_hp", 1500))},
                    {"key": "base_damage", "label": "Base Damage", "default": str(champion.get("base_damage", 700))},
                    {"key": "heal_amount", "label": "Heal Amount", "default": str(champion.get("heal_amount", 200))},
                    {"key": "haste_progress", "label": "Haste Progress", "default": str(champion.get("haste_progress", 15))},
                    {"key": "haste_cooldown", "label": "Haste Cooldown", "default": str(champion.get("haste_cooldown", 3))},
                ],
                "submit_handler": submit,
            }

        if page_key == "champion_action":
            action_name = item_key or next(iter(config["champion"]["actions"]))
            action = config["champion"]["actions"][action_name]

            async def submit(values, action=action, action_name=action_name):
                effect = self._require_text(values["effect"], "Effect").casefold()
                if effect not in {"damage", "heal", "haste", "defend", "sacrifice"}:
                    raise ValueError("Effect must be one of damage, heal, haste, defend, or sacrifice.")
                action["effect"] = effect
                action["display_name"] = self._require_text(values["display_name"], "Display name")
                action["description"] = self._require_text(values["description"], "Description")
                action["result_text"] = self._require_text(values["result_text"], "Result text")
                self._save_registry()
                return f"Updated champion action `{action_name}`."

            return {
                "title": f"{definition['name']} • Champion Action • {self._action_display_name(action_name, action)}",
                "description": "Edit one champion action's lore-facing presentation.",
                "fields": [
                    {"name": "Internal ID", "value": action_name, "inline": True},
                    {"name": "Effect", "value": self._champion_action_effect(action_name, action), "inline": True},
                    {"name": "Display Name", "value": action.get("display_name", action_name), "inline": True},
                    {"name": "Description", "value": action.get("description", "None"), "inline": False},
                    {"name": "Result Text", "value": action.get("result_text", "None"), "inline": False},
                ],
                "form_title": f"Edit {action_name}",
                "form_fields": [
                    {
                        "key": "effect",
                        "label": "Effect",
                        "default": self._champion_action_effect(action_name, action),
                        "placeholder": "damage, heal, haste, defend, sacrifice",
                    },
                    {"key": "display_name", "label": "Display Name", "default": action.get("display_name", action_name)},
                    {"key": "description", "label": "Description", "default": action.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "result_text", "label": "Result Text", "default": action.get("result_text", ""), "style": discord.TextStyle.paragraph},
                ],
                "submit_handler": submit,
            }

        if page_key == "champion_risk":
            champion = config["champion"]

            async def submit(values):
                champion["sacrifice_hp"] = self._parse_int(values["sacrifice_hp"], "Sacrifice HP", min_value=0)
                champion["sacrifice_progress"] = self._parse_int(values["sacrifice_progress"], "Sacrifice progress", min_value=0)
                champion["defend_multiplier"] = self._parse_float(values["defend_multiplier"], "Defend multiplier", min_value=0.0)
                champion["vulnerable_multiplier"] = self._parse_float(values["vulnerable_multiplier"], "Vulnerable multiplier", min_value=0.0)
                self._save_registry()
                return "Updated champion risk settings."

            return {
                "title": f"{definition['name']} • Champion Risk",
                "description": "Sacrifice cost and incoming damage multipliers.",
                "fields": [
                    {"name": "Sacrifice HP", "value": str(champion.get("sacrifice_hp", 0)), "inline": True},
                    {"name": "Sacrifice Progress", "value": str(champion.get("sacrifice_progress", 0)), "inline": True},
                    {"name": "Defend Multiplier", "value": str(champion.get("defend_multiplier", 0.0)), "inline": True},
                    {"name": "Vulnerable Multiplier", "value": str(champion.get("vulnerable_multiplier", 0.0)), "inline": True},
                ],
                "form_title": "Edit Champion Risk",
                "form_fields": [
                    {"key": "sacrifice_hp", "label": "Sacrifice HP", "default": str(champion.get("sacrifice_hp", 350))},
                    {"key": "sacrifice_progress", "label": "Sacrifice Progress", "default": str(champion.get("sacrifice_progress", 18))},
                    {"key": "defend_multiplier", "label": "Defend Multiplier", "default": str(champion.get("defend_multiplier", 0.6))},
                    {"key": "vulnerable_multiplier", "label": "Vulnerable Multiplier", "default": str(champion.get("vulnerable_multiplier", 1.25))},
                ],
                "submit_handler": submit,
            }

        if page_key == "priest_core":
            priest = config["priest"]

            async def submit(values):
                priest["max_mana"] = self._parse_int(values["max_mana"], "Max mana", min_value=0)
                priest["mana_regen"] = self._parse_int(values["mana_regen"], "Mana regen", min_value=0)
                self._save_registry()
                return "Updated priest core."

            return {
                "title": f"{definition['name']} • Priest Core",
                "description": "Priest mana pool and regeneration.",
                "fields": [
                    {"name": "Max Mana", "value": str(priest.get("max_mana", 0)), "inline": True},
                    {"name": "Mana Regen", "value": str(priest.get("mana_regen", 0)), "inline": True},
                ],
                "form_title": "Edit Priest Core",
                "form_fields": [
                    {"key": "max_mana", "label": "Max Mana", "default": str(priest.get("max_mana", 100))},
                    {"key": "mana_regen", "label": "Mana Regen", "default": str(priest.get("mana_regen", 10))},
                ],
                "submit_handler": submit,
            }

        if page_key == "priest_action":
            action_name = item_key or next(iter(config["priest"]["actions"]))
            action = config["priest"]["actions"][action_name]

            async def submit(values, action=action, action_name=action_name):
                action["display_name"] = self._require_text(values["display_name"], "Display name")
                action["description"] = self._require_text(values["description"], "Description")
                action["result_text"] = self._require_text(values["result_text"], "Result text")
                action["mana_cost"] = self._parse_int(values["mana_cost"], "Mana cost", min_value=0)
                for key, field_name in (
                    ("damage_boost", "Damage boost"),
                    ("shield", "Shield"),
                    ("guardian_damage_down", "Guardian damage down"),
                    ("heal", "Heal"),
                    ("progress", "Progress"),
                ):
                    if key in action:
                        if key == "guardian_damage_down":
                            action[key] = self._parse_float(values[key], field_name, min_value=0.0)
                        else:
                            action[key] = self._parse_int(values[key], field_name, min_value=0)
                self._save_registry()
                return f"Updated priest action `{action_name}`."

            form_fields = [
                {"key": "display_name", "label": "Display Name", "default": action.get("display_name", action_name)},
                {"key": "description", "label": "Description", "default": action.get("description", ""), "style": discord.TextStyle.paragraph},
                {"key": "result_text", "label": "Result Text", "default": action.get("result_text", ""), "style": discord.TextStyle.paragraph},
                {"key": "mana_cost", "label": "Mana Cost", "default": str(action.get("mana_cost", 0))},
            ]
            for key, label in (
                ("damage_boost", "Damage Boost"),
                ("shield", "Shield"),
                ("guardian_damage_down", "Guardian Damage Down"),
                ("heal", "Heal"),
                ("progress", "Progress"),
            ):
                if key in action:
                    form_fields.append({"key": key, "label": label, "default": str(action.get(key, 0))})

            return {
                "title": f"{definition['name']} • Priest Action • {self._action_display_name(action_name, action)}",
                "description": "Edit one priest spell profile.",
                "fields": [
                    {"name": key.replace("_", " ").title(), "value": str(value), "inline": True}
                    for key, value in action.items()
                ],
                "form_title": f"Edit {action_name}",
                "form_fields": form_fields,
                "submit_handler": submit,
            }

        if page_key == "follower_action":
            action_name = item_key or next(iter(config["followers"]["actions"]))
            action = config["followers"]["actions"][action_name]

            async def submit(values, action=action, action_name=action_name):
                action["display_name"] = self._require_text(values["display_name"], "Display name")
                action["description"] = self._require_text(values["description"], "Description")
                for key, field_name in (
                    ("progress", "Progress"),
                    ("cap_total", "Cap Total"),
                    ("shield", "Shield"),
                    ("healing_boost", "Healing Boost"),
                    ("guardian_damage_down", "Guardian Damage Down"),
                    ("heal", "Heal"),
                ):
                    if key in action:
                        if key in {"healing_boost", "guardian_damage_down"}:
                            action[key] = self._parse_float(values[key], field_name, min_value=0.0)
                        else:
                            action[key] = self._parse_int(values[key], field_name, min_value=0)
                self._save_registry()
                return f"Updated follower action `{action_name}`."

            form_fields = [
                {"key": "display_name", "label": "Display Name", "default": action.get("display_name", action_name)},
                {"key": "description", "label": "Description", "default": action.get("description", ""), "style": discord.TextStyle.paragraph},
            ]
            for key, label in (
                ("progress", "Progress"),
                ("cap_total", "Cap Total"),
                ("shield", "Shield"),
                ("healing_boost", "Healing Boost"),
                ("guardian_damage_down", "Guardian Damage Down"),
                ("heal", "Heal"),
            ):
                if key in action:
                    form_fields.append({"key": key, "label": label, "default": str(action.get(key, 0))})

            return {
                "title": f"{definition['name']} • Follower Action • {self._action_display_name(action_name, action)}",
                "description": "Edit one follower support action.",
                "fields": [
                    {"name": key.replace("_", " ").title(), "value": str(value), "inline": True}
                    for key, value in action.items()
                ],
                "form_title": f"Edit {action_name}",
                "form_fields": form_fields,
                "submit_handler": submit,
            }

        if page_key == "guardian_core":
            guardian = config["guardian"]

            async def submit(values):
                guardian["max_hp"] = self._parse_int(values["max_hp"], "Max HP", min_value=1)
                guardian["respawn_hp_ratio"] = self._parse_float(values["respawn_hp_ratio"], "Respawn HP ratio", min_value=0.0, max_value=1.0)
                self._save_registry()
                return "Updated guardian core."

            return {
                "title": f"{definition['name']} • Guardian Core",
                "description": "Guardian total HP and respawn ratio.",
                "fields": [
                    {"name": "Max HP", "value": str(guardian.get("max_hp", 0)), "inline": True},
                    {"name": "Respawn HP Ratio", "value": str(guardian.get("respawn_hp_ratio", 0.0)), "inline": True},
                ],
                "form_title": "Edit Guardian Core",
                "form_fields": [
                    {"key": "max_hp", "label": "Max HP", "default": str(guardian.get("max_hp", 5000))},
                    {"key": "respawn_hp_ratio", "label": "Respawn HP Ratio", "default": str(guardian.get("respawn_hp_ratio", 0.45))},
                ],
                "submit_handler": submit,
            }

        if page_key == "guardian_phase":
            phase_index = int(item_key or "0")
            phase = config["guardian"]["phases"][phase_index]

            async def submit(values, phase=phase):
                phase["threshold"] = self._parse_int(values["threshold"], "Threshold", min_value=0)
                phase["name"] = self._require_text(values["name"], "Phase name")
                phase["description"] = self._require_text(values["description"], "Phase description")
                phase["abilities"] = self._parse_csv_list(values["abilities"])
                self._save_registry()
                return f"Updated guardian phase `{phase['name']}`."

            return {
                "title": f"{definition['name']} • Guardian Phase • {phase.get('name', phase_index + 1)}",
                "description": phase.get("description", ""),
                "fields": [
                    {"name": "Threshold", "value": str(phase.get("threshold", 0)), "inline": True},
                    {"name": "Abilities", "value": ", ".join(phase.get("abilities", [])) or "None", "inline": False},
                ],
                "form_title": "Edit Guardian Phase",
                "form_fields": [
                    {"key": "threshold", "label": "Threshold", "default": str(phase.get("threshold", 0))},
                    {"key": "name", "label": "Name", "default": phase.get("name", "")},
                    {"key": "description", "label": "Description", "default": phase.get("description", ""), "style": discord.TextStyle.paragraph},
                    {"key": "abilities", "label": "Abilities CSV", "default": ", ".join(phase.get("abilities", []))},
                ],
                "submit_handler": submit,
            }

        if page_key == "guardian_ability_copy":
            ability_name = item_key or next(iter(config["guardian"]["abilities"]))
            ability = config["guardian"]["abilities"][ability_name]

            async def submit(values, ability=ability, ability_name=ability_name):
                ability["display_name"] = self._require_text(values["display_name"], "Display name")
                ability["description"] = self._require_text(values["description"], "Description")
                if "damage_range" in ability:
                    ability["damage_text"] = self._require_text(values["damage_text"], "Damage text")
                if "shield" in ability:
                    ability["shield_text"] = self._require_text(values["shield_text"], "Shield text")
                if "progress_down" in ability:
                    ability["progress_text"] = self._require_text(values["progress_text"], "Progress text")
                self._save_registry()
                return f"Updated guardian copy `{ability_name}`."

            form_fields = [
                {"key": "display_name", "label": "Display Name", "default": ability.get("display_name", ability_name.replace("_", " ").title())},
                {"key": "description", "label": "Description", "default": ability.get("description", ""), "style": discord.TextStyle.paragraph},
            ]
            if "damage_range" in ability:
                form_fields.append({"key": "damage_text", "label": "Damage Text", "default": str(ability.get("damage_text", "")), "style": discord.TextStyle.paragraph})
            if "shield" in ability:
                form_fields.append({"key": "shield_text", "label": "Shield Text", "default": str(ability.get("shield_text", "")), "style": discord.TextStyle.paragraph})
            if "progress_down" in ability:
                form_fields.append({"key": "progress_text", "label": "Progress Text", "default": str(ability.get("progress_text", "")), "style": discord.TextStyle.paragraph})

            return {
                "title": f"{definition['name']} • Guardian Copy • {self._guardian_ability_display_name(ability_name, ability)}",
                "description": "Edit one guardian ability's display label and narration text.",
                "fields": [
                    {"name": "Display Name", "value": ability.get("display_name", ability_name), "inline": False},
                    {"name": "Description", "value": ability.get("description", "None"), "inline": False},
                    *(
                        [{"name": "Damage Text", "value": ability.get("damage_text", "None"), "inline": False}]
                        if "damage_range" in ability else []
                    ),
                    *(
                        [{"name": "Shield Text", "value": ability.get("shield_text", "None"), "inline": False}]
                        if "shield" in ability else []
                    ),
                    *(
                        [{"name": "Progress Text", "value": ability.get("progress_text", "None"), "inline": False}]
                        if "progress_down" in ability else []
                    ),
                ],
                "form_title": f"Edit {ability_name}",
                "form_fields": form_fields,
                "submit_handler": submit,
            }

        ability_name = item_key or next(iter(config["guardian"]["abilities"]))
        ability = config["guardian"]["abilities"][ability_name]

        async def submit(values, ability=ability, ability_name=ability_name):
            if "damage_range" in ability:
                ability["damage_range"] = [
                    self._parse_int(values["damage_min"], "Damage min", min_value=0),
                    self._parse_int(values["damage_max"], "Damage max", min_value=self._parse_int(values["damage_min"], "Damage min", min_value=0)),
                ]
            if "shield" in ability:
                ability["shield"] = self._parse_int(values["shield"], "Shield", min_value=0)
            if "progress_down" in ability:
                ability["progress_down"] = self._parse_int(values["progress_down"], "Progress down", min_value=0)
            if "damage_down" in ability:
                ability["damage_down"] = self._parse_int(values["damage_down"], "Damage down", min_value=0)
            if "heal_ratio" in ability:
                ability["heal_ratio"] = self._parse_float(values["heal_ratio"], "Heal ratio", min_value=0.0)
            self._save_registry()
            return f"Updated guardian ability `{ability_name}`."

        form_fields = []
        if "damage_range" in ability:
            form_fields.extend(
                [
                    {"key": "damage_min", "label": "Damage Min", "default": str(ability["damage_range"][0])},
                    {"key": "damage_max", "label": "Damage Max", "default": str(ability["damage_range"][1])},
                ]
            )
        if "shield" in ability:
            form_fields.append({"key": "shield", "label": "Shield", "default": str(ability.get("shield", 0))})
        if "progress_down" in ability:
            form_fields.append({"key": "progress_down", "label": "Progress Down", "default": str(ability.get("progress_down", 0))})
        if "damage_down" in ability:
            form_fields.append({"key": "damage_down", "label": "Damage Down", "default": str(ability.get("damage_down", 0))})
        if "heal_ratio" in ability:
            form_fields.append({"key": "heal_ratio", "label": "Heal Ratio", "default": str(ability.get("heal_ratio", 0.0))})

        return {
            "title": f"{definition['name']} • Guardian Ability • {self._guardian_ability_display_name(ability_name, ability)}",
            "description": "Edit one guardian ability profile.",
            "fields": [
                {"name": key.replace("_", " ").title(), "value": str(value), "inline": True}
                for key, value in ability.items()
            ],
            "form_title": f"Edit {ability_name}",
            "form_fields": form_fields,
            "submit_handler": submit,
        }

    def _build_overview_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Raid Builder Modes",
            description=(
                "This cog is the skeleton registry for remastered god raids. "
                "Unset modes route to the current live raid commands."
            ),
            color=discord.Color.orange(),
        )

        for spec in MODE_SPECS.values():
            embed.add_field(
                name=f"{spec.display_name} [{spec.skeleton}]",
                value=(
                    f"{spec.summary}\n"
                    f"Route: {self._get_route_text(spec.key)}\n"
                    f"Legacy usage: `{spec.legacy_usage}`"
                ),
                inline=False,
            )

        embed.set_footer(text="Use `raidmode show <good|evil|chaos>` for the framework modules.")
        return embed

    def _build_mode_embed(self, spec: RaidModeSpec) -> discord.Embed:
        active_definition = self._get_active_definition(spec.key)
        selected_definition_id = self._get_active_definition_id(spec.key)
        embed = discord.Embed(
            title=f"{spec.display_name} Mode",
            description=spec.summary,
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Skeleton", value=f"`{spec.skeleton}`", inline=True)
        embed.add_field(
            name="Active Definition",
            value=f"`{active_definition['id']}`" if active_definition else f"`{selected_definition_id or 'none'}`",
            inline=True,
        )
        embed.add_field(
            name="Fallback Route",
            value=f"`{spec.legacy_command}`",
            inline=True,
        )

        for option_group in spec.option_groups:
            options = ", ".join(f"`{option}`" for option in option_group.options)
            embed.add_field(
                name=option_group.title,
                value=f"{option_group.summary}\nOptions: {options}",
                inline=False,
            )

        embed.set_footer(
            text="Published active definitions run natively. Invalid or unset modes fall back to legacy."
        )
        return embed

    def _build_definition_embed(self, definition: dict[str, Any]) -> discord.Embed:
        skeleton = self._definition_skeleton_key(definition) or "unknown"
        embed = discord.Embed(
            title=definition.get("name", definition["id"]),
            description=definition.get("description", ""),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="ID", value=f"`{definition['id']}`", inline=True)
        embed.add_field(name="Owner", value=f"`{definition.get('mode', 'unknown')}`", inline=True)
        embed.add_field(name="Skeleton", value=f"`{skeleton}`", inline=True)
        embed.add_field(name="Status", value=f"`{definition.get('status', 'draft')}`", inline=True)

        config = definition.get("config", {})
        if skeleton == "trial":
            embed.add_field(
                name="Trial Summary",
                value=(
                    f"Phases: {len(config.get('phases', []))}\n"
                    f"Join Timeout: {config.get('join_timeout', 'n/a')}s\n"
                    f"Faith: {config.get('eligibility', {}).get('god', 'any')}"
                ),
                inline=False,
            )
        elif skeleton == "ritual":
            embed.add_field(
                name="Ritual Summary",
                value=(
                    f"Turns: {config.get('ritual', {}).get('max_turns', 'n/a')}\n"
                    f"AI Fallback: {config.get('allow_ai_fallback', False)}\n"
                    f"Follower Actions: {len(config.get('followers', {}).get('actions', {}))}"
                ),
                inline=False,
            )
        elif skeleton == "attrition":
            embed.add_field(
                name="Attrition Summary",
                value=(
                    f"Boss: {config.get('boss_name', 'n/a')}\n"
                    f"Boss HP: {config.get('boss_hp', 'n/a')}\n"
                    f"Follower HP: {config.get('player_hp', 'n/a')}"
                ),
                inline=False,
            )

        source_definition_id = definition.get("source_definition_id")
        if source_definition_id:
            embed.add_field(name="Source", value=f"`{source_definition_id}`", inline=False)

        active_on_modes = [
            mode_key
            for mode_key, mode_state in self.registry["modes"].items()
            if mode_state.get("active_definition_id") == definition["id"]
        ]
        embed.add_field(
            name="Active On",
            value=", ".join(f"`{mode_key}`" for mode_key in active_on_modes) if active_on_modes else "`none`",
            inline=False,
        )
        embed.set_footer(text=f"Registry file: {self.registry_path.as_posix()}")
        return embed

    @commands.check_any(is_gm(), is_god())
    @commands.group(
        name="raidmode",
        aliases=["raidbuilder"],
        hidden=True,
        invoke_without_command=True,
        brief=_("Inspect or launch the remastered raid mode scaffold."),
    )
    async def raidmode(self, ctx):
        await ctx.send(embed=self._build_overview_embed())

    @raidmode.command(name="status", hidden=True, brief=_("Show raid mode routing status."))
    async def raidmode_status(self, ctx):
        await ctx.send(embed=self._build_overview_embed())

    @raidmode.command(name="show", hidden=True, brief=_("Show the framework for a raid mode."))
    async def raidmode_show(self, ctx, mode: str):
        spec = self._get_mode_spec(mode)
        if spec is None:
            await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
            return
        await ctx.send(embed=self._build_mode_embed(spec))

    @raidmode.command(name="builder", hidden=True, brief=_("Open the interactive raid builder."))
    async def raidmode_builder(self, ctx, mode: str = None, definition_id: str = None):
        initial_mode = None
        initial_definition_id = None

        if definition_id is not None:
            normalized_definition_id = definition_id.casefold()
            definition = self._get_definition(normalized_definition_id)
            if definition is None:
                await ctx.send(f"Definition `{normalized_definition_id}` does not exist.")
                return
            initial_definition_id = normalized_definition_id
            initial_mode = definition.get("mode")

        if mode is not None:
            spec = self._get_mode_spec(mode)
            if spec is None:
                await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
                return
            if initial_mode and initial_mode != spec.key:
                await ctx.send(
                    f"`{initial_definition_id}` belongs to `{initial_mode}`, not `{spec.key}`."
                )
                return
            initial_mode = spec.key

        builder_view = RaidBuilderPanelView(
            cog=self,
            ctx=ctx,
            initial_mode=initial_mode,
            initial_definition_id=initial_definition_id,
        )
        await builder_view.start()

    @raidmode.command(name="defs", hidden=True, brief=_("List registered raid definitions."))
    async def raidmode_defs(self, ctx, mode: str = None):
        filtered_mode = mode.casefold() if mode else None
        if filtered_mode and filtered_mode not in MODE_SPECS:
            await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
            return

        embed = discord.Embed(
            title="Raid Definitions",
            color=discord.Color.blurple(),
        )
        for definition_id, definition in sorted(self.registry["definitions"].items()):
            definition_mode = definition.get("mode", "unknown")
            if filtered_mode and definition_mode != filtered_mode:
                continue
            active_marker = ""
            if self._get_active_definition_id(definition_mode) == definition_id:
                active_marker = " [active]"
            embed.add_field(
                name=f"{definition_id}{active_marker}",
                value=(
                    f"Owner: `{definition_mode}`\n"
                    f"Skeleton: `{self._definition_skeleton_key(definition) or 'unknown'}`\n"
                    f"Status: `{definition.get('status', 'draft')}`\n"
                    f"Runtime: `{definition.get('runtime', 'native')}`"
                ),
                inline=False,
            )

        if not embed.fields:
            embed.description = "No definitions matched that filter."
        await ctx.send(embed=embed)

    @raidmode.command(name="inspectdef", hidden=True, brief=_("Inspect one raid definition."))
    async def raidmode_inspectdef(self, ctx, definition_id: str):
        normalized_definition_id = definition_id.casefold()
        definition = self._get_definition(normalized_definition_id)
        if definition is None:
            await ctx.send(f"Definition `{normalized_definition_id}` does not exist.")
            return
        await ctx.send(embed=self._build_definition_embed(definition))

    @raidmode.command(name="create", hidden=True, brief=_("Create a draft definition from a skeleton starter."))
    async def raidmode_create(self, ctx, mode: str, definition_id: str, skeleton: str = None):
        spec = self._get_mode_spec(mode)
        if spec is None:
            await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
            return

        normalized_definition_id = self._validate_definition_id(definition_id)
        if normalized_definition_id is None:
            await ctx.send("Definition ids must be 3-64 chars and use only lowercase letters, numbers, `_`, or `-`.")
            return
        if normalized_definition_id in self.registry["definitions"]:
            await ctx.send(f"Definition `{normalized_definition_id}` already exists.")
            return

        skeleton_key = self._coerce_skeleton_key(skeleton) if skeleton is not None else spec.skeleton
        if skeleton_key is None:
            await ctx.send(
                "Valid skeletons are `good`, `evil`, `chaos`, `trial`, `ritual`, and `attrition`."
            )
            return

        self.registry["definitions"][normalized_definition_id] = self.build_draft_from_starter(
            spec.key,
            normalized_definition_id,
            skeleton_key=skeleton_key,
        )
        self._save_registry()
        await ctx.send(
            f"Created draft `{normalized_definition_id}` for `{spec.key}` from "
            f"`{SKELETON_STARTER_DEFINITION_IDS[skeleton_key]}`. "
            f"Open `raidmode builder {spec.key} {normalized_definition_id}` to customize it, then publish it."
        )

    @raidmode.command(name="publish", hidden=True, brief=_("Publish a draft definition."))
    async def raidmode_publish(self, ctx, definition_id: str):
        normalized_definition_id = definition_id.casefold()
        definition = self._get_definition(normalized_definition_id)
        if definition is None:
            await ctx.send(f"Definition `{normalized_definition_id}` does not exist.")
            return
        definition["status"] = "published"
        self._save_registry()
        await ctx.send(f"Published `{normalized_definition_id}`.")

    @raidmode.command(name="unpublish", hidden=True, brief=_("Return a definition to draft status."))
    async def raidmode_unpublish(self, ctx, definition_id: str):
        normalized_definition_id = definition_id.casefold()
        definition = self._get_definition(normalized_definition_id)
        if definition is None:
            await ctx.send(f"Definition `{normalized_definition_id}` does not exist.")
            return
        definition["status"] = "draft"
        self._save_registry()
        await ctx.send(f"`{normalized_definition_id}` is now a draft again.")

    @raidmode.command(name="activate", hidden=True, brief=_("Activate a published definition for a mode."))
    async def raidmode_activate(self, ctx, mode: str, definition_id: str):
        spec = self._get_mode_spec(mode)
        if spec is None:
            await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
            return

        normalized_definition_id = definition_id.casefold()
        definition = self._get_definition(normalized_definition_id)
        if definition is None:
            await ctx.send(f"Definition `{normalized_definition_id}` does not exist.")
            return
        if definition.get("mode") != spec.key:
            await ctx.send(
                f"`{normalized_definition_id}` belongs to `{definition.get('mode', 'unknown')}`, not `{spec.key}`."
            )
            return
        if definition.get("status") != "published":
            await ctx.send("Only published definitions can be activated.")
            return

        self.registry["modes"][spec.key]["active_definition_id"] = normalized_definition_id
        self._save_registry()
        await ctx.send(
            f"Activated `{normalized_definition_id}` for `{spec.key}`. `raidmode {spec.key}` will now use the custom runtime."
        )

    @raidmode.command(name="deactivate", hidden=True, brief=_("Deactivate the custom definition for a mode."))
    async def raidmode_deactivate(self, ctx, mode: str):
        spec = self._get_mode_spec(mode)
        if spec is None:
            await ctx.send("Valid modes are `good`, `evil`, and `chaos`.")
            return

        self.registry["modes"][spec.key]["active_definition_id"] = None
        self._save_registry()
        await ctx.send(
            f"Cleared the active definition for `{spec.key}`. It now routes to `{spec.legacy_command}`."
        )

    @is_god()
    @raidmode.command(name="good", hidden=True, brief=_("Launch the good raid mode."))
    async def raidmode_good(self, ctx):
        await self._launch_mode(ctx, "good")

    @is_gm()
    @raidmode.command(name="evil", hidden=True, brief=_("Launch the evil raid mode."))
    async def raidmode_evil(self, ctx):
        await self._launch_mode(ctx, "evil")

    @is_gm()
    @raidmode.command(name="chaos", hidden=True, brief=_("Launch the chaos raid mode."))
    async def raidmode_chaos(self, ctx, boss_hp: IntGreaterThan(0)):
        await self._launch_mode(ctx, "chaos", boss_hp=boss_hp)


async def setup(bot):
    await bot.add_cog(RaidBuilder(bot))
