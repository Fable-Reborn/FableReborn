import io
import json
import logging
import random
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import discord

from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View

from classes.enums import DonatorRank
from classes.items import ItemType
from classes.badges import Badge
from cogs.quests.campaign_content import (
    CampaignPackageError,
    CHOICE_NODE_TYPES,
    COLLECTION_EFFECT_TYPES,
    COLLECTION_REWARD_TYPES,
    MAX_PROMPT_OPTIONS,
    SCHEMA_VERSION as CAMPAIGN_SCHEMA_VERSION,
    builtin_install_decision,
    build_reference_catalog,
    node_by_id,
    normalize_endgame_event,
    normalize_key as normalize_campaign_key,
    normalize_system_unlock_key,
    quest_record_from_node,
    resolve_warfront,
    validate_builtin_package,
    validate_package,
)
from cogs.quests.fable_engine import (
    FableStateError,
    FableStateService,
    MODEL_CONDITION_TYPES,
    MODEL_EFFECT_TYPES,
    STATE_CONDITION_TYPES,
    STATE_EFFECT_TYPES,
    compare_state_values,
    expand_model_effect,
    model_state_key,
    normalize_state_key,
)
from utils.april_fools import APRIL_FOOLS_GREG_FLAG
from utils.checks import has_char, is_gm
from utils import misc as rpgtools


logger = logging.getLogger(__name__)


class _AsyncContextValue:
    """Use an existing value where an async context manager is expected."""

    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@dataclass(frozen=True)
class QuestStepDef:
    title: str
    objective: str
    key_item_key: str
    key_item_name: str
    key_item_description: str
    completion_blurb: str
    turn_in_pages: tuple[dict, ...]
    required_pve_wins: int = 0
    required_greg_skulls: int = 0
    required_high_tier_wins: int = 0
    high_tier_min: int = 8


@dataclass(frozen=True)
class QuestDef:
    key: str
    name: str
    category: str
    short_description: str
    reward_text: str
    start_text: str
    steps: tuple[QuestStepDef, ...]


GREG_QUEST = QuestDef(
    key="gregapocalypse",
    name="The Curse of a Thousand Gregs",
    category="Events",
    short_description=(
        "Work with Brother Halric to trace the Gregbound curse from the Black Ledger "
        "to the sealed crypt beneath the abbey."
    ),
    reward_text=(
        "Complete the investigation and unlock access to `$greg boss` once the "
        "realm breaks the final seal."
    ),
    start_text=(
        "Brother Halric draws you aside beneath the abbey bells. He needs proof, relics, "
        "and a hunter willing to follow the Gregbound trail into forbidden ground."
    ),
    steps=(
        QuestStepDef(
            title="The Black Ledger",
            objective="Gather 5 Greg Skulls in PvE and recover the Black Ledger Fragment.",
            key_item_key="black_ledger_fragment",
            key_item_name="Black Ledger Fragment",
            key_item_description=(
                "A burnt scrap of burial parchment. Every surviving line has been rewritten to the same name: Greg."
            ),
            completion_blurb="Brother Halric can read the first pattern in the curse from this fragment.",
            required_greg_skulls=5,
            turn_in_pages=(
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Black Ledger",
                    "text": (
                        "Brother Halric waits in the abbey archive with one gloved hand resting on a ledger so old "
                        "its spine looks mummified.\n\n"
                        "When you place the burnt fragment before him, he does not greet you. He only smooths the ash "
                        "from its edge and turns it toward the candlelight.\n\n"
                        "Every surviving line bears the same name.\n\n"
                        "`Greg.`"
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_02_49_28_PM.png"
                    ),
                },
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Name-Eater",
                    "text": (
                        "\"This is no simple rising of corpses,\" Halric says at last. \"Something is eating names.\"\n\n"
                        "He opens the ledger to fresher entries: kennel records, burial rolls, companion tags. The same "
                        "rot has reached the living and the beasts alike.\n\n"
                        "\"Find where the Gregbound gather next,\" he tells you. \"The bells are counting for something.\""
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_02_49_28_PM.png"
                    ),
                },
            ),
        ),
        QuestStepDef(
            title="The Bells Toll",
            objective="Win 3 more PvE battles and recover the Nameless Bell.",
            key_item_key="nameless_bell",
            key_item_name="Nameless Bell",
            key_item_description=(
                "A cracked handbell that rings with no striker. Its fading note sounds disturbingly close to 'Greg.'"
            ),
            completion_blurb="The bell's tone should point Halric toward the place beneath the abbey.",
            required_pve_wins=3,
            turn_in_pages=(
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Bells Toll",
                    "text": (
                        "You find Halric beneath a bell tower no one has used in years.\n\n"
                        "When he takes the cracked bell from your hands, the dead in the distant fog stop where they stand, "
                        "then all turn toward the abbey hill at once.\n\n"
                        "\"Do you see it now?\" Halric asks. \"They are not wandering. They are being counted.\""
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_02_54_37_PM.png"
                    ),
                },
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Road Beneath",
                    "text": (
                        "Another toll rolls through the dark with no rope and no wind.\n\n"
                        "\"Each note marks another name lost,\" Halric says. \"And whatever waits below already claims them.\"\n\n"
                        "He turns toward the oldest graves in the valley.\n\n"
                        "\"Hunt stronger Gregbound. We will need the ash of the marked dead to read the hidden road.\""
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_02_54_37_PM.png"
                    ),
                },
            ),
        ),
        QuestStepDef(
            title="The Black Crypt",
            objective="Reach 25 Greg Skulls and win a Tier 8+ PvE battle to recover Crypt Seal Ash.",
            key_item_key="crypt_seal_ash",
            key_item_name="Crypt Seal Ash",
            key_item_description=(
                "Warm ash clinging to a sliver of seal-stone. It shifts in the hand as though trying to remember a buried door."
            ),
            completion_blurb="Halric can use this ash to trace the route into the Black Crypt.",
            required_greg_skulls=25,
            required_high_tier_wins=1,
            high_tier_min=8,
            turn_in_pages=(
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Black Crypt",
                    "text": (
                        "Halric pours the ash across a cracked map-table in the abbey undercroft.\n\n"
                        "For a long moment it lies still. Then the soot begins to crawl, slipping through the grooves in the "
                        "stone until it draws a path beneath the graveyard, beneath the abbey, beneath the oldest foundations "
                        "in the valley.\n\n"
                        "\"There,\" Halric whispers. \"The Black Crypt.\""
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_02_58_56_PM.png"
                    ),
                },
                {
                    "title": "Gregapocalypse",
                    "subtitle": "The Last Door",
                    "text": (
                        "\"The seal is broken from within,\" Halric says. \"Whatever sits below no longer waits in silence.\"\n\n"
                        "He steps aside from the final stair and lowers his voice to a whisper.\n\n"
                        "\"When the realm breaks the last seal, go below. And if it speaks your name... pray it still remembers "
                        "the right one.\"\n\n"
                        "You are ready. When the community opens the way, descend with `$greg boss`."
                    ),
                    "image": (
                        "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
                        "295173706496475136_ChatGPT_Image_Mar_30_2026_03_13_18_PM.png"
                    ),
                },
            ),
        ),
    ),
)


QUEST_DEFINITIONS = {}
KEY_ITEM_DEFINITIONS = {
    step.key_item_key: {
        "name": step.key_item_name,
        "description": step.key_item_description,
        "quest_key": GREG_QUEST.key,
        "quest_name": GREG_QUEST.name,
    }
    for step in GREG_QUEST.steps
}

MONSTERS_PATH = Path("monsters.json")
BUILTIN_CAMPAIGN_DIR = Path(__file__).resolve().parent / "data" / "builtin_campaigns"
CUSTOM_QUEST_SOURCES = {
    "none",
    "pve",
    "adventure",
    "battletower",
    "dragonparty",
    "cbt",
    "raidbattle",
    "jurytower",
    "scripted",
    "frontier_boss",
    "divine_victory",
    "omnithrone_phase",
    "omnithrone_completion",
}
CUSTOM_QUEST_SOURCE_ALIASES = {
    "none": "none",
    "pve": "pve",
    "adventure": "adventure",
    "battletower": "battletower",
    "battle tower": "battletower",
    "dragonparty": "dragonparty",
    "dragon party": "dragonparty",
    "dragon": "dragonparty",
    "dragon challenge": "dragonparty",
    "dragon challenge party": "dragonparty",
    "dragonchallenge": "dragonparty",
    "dragonchallengeparty": "dragonparty",
    "dragonchallenge party": "dragonparty",
    "cbt": "cbt",
    "couples battletower": "cbt",
    "couples battle tower": "cbt",
    "couplesbattletower": "cbt",
    "raidbattle": "raidbattle",
    "raid battle": "raidbattle",
    "raid battle 2v1": "raidbattle",
    "raid battle 2v2": "raidbattle",
    "raidbattle2v1": "raidbattle",
    "raidbattle2v2": "raidbattle",
    "jurytower": "jurytower",
    "jury tower": "jurytower",
    "jurytower fight": "jurytower",
    "jurttower": "jurytower",
    "jurt tower": "jurytower",
    "scripted": "scripted",
    "frontier boss": "frontier_boss",
    "frontier boss clear": "frontier_boss",
    "frontier_boss": "frontier_boss",
    "divine victory": "divine_victory",
    "divine_victory": "divine_victory",
    "omnithrone phase": "omnithrone_phase",
    "omnithrone_phase": "omnithrone_phase",
    "omnithrone completion": "omnithrone_completion",
    "omnithrone_completion": "omnithrone_completion",
}
CUSTOM_QUEST_SOURCE_LABELS = {
    "none": "anywhere",
    "pve": "PvE",
    "adventure": "Adventure",
    "battletower": "Battle Tower",
    "dragonparty": "Dragon Party",
    "cbt": "Couples Battle Tower",
    "raidbattle": "Raid Battle",
    "jurytower": "Jury Tower",
    "scripted": "Scripted Encounter",
    "frontier_boss": "Frontier Boss",
    "divine_victory": "Tier 11 Divine Victory",
    "omnithrone_phase": "Omnithrone Phase",
    "omnithrone_completion": "Omnithrone Completion",
}
CUSTOM_QUEST_SOURCE_HELP = "none, pve, adventure, battletower, dragonparty, cbt, raidbattle, jurytower, scripted, frontier_boss, divine_victory, omnithrone_phase, omnithrone_completion"
CUSTOM_QUEST_REAL_SOURCE_HELP = "pve, adventure, battletower, dragonparty, cbt, raidbattle, jurytower, scripted, frontier_boss, divine_victory, omnithrone_phase, omnithrone_completion"
CUSTOM_QUEST_MODES = {"progress", "key_item"}
CUSTOM_QUEST_TURNIN_TYPES = {"progress", "key_item", "crate", "egg", "money"}
CUSTOM_QUEST_REWARD_TYPES = {
    "money", "crate", "item", "egg", "none", "bundle"
} | COLLECTION_REWARD_TYPES
QUEST_CRATE_RARITIES = {
    "common",
    "uncommon",
    "rare",
    "magic",
    "legendary",
    "fortune",
    "divine",
    "materials",
}
QUEST_PATREON_TIERS = {tier.name for tier in DonatorRank}
QUEST_BUILDER_ACTIONS = (
    ("text", "Quest Text", "Edit the journal description, NPC offer text, and turn-in text."),
    ("objective_progress", "Progress Objective", "Set source, count, and optional target filter."),
    ("objective_keyitem", "Key Item Objective", "Set a quest key item found from gameplay."),
    ("objective_drops", "Key Item Drops", "Set drop chance, quantity range, and turn-in amount."),
    ("turnin_key_item", "Turn-In: Key Item", "Require the quest key item at hand-in."),
    ("turnin_progress", "Turn-In: Progress", "Turn in with progress only."),
    ("turnin_crate", "Turn-In: Crate", "Require crates at hand-in."),
    ("turnin_money", "Turn-In: Money", "Require gold at hand-in."),
    ("turnin_egg", "Turn-In: Egg", "Require a specific egg at hand-in."),
    ("reward_money", "Reward: Money", "Grant gold on completion."),
    ("reward_crate", "Reward: Crate", "Grant crates on completion."),
    ("reward_egg", "Reward: Egg", "Grant a monster egg on completion."),
    ("reward_item", "Reward: Item", "Grant a custom weapon or shield."),
    ("reward_none", "Reward: None", "Story-only turn-in with no material reward."),
    ("access", "Access Rules", "Set GM, booster, and Patreon locks."),
    ("prereq", "Prerequisites", "Require other quests first."),
    ("cutscene", "Cutscenes", "Attach accept and turn-in cutscenes."),
)

GREG_INTRO_CUTSCENE_PAGES = (
    {
        "title": "Gregapocalypse",
        "text": (
            "At first, they thought it was grave-robbers.\n\n"
            "Then came the bells.\n\n"
            "One by one, from village crypts, roadside tombs, and forgotten churchyards, "
            "the dead clawed their way back into the moonlight. They did not howl. They did "
            "not hunt. They rose as if answering some distant summons, stumbling through the "
            "fog with earth in their mouths and one sound upon their tongues.\n\n"
            "A single name.\n\n"
            "Greg."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_bf7f8806-d8d5-4599-8632-2554eef5039c.png"
        ),
    },
    {
        "title": "The Curse Spreads",
        "text": (
            "By dawn, it was no longer only the dead.\n\n"
            "Hounds turned at their masters' voices as though hearing strangers. Stable-beasts "
            "stamped and wailed. Familiars, companions, and battle-pets stared with hollow eyes, "
            "as if some hand within them had begun to scrape away what they once were.\n\n"
            "In the square, before witnesses, one poor soul watched their own companion shudder, "
            "stiffen, and begin to change.\n\n"
            "Not into some beast of fang or plague.\n\n"
            "Into a Greg."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_11_33_PM.png"
        ),
    },
    {
        "title": "The Black Ledger",
        "text": (
            "The abbey keepers searched the burial rolls for answers.\n\n"
            "They found only terror.\n\n"
            "Every death record, no matter how old, had been rewritten in the same hand. "
            "Knights, beggars, children, beasts, wanderers, stillborn babes, plague-dead, "
            "nameless bones pulled from riverbeds, all of them now bore the same inscription.\n\n"
            "Greg.\n\n"
            "And where the ink had not changed, the parchment had blackened as if scorched from within."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_d8a2cdb4-5c83-474c-be9b-33cb060e05a6.png"
        ),
    },
    {
        "title": "What Was Forgotten",
        "text": (
            "There are old whispers beneath Fable's soil.\n\n"
            "They speak of a keeper of graves, a scribe of the unremembered dead, who would not "
            "suffer the lost to vanish from the world without a name. In secret, he gathered the "
            "names of the buried, the forsaken, and the forgotten, and set them down in a book no "
            "fire should have touched.\n\n"
            "But some rites are not meant for mortal hands.\n\n"
            "Something answered.\n\n"
            "And where there had once been thousands of names, only one remained."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_23_39_PM.png"
        ),
    },
    {
        "title": "Now the Bells Toll for Us",
        "text": (
            "The curse no longer sleeps in crypt and graveyard alone.\n\n"
            "It moves through pet and tower, through ruin and road, through the living and the dead "
            "alike. Those struck by it do not merely sicken. They are unmade, little by little, until "
            "their own true name slips from them like ash in rain.\n\n"
            "The grave-priests beg for aid. The villages bar their doors. The towers murmur with voices "
            "that are no longer their own.\n\n"
            "If this blight is not cut out at its root, Fable will soon be a realm of one name and a "
            "thousand empty faces."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_28_11_PM.png"
        ),
    },
    {
        "title": "Your Charge",
        "text": (
            "Go forth into the dark places.\n\n"
            "Gather the remnants of what has been stolen.\n\n"
            "Hunt the Gregbound dead.\n\n"
            "Find the buried source of the curse.\n\n"
            "And before the final bell is rung, restore the names of the lost.\n\n"
            "Or join them."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_29_2026_09_34_05_PM.png"
        ),
    },
)

GREG_BOSS_LIBRARY_PAGES = (
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Black Crypt",
        "text": (
            "The doors of the crypt drag open.\n\n"
            "Rows of the dead kneel in silence.\n\n"
            "At the far end of the chamber, a lone figure sits upon a throne of broken "
            "grave-stone and blackened ledgers.\n\n"
            "Then it lifts its head.\n\n"
            "“Another one,” it says."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_16_03_PM.png"
        ),
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The One Upon the Throne",
        "text": (
            "Your pet bristles at your side.\n\n"
            "The figure rises slowly, candlelight catching on a crown of bent grave-nails.\n\n"
            "“All this way,” it murmurs, “just to die protecting a name that will not "
            "outlive your bones.”\n\n"
            "From the dark around you comes a whisper, low and endless.\n\n"
            "`Greg. Greg. Greg.`"
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_16_03_PM.png"
        ),
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Exchange",
        "text": (
            "You tighten your grip on your weapon.\n\n"
            "“So this is your doing?”\n\n"
            "The figure tilts its head, almost amused.\n\n"
            "“My doing?” it says. “No.”\n\n"
            "It takes one step down from the throne.\n\n"
            "“My correction.”"
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_21_10_PM.png"
        ),
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Name Revealed",
        "text": (
            "The candles flare bright.\n\n"
            "The dead rise as one.\n\n"
            "All around you, hollow voices murmur from the dark.\n\n"
            "`Greg. Greg. Greg.`\n\n"
            "The figure spreads its arms.\n\n"
            "“I am the last name they will ever need.”"
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_21_10_PM.png"
        ),
    },
    {
        "title": "The Greg of All Gregs",
        "subtitle": "The Greg of All Gregs",
        "text": (
            "Its eyes burn with pale fire.\n\n"
            "“I am the Greg of All Gregs.”\n\n"
            "Then it smiles.\n\n"
            "“Come, hero. Let us see if your name survives mine.”"
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_21_10_PM.png"
        ),
    },
)

GREG_EPILOGUE_CUTSCENE_PAGES = (
    {
        "title": "Gregapocalypse",
        "subtitle": "The Last Bell Falls Silent",
        "text": (
            "Brother Halric is waiting when you climb from the undercroft, as though he never once dared "
            "leave the abbey steps.\n\n"
            "You place the shattered seal in his hands.\n\n"
            "For a moment he says nothing. His thumb brushes the cracked edge, and the last cold pulse of the "
            "Black Crypt seems to die there between his fingers.\n\n"
            "\"Then it is done,\" he says at last. \"The last door has broken, and what lay below it will not rise again.\""
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_23_56_PM.png"
        ),
    },
    {
        "title": "Gregapocalypse",
        "subtitle": "Names Remembered",
        "text": (
            "Beyond the abbey walls, the bells finally fall silent.\n\n"
            "No dead answer them. No hollow voice repeats that stolen name back through the fog. In the kennels, in the "
            "graveyard, in the dark roads beyond the village, something long-twisted begins at last to loosen its grip.\n\n"
            "Halric closes his eyes.\n\n"
            "\"The dead were not asking for Greg,\" he murmurs. \"They were asking not to be forgotten.\""
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_26_24_PM.png"
        ),
    },
    {
        "title": "Gregapocalypse",
        "subtitle": "The Realm Endures",
        "text": (
            "He returns the broken seal to you like a relic, not a trophy.\n\n"
            "\"Keep it,\" he says. \"Let it remind the living what becomes of a world that stops remembering its own.\"\n\n"
            "The churchyard is quiet now. The ledgers will need mending. The graves will need blessing. The realm will speak "
            "of this in laughter before long, because that is what the living do when terror finally passes.\n\n"
            "But tonight, the names of the lost belong to themselves again.\n\n"
            "And yours remains your own."
        ),
        "image": (
            "https://pub-0e7afc36364b4d5dbd1fd2bea161e4d1.r2.dev/"
            "295173706496475136_ChatGPT_Image_Mar_30_2026_03_26_24_PM.png"
        ),
    },
)

DEFAULT_CUTSCENE_DEFINITIONS = {
    "greg_intro_lore": {
        "title": "Gregapocalypse",
        "pages": GREG_INTRO_CUTSCENE_PAGES,
    },
    "greg_boss_intro": {
        "title": "The Greg of All Gregs",
        "pages": GREG_BOSS_LIBRARY_PAGES,
    },
    "greg_black_ledger": {
        "title": "Gregapocalypse: The Black Ledger",
        "pages": GREG_QUEST.steps[0].turn_in_pages,
    },
    "greg_bells_toll": {
        "title": "Gregapocalypse: The Bells Toll",
        "pages": GREG_QUEST.steps[1].turn_in_pages,
    },
    "greg_black_crypt": {
        "title": "Gregapocalypse: The Black Crypt",
        "pages": GREG_QUEST.steps[2].turn_in_pages,
    },
    "greg_epilogue": {
        "title": "Gregapocalypse: The Last Name Left",
        "pages": GREG_EPILOGUE_CUTSCENE_PAGES,
    },
}


class QuestPageView(View):
    def __init__(self, pages, user_id):
        super().__init__(timeout=300)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self.completed = False
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        prev_button = Button(
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.current_page == 0,
        )
        prev_button.callback = self.prev_callback

        next_button = Button(
            style=discord.ButtonStyle.secondary,
            emoji="✅" if self.current_page >= len(self.pages) - 1 else "▶️",
            label="Continue" if self.current_page >= len(self.pages) - 1 else None,
        )
        next_button.callback = self.next_callback

        self.add_item(prev_button)
        self.add_item(
            Button(
                style=discord.ButtonStyle.gray,
                label=f"{self.current_page + 1}/{len(self.pages)}",
                disabled=True,
            )
        )
        self.add_item(next_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This quest scene is not yours.",
                ephemeral=True,
            )
            return False
        return True

    async def prev_callback(self, interaction):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self,
        )

    async def next_callback(self, interaction):
        if self.current_page >= len(self.pages) - 1:
            self.completed = True
            self.stop()
            await interaction.response.edit_message(
                embed=self.pages[self.current_page],
                view=None,
            )
            return
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class QuestJournalCategorySelect(discord.ui.Select):
    def __init__(self, journal_view: "QuestJournalView"):
        self.journal_view = journal_view
        options = [
            discord.SelectOption(
                label=category[:100],
                value=category,
                default=category == self.journal_view.selected_category,
            )
            for category in self.journal_view.categories
        ]
        super().__init__(
            placeholder="Select a quest category",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.journal_view.selected_category = self.values[0]
        quests = self.journal_view.filtered_entries
        self.journal_view.selected_quest_key = quests[0]["quest_key"] if quests else None
        await self.journal_view.refresh(interaction)


class QuestJournalQuestSelect(discord.ui.Select):
    def __init__(self, journal_view: "QuestJournalView"):
        self.journal_view = journal_view
        options = []
        for entry in self.journal_view.filtered_entries[:25]:
            label = entry["name"][:100]
            description = f"{entry['snapshot']['status_label']} - {entry['category']}"[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=entry["quest_key"],
                    description=description,
                    default=entry["quest_key"] == self.journal_view.selected_quest_key,
                )
            )
        super().__init__(
            placeholder="Select a specific quest",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.journal_view.selected_quest_key = self.values[0]
        await self.journal_view.refresh(interaction)


class QuestJournalAvailableButton(Button):
    def __init__(self, journal_view: "QuestJournalView"):
        super().__init__(
            label="Greg Quests",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        self.journal_view = journal_view

    async def callback(self, interaction: discord.Interaction):
        await self.journal_view.show_available(interaction)


class QuestJournalView(View):
    def __init__(self, *, cog: "Quests", ctx, entries: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.entries = entries
        self.categories = sorted({entry["category"] for entry in entries})
        self.selected_category = self._default_category()
        first_entry = self.filtered_entries[0] if self.filtered_entries else None
        self.selected_quest_key = first_entry["quest_key"] if first_entry else None
        self._sync_controls()

    def _default_category(self) -> str | None:
        if "Events" in self.categories:
            return "Events"
        return self.categories[0] if self.categories else None

    @property
    def filtered_entries(self) -> list[dict]:
        if self.selected_category is None:
            return []
        return [
            entry
            for entry in self.entries
            if entry["category"] == self.selected_category
        ]

    def _selected_entry(self) -> dict | None:
        for entry in self.filtered_entries:
            if entry["quest_key"] == self.selected_quest_key:
                return entry
        return self.filtered_entries[0] if self.filtered_entries else None

    def _sync_controls(self):
        self.clear_items()
        if self.categories:
            self.add_item(QuestJournalCategorySelect(self))
        if self.filtered_entries:
            if self.selected_quest_key not in {
                entry["quest_key"] for entry in self.filtered_entries
            }:
                self.selected_quest_key = self.filtered_entries[0]["quest_key"]
            self.add_item(QuestJournalQuestSelect(self))
        self.add_item(QuestJournalAvailableButton(self))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Quest Journal",
            color=0x3E2617,
        )

        if not self.entries:
            embed.description = "You do not have any accepted quests right now."
            embed.set_footer(text="Use $quests accept <quest> to begin one.")
            return embed

        selected = self._selected_entry()
        if selected is None:
            embed.description = "No quest is selected."
            return embed

        row = selected["row"]
        snapshot = selected["snapshot"]
        embed.description = selected["short_description"]

        embed.add_field(name="Category", value=selected["category"], inline=True)
        embed.add_field(name="Quest", value=selected["name"], inline=True)
        embed.add_field(name="Status", value=snapshot["status_label"], inline=True)

        if row["status"] == "completed":
            requirements_text = "All chapters turned in."
            turn_in_text = "Already completed."
        else:
            requirements_text = "\n".join(snapshot["progress_lines"])
            turn_in_text = snapshot.get(
                "turn_in_text",
                f"Use `$quests turnin {selected['quest_key']}` when ready.",
            )
            current_chapter = snapshot.get("current_chapter")
            if current_chapter:
                embed.add_field(name="Current Chapter", value=current_chapter, inline=True)

        embed.add_field(name="Requirements", value=requirements_text, inline=False)
        embed.add_field(name="Reward", value=selected["reward_text"], inline=False)
        embed.add_field(name="Turn In", value=turn_in_text, inline=False)
        embed.set_footer(text="Use the dropdowns to switch quests, or open Greg Quests below.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This quest journal is not yours.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self._sync_controls()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def show_available(self, interaction: discord.Interaction):
        embed, view = await self.cog._build_greg_quest_board(
            self.ctx,
            has_active_entries=True,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class QuestBoardCategorySelect(discord.ui.Select):
    def __init__(self, board_view: "QuestBoardView"):
        self.board_view = board_view
        options = [
            discord.SelectOption(
                label=category[:100],
                value=category,
                default=category == self.board_view.selected_category,
            )
            for category in self.board_view.categories
        ]
        super().__init__(
            placeholder="Select a quest category",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.board_view.selected_category = self.values[0]
        quests = self.board_view.filtered_entries
        self.board_view.selected_quest_key = quests[0]["quest_key"] if quests else None
        await self.board_view.refresh(interaction)


class QuestBoardQuestSelect(discord.ui.Select):
    def __init__(self, board_view: "QuestBoardView"):
        self.board_view = board_view
        options = []
        for entry in self.board_view.filtered_entries[:25]:
            description = entry["objective_text"].replace("\n", " ")
            if entry["repeatable"]:
                description = f"Repeatable • {description}"
            options.append(
                discord.SelectOption(
                    label=entry["name"][:100],
                    value=entry["quest_key"],
                    description=description[:100] or entry["category"][:100],
                    default=entry["quest_key"] == self.board_view.selected_quest_key,
                )
            )
        super().__init__(
            placeholder="Select a quest to inspect",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.board_view.selected_quest_key = self.values[0]
        await self.board_view.refresh(interaction)


class QuestBoardAcceptButton(Button):
    def __init__(self, board_view: "QuestBoardView"):
        super().__init__(
            label="Accept Quest",
            style=discord.ButtonStyle.success,
            row=2,
            disabled=not board_view.entries,
        )
        self.board_view = board_view

    async def callback(self, interaction: discord.Interaction):
        selected = self.board_view._selected_entry()
        if selected is None:
            return await interaction.response.send_message(
                "No quest is selected.",
                ephemeral=True,
            )

        await interaction.response.defer()
        try:
            accept_data = await self.board_view.cog._accept_quest_for_user(
                self.board_view.ctx.author.id,
                selected["quest_key"],
            )
        except ValueError as exc:
            return await interaction.followup.send(str(exc), ephemeral=True)

        await self.board_view.cog._send_quest_accept_messages(
            self.board_view.ctx,
            accept_data,
        )
        await self.board_view.reload(has_active_entries=True)
        await interaction.message.edit(
            embed=self.board_view.build_embed(),
            view=self.board_view,
        )


class QuestBoardJournalButton(Button):
    def __init__(self, board_view: "QuestBoardView"):
        super().__init__(
            label="View Journal",
            style=discord.ButtonStyle.secondary,
            row=2,
            disabled=not board_view.has_active_entries,
        )
        self.board_view = board_view

    async def callback(self, interaction: discord.Interaction):
        embed, view = await self.board_view.cog._build_journal_display(
            self.board_view.ctx
        )
        if embed is None or view is None:
            await self.board_view.reload(has_active_entries=False)
            return await interaction.response.edit_message(
                embed=self.board_view.build_embed(),
                view=self.board_view,
            )
        await interaction.response.edit_message(embed=embed, view=view)


class QuestBoardView(View):
    def __init__(
        self,
        *,
        cog: "Quests",
        ctx,
        entries: list[dict],
        empty_text: str,
        has_active_entries: bool = False,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.entries = entries
        self.empty_text = empty_text
        self.has_active_entries = has_active_entries
        self.categories = sorted({entry["category"] for entry in entries})
        self.selected_category = self._default_category()
        first_entry = self.filtered_entries[0] if self.filtered_entries else None
        self.selected_quest_key = first_entry["quest_key"] if first_entry else None
        self._sync_controls()

    def _default_category(self) -> str | None:
        if "Events" in self.categories:
            return "Events"
        return self.categories[0] if self.categories else None

    @property
    def filtered_entries(self) -> list[dict]:
        if self.selected_category is None:
            return []
        return [
            entry
            for entry in self.entries
            if entry["category"] == self.selected_category
        ]

    def _selected_entry(self) -> dict | None:
        for entry in self.filtered_entries:
            if entry["quest_key"] == self.selected_quest_key:
                return entry
        return self.filtered_entries[0] if self.filtered_entries else None

    def _sync_controls(self):
        self.clear_items()
        if self.categories:
            self.add_item(QuestBoardCategorySelect(self))
        if self.filtered_entries:
            if self.selected_quest_key not in {
                entry["quest_key"] for entry in self.filtered_entries
            }:
                self.selected_quest_key = self.filtered_entries[0]["quest_key"]
            self.add_item(QuestBoardQuestSelect(self))
        self.add_item(QuestBoardAcceptButton(self))
        self.add_item(QuestBoardJournalButton(self))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Greg Quests",
            color=0x5D2E12,
        )

        if not self.entries:
            embed.description = self.empty_text
            footer_text = (
                "Use View Journal to return to your active quests."
                if self.has_active_entries
                else "No Greg quests are available to accept right now."
            )
            embed.set_footer(text=footer_text)
            return embed

        selected = self._selected_entry()
        if selected is None:
            embed.description = "No quest is selected."
            return embed

        description_parts = [
            str(selected["short_description"]).strip(),
        ]
        offer_text = str(selected.get("offer_text") or "").strip()
        if offer_text and offer_text not in description_parts:
            description_parts.append(offer_text)
        embed.description = "\n\n".join(part for part in description_parts if part)

        embed.add_field(name="Category", value=selected["category"], inline=True)
        embed.add_field(name="Quest", value=selected["name"], inline=True)
        embed.add_field(
            name="Repeatable",
            value="Yes" if selected["repeatable"] else "No",
            inline=True,
        )
        embed.add_field(
            name="Objective",
            value=selected["objective_text"],
            inline=False,
        )
        embed.add_field(name="Reward", value=selected["reward_text"], inline=False)
        embed.add_field(
            name="How to Start",
            value=(
                f"Press **Accept Quest** below or use "
                f"`$quests accept {selected['quest_key']}`."
            ),
            inline=False,
        )
        embed.set_footer(
            text="Use the dropdowns to browse Greg event quests."
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This quest board is not yours.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self._sync_controls()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def reload(self, *, has_active_entries: bool | None = None):
        self.entries = await self.cog._get_available_greg_quest_entries(
            self.ctx.author.id
        )
        self.empty_text = await self.cog._greg_quest_board_empty_text(
            self.ctx.author.id
        )
        if has_active_entries is not None:
            self.has_active_entries = has_active_entries
        self.categories = sorted({entry["category"] for entry in self.entries})
        if self.selected_category not in self.categories:
            self.selected_category = self._default_category()
        filtered_keys = {entry["quest_key"] for entry in self.filtered_entries}
        if self.selected_quest_key not in filtered_keys:
            first_entry = self.filtered_entries[0] if self.filtered_entries else None
            self.selected_quest_key = first_entry["quest_key"] if first_entry else None
        self._sync_controls()


class GMQuestBuilderFormModal(Modal):
    def __init__(self, builder_view: "GMQuestBuilderView", *, title: str, fields: list[dict], submit_handler):
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
                "This quest builder is not for you.",
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


class GMQuestBuilderQuestSelect(discord.ui.Select):
    def __init__(self, builder_view: "GMQuestBuilderView"):
        self.builder_view = builder_view
        options = []
        for quest_def in builder_view.quest_defs[:25]:
            state = "active" if quest_def["is_active"] else "draft"
            options.append(
                discord.SelectOption(
                    label=quest_def["name"][:100],
                    value=quest_def["quest_key"],
                    description=f"{quest_def['category']} • {state}"[:100],
                    default=quest_def["quest_key"] == builder_view.selected_quest_key,
                )
            )
        if not options:
            options.append(
                discord.SelectOption(
                    label="No quests yet",
                    value="__none__",
                    description="Create a custom quest to begin.",
                    default=True,
                )
            )
        super().__init__(
            placeholder="Choose a custom quest",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not builder_view.quest_defs,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] != "__none__":
            self.builder_view.selected_quest_key = self.values[0]
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class GMQuestBuilderActionSelect(discord.ui.Select):
    def __init__(self, builder_view: "GMQuestBuilderView"):
        self.builder_view = builder_view
        options = [
            discord.SelectOption(
                label=label[:100],
                value=value,
                description=description[:100],
                default=value == builder_view.selected_action,
            )
            for value, label, description in QUEST_BUILDER_ACTIONS
        ]
        super().__init__(
            placeholder="Choose what to edit",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.builder_view.selected_action = self.values[0]
        await interaction.response.defer()
        await self.builder_view.refresh_message()


class GMQuestBuilderView(View):
    def __init__(self, *, cog: "Quests", ctx):
        super().__init__(timeout=900)
        self.cog = cog
        self.ctx = ctx
        self.author = ctx.author
        self.quest_defs: list[dict] = []
        self.selected_quest_key: str | None = None
        self.selected_action = QUEST_BUILDER_ACTIONS[0][0]
        self.message = None

    async def refresh_data(self):
        async with self.cog.bot.pool.acquire() as conn:
            self.quest_defs = await self.cog._fetch_custom_quest_definitions(
                conn=conn,
                active_only=False,
            )
        if self.quest_defs and self.selected_quest_key not in {
            quest_def["quest_key"] for quest_def in self.quest_defs
        }:
            self.selected_quest_key = self.quest_defs[0]["quest_key"]
        elif not self.quest_defs:
            self.selected_quest_key = None

    def selected_quest(self) -> dict | None:
        for quest_def in self.quest_defs:
            if quest_def["quest_key"] == self.selected_quest_key:
                return quest_def
        return self.quest_defs[0] if self.quest_defs else None

    def action_help(self) -> str:
        for value, _label, description in QUEST_BUILDER_ACTIONS:
            if value == self.selected_action:
                return description
        return "Select an action."

    def build_embed(self) -> discord.Embed:
        selected = self.selected_quest()
        if not selected:
            embed = discord.Embed(
                title="GM Quest Builder",
                description="No custom quests exist yet. Create one to begin.",
                color=0x5D2E12,
            )
            embed.add_field(name="Selected Editor", value=self.action_help(), inline=False)
            embed.set_footer(text="Create Quest starts a new draft.")
            return embed
        embed = self.cog._build_custom_quest_admin_embed(selected)
        embed.title = f"GM Quest Builder: {selected['name']}"
        embed.add_field(
            name="Selected Editor",
            value=f"`{self.selected_action}`\n{self.action_help()}",
            inline=False,
        )
        embed.set_footer(text="Select a quest, choose an editor, then press Edit Selected.")
        return embed

    def _sync_controls(self):
        self.clear_items()
        self.add_item(GMQuestBuilderQuestSelect(self))
        self.add_item(GMQuestBuilderActionSelect(self))

        selected = self.selected_quest()

        create_button = Button(style=discord.ButtonStyle.green, label="Create Quest", row=2)
        create_button.callback = self.create_callback
        self.add_item(create_button)

        edit_button = Button(
            style=discord.ButtonStyle.blurple,
            label="Edit Selected",
            row=2,
            disabled=selected is None,
        )
        edit_button.callback = self.edit_callback
        self.add_item(edit_button)

        active_button = Button(
            style=discord.ButtonStyle.secondary,
            label="Set Draft" if selected and selected["is_active"] else "Publish",
            row=2,
            disabled=selected is None,
        )
        active_button.callback = self.active_callback
        self.add_item(active_button)

        repeat_button = Button(
            style=discord.ButtonStyle.secondary,
            label="Make One-Time" if selected and selected["repeatable"] else "Make Repeatable",
            row=2,
            disabled=selected is None,
        )
        repeat_button.callback = self.repeatable_callback
        self.add_item(repeat_button)

        preview_accept = Button(
            style=discord.ButtonStyle.secondary,
            label="Preview Accept",
            row=3,
            disabled=selected is None or not str(selected.get("accept_cutscene_key") or "").strip(),
        )
        preview_accept.callback = self.preview_accept_callback
        self.add_item(preview_accept)

        preview_turnin = Button(
            style=discord.ButtonStyle.secondary,
            label="Preview Turn-In",
            row=3,
            disabled=selected is None or not str(selected.get("turnin_cutscene_key") or "").strip(),
        )
        preview_turnin.callback = self.preview_turnin_callback
        self.add_item(preview_turnin)

        refresh_button = Button(style=discord.ButtonStyle.gray, label="Refresh", row=3)
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

    async def refresh_message(self):
        await self.refresh_data()
        self._sync_controls()
        if self.message is not None:
            await self.message.edit(embed=self.build_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This quest builder is not for you.",
                ephemeral=True,
            )
            return False
        return True

    def _selected_or_error(self) -> dict:
        selected = self.selected_quest()
        if not selected:
            raise ValueError("No quest is selected.")
        return selected

    def _action_label(self, action_value: str | None = None) -> str:
        target = action_value or self.selected_action
        for value, label, _description in QUEST_BUILDER_ACTIONS:
            if value == target:
                return label
        return "Quest Editor"

    def _parse_int(self, raw_value: str, label: str, *, minimum: int = 0) -> int:
        try:
            value = int(str(raw_value).replace(",", "").strip())
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if value < minimum:
            raise ValueError(f"{label} must be at least {minimum}.")
        return value

    def _fields_for_action(self, selected: dict, action: str) -> list[dict] | None:
        objective = selected.get("objective") or {}
        turnin = selected.get("turnin") or {}
        reward = selected.get("reward") or {}
        access = selected.get("access") or {}

        if action == "text":
            return [
                {
                    "key": "name",
                    "label": "Quest Name",
                    "default": selected.get("name") or "",
                    "placeholder": "The Fisher's Request",
                },
                {
                    "key": "category",
                    "label": "Category",
                    "default": selected.get("category") or "General",
                    "placeholder": "Events",
                },
                {
                    "key": "short_description",
                    "label": "Journal Description",
                    "default": selected.get("short_description") or "",
                    "style": discord.TextStyle.paragraph,
                    "placeholder": "A short quest summary shown in the journal.",
                },
                {
                    "key": "offer_text",
                    "label": "NPC Offer Text",
                    "default": selected.get("offer_text") or "",
                    "style": discord.TextStyle.paragraph,
                    "placeholder": "Quest giver text in MMO quest style.",
                },
                {
                    "key": "turnin_text",
                    "label": "Turn-In Text",
                    "default": selected.get("turnin_text") or "",
                    "style": discord.TextStyle.paragraph,
                    "required": False,
                    "placeholder": "Optional hand-in hint shown in the quest journal.",
                },
            ]

        if action == "objective_progress":
            return [
                {
                    "key": "source",
                    "label": "Source",
                    "default": objective.get("source") or "pve",
                    "placeholder": CUSTOM_QUEST_SOURCE_HELP,
                },
                {
                    "key": "required_count",
                    "label": "Required Count",
                    "default": str(objective.get("required_count") or 0),
                    "placeholder": "10",
                },
                {
                    "key": "target_name",
                    "label": "Target Name",
                    "default": objective.get("target_name") or "",
                    "required": False,
                    "placeholder": "Optional specific monster/floor name or any",
                },
            ]

        if action == "objective_keyitem":
            return [
                {
                    "key": "source",
                    "label": "Source",
                    "default": objective.get("source") or "pve",
                    "placeholder": CUSTOM_QUEST_REAL_SOURCE_HELP,
                },
                {
                    "key": "required_count",
                    "label": "Progress Before Drops",
                    "default": str(objective.get("required_count") or 0),
                    "placeholder": "0 for item only, or 5",
                },
                {
                    "key": "key_item_name",
                    "label": "Key Item Name",
                    "default": objective.get("key_item_name") or "",
                    "placeholder": "Black Ledger Fragment",
                },
                {
                    "key": "key_item_description",
                    "label": "Key Item Description",
                    "default": objective.get("key_item_description") or "",
                    "style": discord.TextStyle.paragraph,
                    "placeholder": "Describe the quest item for $inv.",
                },
                {
                    "key": "target_name",
                    "label": "Target Name",
                    "default": objective.get("target_name") or "",
                    "required": False,
                    "placeholder": "Optional specific monster/floor name or any",
                },
            ]

        if action == "objective_drops":
            return [
                {
                    "key": "drop_chance_percent",
                    "label": "Drop Chance %",
                    "default": str(int(float(objective.get("drop_chance_percent") or 100))),
                    "placeholder": "100",
                },
                {
                    "key": "drop_quantity_min",
                    "label": "Drop Min",
                    "default": str(objective.get("drop_quantity_min") or 1),
                    "placeholder": "1",
                },
                {
                    "key": "drop_quantity_max",
                    "label": "Drop Max",
                    "default": str(objective.get("drop_quantity_max") or 1),
                    "placeholder": "3",
                },
                {
                    "key": "key_item_required_quantity",
                    "label": "Turn-In Qty",
                    "default": str(objective.get("key_item_required_quantity") or 1),
                    "placeholder": "1",
                },
            ]

        if action == "turnin_progress":
            return None

        if action == "turnin_key_item":
            return None

        if action == "turnin_crate":
            return [
                {
                    "key": "rarity",
                    "label": "Crate Rarity",
                    "default": turnin.get("rarity") or "common",
                    "placeholder": "common, rare, magic, legendary...",
                },
                {
                    "key": "amount",
                    "label": "Crate Amount",
                    "default": str(turnin.get("amount") or 1),
                    "placeholder": "2",
                },
            ]

        if action == "turnin_money":
            return [
                {
                    "key": "amount",
                    "label": "Gold Amount",
                    "default": str(turnin.get("amount") or 1000),
                    "placeholder": "5000",
                },
            ]

        if action == "turnin_egg":
            return [
                {
                    "key": "egg_name",
                    "label": "Egg Name",
                    "default": turnin.get("egg_name") or "",
                    "placeholder": "Sneevil",
                },
                {
                    "key": "amount",
                    "label": "Egg Amount",
                    "default": str(turnin.get("amount") or 1),
                    "placeholder": "1",
                },
            ]

        if action == "reward_money":
            return [
                {
                    "key": "amount",
                    "label": "Gold Reward",
                    "default": str(reward.get("amount") or 1000),
                    "placeholder": "15000",
                },
            ]

        if action == "reward_crate":
            return [
                {
                    "key": "rarity",
                    "label": "Crate Rarity",
                    "default": reward.get("rarity") or "common",
                    "placeholder": "common, rare, magic, legendary...",
                },
                {
                    "key": "amount",
                    "label": "Crate Amount",
                    "default": str(reward.get("amount") or 1),
                    "placeholder": "2",
                },
            ]

        if action == "reward_egg":
            return [
                {
                    "key": "monster_name",
                    "label": "Monster Name",
                    "default": reward.get("monster_name") or "",
                    "placeholder": "Sneevil",
                },
            ]

        if action == "reward_item":
            return [
                {
                    "key": "name",
                    "label": "Item Name",
                    "default": reward.get("name") or "",
                    "placeholder": "Halric's Buckler",
                },
                {
                    "key": "item_type",
                    "label": "Item Type",
                    "default": reward.get("item_type") or "Shield",
                    "placeholder": "Sword, Shield, Spear...",
                },
                {
                    "key": "stat",
                    "label": "Stat Value",
                    "default": str(reward.get("stat") or 0),
                    "placeholder": "220",
                },
                {
                    "key": "value",
                    "label": "Gold Value",
                    "default": str(reward.get("value") or 0),
                    "placeholder": "45000",
                },
                {
                    "key": "element",
                    "label": "Element",
                    "default": reward.get("element") or "Light",
                    "placeholder": "Light",
                },
            ]

        if action == "reward_none":
            return None

        if action == "access":
            return [
                {
                    "key": "gm_only",
                    "label": "GM Only",
                    "default": "on" if access.get("gm_only") else "off",
                    "placeholder": "on or off",
                },
                {
                    "key": "booster_only",
                    "label": "Booster Only",
                    "default": "on" if access.get("booster_only") else "off",
                    "placeholder": "on or off",
                },
                {
                    "key": "patreon_tier",
                    "label": "Patreon Tier",
                    "default": access.get("patreon_tier") or "none",
                    "placeholder": "none or a DonatorRank tier",
                },
                {
                    "key": "event_flag",
                    "label": "Event Flag",
                    "default": access.get("event_flag") or "none",
                    "required": False,
                    "placeholder": "none, april:greg_mode, event:halloween",
                },
            ]

        if action == "prereq":
            return [
                {
                    "key": "prerequisites",
                    "label": "Prerequisite Quests",
                    "default": ", ".join(str(key) for key in (selected.get("prerequisites") or [])),
                    "required": False,
                    "style": discord.TextStyle.paragraph,
                    "placeholder": "greg_ledger, greg_bells or none",
                },
            ]

        if action == "cutscene":
            return [
                {
                    "key": "accept_cutscene_key",
                    "label": "Accept Cutscene",
                    "default": selected.get("accept_cutscene_key") or "none",
                    "required": False,
                    "placeholder": "greg_intro_lore or none",
                },
                {
                    "key": "turnin_cutscene_key",
                    "label": "Turn-In Cutscene",
                    "default": selected.get("turnin_cutscene_key") or "none",
                    "required": False,
                    "placeholder": "greg_black_ledger, greg_epilogue, or none",
                },
            ]

        return None

    async def _apply_action(self, quest_key: str, action: str, values: dict[str, str]) -> str:
        async with self.cog.bot.pool.acquire() as conn:
            if action == "text":
                name = str(values.get("name") or "").strip()
                category = str(values.get("category") or "").strip()
                if not name:
                    raise ValueError("Quest name cannot be blank.")
                if not category:
                    raise ValueError("Category cannot be blank.")
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {
                        "name": name,
                        "category": category,
                        "short_description": str(values.get("short_description") or "").strip(),
                        "offer_text": str(values.get("offer_text") or "").strip(),
                        "turnin_text": str(values.get("turnin_text") or "").strip(),
                    },
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated text for **{custom_def['name']}**."

            if action == "objective_progress":
                source = self.cog._normalize_source(values.get("source"))
                if source is None:
                    raise ValueError(f"Source must be one of: {CUSTOM_QUEST_SOURCE_HELP}.")
                required_count = self._parse_int(values.get("required_count") or "0", "Required count", minimum=0)
                target_name = str(values.get("target_name") or "").strip()
                if target_name.lower() == "any":
                    target_name = ""
                if source == "adventure" and target_name:
                    raise ValueError("Adventure objectives currently only support count-based progress.")
                objective = {
                    "source": source,
                    "mode": "progress",
                    "required_count": required_count,
                    "target_name": target_name,
                }
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {
                        "objective_json": json.dumps(objective, sort_keys=True),
                        "turnin_json": json.dumps({"type": "progress"}, sort_keys=True),
                    },
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated progress objective for **{custom_def['name']}**."

            if action == "objective_keyitem":
                source = self.cog._normalize_source(values.get("source"))
                if source is None or source == "none":
                    raise ValueError(f"Key item objectives need a real source: {CUSTOM_QUEST_REAL_SOURCE_HELP}.")
                required_count = self._parse_int(values.get("required_count") or "0", "Required count", minimum=0)
                key_item_name = str(values.get("key_item_name") or "").strip()
                key_item_description = str(values.get("key_item_description") or "").strip()
                if not key_item_name:
                    raise ValueError("Key item name cannot be blank.")
                if not key_item_description:
                    raise ValueError("Key item description cannot be blank.")
                target_name = str(values.get("target_name") or "").strip()
                if target_name.lower() == "any":
                    target_name = ""
                if source == "adventure" and target_name:
                    raise ValueError("Adventure objectives currently only support count-based progress.")
                key_item_key = self.cog._normalize_custom_quest_key(f"{quest_key}_{key_item_name}")
                if not key_item_key:
                    raise ValueError("Could not derive a valid key item key from that name.")
                objective = {
                    "source": source,
                    "mode": "key_item",
                    "required_count": required_count,
                    "target_name": target_name,
                    "key_item_key": key_item_key,
                    "key_item_name": key_item_name,
                    "key_item_description": key_item_description,
                    "drop_chance_percent": 100,
                    "drop_quantity_min": 1,
                    "drop_quantity_max": 1,
                    "key_item_required_quantity": 1,
                }
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {
                        "objective_json": json.dumps(objective, sort_keys=True),
                        "turnin_json": json.dumps({"type": "key_item"}, sort_keys=True),
                    },
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated key item objective for **{custom_def['name']}**."

            if action == "objective_drops":
                existing = await self.cog._fetch_custom_quest_definition(quest_key, conn=conn)
                objective = (existing or {}).get("objective") or {}
                if str(objective.get("mode") or "").lower() != "key_item":
                    raise ValueError("Set a Key Item Objective first before editing drop rules.")
                try:
                    drop_chance_percent = float(str(values.get("drop_chance_percent") or "100").replace(",", "").strip())
                except ValueError as exc:
                    raise ValueError("Drop chance must be a number between 0 and 100.") from exc
                if drop_chance_percent < 0 or drop_chance_percent > 100:
                    raise ValueError("Drop chance must be between 0 and 100.")
                drop_quantity_min = self._parse_int(values.get("drop_quantity_min") or "1", "Drop minimum", minimum=1)
                drop_quantity_max = self._parse_int(values.get("drop_quantity_max") or "1", "Drop maximum", minimum=1)
                key_item_required_quantity = self._parse_int(
                    values.get("key_item_required_quantity") or "1",
                    "Turn-in quantity",
                    minimum=1,
                )
                if drop_quantity_max < drop_quantity_min:
                    raise ValueError("Drop maximum must be greater than or equal to drop minimum.")
                objective.update(
                    {
                        "drop_chance_percent": drop_chance_percent,
                        "drop_quantity_min": drop_quantity_min,
                        "drop_quantity_max": drop_quantity_max,
                        "key_item_required_quantity": key_item_required_quantity,
                    }
                )
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"objective_json": json.dumps(objective, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated key item drop rules for **{custom_def['name']}**."

            if action == "turnin_progress":
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"turnin_json": json.dumps({"type": "progress"}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Turn-in for **{custom_def['name']}** now uses progress only."

            if action == "turnin_key_item":
                existing = await self.cog._fetch_custom_quest_definition(quest_key, conn=conn)
                objective = (existing or {}).get("objective") or {}
                if str(objective.get("mode") or "").lower() != "key_item":
                    raise ValueError("Set a Key Item Objective first before requiring a key item turn-in.")
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"turnin_json": json.dumps({"type": "key_item"}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Turn-in for **{custom_def['name']}** now requires the quest key item."

            if action == "turnin_crate":
                rarity = self.cog._normalize_crate_rarity(values.get("rarity"))
                if rarity is None:
                    raise ValueError("Unknown crate rarity.")
                amount = self._parse_int(values.get("amount") or "1", "Crate amount", minimum=1)
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"turnin_json": json.dumps({"type": "crate", "rarity": rarity, "amount": amount}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Turn-in for **{custom_def['name']}** now requires crates."

            if action == "turnin_money":
                amount = self._parse_int(values.get("amount") or "1", "Gold amount", minimum=1)
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"turnin_json": json.dumps({"type": "money", "amount": amount}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Turn-in for **{custom_def['name']}** now requires gold."

            if action == "turnin_egg":
                egg_name = str(values.get("egg_name") or "").strip()
                if not egg_name:
                    raise ValueError("Egg name cannot be blank.")
                amount = self._parse_int(values.get("amount") or "1", "Egg amount", minimum=1)
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"turnin_json": json.dumps({"type": "egg", "egg_name": egg_name, "amount": amount}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Turn-in for **{custom_def['name']}** now requires eggs."

            if action == "reward_money":
                amount = self._parse_int(values.get("amount") or "1", "Gold reward", minimum=1)
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"reward_json": json.dumps({"type": "money", "amount": amount}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Reward for **{custom_def['name']}** now grants gold."

            if action == "reward_crate":
                rarity = self.cog._normalize_crate_rarity(values.get("rarity"))
                if rarity is None:
                    raise ValueError("Unknown crate rarity.")
                amount = self._parse_int(values.get("amount") or "1", "Crate amount", minimum=1)
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"reward_json": json.dumps({"type": "crate", "rarity": rarity, "amount": amount}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Reward for **{custom_def['name']}** now grants crates."

            if action == "reward_egg":
                monster_name = str(values.get("monster_name") or "").strip()
                if not monster_name:
                    raise ValueError("Monster name cannot be blank.")
                monster = await self.cog._find_monster_by_name(monster_name)
                if not monster:
                    raise ValueError("Unknown monster name for egg reward.")
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"reward_json": json.dumps({"type": "egg", "monster_name": monster["name"]}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Reward for **{custom_def['name']}** now grants a **{monster['name']} Egg**."

            if action == "reward_item":
                item_type_raw = str(values.get("item_type") or "").strip()
                item_type = next(
                    (
                        item_type
                        for item_type in ItemType
                        if item_type.value.lower() == item_type_raw.lower()
                        or item_type.name.lower() == item_type_raw.lower()
                    ),
                    None,
                )
                if item_type is None:
                    valid_types = ", ".join(item.value for item in ItemType)
                    raise ValueError(f"Unknown item type. Valid types: {valid_types}")
                reward_name = str(values.get("name") or "").strip()
                if not reward_name:
                    raise ValueError("Item reward name cannot be blank.")
                stat = self._parse_int(values.get("stat") or "0", "Stat value", minimum=0)
                value = self._parse_int(values.get("value") or "0", "Gold value", minimum=0)
                element = str(values.get("element") or "Light").strip() or "Light"
                reward = {
                    "type": "item",
                    "name": reward_name,
                    "item_type": item_type.value,
                    "stat": stat,
                    "value": value,
                    "element": element,
                }
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"reward_json": json.dumps(reward, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Reward for **{custom_def['name']}** now grants a custom item."

            if action == "reward_none":
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"reward_json": json.dumps({"type": "none"}, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Reward for **{custom_def['name']}** is now story-only."

            if action == "access":
                gm_only = self.cog._parse_bool(values.get("gm_only"))
                booster_only = self.cog._parse_bool(values.get("booster_only"))
                if gm_only is None or booster_only is None:
                    raise ValueError("GM only and booster only must be `on` or `off`.")
                patreon_raw = str(values.get("patreon_tier") or "").strip()
                patreon_tier = None if not patreon_raw or patreon_raw.lower() == "none" else self.cog._normalize_patreon_tier(patreon_raw)
                if patreon_raw and patreon_raw.lower() != "none" and patreon_tier is None:
                    tiers = ", ".join(sorted(QUEST_PATREON_TIERS))
                    raise ValueError(f"Unknown Patreon tier. Use one of: {tiers}, or `none`.")
                event_flag = self.cog._normalize_event_flag(values.get("event_flag"))
                access_json = {
                    "gm_only": gm_only,
                    "booster_only": booster_only,
                    "patreon_tier": patreon_tier or "",
                    "event_flag": event_flag,
                }
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"access_json": json.dumps(access_json, sort_keys=True)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated access rules for **{custom_def['name']}**."

            if action == "prereq":
                prereq_raw = str(values.get("prerequisites") or "").strip()
                if not prereq_raw or prereq_raw.lower() == "none":
                    prerequisites = []
                else:
                    prerequisites = []
                    for raw_value in [part.strip() for part in prereq_raw.split(",") if part.strip()]:
                        normalized_value = raw_value.lower()
                        if normalized_value not in QUEST_DEFINITIONS:
                            normalized_value = self.cog._normalize_custom_quest_key(raw_value)
                        prerequisites.append(normalized_value)
                    for prereq_key in prerequisites:
                        if prereq_key in QUEST_DEFINITIONS:
                            continue
                        custom = await self.cog._fetch_custom_quest_definition(prereq_key, conn=conn)
                        if not custom:
                            raise ValueError(f"Unknown prerequisite quest: `{prereq_key}`.")
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {"prerequisite_keys_json": json.dumps(prerequisites)},
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                if prerequisites:
                    return f"Updated prerequisites for **{custom_def['name']}**."
                return f"Cleared prerequisites for **{custom_def['name']}**."

            if action == "cutscene":
                accept_raw = str(values.get("accept_cutscene_key") or "").strip()
                turnin_raw = str(values.get("turnin_cutscene_key") or "").strip()
                accept_cutscene_key = "" if not accept_raw or accept_raw.lower() == "none" else self.cog._normalize_custom_quest_key(accept_raw)
                turnin_cutscene_key = "" if not turnin_raw or turnin_raw.lower() == "none" else self.cog._normalize_custom_quest_key(turnin_raw)
                if accept_cutscene_key:
                    row = await self.cog._fetch_cutscene_row(accept_cutscene_key, conn=conn)
                    if not row:
                        raise ValueError("That accept cutscene does not exist.")
                if turnin_cutscene_key:
                    row = await self.cog._fetch_cutscene_row(turnin_cutscene_key, conn=conn)
                    if not row:
                        raise ValueError("That turn-in cutscene does not exist.")
                custom_def = await self.cog._update_custom_quest_fields(
                    quest_key,
                    {
                        "accept_cutscene_key": accept_cutscene_key or None,
                        "turnin_cutscene_key": turnin_cutscene_key or None,
                    },
                    conn=conn,
                    created_by=self.author.id,
                )
                self.selected_quest_key = quest_key
                return f"Updated cutscenes for **{custom_def['name']}**."

        raise ValueError("Unknown builder action.")

    async def create_callback(self, interaction: discord.Interaction):
        fields = [
            {
                "key": "quest_key",
                "label": "Quest Key",
                "placeholder": "fisher_job",
            },
            {
                "key": "category",
                "label": "Category",
                "default": "General",
                "placeholder": "Events",
            },
            {
                "key": "name",
                "label": "Quest Name",
                "placeholder": "The Fisher's Request",
            },
        ]

        async def submit_handler(values: dict[str, str]) -> str:
            quest_key = self.cog._normalize_custom_quest_key(values.get("quest_key"))
            if not quest_key:
                raise ValueError("Quest key must contain letters or numbers.")
            if quest_key in QUEST_DEFINITIONS:
                raise ValueError("That quest key is already used by a built-in quest.")
            category = str(values.get("category") or "").strip() or "General"
            name = str(values.get("name") or "").strip()
            if not name:
                raise ValueError("Quest name cannot be blank.")

            async with self.cog.bot.pool.acquire() as conn:
                existing = await self.cog._fetch_custom_quest_definition(quest_key, conn=conn)
                if existing:
                    raise ValueError("That custom quest key already exists.")
                await conn.execute(
                    """
                    INSERT INTO custom_quests (
                        quest_key, name, category, short_description, offer_text, turnin_text, objective_json,
                        turnin_json, reward_json, access_json, prerequisite_keys_json,
                        accept_cutscene_key, turnin_cutscene_key, repeatable, is_active, created_by, updated_at
                    )
                    VALUES ($1, $2, $3, '', '', '', '{}', '{}', '{}', '{}', '[]', NULL, NULL, FALSE, FALSE, $4, NOW())
                    """,
                    quest_key,
                    name,
                    category,
                    self.author.id,
                )
            self.selected_quest_key = quest_key
            self.selected_action = "text"
            return f"Created **{name}**."

        modal = GMQuestBuilderFormModal(
            self,
            title="Create Quest",
            fields=fields,
            submit_handler=submit_handler,
        )
        await interaction.response.send_modal(modal)

    async def edit_callback(self, interaction: discord.Interaction):
        try:
            selected = self._selected_or_error()
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)

        action = self.selected_action
        fields = self._fields_for_action(selected, action)
        if fields is None:
            try:
                response_text = await self._apply_action(selected["quest_key"], action, {})
            except ValueError as exc:
                return await interaction.response.send_message(str(exc), ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            await self.refresh_message()
            await interaction.followup.send(response_text, ephemeral=True)
            return

        modal = GMQuestBuilderFormModal(
            self,
            title=self._action_label(action),
            fields=fields,
            submit_handler=lambda values: self._apply_action(selected["quest_key"], action, values),
        )
        await interaction.response.send_modal(modal)

    async def active_callback(self, interaction: discord.Interaction):
        try:
            selected = self._selected_or_error()
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)

        async with self.cog.bot.pool.acquire() as conn:
            custom_def = await self.cog._update_custom_quest_fields(
                selected["quest_key"],
                {"is_active": not selected["is_active"]},
                conn=conn,
                created_by=self.author.id,
            )
        self.selected_quest_key = selected["quest_key"]
        await interaction.response.defer(ephemeral=True)
        await self.refresh_message()
        status = "active" if custom_def["is_active"] else "draft"
        await interaction.followup.send(f"**{custom_def['name']}** is now **{status}**.", ephemeral=True)

    async def repeatable_callback(self, interaction: discord.Interaction):
        try:
            selected = self._selected_or_error()
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)

        async with self.cog.bot.pool.acquire() as conn:
            custom_def = await self.cog._update_custom_quest_fields(
                selected["quest_key"],
                {"repeatable": not selected["repeatable"]},
                conn=conn,
                created_by=self.author.id,
            )
        self.selected_quest_key = selected["quest_key"]
        await interaction.response.defer(ephemeral=True)
        await self.refresh_message()
        label = "repeatable" if custom_def["repeatable"] else "one-time"
        await interaction.followup.send(f"**{custom_def['name']}** is now **{label}**.", ephemeral=True)

    async def preview_accept_callback(self, interaction: discord.Interaction):
        try:
            selected = self._selected_or_error()
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)
        cutscene_key = str(selected.get("accept_cutscene_key") or "").strip()
        if not cutscene_key:
            return await interaction.response.send_message("This quest has no accept cutscene attached.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(f"Previewing `{cutscene_key}` in this channel.", ephemeral=True)
        await self.cog.play_cutscene(self.ctx, cutscene_key, mark_seen=False)

    async def preview_turnin_callback(self, interaction: discord.Interaction):
        try:
            selected = self._selected_or_error()
        except ValueError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)
        cutscene_key = str(selected.get("turnin_cutscene_key") or "").strip()
        if not cutscene_key:
            return await interaction.response.send_message("This quest has no turn-in cutscene attached.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(f"Previewing `{cutscene_key}` in this channel.", ephemeral=True)
        await self.cog.play_cutscene(self.ctx, cutscene_key, mark_seen=False)

    async def refresh_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.refresh_message()
        await interaction.followup.send("Quest builder refreshed.", ephemeral=True)


class CampaignActionView(View):
    """Clickable campaign decisions that remain bound to their original prompt."""

    def __init__(
        self,
        *,
        cog,
        ctx,
        run_id: str,
        campaign_key: str,
        node_key: str,
        options: list[dict],
        action_kind: str,
        stage_key: str = "",
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.ctx = ctx
        self.owner_id = ctx.author.id
        self.run_id = run_id
        self.campaign_key = campaign_key
        self.node_key = node_key
        self.stage_key = stage_key
        self.action_kind = action_kind
        self.message = None

        for index, option in enumerate(options[:MAX_PROMPT_OPTIONS], start=1):
            fallback = "Act" if action_kind == "act" else "Continue"
            label = f"{index}. {option.get('label') or fallback}"[:80]
            button = Button(
                label=label,
                style=(
                    discord.ButtonStyle.secondary
                    if action_kind == "act"
                    else discord.ButtonStyle.primary
                ),
                row=(index - 1) // 5,
            )

            async def callback(interaction, selected=index):
                await self._select(interaction, selected)

            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "This story prompt belongs to another player.",
            ephemeral=True,
        )
        return False

    async def _select(self, interaction: discord.Interaction, option: int) -> None:
        is_current = await self.cog._campaign_prompt_matches(
            self.owner_id,
            run_id=self.run_id,
            campaign_key=self.campaign_key,
            node_key=self.node_key,
            action_kind=self.action_kind,
            stage_key=self.stage_key,
        )
        if not is_current:
            await interaction.response.send_message(
                "That story prompt has expired. Use `$campaign` to open the current one.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
        self.stop()

        if self.action_kind == "act":
            await self.cog._resolve_campaign_act(
                self.ctx,
                option,
                expected_prompt=(
                    self.run_id,
                    self.campaign_key,
                    self.node_key,
                    self.stage_key,
                ),
            )
        else:
            await self.cog._resolve_campaign_choice(
                self.ctx,
                option,
                expected_prompt=(self.run_id, self.campaign_key, self.node_key),
            )

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Quests(commands.Cog):
    GREG_INTRO_CUTSCENE_KEY = "greg_intro_lore"

    def __init__(self, bot):
        self.bot = bot
        self._monster_cache = None
        self.fable_state = FableStateService()

    async def cog_load(self):
        await self._init_tables()
        await self.install_builtin_campaign_packages()

    async def _init_tables(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_quests (
                    user_id BIGINT NOT NULL,
                    quest_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    step_index INTEGER NOT NULL DEFAULT 0,
                    completion_count INTEGER NOT NULL DEFAULT 0,
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    turned_in_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id, quest_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_key_items (
                    user_id BIGINT NOT NULL,
                    item_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    source_quest TEXT,
                    obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            await conn.execute(
                """
                ALTER TABLE player_quests
                ADD COLUMN IF NOT EXISTS completion_count INTEGER NOT NULL DEFAULT 0
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_quests (
                    quest_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    short_description TEXT NOT NULL DEFAULT '',
                    offer_text TEXT NOT NULL DEFAULT '',
                    turnin_text TEXT NOT NULL DEFAULT '',
                    objective_json TEXT NOT NULL DEFAULT '{}',
                    turnin_json TEXT NOT NULL DEFAULT '{}',
                    reward_json TEXT NOT NULL DEFAULT '{}',
                    access_json TEXT NOT NULL DEFAULT '{}',
                    prerequisite_keys_json TEXT NOT NULL DEFAULT '[]',
                    accept_cutscene_key TEXT,
                    turnin_cutscene_key TEXT,
                    repeatable BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    created_by BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                ALTER TABLE custom_quests
                ADD COLUMN IF NOT EXISTS turnin_text TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quest_cutscenes (
                    cutscene_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    pages_json TEXT NOT NULL DEFAULT '[]',
                    created_by BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_cutscenes (
                    user_id BIGINT NOT NULL,
                    cutscene_key TEXT NOT NULL,
                    view_count INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, cutscene_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_content (
                    campaign_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    start_node_key TEXT NOT NULL,
                    campaign_json TEXT NOT NULL,
                    package_key TEXT NOT NULL DEFAULT '',
                    content_version INTEGER NOT NULL DEFAULT 1,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    created_by BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_campaigns (
                    user_id BIGINT NOT NULL,
                    campaign_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_node_key TEXT NOT NULL,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    choices_json TEXT NOT NULL DEFAULT '{}',
                    unlocks_json TEXT NOT NULL DEFAULT '[]',
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id, campaign_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_system_unlocks (
                    user_id BIGINT NOT NULL,
                    unlock_key TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'system',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, unlock_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quest_objective_events (
                    user_id BIGINT NOT NULL,
                    source TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, source, event_id)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_builtin_packages (
                    package_key TEXT PRIMARY KEY,
                    content_version INTEGER NOT NULL CHECK (content_version >= 1),
                    source_file TEXT NOT NULL,
                    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_reputation (
                    user_id BIGINT NOT NULL,
                    reputation_key TEXT NOT NULL,
                    points INTEGER NOT NULL DEFAULT 0,
                    rank INTEGER NOT NULL DEFAULT 0,
                    tier_key TEXT NOT NULL DEFAULT 'neutral',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, reputation_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_monsters (
                    monster_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    tier INTEGER NOT NULL DEFAULT 1,
                    hp INTEGER NOT NULL,
                    attack INTEGER NOT NULL,
                    defense INTEGER NOT NULL,
                    element TEXT NOT NULL DEFAULT 'Nature',
                    url TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await self._migrate_campaign_tables(conn)
            await self.fable_state.initialize(conn)
            await self._seed_default_cutscenes(conn)
            await self._attach_default_greg_finale_cutscene(conn)
            await self._remove_legacy_greg_quest_data(conn)

    async def _migrate_campaign_tables(self, conn):
        """Bring existing campaign tables up to the schema expected by this cog."""
        migrations = (
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS start_node_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS campaign_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS package_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS content_version INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS created_by BIGINT",
            "ALTER TABLE campaign_content ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS current_node_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS history_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS choices_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS unlocks_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE player_campaigns ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
            "ALTER TABLE player_reputation ADD COLUMN IF NOT EXISTS points INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE player_reputation ADD COLUMN IF NOT EXISTS rank INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE player_reputation ADD COLUMN IF NOT EXISTS tier_key TEXT NOT NULL DEFAULT 'neutral'",
            "ALTER TABLE player_reputation ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS tier INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS hp INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS attack INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS defense INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS element TEXT NOT NULL DEFAULT 'Nature'",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS url TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS tags_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE content_monsters ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        )
        for statement in migrations:
            await conn.execute(statement)

        indexes = (
            "CREATE INDEX IF NOT EXISTS campaign_content_active_idx ON campaign_content (is_active, title)",
            "CREATE INDEX IF NOT EXISTS player_campaigns_user_status_idx ON player_campaigns (user_id, status, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS player_reputation_user_rank_idx ON player_reputation (user_id, rank DESC, points DESC)",
            "CREATE INDEX IF NOT EXISTS content_monsters_tier_name_idx ON content_monsters (tier, name)",
            "CREATE INDEX IF NOT EXISTS player_quests_user_status_idx ON player_quests (user_id, status)",
            "CREATE INDEX IF NOT EXISTS custom_quests_active_category_idx ON custom_quests (is_active, category, quest_key)",
            "CREATE INDEX IF NOT EXISTS player_system_unlocks_user_idx ON player_system_unlocks (user_id, unlocked_at)",
            "CREATE INDEX IF NOT EXISTS quest_objective_events_user_idx ON quest_objective_events (user_id, occurred_at DESC)",
        )
        for statement in indexes:
            await conn.execute(statement)

    async def _seed_default_cutscenes(self, conn):
        for cutscene_key, definition in DEFAULT_CUTSCENE_DEFINITIONS.items():
            await conn.execute(
                """
                INSERT INTO quest_cutscenes (cutscene_key, title, pages_json, created_by, updated_at)
                VALUES ($1, $2, $3, 0, NOW())
                ON CONFLICT (cutscene_key) DO NOTHING
                """,
                cutscene_key,
                definition["title"],
                json.dumps(list(definition["pages"])),
            )

    async def _attach_default_greg_finale_cutscene(self, conn):
        await conn.execute(
            """
            UPDATE custom_quests
            SET turnin_cutscene_key = 'greg_epilogue',
                updated_at = NOW()
            WHERE quest_key = 'greg_finale'
              AND COALESCE(turnin_cutscene_key, '') = ''
            """
        )

    async def _remove_legacy_greg_quest_data(self, conn):
        await conn.execute(
            """
            DELETE FROM player_key_items
            WHERE source_quest = 'gregapocalypse'
            """
        )
        await conn.execute(
            """
            DELETE FROM player_quests
            WHERE quest_key = 'gregapocalypse'
            """
        )

    def _greg_mode_enabled(self) -> bool:
        flags = getattr(self.bot, "april_fools_flags", {}) or {}
        return bool(flags.get(APRIL_FOOLS_GREG_FLAG, False))

    def _skulls_for_pve(self, levelchoice: int) -> int:
        if levelchoice >= 11:
            return 3
        if levelchoice >= 8:
            return 2
        return 1

    def _quest_available(self, quest_key: str) -> bool:
        if str(quest_key or "").strip().lower() == GREG_QUEST.key:
            return self._greg_mode_enabled()
        return True

    def _load_progress(self, raw_value) -> dict:
        if isinstance(raw_value, dict):
            return dict(raw_value)
        if not raw_value:
            return {}
        try:
            return json.loads(str(raw_value))
        except Exception:
            return {}

    def _dump_progress(self, progress: dict) -> str:
        return json.dumps(progress, sort_keys=True)

    def _normalize_custom_quest_key(self, raw: str) -> str:
        cleaned = "".join(
            char.lower() if char.isalnum() else "_"
            for char in str(raw or "").strip()
        )
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_")

    def _split_pipe_args(self, raw: str, min_parts: int, max_parts: int | None = None) -> list[str]:
        parts = [part.strip() for part in str(raw or "").split("|")]
        if max_parts is not None and len(parts) > max_parts:
            raise ValueError(f"Expected at most {max_parts} pipe-separated values.")
        if len(parts) < min_parts:
            raise ValueError(f"Expected at least {min_parts} pipe-separated values.")
        if any(not part for part in parts[:min_parts]):
            raise ValueError("Required fields cannot be blank.")
        return parts

    def _normalize_crate_rarity(self, raw: str) -> str | None:
        rarity = str(raw or "").strip().lower()
        return rarity if rarity in QUEST_CRATE_RARITIES else None

    def _normalize_source(self, raw: str) -> str | None:
        source = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
        source = " ".join(source.split())
        if not source:
            return None
        canonical = CUSTOM_QUEST_SOURCE_ALIASES.get(source)
        if canonical:
            return canonical
        compact = source.replace(" ", "")
        return compact if compact in CUSTOM_QUEST_SOURCES else None

    def _source_label(self, raw: str | None) -> str:
        source = self._normalize_source(raw)
        if source:
            return CUSTOM_QUEST_SOURCE_LABELS.get(source, source.title())
        return str(raw or "Quest").title()

    def _normalize_mode(self, raw: str) -> str | None:
        mode = str(raw or "").strip().lower()
        return mode if mode in CUSTOM_QUEST_MODES else None

    def _normalize_patreon_tier(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        tier = str(raw).strip().lower()
        return tier if tier in QUEST_PATREON_TIERS else None

    def _normalize_event_flag(self, raw: str | None) -> str:
        value = str(raw or "").strip().lower()
        if not value or value == "none":
            return ""
        return value

    def _event_flag_enabled(self, raw: str | None) -> bool:
        flag_value = self._normalize_event_flag(raw)
        if not flag_value:
            return True

        if flag_value.startswith("april:"):
            flag_key = flag_value.split(":", 1)[1]
            flags = getattr(self.bot, "april_fools_flags", {}) or {}
            return bool(flags.get(flag_key, False))

        if flag_value.startswith("event:"):
            flag_key = flag_value.split(":", 1)[1]
            flags = getattr(self.bot, "event_flags", {}) or {}
            return bool(flags.get(flag_key, False))

        april_flags = getattr(self.bot, "april_fools_flags", {}) or {}
        if flag_value in april_flags:
            return bool(april_flags.get(flag_value, False))

        event_flags = getattr(self.bot, "event_flags", {}) or {}
        if flag_value in event_flags:
            return bool(event_flags.get(flag_value, False))

        return False

    def _event_flag_label(self, raw: str | None) -> str:
        value = self._normalize_event_flag(raw)
        return value or "none"

    def _match_name_filter(self, target_name: str | None, *candidates: str | None) -> bool:
        target = str(target_name or "").strip().lower()
        if not target:
            return True
        normalized_candidates = [
            str(candidate).strip().lower()
            for candidate in candidates
            if str(candidate or "").strip()
        ]
        return any(target in candidate for candidate in normalized_candidates)

    async def _fetch_cutscene_row(self, cutscene_key: str, *, conn=None):
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            return await conn.fetchrow(
                """
                SELECT cutscene_key, title, pages_json, created_by, updated_at
                FROM quest_cutscenes
                WHERE cutscene_key = $1
                """,
                cutscene_key,
            )
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _get_cutscene_pages(self, cutscene_key: str, *, conn=None) -> list[dict]:
        row = await self._fetch_cutscene_row(cutscene_key, conn=conn)
        if not row:
            return []
        pages = self._load_progress(row["pages_json"])
        return pages if isinstance(pages, list) else []

    async def _mark_cutscene_seen(self, user_id: int, cutscene_key: str, *, conn=None) -> None:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            await conn.execute(
                """
                INSERT INTO player_cutscenes (
                    user_id,
                    cutscene_key,
                    view_count,
                    first_seen_at,
                    last_seen_at
                )
                VALUES ($1, $2, 1, NOW(), NOW())
                ON CONFLICT (user_id, cutscene_key)
                DO UPDATE SET view_count = player_cutscenes.view_count + 1,
                              last_seen_at = NOW()
                """,
                user_id,
                cutscene_key,
            )
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def has_seen_cutscene(self, user_id: int, cutscene_key: str, *, conn=None) -> bool:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            seen = await conn.fetchval(
                """
                SELECT 1
                FROM player_cutscenes
                WHERE user_id = $1 AND cutscene_key = $2
                """,
                user_id,
                cutscene_key,
            )
            return bool(seen)
        finally:
            if local:
                await self.bot.pool.release(conn)

    def _requires_greg_intro_cutscene(self, quest_key: str | None) -> bool:
        normalized = str(quest_key or "").strip().lower()
        return normalized == GREG_QUEST.key or normalized.startswith("greg_")

    async def _ensure_greg_intro_seen(self, user_id: int, *, conn=None) -> tuple[bool, str | None]:
        if await self.has_seen_cutscene(user_id, self.GREG_INTRO_CUTSCENE_KEY, conn=conn):
            return True, None
        return False, "Watch the Gregapocalypse intro with `$greg` before taking Greg quests."

    async def play_cutscene(
        self,
        ctx,
        cutscene_key: str,
        *,
        mark_seen: bool = True,
        wait_for_completion: bool = False,
    ) -> bool:
        row = await self._fetch_cutscene_row(cutscene_key)
        if not row:
            return False
        pages_data = self._load_progress(row["pages_json"])
        if not isinstance(pages_data, list) or not pages_data:
            return False
        pages = self._create_cutscene_pages(
            pages_data,
            str(row["title"] or "Quest Scene"),
            ctx,
        )
        view = QuestPageView(pages, ctx.author.id)
        view.message = await ctx.send(embed=pages[0], view=view)
        if wait_for_completion:
            await view.wait()
            if not view.completed:
                return False
        if mark_seen:
            await self._mark_cutscene_seen(ctx.author.id, cutscene_key)
        return True

    async def _get_monster_catalog(self) -> list[dict]:
        if self._monster_cache is not None:
            return self._monster_cache
        catalog = []
        try:
            with MONSTERS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            data = {}

        for monsters in data.values():
            if not isinstance(monsters, list):
                continue
            for monster in monsters:
                if isinstance(monster, dict) and monster.get("name"):
                    catalog.append(dict(monster))

        try:
            rows = await self.bot.pool.fetch(
                """
                SELECT monster_key, name, tier, hp, attack, defense, element, url, tags_json
                FROM content_monsters
                ORDER BY tier, name
                """
            )
        except Exception:
            rows = []
        known_names = {str(monster.get("name") or "").casefold() for monster in catalog}
        for row in rows:
            if str(row["name"]).casefold() in known_names:
                continue
            catalog.append(
                {
                    "key": row["monster_key"],
                    "name": row["name"],
                    "tier": row["tier"],
                    "hp": row["hp"],
                    "attack": row["attack"],
                    "defense": row["defense"],
                    "element": row["element"],
                    "url": row["url"],
                    "tags": self._load_progress(row["tags_json"]),
                }
            )
        self._monster_cache = catalog
        return catalog

    async def _find_monster_by_name(self, monster_name: str) -> dict | None:
        target = str(monster_name or "").strip().lower()
        if not target:
            return None
        for monster in await self._get_monster_catalog():
            if str(monster.get("name", "")).strip().lower() == target:
                return monster
        return None

    def _campaign_cutscene_payload(self, campaign: dict, node: dict, slot: str) -> tuple[str, dict] | None:
        payload = (node.get("cutscenes") or {}).get(slot)
        if not isinstance(payload, dict):
            return None
        presentation = str(
            payload.get("presentation") or payload.get("type") or "cutscene"
        ).strip().lower()
        if presentation == "dialogue":
            entries = payload.get("lines") or payload.get("pages") or []
        else:
            entries = payload.get("pages") or payload.get("lines") or []
        if not isinstance(entries, list) or not entries:
            return None
        pages = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            page = dict(entry)
            if presentation == "dialogue" or page.get("speaker"):
                page["presentation"] = "dialogue"
            pages.append(page)
        if not pages:
            return None
        key = normalize_campaign_key(
            payload.get("key") or f"{campaign['key']}_{node['id']}_{slot}"
        )
        return key, {
            "title": str(payload.get("title") or node.get("title") or "Campaign Scene"),
            "pages": pages,
        }

    async def _import_standalone_quest(self, conn, quest: dict, created_by: int) -> None:
        quest_key = normalize_campaign_key(quest.get("quest_key"))
        if not quest_key:
            return
        await conn.execute(
            """
            INSERT INTO custom_quests (
                quest_key, name, category, short_description, offer_text, turnin_text,
                objective_json, turnin_json, reward_json, access_json,
                prerequisite_keys_json, accept_cutscene_key, turnin_cutscene_key,
                repeatable, is_active, created_by, updated_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,NOW())
            ON CONFLICT (quest_key) DO UPDATE SET
                name=EXCLUDED.name, category=EXCLUDED.category,
                short_description=EXCLUDED.short_description, offer_text=EXCLUDED.offer_text,
                turnin_text=EXCLUDED.turnin_text, objective_json=EXCLUDED.objective_json,
                turnin_json=EXCLUDED.turnin_json, reward_json=EXCLUDED.reward_json,
                access_json=EXCLUDED.access_json,
                prerequisite_keys_json=EXCLUDED.prerequisite_keys_json,
                accept_cutscene_key=EXCLUDED.accept_cutscene_key,
                turnin_cutscene_key=EXCLUDED.turnin_cutscene_key,
                repeatable=EXCLUDED.repeatable, is_active=EXCLUDED.is_active,
                created_by=EXCLUDED.created_by, updated_at=NOW()
            """,
            quest_key,
            str(quest.get("name") or quest_key.replace("_", " ").title()),
            str(quest.get("category") or "General"),
            str(quest.get("short_description") or ""),
            str(quest.get("offer_text") or ""),
            str(quest.get("turnin_text") or ""),
            json.dumps(quest.get("objective") or {}, sort_keys=True),
            json.dumps(quest.get("turnin") or {}, sort_keys=True),
            json.dumps(quest.get("reward") or {"type": "none"}, sort_keys=True),
            json.dumps(quest.get("access") or {}, sort_keys=True),
            json.dumps(quest.get("prerequisites") or []),
            normalize_campaign_key(quest.get("accept_cutscene_key")) or None,
            normalize_campaign_key(quest.get("turnin_cutscene_key")) or None,
            bool(quest.get("repeatable", False)),
            bool(quest.get("is_active", False)),
            created_by,
        )

    async def _import_campaign_package(self, package: dict, *, created_by: int, conn=None) -> dict:
        package = validate_package(package)
        package_key = normalize_campaign_key(package.get("package_key"))
        try:
            content_version = max(1, int(package.get("content_version") or 1))
        except (TypeError, ValueError) as exc:
            raise CampaignPackageError(
                ["content_version must be a positive integer when provided."]
            ) from exc
        quest_count = 0
        cutscene_count = 0
        owns_connection = conn is None
        connection_context = self.bot.pool.acquire() if owns_connection else _AsyncContextValue(conn)
        async with connection_context as conn:
            transaction_context = conn.transaction() if owns_connection else _AsyncContextValue()
            async with transaction_context:
                for cutscene in package.get("cutscenes") or []:
                    if not isinstance(cutscene, dict):
                        continue
                    cutscene_key = normalize_campaign_key(cutscene.get("key"))
                    pages = cutscene.get("pages") or []
                    if not cutscene_key or not isinstance(pages, list):
                        continue
                    await conn.execute(
                        """
                        INSERT INTO quest_cutscenes (cutscene_key, title, pages_json, created_by, updated_at)
                        VALUES ($1,$2,$3,$4,NOW())
                        ON CONFLICT (cutscene_key) DO UPDATE SET
                            title=EXCLUDED.title, pages_json=EXCLUDED.pages_json,
                            created_by=EXCLUDED.created_by, updated_at=NOW()
                        """,
                        cutscene_key,
                        str(cutscene.get("title") or "Quest Scene"),
                        json.dumps(pages),
                        created_by,
                    )
                    cutscene_count += 1

                for monster in package.get("monsters") or []:
                    await conn.execute(
                        """
                        INSERT INTO content_monsters (
                            monster_key, name, tier, hp, attack, defense, element, url, tags_json, updated_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (monster_key) DO UPDATE SET
                            name=EXCLUDED.name, tier=EXCLUDED.tier, hp=EXCLUDED.hp,
                            attack=EXCLUDED.attack, defense=EXCLUDED.defense,
                            element=EXCLUDED.element, url=EXCLUDED.url,
                            tags_json=EXCLUDED.tags_json, updated_at=NOW()
                        """,
                        monster["key"],
                        monster["name"],
                        monster["tier"],
                        monster["hp"],
                        monster["attack"],
                        monster["defense"],
                        monster["element"],
                        monster["url"],
                        json.dumps(monster.get("tags") or []),
                    )

                for quest in package.get("standalone_quests") or []:
                    if isinstance(quest, dict):
                        await self._import_standalone_quest(conn, quest, created_by)
                        quest_count += 1

                for campaign in package.get("campaigns") or []:
                    installed_version = await conn.fetchval(
                        "SELECT content_version FROM campaign_content WHERE campaign_key=$1",
                        campaign["key"],
                    )
                    if installed_version is not None and content_version < int(installed_version):
                        raise CampaignPackageError(
                            [
                                f"Campaign `{campaign['key']}` is version {installed_version}; "
                                f"refusing to replace it with older version {content_version}."
                            ]
                        )
                    await conn.execute(
                        """
                        INSERT INTO campaign_content (
                            campaign_key, title, description, start_node_key,
                            campaign_json, package_key, content_version,
                            is_active, created_by, updated_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                        ON CONFLICT (campaign_key) DO UPDATE SET
                            title=EXCLUDED.title, description=EXCLUDED.description,
                            start_node_key=EXCLUDED.start_node_key,
                            campaign_json=EXCLUDED.campaign_json,
                            package_key=EXCLUDED.package_key,
                            content_version=EXCLUDED.content_version,
                            is_active=EXCLUDED.is_active, created_by=EXCLUDED.created_by,
                            updated_at=NOW()
                        """,
                        campaign["key"],
                        campaign["title"],
                        campaign["description"],
                        campaign["start_node"],
                        json.dumps(campaign, sort_keys=True),
                        package_key,
                        content_version,
                        campaign["is_active"],
                        created_by,
                    )
                    for node in campaign.get("nodes") or []:
                        imported_node_cutscenes = {}
                        for slot in (node.get("cutscenes") or {}):
                            cutscene = self._campaign_cutscene_payload(campaign, node, slot)
                            if not cutscene:
                                continue
                            cutscene_key, definition = cutscene
                            await conn.execute(
                                """
                                INSERT INTO quest_cutscenes (cutscene_key, title, pages_json, created_by, updated_at)
                                VALUES ($1,$2,$3,$4,NOW())
                                ON CONFLICT (cutscene_key) DO UPDATE SET
                                    title=EXCLUDED.title, pages_json=EXCLUDED.pages_json,
                                    created_by=EXCLUDED.created_by, updated_at=NOW()
                                """,
                                cutscene_key,
                                definition["title"],
                                json.dumps(definition["pages"]),
                                created_by,
                            )
                            cutscene_count += 1
                            imported_node_cutscenes[slot] = cutscene_key
                        if node.get("type") != "quest":
                            continue
                        record = quest_record_from_node(campaign, node)
                        accept_cutscene = imported_node_cutscenes.get("accept")
                        turnin_cutscene = imported_node_cutscenes.get("turnin")
                        record["accept_cutscene_key"] = accept_cutscene or ""
                        record["turnin_cutscene_key"] = turnin_cutscene or ""
                        await self._import_standalone_quest(conn, record, created_by)
                        quest_count += 1
        self._monster_cache = None
        return {
            "campaigns": len(package.get("campaigns") or []),
            "quests": quest_count,
            "cutscenes": cutscene_count,
            "monsters": len(package.get("monsters") or []),
        }

    async def install_builtin_campaign_packages(self) -> list[dict]:
        """Install or monotonically upgrade checked-in campaign packages."""
        if not BUILTIN_CAMPAIGN_DIR.is_dir():
            return []
        results = []
        for source_path in sorted(BUILTIN_CAMPAIGN_DIR.glob("*.json")):
            try:
                with source_path.open("r", encoding="utf-8") as package_file:
                    package = validate_builtin_package(json.load(package_file))
            except (OSError, json.JSONDecodeError, CampaignPackageError) as exc:
                logger.error("Invalid builtin campaign package %s: %s", source_path, exc)
                continue

            package_key = package["package_key"]
            bundled_version = int(package["content_version"])
            campaign_keys = [
                campaign["key"]
                for campaign in package.get("campaigns") or []
                if isinstance(campaign, dict) and campaign.get("key")
            ]
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    installed_version = await conn.fetchval(
                        """
                        SELECT content_version
                        FROM campaign_builtin_packages
                        WHERE package_key=$1
                        FOR UPDATE
                        """,
                        package_key,
                    )
                    unmanaged_conflict = False
                    if installed_version is None and campaign_keys:
                        unmanaged_conflict = bool(
                            await conn.fetchval(
                                """
                                SELECT 1
                                FROM campaign_content
                                WHERE campaign_key = ANY($1::text[])
                                  AND COALESCE(package_key, '') <> $2
                                LIMIT 1
                                """,
                                campaign_keys,
                                package_key,
                            )
                        )
                    decision = builtin_install_decision(
                        int(installed_version) if installed_version is not None else None,
                        bundled_version,
                        has_unmanaged_conflicts=unmanaged_conflict,
                    )
                    if decision in {"skip", "conflict"}:
                        results.append(
                            {
                                "package_key": package_key,
                                "content_version": bundled_version,
                                "decision": decision,
                            }
                        )
                        if decision == "conflict":
                            logger.error(
                                "Builtin campaign package %s conflicts with unmanaged campaign content",
                                package_key,
                            )
                        continue

                    summary = await self._import_campaign_package(
                        package,
                        created_by=0,
                        conn=conn,
                    )
                    await conn.execute(
                        """
                        INSERT INTO campaign_builtin_packages (
                            package_key, content_version, source_file,
                            installed_at, updated_at
                        ) VALUES ($1,$2,$3,NOW(),NOW())
                        ON CONFLICT (package_key) DO UPDATE SET
                            content_version=EXCLUDED.content_version,
                            source_file=EXCLUDED.source_file,
                            updated_at=NOW()
                        """,
                        package_key,
                        bundled_version,
                        source_path.name,
                    )
                    results.append(
                        {
                            "package_key": package_key,
                            "content_version": bundled_version,
                            "decision": decision,
                            **summary,
                        }
                    )
        if results:
            logger.info("Builtin Fable packages: %s", results)
        return results

    async def _build_campaign_export_package(self) -> dict:
        campaigns = []
        package_keys = set()
        content_versions = []
        rows = await self.bot.pool.fetch(
            """
            SELECT campaign_json, package_key, content_version
            FROM campaign_content ORDER BY campaign_key
            """
        )
        for row in rows:
            campaign = self._load_progress(row["campaign_json"])
            if isinstance(campaign, dict):
                campaigns.append(campaign)
            if str(row["package_key"] or "").strip():
                package_keys.add(str(row["package_key"]))
            content_versions.append(int(row["content_version"] or 1))

        campaign_quest_keys = {
            quest_record_from_node(campaign, node)["quest_key"]
            for campaign in campaigns
            for node in campaign.get("nodes") or []
            if node.get("type") == "quest"
        }
        standalone_quests = []
        for custom_def in await self._fetch_custom_quest_definitions(active_only=False):
            if custom_def["quest_key"] in campaign_quest_keys:
                continue
            standalone_quests.append(custom_def)

        cutscenes = []
        for row in await self.bot.pool.fetch(
            "SELECT cutscene_key, title, pages_json FROM quest_cutscenes ORDER BY cutscene_key"
        ):
            cutscenes.append(
                {
                    "key": row["cutscene_key"],
                    "title": row["title"],
                    "pages": self._load_progress(row["pages_json"]),
                }
            )

        monsters = []
        seen_names = set()
        try:
            with MONSTERS_PATH.open("r", encoding="utf-8") as monster_file:
                file_monsters = json.load(monster_file)
        except OSError:
            file_monsters = {}
        for tier, entries in file_monsters.items():
            for monster in entries if isinstance(entries, list) else []:
                if not isinstance(monster, dict) or not monster.get("name"):
                    continue
                payload = dict(monster)
                payload["key"] = normalize_campaign_key(payload.get("key") or payload["name"])
                payload["tier"] = int(tier)
                payload.setdefault("tags", [])
                monsters.append(payload)
                seen_names.add(str(payload["name"]).casefold())
        for row in await self.bot.pool.fetch(
            "SELECT monster_key, name, tier, hp, attack, defense, element, url, tags_json FROM content_monsters ORDER BY tier, name"
        ):
            if str(row["name"]).casefold() in seen_names:
                continue
            monsters.append(
                {
                    "key": row["monster_key"], "name": row["name"], "tier": row["tier"],
                    "hp": row["hp"], "attack": row["attack"], "defense": row["defense"],
                    "element": row["element"], "url": row["url"],
                    "tags": self._load_progress(row["tags_json"]),
                }
            )

        exported = {
            "schema": "fablereborn.campaign-package",
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "campaigns": campaigns,
            "standalone_quests": standalone_quests,
            "cutscenes": cutscenes,
            "monsters": monsters,
            "reference": build_reference_catalog(monsters),
        }
        if len(package_keys) == 1:
            exported["package_key"] = next(iter(package_keys))
            if content_versions:
                exported["content_version"] = max(content_versions)
        return exported

    async def _fetch_campaign_definition(
        self,
        campaign_key: str,
        *,
        user_id: int | None = None,
        conn=None,
    ) -> dict | None:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            normalized_key = normalize_campaign_key(campaign_key)
            if user_id is not None:
                run = await self._selected_campaign_run(
                    conn,
                    user_id,
                    campaign_key=normalized_key,
                )
                raw = run["campaign_json_snapshot"] if run else None
            else:
                raw = None
            if not raw or str(raw).strip() == "{}":
                raw = await conn.fetchval(
                    "SELECT campaign_json FROM campaign_content WHERE campaign_key=$1",
                    normalized_key,
                )
            campaign = self._load_progress(raw)
            return campaign if isinstance(campaign, dict) and campaign else None
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _selected_campaign_run(
        self,
        conn,
        user_id: int,
        *,
        campaign_key: str = "",
        statuses: list[str] | tuple[str, ...] | None = None,
        for_update: bool = False,
    ):
        """Return the focused run, falling back to the canonical run."""
        normalized_key = normalize_campaign_key(campaign_key)
        clauses = ["fcr.user_id=$1"]
        arguments: list[object] = [user_id]
        if normalized_key:
            arguments.append(normalized_key)
            clauses.append(f"fcr.campaign_key=${len(arguments)}")
        if statuses:
            arguments.append(list(statuses))
            clauses.append(f"fcr.status=ANY(${len(arguments)}::text[])")
        lock = " FOR UPDATE OF fcr" if for_update else ""
        return await conn.fetchrow(
            f"""
            SELECT fcr.*
            FROM fable_campaign_runs fcr
            LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY (fcr.run_id=fp.selected_run_id) DESC,
                     fcr.is_canonical DESC, fcr.updated_at DESC
            LIMIT 1{lock}
            """,
            *arguments,
        )

    def _campaign_quest_key(self, campaign: dict, node: dict) -> str:
        return quest_record_from_node(campaign, node)["quest_key"]

    async def grant_system_unlock(
        self,
        user_id: int,
        unlock_key: object,
        *,
        source: str = "system",
        metadata: dict | None = None,
        conn=None,
    ) -> bool:
        """Grant a durable cross-system unlock and report whether it was new."""
        key = normalize_system_unlock_key(unlock_key)
        if not key:
            raise ValueError("System unlocks need a valid key.")
        owns_connection = conn is None
        connection_context = self.bot.pool.acquire() if owns_connection else _AsyncContextValue(conn)
        async with connection_context as connection:
            inserted = await connection.fetchval(
                """
                INSERT INTO player_system_unlocks (
                    user_id, unlock_key, source, metadata_json, unlocked_at
                ) VALUES ($1,$2,$3,$4,NOW())
                ON CONFLICT (user_id, unlock_key) DO NOTHING
                RETURNING unlock_key
                """,
                user_id,
                key,
                str(source or "system"),
                json.dumps(metadata or {}, allow_nan=False, sort_keys=True),
            )
        return bool(inserted)

    async def has_fable_reward(
        self,
        user_id: int,
        reward_type: object,
        reward_key: object,
        *,
        conn=None,
    ) -> bool:
        """Public entitlement API for profiles, travel, shops, and battle systems."""
        owns_connection = conn is None
        if owns_connection:
            conn = await self.bot.pool.acquire()
        try:
            return await self.fable_state.has_reward(
                conn,
                user_id=user_id,
                reward_type=reward_type,
                reward_key=reward_key,
            )
        finally:
            if owns_connection:
                await self.bot.pool.release(conn)

    async def list_fable_rewards(
        self,
        user_id: int,
        reward_type: object = "",
        *,
        conn=None,
    ) -> list[dict]:
        owns_connection = conn is None
        if owns_connection:
            conn = await self.bot.pool.acquire()
        try:
            return await self.fable_state.list_rewards(
                conn,
                user_id=user_id,
                reward_type=reward_type,
            )
        finally:
            if owns_connection:
                await self.bot.pool.release(conn)

    async def _apply_campaign_effects(
        self,
        user_id: int,
        campaign_key: str,
        *,
        effects: list | None = None,
        unlocks: list | None = None,
        event_key: str = "",
        source: str | None = None,
        run_id: str | None = None,
        conn,
    ) -> list[str]:
        messages = []
        effect_source = str(source or f"campaign:{campaign_key}").strip()
        if run_id:
            row = await conn.fetchrow(
                """
                SELECT run_id, unlocks_json, is_canonical
                FROM fable_campaign_runs
                WHERE run_id=$1 AND user_id=$2 AND campaign_key=$3
                FOR UPDATE
                """,
                run_id,
                user_id,
                campaign_key,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT run_id, unlocks_json, is_canonical
                FROM fable_campaign_runs
                WHERE user_id=$1 AND campaign_key=$2 AND is_canonical=TRUE
                FOR UPDATE
                """,
                user_id,
                campaign_key,
            )
        if not row:
            raise RuntimeError("Campaign effects require an active campaign run.")
        resolved_run_id = str(row["run_id"])
        is_canonical_run = bool(row["is_canonical"])
        current_unlocks = list(self._load_progress(row["unlocks_json"]) if row else [])
        replay_state_effects = []
        for unlock in unlocks or []:
            unlock_scope = (
                str(unlock.get("scope") or "campaign").strip().lower()
                if isinstance(unlock, dict)
                else "campaign"
            )
            unlock_key = str(unlock.get("key") if isinstance(unlock, dict) else unlock).strip()
            if unlock_scope in {"system", "global"}:
                system_key = normalize_system_unlock_key(unlock_key)
                if not system_key:
                    continue
                result = await conn.execute(
                    """
                    INSERT INTO player_system_unlocks (
                        user_id, unlock_key, source, metadata_json, unlocked_at
                    ) VALUES ($1,$2,$3,$4,NOW())
                    ON CONFLICT (user_id, unlock_key) DO NOTHING
                    """,
                    user_id,
                    system_key,
                    effect_source,
                    json.dumps({"campaign_key": campaign_key}, sort_keys=True),
                )
                if str(result).endswith(" 1"):
                    messages.append(f"Permanently unlocked **{system_key}**")
                continue
            if unlock_key and unlock_key not in current_unlocks:
                current_unlocks.append(unlock_key)
                messages.append(f"Unlocked **{unlock_key}**")

        for effect_index, effect in enumerate(effects or []):
            if not isinstance(effect, dict):
                continue
            effect_type = str(effect.get("type") or "").strip().lower()
            key = normalize_campaign_key(effect.get("key"))
            effect_metadata = (
                effect.get("metadata") if isinstance(effect.get("metadata"), dict) else {}
            )
            if effect_type == "unlock" and key:
                if key not in current_unlocks:
                    current_unlocks.append(key)
                    messages.append(f"Unlocked **{key}**")
            elif effect_type in {"system_unlock", "global_unlock"} and key:
                result = await conn.execute(
                    """
                    INSERT INTO player_system_unlocks (
                        user_id, unlock_key, source, metadata_json, unlocked_at
                    ) VALUES ($1,$2,$3,$4,NOW())
                    ON CONFLICT (user_id, unlock_key) DO NOTHING
                    """,
                    user_id,
                    normalize_system_unlock_key(key),
                    effect_source,
                    json.dumps(
                        {"campaign_key": campaign_key, **effect_metadata},
                        sort_keys=True,
                    ),
                )
                if str(result).endswith(" 1"):
                    messages.append(f"Permanently unlocked **{key}**")
            elif effect_type in COLLECTION_EFFECT_TYPES and key:
                reward_type = normalize_campaign_key(effect.get("reward_type"))
                display_name = str(
                    effect.get("name")
                    or effect.get("display_name")
                    or key.replace("_", " ").title()
                )
                if reward_type == "system_unlock":
                    await self.grant_system_unlock(
                        user_id,
                        key,
                        source=effect_source,
                        metadata={"campaign_key": campaign_key, **effect_metadata},
                        conn=conn,
                    )
                inserted = await self.fable_state.grant_reward(
                    conn,
                    user_id=user_id,
                    reward_type=reward_type,
                    reward_key=key,
                    display_name=display_name,
                    source=effect_source,
                    metadata={"campaign_key": campaign_key, **effect_metadata},
                )
                if inserted:
                    messages.append(f"Unlocked **{display_name}**")
            elif effect_type in {"reputation", "faction_standing"} and key:
                if not is_canonical_run:
                    points = int(
                        effect.get("points")
                        if effect.get("points") is not None
                        else effect.get("delta") or 0
                    )
                    if points:
                        replay_state_effects.append(
                            {
                                "type": "state_increment",
                                "key": f"faction.{key}.points",
                                "delta": points,
                            }
                        )
                    if effect.get("rank_delta"):
                        replay_state_effects.append(
                            {
                                "type": "state_increment",
                                "key": f"faction.{key}.rank",
                                "delta": int(effect["rank_delta"]),
                            }
                        )
                    if effect.get("set_rank") is not None:
                        replay_state_effects.append(
                            {
                                "type": "state_set",
                                "key": f"faction.{key}.rank",
                                "value": int(effect["set_rank"]),
                            }
                        )
                    messages.append(
                        f"Alternate-history standing changed for **{key.replace('_', ' ').title()}**."
                    )
                    continue
                factions = self.bot.get_cog("Factions")
                if factions is None:
                    raise RuntimeError("The Factions cog is required for faction-standing effects.")
                change = await factions.change_standing(
                    user_id,
                    key,
                    int(
                        effect.get("points")
                        if effect.get("points") is not None
                        else effect.get("delta") or 0
                    ),
                    source=effect_source,
                    event_key=(
                        f"{event_key}:effect:{effect_index}" if event_key else ""
                    ),
                    metadata={
                        "campaign_key": campaign_key,
                        **effect_metadata,
                    },
                    rank_delta=int(effect.get("rank_delta") or 0),
                    set_rank=effect.get("set_rank"),
                    conn=conn,
                )
                if change.applied and change.message():
                    messages.append(change.message())
            elif effect_type == "faction_membership" and key:
                if not is_canonical_run:
                    membership = normalize_campaign_key(
                        effect.get("status") or effect.get("value") or "member"
                    )
                    replay_state_effects.append(
                        {
                            "type": "state_set",
                            "key": f"faction.{key}.membership",
                            "value": membership,
                        }
                    )
                    messages.append(
                        f"Alternate-history allegiance with **{key.replace('_', ' ').title()}** is now **{membership.replace('_', ' ').title()}**."
                    )
                    continue
                factions = self.bot.get_cog("Factions")
                if factions is None:
                    raise RuntimeError("The Factions cog is required for faction-membership effects.")
                change = await factions.set_membership(
                    user_id,
                    key,
                    effect.get("status") or effect.get("value") or "member",
                    source=effect_source,
                    event_key=(
                        f"{event_key}:effect:{effect_index}" if event_key else ""
                    ),
                    metadata={
                        "campaign_key": campaign_key,
                        **effect_metadata,
                    },
                    conn=conn,
                )
                if change.applied and change.message():
                    messages.append(change.message())

        authored_state_effects = [
            effect
            for effect in effects or []
            if isinstance(effect, dict)
            and str(effect.get("type") or "").strip().lower()
            in STATE_EFFECT_TYPES | MODEL_EFFECT_TYPES
        ]
        state_effects = [
            expand_model_effect(effect) for effect in authored_state_effects
        ] + replay_state_effects
        if state_effects:
            mutations = await self.fable_state.apply_effects(
                conn,
                user_id=user_id,
                campaign_key=campaign_key,
                effects=state_effects,
                event_key=event_key,
                source=effect_source,
                run_id=resolved_run_id,
                metadata={"campaign_key": campaign_key},
            )
            for effect, mutation in zip(authored_state_effects, mutations):
                authored_message = str(effect.get("message") or "").strip()
                if authored_message:
                    messages.append(authored_message)

        await conn.execute(
            """
            UPDATE fable_campaign_runs SET unlocks_json=$2, updated_at=NOW()
            WHERE run_id=$1
            """,
            resolved_run_id,
            json.dumps(current_unlocks),
        )
        return messages

    async def _available_campaign_edges(
        self,
        user_id: int,
        edges: list,
        *,
        conn,
        campaign_key: str = "",
        run_id: str | None = None,
        campaign: dict | None = None,
    ) -> list[dict]:
        available = []
        for edge in edges or []:
            allowed, _reason = await self._evaluate_campaign_conditions(
                user_id,
                edge.get("conditions") or [],
                conn=conn,
                campaign_key=campaign_key,
                run_id=run_id,
            )
            if not allowed:
                continue
            if campaign is not None:
                target = node_by_id(campaign, edge.get("target"))
                if target is None:
                    continue
                allowed, _reason = await self._evaluate_campaign_conditions(
                    user_id,
                    target.get("requirements") or [],
                    conn=conn,
                    campaign_key=campaign_key,
                    run_id=run_id,
                )
                if not allowed:
                    continue
            available.append(edge)
        return available

    async def _campaign_epilogue_fragments(
        self,
        user_id: int,
        campaign: dict,
        ending_node: dict,
        *,
        conn,
        run_id: str | None,
    ) -> list[dict]:
        """Resolve ordered, conditional epilogue fragments for an ending."""
        authored = list(campaign.get("epilogue") or []) + list(
            ending_node.get("epilogue") or []
        )
        rendered = []
        for index, fragment in enumerate(authored):
            if not isinstance(fragment, dict):
                continue
            allowed, _reason = await self._evaluate_campaign_conditions(
                user_id,
                fragment.get("conditions") or [],
                conn=conn,
                campaign_key=campaign["key"],
                run_id=run_id,
            )
            if not allowed:
                continue
            rendered.append(
                {
                    "id": normalize_campaign_key(
                        fragment.get("id") or f"epilogue_{index + 1}"
                    ),
                    "title": str(fragment.get("title") or "Aftermath").strip(),
                    "text": str(fragment.get("text") or "").strip(),
                    "order": int(fragment.get("order", (index + 1) * 10)),
                }
            )
        return sorted(
            rendered,
            key=lambda fragment: (fragment["order"], fragment["id"]),
        )

    async def _process_campaign_autonomous_events(
        self,
        ctx,
        campaign: dict,
        node_id: str,
        *,
        run_id: str,
    ) -> str:
        """Resolve one-shot companion/world decisions triggered on node entry."""
        matching = [
            event
            for event in campaign.get("autonomous_events") or []
            if isinstance(event, dict) and event.get("trigger_node") == node_id
        ]
        if not matching:
            return ""
        rendered = []
        redirect_target = ""
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for event in matching:
                    marker_key = f"event.autonomous.{event['id']}"
                    exists, resolved = await self.fable_state.get_state(
                        conn,
                        user_id=ctx.author.id,
                        campaign_key=campaign["key"],
                        state_key=marker_key,
                        run_id=run_id,
                    )
                    if exists and resolved:
                        continue
                    allowed, _reason = await self._evaluate_campaign_conditions(
                        ctx.author.id,
                        event.get("conditions") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=run_id,
                    )
                    if not allowed:
                        continue
                    effects = list(event.get("effects") or []) + [
                        {"type": "state_set", "key": marker_key, "value": True}
                    ]
                    messages = await self._apply_campaign_effects(
                        ctx.author.id,
                        campaign["key"],
                        effects=effects,
                        unlocks=event.get("unlocks") or [],
                        event_key=f"campaign:{campaign['key']}:autonomous:{event['id']}",
                        source=f"autonomous:{event['id']}",
                        run_id=run_id,
                        conn=conn,
                    )
                    rendered.append(
                        (
                            str(event.get("title") or "Companion Decision"),
                            str(event.get("text") or ""),
                            messages,
                        )
                    )
                    if event.get("redirect_target"):
                        redirect_target = event["redirect_target"]
                        await conn.execute(
                            """
                            UPDATE fable_campaign_runs
                            SET current_node_key=$2, status='entering', updated_at=NOW()
                            WHERE run_id=$1
                            """,
                            run_id,
                            redirect_target,
                        )
                        break
        for title, text, messages in rendered:
            embed = discord.Embed(title=title, description=text, color=0x6B4C8A)
            if messages:
                embed.add_field(
                    name="Consequences",
                    value="\n".join(messages)[:1024],
                    inline=False,
                )
            await ctx.send(embed=embed)
        return redirect_target

    def _campaign_choice_embed(self, campaign: dict, node: dict, edges: list[dict]) -> discord.Embed:
        embed = discord.Embed(
            title=node.get("title") or campaign.get("title") or "Campaign Choice",
            description=node.get("description") or "Choose what your character does next.",
            color=0x7A4B20,
        )
        for index, edge in enumerate(edges, start=1):
            embed.add_field(
                name=f"{index}. {edge.get('label') or 'Continue'}",
                value=edge.get("description") or f"Continue to `{edge.get('target')}`.",
                inline=False,
            )
        embed.set_footer(text="Choose with $campaign choose <number>")
        return embed

    async def _campaign_prompt_matches(
        self,
        user_id: int,
        *,
        run_id: str,
        campaign_key: str,
        node_key: str,
        action_kind: str,
        stage_key: str = "",
    ) -> bool:
        """Reject stale buttons before they can act on a later story prompt."""
        if action_kind == "act":
            row = await self.bot.pool.fetchrow(
                """
                SELECT fcr.run_id, fcr.campaign_key, fcr.current_node_key,
                       fsa.current_stage_key
                FROM fable_campaign_runs fcr
                JOIN fable_scenario_attempts fsa ON fsa.run_id=fcr.run_id
                LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
                WHERE fcr.user_id=$1 AND fcr.run_id=$2
                  AND fcr.status='awaiting_scenario' AND fsa.status='active'
                LIMIT 1
                """,
                user_id,
                run_id,
            )
            return bool(
                row
                and str(row["run_id"]) == run_id
                and row["campaign_key"] == campaign_key
                and row["current_node_key"] == node_key
                and row["current_stage_key"] == stage_key
            )
        row = await self.bot.pool.fetchrow(
            """
            SELECT fcr.run_id, fcr.campaign_key, fcr.current_node_key
            FROM fable_campaign_runs fcr
            LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
            WHERE fcr.user_id=$1 AND fcr.run_id=$2
              AND fcr.status='awaiting_choice'
            LIMIT 1
            """,
            user_id,
            run_id,
        )
        return bool(
            row
            and str(row["run_id"]) == run_id
            and row["campaign_key"] == campaign_key
            and row["current_node_key"] == node_key
        )

    async def _send_campaign_choice_prompt(
        self,
        ctx,
        campaign: dict,
        node: dict,
        edges: list[dict],
        *,
        run_id: str,
    ) -> None:
        view = CampaignActionView(
            cog=self,
            ctx=ctx,
            run_id=run_id,
            campaign_key=campaign["key"],
            node_key=node["id"],
            options=edges,
            action_kind="choose",
        )
        message = await ctx.send(
            embed=self._campaign_choice_embed(campaign, node, edges),
            view=view,
        )
        view.message = message

    async def _send_campaign_encounter(self, ctx, node: dict) -> None:
        encounter = node.get("encounter") or {}
        if not encounter or str(encounter.get("kind") or "none") == "none":
            return
        party = encounter.get("party") or {}
        minimum = max(1, int(party.get("min") or 1))
        maximum = max(minimum, int(party.get("max") or minimum))
        embed = discord.Embed(
            title=f"Encounter: {encounter.get('name') or node.get('title') or 'Campaign Battle'}",
            description=str(encounter.get("description") or "This objective uses an existing battle mode."),
            color=0x8B1E1E,
        )
        embed.add_field(name="Mode", value=str(encounter.get("kind") or "external_command").replace("_", " ").title())
        embed.add_field(name="Party", value=f"{minimum}-{maximum} player(s)")
        if encounter.get("monster"):
            embed.add_field(name="Enemy", value=str(encounter["monster"]), inline=False)
        if encounter.get("launch_command"):
            embed.add_field(name="Begin", value=f"`{encounter['launch_command']}`", inline=False)
        await ctx.send(embed=embed)

    async def _play_campaign_node_cutscene(
        self,
        ctx,
        campaign: dict,
        node: dict,
        slot: str = "enter",
    ) -> bool:
        payload = self._campaign_cutscene_payload(campaign, node, slot)
        if not payload:
            return True
        cutscene_key, _definition = payload
        completed = await self.play_cutscene(
            ctx,
            cutscene_key,
            wait_for_completion=True,
        )
        if not completed:
            await ctx.send(
                "Your campaign scene has paused. Use `$campaign` when you are ready to continue."
            )
        return completed

    @staticmethod
    def _scenario_stage(scenario: dict, stage_key: str) -> dict | None:
        normalized = normalize_campaign_key(stage_key)
        return next(
            (
                stage
                for stage in scenario.get("stages") or []
                if isinstance(stage, dict) and stage.get("id") == normalized
            ),
            None,
        )

    @staticmethod
    def _scenario_outcome(scenario: dict, outcome_key: str) -> dict | None:
        normalized = normalize_campaign_key(outcome_key)
        return next(
            (
                outcome
                for outcome in scenario.get("outcomes") or []
                if isinstance(outcome, dict) and outcome.get("id") == normalized
            ),
            None,
        )

    async def _available_scenario_actions(
        self,
        user_id: int,
        campaign_key: str,
        scenario: dict,
        stage: dict,
        *,
        conn,
        run_id: str,
        campaign: dict | None = None,
    ) -> list[dict]:
        available = []
        for action in stage.get("actions") or []:
            if not isinstance(action, dict):
                continue
            allowed, _reason = await self._evaluate_campaign_conditions(
                user_id,
                action.get("conditions") or [],
                conn=conn,
                campaign_key=campaign_key,
                run_id=run_id,
            )
            if not allowed:
                continue
            if action.get("outcome"):
                outcome = self._scenario_outcome(scenario, action["outcome"])
                if not outcome:
                    continue
                allowed, _reason = await self._evaluate_campaign_conditions(
                    user_id,
                    outcome.get("conditions") or [],
                    conn=conn,
                    campaign_key=campaign_key,
                    run_id=run_id,
                )
                if not allowed:
                    continue
                if campaign is not None:
                    target = node_by_id(campaign, outcome.get("target"))
                    if target is None:
                        continue
                    allowed, _reason = await self._evaluate_campaign_conditions(
                        user_id,
                        target.get("requirements") or [],
                        conn=conn,
                        campaign_key=campaign_key,
                        run_id=run_id,
                    )
                    if not allowed:
                        continue
            available.append(action)
        return available

    async def _send_campaign_scenario_stage(
        self,
        ctx,
        campaign: dict,
        node: dict,
        *,
        run_id: str,
    ) -> bool:
        scenario = node.get("scenario") or {}
        async with self.bot.pool.acquire() as conn:
            attempt = await conn.fetchrow(
                """
                SELECT fsa.attempt_id, fsa.run_id, fsa.current_stage_key
                FROM fable_scenario_attempts fsa
                JOIN fable_campaign_runs fcr ON fcr.run_id=fsa.run_id
                WHERE fcr.user_id=$1 AND fcr.campaign_key=$2
                  AND fcr.run_id=$4 AND fsa.node_key=$3
                  AND fsa.status='active'
                """,
                ctx.author.id,
                campaign["key"],
                node["id"],
                run_id,
            )
            if not attempt:
                await self._enter_campaign_scenario(
                    ctx,
                    campaign,
                    node,
                    run_id=run_id,
                )
                return False
            stage = self._scenario_stage(scenario, attempt["current_stage_key"])
            if not stage:
                await ctx.send("This scenario points to a missing stage. Ask a GM to inspect it.")
                return False
            actions = await self._available_scenario_actions(
                ctx.author.id,
                campaign["key"],
                scenario,
                stage,
                conn=conn,
                run_id=str(attempt["run_id"]),
                campaign=campaign,
            )
        embed = discord.Embed(
            title=stage.get("title") or node.get("title") or "Campaign Scenario",
            description=stage.get("description") or node.get("description") or "Choose your approach.",
            color=0x8B5A2B,
        )
        if stage.get("launch_command"):
            embed.add_field(
                name="Encounter",
                value=f"`{stage['launch_command']}`",
                inline=False,
            )
        for index, action in enumerate(actions, start=1):
            embed.add_field(
                name=f"{index}. {action.get('label') or 'Act'}",
                value=action.get("description") or "Commit to this approach.",
                inline=False,
            )
        embed.set_footer(text="Act with $campaign act <number>")
        view = CampaignActionView(
            cog=self,
            ctx=ctx,
            run_id=str(attempt["run_id"]),
            campaign_key=campaign["key"],
            node_key=node["id"],
            stage_key=stage["id"],
            options=actions,
            action_kind="act",
        )
        message = await ctx.send(embed=embed, view=view)
        view.message = message
        return True

    @staticmethod
    def _warfront_front(warfront: dict, front_key: str) -> dict | None:
        normalized = normalize_campaign_key(front_key)
        return next(
            (
                front for front in warfront.get("fronts") or []
                if isinstance(front, dict) and front.get("id") == normalized
            ),
            None,
        )

    @staticmethod
    def _warfront_asset(warfront: dict, asset_key: str) -> dict | None:
        normalized = normalize_campaign_key(asset_key)
        return next(
            (
                asset for asset in warfront.get("assets") or []
                if isinstance(asset, dict) and asset.get("key") == normalized
            ),
            None,
        )

    async def _available_warfront_assets(
        self,
        user_id: int,
        campaign: dict,
        warfront: dict,
        *,
        conn,
        run_id: str,
    ) -> list[dict]:
        available = []
        for asset in warfront.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            allowed, _reason = await self._evaluate_campaign_conditions(
                user_id,
                asset.get("conditions") or [],
                conn=conn,
                campaign_key=campaign["key"],
                run_id=run_id,
            )
            if allowed:
                available.append(asset)
        return available

    async def _available_warfront_fronts(
        self,
        user_id: int,
        campaign: dict,
        warfront: dict,
        *,
        conn,
        run_id: str,
    ) -> list[dict]:
        available = []
        for front in warfront.get("fronts") or []:
            if not isinstance(front, dict):
                continue
            allowed, _reason = await self._evaluate_campaign_conditions(
                user_id,
                front.get("conditions") or [],
                conn=conn,
                campaign_key=campaign["key"],
                run_id=run_id,
            )
            if allowed:
                available.append(front)
        return available

    async def _send_campaign_warfront_plan(
        self,
        ctx,
        campaign: dict,
        node: dict,
        *,
        run_id: str,
    ) -> bool:
        warfront = node.get("warfront") or {}
        async with self.bot.pool.acquire() as conn:
            attempt = await conn.fetchrow(
                """
                SELECT player_front_key, assignments_json
                FROM fable_warfront_attempts
                WHERE run_id=$1 AND node_key=$2 AND status='planning'
                """,
                run_id,
                node["id"],
            )
            if not attempt:
                await self._enter_campaign_warfront(
                    ctx,
                    campaign,
                    node,
                    run_id=run_id,
                )
                return False
            assets = await self._available_warfront_assets(
                ctx.author.id,
                campaign,
                warfront,
                conn=conn,
                run_id=run_id,
            )
            fronts = await self._available_warfront_fronts(
                ctx.author.id,
                campaign,
                warfront,
                conn=conn,
                run_id=run_id,
            )
        assignments = self._load_progress(attempt["assignments_json"])
        player_front = str(attempt["player_front_key"] or "")
        asset_names = {asset["key"]: asset.get("name") or asset["key"] for asset in assets}
        embed = discord.Embed(
            title=warfront.get("title") or node.get("title") or "Warfront Plan",
            description=warfront.get("description") or node.get("description") or "Allocate your available forces.",
            color=0x8B1E1E,
        )
        for front in fronts:
            assigned = list(assignments.get(front["id"]) or [])
            forces = [asset_names.get(key, key.replace("_", " ").title()) for key in assigned]
            if player_front == front["id"]:
                forces.insert(0, "You")
            embed.add_field(
                name=f"{front['title']} · Difficulty {front['difficulty']}",
                value=(
                    f"{front.get('description') or 'A contested front.'}\n"
                    f"Assigned: {', '.join(forces) if forces else 'Nobody'}"
                )[:1024],
                inline=False,
            )
        if assets:
            embed.add_field(
                name="Available Forces",
                value="\n".join(
                    f"`{asset['key']}` · {asset.get('name') or asset['key']} · Power {asset.get('power', 0)}"
                    for asset in assets[:20]
                )[:1024],
                inline=False,
            )
        if not fronts:
            embed.add_field(
                name="No active fronts",
                value="This operation's front requirements currently hide every route. Contact a GM or revise the campaign package.",
                inline=False,
            )
        embed.set_footer(
            text="$campaign assign player <front> · $campaign assign <force> <front> · $campaign deploy"
        )
        await ctx.send(embed=embed)
        return True

    async def _enter_campaign_warfront(
        self,
        ctx,
        campaign: dict,
        node: dict,
        *,
        run_id: str,
    ) -> None:
        warfront = node.get("warfront") or {}
        resolved_target = ""
        messages = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                run = await conn.fetchrow(
                    """
                    SELECT run_id FROM fable_campaign_runs
                    WHERE run_id=$1 AND user_id=$2 AND campaign_key=$3
                    FOR UPDATE
                    """,
                    run_id,
                    ctx.author.id,
                    campaign["key"],
                )
                if not run:
                    return await ctx.send("No campaign run exists for this warfront.")
                messages = await self._apply_campaign_effects(
                    ctx.author.id,
                    campaign["key"],
                    effects=node.get("effects") or [],
                    unlocks=node.get("unlocks") or [],
                    event_key=f"campaign:{campaign['key']}:warfront_node:{node['id']}",
                    run_id=run_id,
                    conn=conn,
                )
                attempt = await conn.fetchrow(
                    """
                    INSERT INTO fable_warfront_attempts (
                        attempt_id, run_id, user_id, campaign_key, node_key,
                        warfront_key, status, player_front_key,
                        assignments_json, result_json, started_at, updated_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,'planning','','{}','{}',NOW(),NOW())
                    ON CONFLICT (run_id, node_key) DO UPDATE SET updated_at=NOW()
                    RETURNING status, result_json
                    """,
                    self.fable_state.new_run_id(),
                    run_id,
                    ctx.author.id,
                    campaign["key"],
                    node["id"],
                    warfront.get("key") or node["id"],
                )
                if attempt and str(attempt["status"]) == "completed":
                    result = self._load_progress(attempt["result_json"])
                    resolved_target = str(result.get("target") or "")
                await conn.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET current_node_key=$2, status=$3, updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    run_id,
                    resolved_target or node["id"],
                    "entering" if resolved_target else "awaiting_warfront",
                )
        if messages:
            await ctx.send("\n".join(messages))
        if resolved_target:
            await self._enter_campaign_node(
                ctx,
                campaign,
                resolved_target,
                run_id=run_id,
            )
            return
        await self._send_campaign_warfront_plan(
            ctx,
            campaign,
            node,
            run_id=run_id,
        )

    async def _enter_campaign_scenario(
        self,
        ctx,
        campaign: dict,
        node: dict,
        *,
        run_id: str,
    ) -> None:
        scenario = node.get("scenario") or {}
        messages = []
        resolved_target = ""
        attempt_was_completed = False
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                run = await conn.fetchrow(
                    """
                    SELECT run_id
                    FROM fable_campaign_runs
                    WHERE run_id=$1 AND user_id=$2 AND campaign_key=$3
                    FOR UPDATE
                    """,
                    run_id,
                    ctx.author.id,
                    campaign["key"],
                )
                if not run:
                    await ctx.send("No matching campaign run exists for this scenario.")
                    return
                messages = await self._apply_campaign_effects(
                    ctx.author.id,
                    campaign["key"],
                    effects=node.get("effects") or [],
                    unlocks=node.get("unlocks") or [],
                    event_key=f"campaign:{campaign['key']}:scenario_node:{node['id']}",
                    run_id=run_id,
                    conn=conn,
                )
                attempt = await conn.fetchrow(
                    """
                    INSERT INTO fable_scenario_attempts (
                        attempt_id, run_id, user_id, campaign_key, node_key,
                        scenario_key, status, current_stage_key, history_json,
                        result_json, started_at, updated_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,'active',$7,'[]','{}',NOW(),NOW())
                    ON CONFLICT (run_id, node_key) DO UPDATE SET updated_at=NOW()
                    RETURNING attempt_id, status, result_json
                    """,
                    self.fable_state.new_run_id(),
                    run["run_id"],
                    ctx.author.id,
                    campaign["key"],
                    node["id"],
                    scenario.get("key") or node["id"],
                    scenario.get("start_stage") or "",
                )
                if attempt and str(attempt["status"]) != "active":
                    attempt_was_completed = True
                    prior_result = self._load_progress(attempt["result_json"])
                    prior_outcome = self._scenario_outcome(
                        scenario,
                        prior_result.get("outcome") if isinstance(prior_result, dict) else "",
                    )
                    resolved_target = str((prior_outcome or {}).get("target") or "")
                await conn.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET current_node_key=$2, status=$3, updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    run_id,
                    resolved_target or node["id"],
                    "entering" if resolved_target else "awaiting_scenario",
                )
        if messages:
            await ctx.send("\n".join(messages))
        if resolved_target:
            await self._enter_campaign_node(
                ctx,
                campaign,
                resolved_target,
                run_id=run_id,
            )
            return
        if attempt_was_completed:
            await ctx.send("This completed scenario has an invalid saved outcome. Ask a GM to inspect it.")
            return
        if not await self._play_campaign_node_cutscene(ctx, campaign, node, "enter"):
            return
        await self._send_campaign_scenario_stage(
            ctx,
            campaign,
            node,
            run_id=run_id,
        )

    async def _enter_campaign_node(
        self,
        ctx,
        campaign: dict,
        node_id: str,
        *,
        run_id: str,
    ) -> None:
        node = node_by_id(campaign, node_id)
        if not node:
            await ctx.send("This campaign points to a missing chapter. Ask a GM to validate its JSON.")
            return

        async with self.bot.pool.acquire() as conn:
            allowed, reason = await self._evaluate_campaign_conditions(
                ctx.author.id,
                node.get("requirements") or [],
                conn=conn,
                campaign_key=campaign["key"],
                run_id=run_id,
            )
        if not allowed:
            await ctx.send(
                f"**{node.get('title', 'Next Chapter')}** is locked:\n{reason}"
            )
            return

        redirect_target = await self._process_campaign_autonomous_events(
            ctx,
            campaign,
            node["id"],
            run_id=run_id,
        )
        if redirect_target:
            await self._enter_campaign_node(
                ctx,
                campaign,
                redirect_target,
                run_id=run_id,
            )
            return

        if node.get("type") == "ending":
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    messages = await self._apply_campaign_effects(
                        ctx.author.id,
                        campaign["key"],
                        effects=node.get("effects") or [],
                        unlocks=node.get("unlocks") or [],
                        event_key=f"campaign:{campaign['key']}:ending:{node['id']}",
                        run_id=run_id,
                        conn=conn,
                    )
                    run = await conn.fetchrow(
                        """
                        SELECT run_id, content_version, history_json,
                               choices_json, unlocks_json
                        FROM fable_campaign_runs
                        WHERE run_id=$1 AND user_id=$2 AND campaign_key=$3
                        FOR UPDATE
                        """,
                        run_id,
                        ctx.author.id,
                        campaign["key"],
                    )
                    story_state = (
                        await self.fable_state.snapshot(conn, str(run["run_id"]))
                        if run
                        else {}
                    )
                    epilogue_fragments = await self._campaign_epilogue_fragments(
                        ctx.author.id,
                        campaign,
                        node,
                        conn=conn,
                        run_id=str(run["run_id"]) if run else None,
                    )
                    ending_history = list(
                        self._load_progress(run["history_json"]) if run else []
                    )
                    if node["id"] not in ending_history:
                        ending_history.append(node["id"])
                    ending_snapshot = {
                        "campaign_key": campaign["key"],
                        "campaign_title": campaign.get("title") or campaign["key"],
                        "ending_node": node["id"],
                        "ending_title": node.get("title") or "Campaign Complete",
                        "content_version": int(run["content_version"] or 1) if run else 1,
                        "history": ending_history,
                        "choices": self._load_progress(run["choices_json"]) if run else {},
                        "unlocks": self._load_progress(run["unlocks_json"]) if run else [],
                        "state": story_state,
                        "epilogue": epilogue_fragments,
                    }
                    await conn.execute(
                        """
                        UPDATE fable_campaign_runs
                        SET status='completed', completed_at=NOW(), updated_at=NOW(),
                            ending_snapshot_json=$2, history_json=$3
                        WHERE run_id=$1
                        """,
                        run_id,
                        json.dumps(ending_snapshot, allow_nan=False, sort_keys=True),
                        json.dumps(ending_history),
                    )
            embed = discord.Embed(
                title=node.get("title") or f"{campaign['title']} Complete",
                description=node.get("description") or "Your campaign is complete.",
                color=0x2F6B3F,
            )
            if messages:
                embed.add_field(name="Consequences", value="\n".join(messages), inline=False)
            for fragment in epilogue_fragments[:12]:
                embed.add_field(
                    name=fragment["title"][:256],
                    value=fragment["text"][:1024],
                    inline=False,
                )
            await ctx.send(embed=embed)
            return

        if node.get("type") == "warfront":
            await self._enter_campaign_warfront(
                ctx,
                campaign,
                node,
                run_id=run_id,
            )
            return

        if node.get("type") == "scenario":
            await self._enter_campaign_scenario(
                ctx,
                campaign,
                node,
                run_id=run_id,
            )
            return

        if node.get("type") != "quest":
            node_type = str(node.get("type") or "scene")
            node_effects = list(node.get("effects") or [])
            if node_type == "travel" and node.get("location_key"):
                node_effects.extend(
                    [
                        {
                            "type": "state_set",
                            "key": "world.current_location",
                            "value": node["location_key"],
                        },
                        {
                            "type": "state_add",
                            "key": "world.visited_locations",
                            "value": node["location_key"],
                        },
                    ]
                )
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    messages = await self._apply_campaign_effects(
                        ctx.author.id,
                        campaign["key"],
                        effects=node_effects,
                        unlocks=node.get("unlocks") or [],
                        event_key=f"campaign:{campaign['key']}:{node_type}_node:{node['id']}",
                        run_id=run_id,
                        conn=conn,
                    )
                    raw_edges = (
                        node.get("options")
                        if node_type in CHOICE_NODE_TYPES
                        else node.get("next")
                    )
                    edges = await self._available_campaign_edges(
                        ctx.author.id,
                        raw_edges or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=run_id,
                        campaign=campaign,
                    )
                    await conn.execute(
                        """
                        UPDATE fable_campaign_runs
                        SET current_node_key=$2, status='awaiting_choice', updated_at=NOW()
                        WHERE run_id=$1
                        """,
                        run_id,
                        node["id"],
                    )
            if messages:
                await ctx.send("\n".join(messages))
            if not await self._play_campaign_node_cutscene(ctx, campaign, node, "enter"):
                return
            if not edges:
                await ctx.send(
                    "No story responses are currently unlocked. "
                    "Your faction standing or another requirement may need to change first."
                )
                return
            await self._send_campaign_choice_prompt(
                ctx,
                campaign,
                node,
                edges,
                run_id=run_id,
            )
            return

        quest_key = self._campaign_quest_key(campaign, node)
        try:
            accept_data = await self._accept_quest_for_user(ctx.author.id, quest_key)
        except ValueError as exc:
            quest_row = await self.bot.pool.fetchrow(
                """
                SELECT status, completion_count
                FROM player_quests
                WHERE user_id=$1 AND quest_key=$2
                """,
                ctx.author.id,
                quest_key,
            )
            replay_run = await self.bot.pool.fetchrow(
                "SELECT is_canonical FROM fable_campaign_runs WHERE run_id=$1",
                run_id,
            )
            quest_status = str(quest_row["status"]) if quest_row else ""
            quest_completed = bool(
                quest_row
                and (
                    quest_status == "completed"
                    or int(quest_row["completion_count"] or 0) > 0
                )
            )
            if replay_run and not replay_run["is_canonical"] and quest_completed:
                await self.bot.pool.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET current_node_key=$2, status='active', updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    run_id,
                    node["id"],
                )
                await ctx.send(
                    f"Chronicle replay recognizes your completed objective for "
                    f"**{node.get('title')}** and continues without granting it again."
                )
                await self._advance_campaign_after_quest(
                    ctx,
                    quest_record_from_node(campaign, node),
                )
                return
            if quest_status == "active":
                await self.bot.pool.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET current_node_key=$2, status='active', updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    run_id,
                    node["id"],
                )
                await ctx.send(
                    f"Campaign chapter **{node.get('title')}** resumed. "
                    f"Continue it through `$quests`."
                )
                await self._send_campaign_encounter(ctx, node)
                return
            await ctx.send(f"Campaign chapter **{node.get('title')}** is ready: {exc}")
            return
        await self.bot.pool.execute(
            """
            UPDATE fable_campaign_runs
            SET current_node_key=$2, status='active', updated_at=NOW()
            WHERE run_id=$1
            """,
            run_id,
            node["id"],
        )
        cutscene_completed = await self._send_quest_accept_messages(
            ctx,
            accept_data,
            wait_for_cutscene=True,
        )
        if not cutscene_completed:
            return
        await self._send_campaign_encounter(ctx, node)

    async def _advance_campaign_after_quest(self, ctx, custom_def: dict) -> None:
        access = custom_def.get("access") or {}
        campaign_key = normalize_campaign_key(access.get("campaign_key"))
        node_key = normalize_campaign_key(access.get("campaign_node_key"))
        if not campaign_key or not node_key:
            return
        campaign = await self._fetch_campaign_definition(
            campaign_key,
            user_id=ctx.author.id,
        )
        node = node_by_id(campaign or {}, node_key)
        if not campaign or not node:
            return

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                state = await self._selected_campaign_run(
                    conn,
                    ctx.author.id,
                    campaign_key=campaign_key,
                    statuses=("active",),
                    for_update=True,
                )
                if not state or state["current_node_key"] != node_key:
                    return
                run_id = str(state["run_id"])
                history = list(self._load_progress(state["history_json"]) or [])
                if node_key not in history:
                    history.append(node_key)
                consequence_messages = await self._apply_campaign_effects(
                    ctx.author.id,
                    campaign_key,
                    effects=node.get("effects") or [],
                    unlocks=node.get("unlocks") or [],
                    event_key=f"campaign:{campaign_key}:quest:{node_key}",
                    run_id=run_id,
                    conn=conn,
                )
                edges = await self._available_campaign_edges(
                    ctx.author.id,
                    node.get("next") or [],
                    conn=conn,
                    campaign_key=campaign_key,
                    run_id=run_id,
                    campaign=campaign,
                )
                if len(edges) == 1:
                    edge = edges[0]
                    consequence_messages.extend(
                        await self._apply_campaign_effects(
                            ctx.author.id,
                            campaign_key,
                            effects=edge.get("effects") or [],
                            unlocks=edge.get("unlocks") or [],
                            event_key=(
                                f"campaign:{campaign_key}:auto:"
                                f"{node_key}:{edge['target']}"
                            ),
                            run_id=run_id,
                            conn=conn,
                        )
                    )
                if len(edges) == 1:
                    await conn.execute(
                        """
                        UPDATE fable_campaign_runs
                        SET current_node_key=$2, status='entering',
                            history_json=$3, updated_at=NOW()
                        WHERE run_id=$1
                        """,
                        run_id,
                        edges[0]["target"],
                        json.dumps(history),
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE fable_campaign_runs
                        SET status=$2, history_json=$3, updated_at=NOW()
                        WHERE run_id=$1
                        """,
                        run_id,
                        "awaiting_choice",
                        json.dumps(history),
                    )

        if consequence_messages:
            await ctx.send("\n".join(consequence_messages))
        if not edges:
            await ctx.send("This chapter has no available next path. A GM may need to review its conditions.")
            return
        if len(edges) > 1:
            await self._send_campaign_choice_prompt(
                ctx,
                campaign,
                node,
                edges,
                run_id=run_id,
            )
            return
        await self._enter_campaign_node(
            ctx,
            campaign,
            edges[0]["target"],
            run_id=run_id,
        )

    def _load_custom_quest_definition(self, row) -> dict:
        if not row:
            return {}
        return {
            "quest_key": str(row["quest_key"]),
            "name": str(row["name"]),
            "category": str(row["category"] or "General"),
            "short_description": str(row["short_description"] or ""),
            "offer_text": str(row["offer_text"] or ""),
            "turnin_text": str(row["turnin_text"] or ""),
            "objective": self._load_progress(row["objective_json"]),
            "turnin": self._load_progress(row["turnin_json"]),
            "reward": self._load_progress(row["reward_json"]),
            "access": self._load_progress(row["access_json"]),
            "prerequisites": self._load_progress(row["prerequisite_keys_json"]),
            "accept_cutscene_key": str(row["accept_cutscene_key"] or "").strip(),
            "turnin_cutscene_key": str(row["turnin_cutscene_key"] or "").strip(),
            "repeatable": bool(row["repeatable"]),
            "is_active": bool(row["is_active"]),
            "created_by": row["created_by"],
        }

    async def _fetch_custom_quest_definition(self, quest_key: str, *, conn=None) -> dict | None:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            row = await conn.fetchrow(
                """
                SELECT quest_key, name, category, short_description, offer_text, turnin_text,
                       objective_json, turnin_json, reward_json, access_json,
                       prerequisite_keys_json, accept_cutscene_key, turnin_cutscene_key,
                       repeatable, is_active, created_by, updated_at
                FROM custom_quests
                WHERE quest_key = $1
                """,
                quest_key,
            )
            return self._load_custom_quest_definition(row) if row else None
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _fetch_custom_quest_definitions(self, *, conn=None, active_only: bool = False) -> list[dict]:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            query = (
                """
                SELECT quest_key, name, category, short_description, offer_text, turnin_text,
                       objective_json, turnin_json, reward_json, access_json,
                       prerequisite_keys_json, accept_cutscene_key, turnin_cutscene_key,
                       repeatable, is_active, created_by, updated_at
                FROM custom_quests
                """
                + ("WHERE is_active = TRUE " if active_only else "")
                + "ORDER BY category ASC, quest_key ASC"
            )
            rows = await conn.fetch(query)
            return [self._load_custom_quest_definition(row) for row in rows]
        finally:
            if local:
                await self.bot.pool.release(conn)

    def _custom_reward_text(self, custom_def: dict) -> str:
        reward = custom_def.get("reward") or {}
        reward_type = str(reward.get("type") or "").lower()
        if reward_type == "bundle":
            parts = [
                self._custom_reward_text({"reward": bundled_reward})
                for bundled_reward in reward.get("rewards") or []
                if isinstance(bundled_reward, dict)
            ]
            return " ".join(parts) if parts else "Reward bundle not configured yet."
        if reward_type == "money":
            return f"Receive **${int(reward.get('amount') or 0):,}**."
        if reward_type == "crate":
            amount = int(reward.get("amount") or 0)
            rarity = str(reward.get("rarity") or "common").capitalize()
            crate_word = "Crate" if amount == 1 else "Crates"
            return f"Receive **{amount} {rarity} {crate_word}**."
        if reward_type == "item":
            return f"Receive **{reward.get('name', 'a custom item')}**."
        if reward_type == "egg":
            return f"Receive a **{reward.get('monster_name', 'monster')} Egg**."
        if reward_type in COLLECTION_REWARD_TYPES:
            display_name = str(
                reward.get("name")
                or reward.get("display_name")
                or reward.get("key")
                or "story reward"
            ).replace("_", " ").title()
            return f"Permanently unlock **{display_name}** ({reward_type.replace('_', ' ')})."
        if reward_type == "none":
            return "Story progression only. No material reward."
        return "Reward not configured yet."

    def _custom_objective_text(self, custom_def: dict) -> str:
        objective = custom_def.get("objective") or {}
        turnin = custom_def.get("turnin") or {}
        source = self._normalize_source(objective.get("source")) or "none"
        required_count = int(objective.get("required_count") or 0)
        key_item_required_quantity = max(1, int(objective.get("key_item_required_quantity") or 1))
        drop_chance_percent = max(0.0, min(100.0, float(objective.get("drop_chance_percent") or 100)))
        drop_quantity_min = max(1, int(objective.get("drop_quantity_min") or 1))
        drop_quantity_max = max(drop_quantity_min, int(objective.get("drop_quantity_max") or drop_quantity_min))
        target_name = str(objective.get("target_name") or "").strip()
        source_label = self._source_label(source)
        turnin_type = str(turnin.get("type") or "").lower()

        if turnin_type == "crate":
            return (
                f"Bring **{int(turnin.get('amount') or 0)} {str(turnin.get('rarity') or 'common').capitalize()} "
                f"Crate(s)** to turn in."
            )
        if turnin_type == "money":
            return f"Bring **${int(turnin.get('amount') or 0):,}** to turn in."
        if turnin_type == "egg":
            return (
                f"Bring **{int(turnin.get('amount') or 0)}x {turnin.get('egg_name', 'Egg')}** "
                "to turn in."
            )
        if turnin_type == "progress":
            if source == "none":
                return "This quest is ready to turn in once accepted."
            target_text = f" matching **{target_name}**" if target_name else ""
            return f"Complete **{required_count}** {source_label} objective(s){target_text}."
        if str(objective.get("mode") or "").lower() == "key_item":
            target_text = f" matching **{target_name}**" if target_name else ""
            progress_text = (
                f"After **{required_count}** {source_label} clear(s){target_text}, "
                if required_count > 0
                else f"From {source_label} clears{target_text}, "
            )
            quantity_text = (
                f"**{drop_quantity_min}** per drop"
                if drop_quantity_min == drop_quantity_max
                else f"**{drop_quantity_min}-{drop_quantity_max}** per drop"
            )
            return (
                f"{progress_text}recover **{objective.get('key_item_name', 'the key item')}** "
                f"at **{drop_chance_percent:.0f}%** chance, {quantity_text}. "
                f"Turn in **{key_item_required_quantity}**."
            )
        target_text = f" matching **{target_name}**" if target_name else ""
        return f"Complete **{required_count}** {source_label} objective(s){target_text}."

    async def _user_is_gm(self, user_id: int, *, conn=None) -> bool:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            result = await conn.fetchval(
                "SELECT 1 FROM game_masters WHERE user_id = $1",
                user_id,
            )
            return bool(result)
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _user_has_booster_role(self, user_id: int) -> bool:
        booster_guild_id, booster_role_id = self.bot._get_patreon_booster_membership_config()
        if not booster_guild_id or not booster_role_id:
            return False
        try:
            member = await self.bot.http.get_member(booster_guild_id, user_id)
        except discord.NotFound:
            return False
        member_roles = [int(role_id) for role_id in member.get("roles", [])]
        return int(booster_role_id) in member_roles

    def _condition_compare(self, actual, operator: str, expected) -> bool:
        operator = str(operator or ">=").strip().lower()
        if operator in {"=", "==", "is"}:
            return str(actual).casefold() == str(expected).casefold()
        if operator in {"!=", "is_not"}:
            return str(actual).casefold() != str(expected).casefold()
        if operator == "contains":
            return str(expected).casefold() in str(actual).casefold()
        if operator == "not_contains":
            return str(expected).casefold() not in str(actual).casefold()
        if operator in {"in", "not_in"}:
            try:
                contained = actual in expected
            except TypeError:
                contained = str(actual).casefold() in str(expected).casefold()
            return not contained if operator == "not_in" else contained
        if operator == "exists":
            return actual is not None
        if operator == "not_exists":
            return actual is None
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if operator == ">":
            return actual_number > expected_number
        if operator == "<":
            return actual_number < expected_number
        if operator == "<=":
            return actual_number <= expected_number
        return actual_number >= expected_number

    async def _evaluate_campaign_condition(
        self,
        user_id: int,
        condition: dict,
        *,
        conn,
        campaign_key: str = "",
        run_id: str | None = None,
    ) -> tuple[bool, str]:
        condition_type = str(condition.get("type") or "").strip().lower()
        key = str(condition.get("key") or "").strip()
        operator = str(condition.get("operator") or ">=").strip()
        expected = condition.get("value", 1)
        custom_description = str(condition.get("description") or "").strip()

        profile = None
        if condition_type in {
            "level", "class", "god", "race", "money", "guild_member", "badge"
        }:
            profile = await conn.fetchrow(
                'SELECT xp, money, "class", god, race, guild, badges FROM profile WHERE "user"=$1',
                user_id,
            )
            if not profile:
                return False, "Create a character first."

        passed = False
        default_text = f"Requirement not met: {condition_type} {key or expected}."
        if condition_type == "quest_completed":
            passed = await self.is_quest_completed(user_id, normalize_campaign_key(key), conn=conn)
            default_text = f"Complete quest **{key}** first."
        elif condition_type == "campaign_completed":
            status = await conn.fetchval(
                """
                SELECT status FROM fable_campaign_runs
                WHERE user_id=$1 AND campaign_key=$2 AND is_canonical=TRUE
                """,
                user_id,
                normalize_campaign_key(key),
            )
            passed = status == "completed"
            default_text = f"Complete campaign **{key}** first."
        elif condition_type == "campaign_choice":
            choice_campaign_key, _, choice_key = key.partition(":")
            if run_id and normalize_campaign_key(choice_campaign_key) == normalize_campaign_key(campaign_key):
                choices_raw = await conn.fetchval(
                    "SELECT choices_json FROM fable_campaign_runs WHERE run_id=$1",
                    run_id,
                )
            else:
                choices_raw = await conn.fetchval(
                    """
                    SELECT choices_json FROM fable_campaign_runs
                    WHERE user_id=$1 AND campaign_key=$2 AND is_canonical=TRUE
                    """,
                    user_id,
                    normalize_campaign_key(choice_campaign_key),
                )
            choices = self._load_progress(choices_raw)
            passed = self._condition_compare(choices.get(choice_key), operator, expected)
            default_text = f"Your earlier choice in **{choice_campaign_key}** does not open this path."
        elif condition_type == "fable_reward":
            reward_type = normalize_campaign_key(condition.get("field"))
            present = await self.fable_state.has_reward(
                conn,
                user_id=user_id,
                reward_type=reward_type,
                reward_key=key,
            )
            expected_bool = str(expected).strip().lower() not in {
                "0", "false", "no", "none",
            }
            passed = self._condition_compare(present, operator, expected_bool)
            default_text = (
                f"Requires {reward_type.replace('_', ' ')} reward **{key}**."
            )
        elif condition_type in {
            "reputation",
            "faction_standing",
            "faction_membership",
            "system_unlock",
        }:
            factions = self.bot.get_cog("Factions")
            if factions is None:
                return False, "Faction requirements are temporarily unavailable."
            is_replay = bool(
                run_id
                and not await conn.fetchval(
                    "SELECT is_canonical FROM fable_campaign_runs WHERE run_id=$1",
                    run_id,
                )
            )
            if is_replay and condition_type != "system_unlock":
                faction_key = normalize_campaign_key(key)
                field = str(condition.get("field") or "rank").strip().lower()
                if condition_type == "faction_membership":
                    field = "membership"
                    expected = normalize_campaign_key(expected) or "member"
                exists, actual = await self.fable_state.get_state(
                    conn,
                    user_id=user_id,
                    campaign_key=campaign_key,
                    state_key=f"faction.{faction_key}.{field}",
                    run_id=run_id,
                )
                if field == "tier":
                    points_exists, points = await self.fable_state.get_state(
                        conn,
                        user_id=user_id,
                        campaign_key=campaign_key,
                        state_key=f"faction.{faction_key}.points",
                        run_id=run_id,
                    )
                    definition = await factions.service.get_definition(
                        faction_key,
                        conn=conn,
                    )
                    ordered = sorted(
                        definition.tiers,
                        key=lambda tier: tier.minimum_points,
                    )
                    current_tier = ordered[0]
                    for tier in ordered:
                        if int(points or 0) >= tier.minimum_points:
                            current_tier = tier
                    target = next(
                        (
                            tier
                            for tier in ordered
                            if str(expected).casefold()
                            in {tier.key.casefold(), tier.name.casefold()}
                        ),
                        None,
                    )
                    if operator in {"=", "==", "is", "!=", "is_not"}:
                        actual = current_tier.key
                        expected = target.key if target else expected
                    else:
                        actual = current_tier.rank
                        expected = target.rank if target else expected
                    exists = points_exists
                elif not exists:
                    actual = "none" if field == "membership" else 0
                    exists = True
                passed = self._condition_compare(actual, operator, expected)
                default_text = (
                    f"This alternate history requires {field} **{expected}** "
                    f"with **{faction_key.replace('_', ' ').title()}**."
                )
                return passed, custom_description or default_text
            return await factions.evaluate_condition(user_id, condition, conn=conn)
        elif condition_type in STATE_CONDITION_TYPES | MODEL_CONDITION_TYPES:
            state_campaign_key = normalize_campaign_key(
                condition.get("campaign_key") or campaign_key
            )
            if not state_campaign_key:
                return False, "This story-state requirement is missing its campaign context."
            try:
                state_key = (
                    model_state_key(condition_type, key, condition.get("field"))
                    if condition_type in MODEL_CONDITION_TYPES
                    else normalize_state_key(key)
                )
            except FableStateError as exc:
                return False, str(exc)
            try:
                exists, actual = await self.fable_state.get_state(
                    conn,
                    user_id=user_id,
                    campaign_key=state_campaign_key,
                    state_key=state_key,
                    run_id=run_id,
                )
            except FableStateError as exc:
                return False, str(exc)
            passed = compare_state_values(actual, operator, expected, exists=exists)
            default_text = f"Your story has not reached **{state_key}** yet."
        elif condition_type == "level":
            actual = int(rpgtools.xptolevel(profile["xp"]))
            passed = self._condition_compare(actual, operator, expected)
            default_text = f"Reach level **{expected}**."
        elif condition_type in {"class", "god", "race"}:
            actual = profile[condition_type]
            passed = self._condition_compare(actual, operator, key or expected)
            default_text = f"Requires {condition_type} **{key or expected}**."
        elif condition_type == "money":
            passed = self._condition_compare(profile["money"], operator, expected)
            default_text = f"Carry at least **${int(expected):,}**."
        elif condition_type == "guild_member":
            passed = bool(int(profile["guild"] or 0)) == bool(expected)
            default_text = "Join a guild first."
        elif condition_type in {"item_owned", "item_equipped"}:
            equipped_only = condition_type == "item_equipped" or bool(condition.get("equipped"))
            passed = bool(
                await conn.fetchval(
                    """
                    SELECT 1
                    FROM allitems ai
                    JOIN inventory i ON i.item = ai.id
                    WHERE ai.owner = $1
                      AND (lower(ai.name) = lower($2) OR lower(ai.type::text) = lower($2))
                      AND ($3 = FALSE OR i.equipped = TRUE)
                    LIMIT 1
                    """,
                    user_id,
                    key,
                    equipped_only,
                )
            )
            action = "Equip" if equipped_only else "Own"
            default_text = f"{action} the item or weapon type **{key}**."
        elif condition_type in {"pet_owned", "pet_equipped"}:
            equipped_only = condition_type == "pet_equipped" or bool(condition.get("equipped"))
            passed = bool(
                await conn.fetchval(
                    """
                    SELECT 1
                    FROM monster_pets
                    WHERE user_id = $1
                      AND (lower(name) = lower($2) OR lower(default_name) = lower($2))
                      AND ($3 = FALSE OR equipped = TRUE)
                    LIMIT 1
                    """,
                    user_id,
                    key,
                    equipped_only,
                )
            )
            action = "Equip" if equipped_only else "Own"
            default_text = f"{action} the pet **{key}**."
        elif condition_type == "badge":
            badge = Badge.from_string(key)
            if badge and profile["badges"] is not None:
                passed = bool(Badge.from_db(profile["badges"]) & badge)
            default_text = f"Earn the **{Badge.display_name_for(key.upper())}** badge."
        elif condition_type == "unlock":
            if run_id:
                rows = await conn.fetch(
                    "SELECT unlocks_json FROM fable_campaign_runs WHERE run_id=$1",
                    run_id,
                )
            else:
                rows = await conn.fetch(
                    "SELECT unlocks_json FROM fable_campaign_runs WHERE user_id=$1 AND is_canonical=TRUE",
                    user_id,
                )
            unlocks = {
                str(unlock)
                for row in rows
                for unlock in (self._load_progress(row["unlocks_json"]) or [])
            }
            passed = key in unlocks
            default_text = f"Unlock **{key}** first."

        return passed, custom_description or default_text

    async def _evaluate_campaign_conditions(
        self,
        user_id: int,
        conditions: object,
        *,
        conn=None,
        campaign_key: str = "",
        run_id: str | None = None,
    ) -> tuple[bool, str | None]:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            async def evaluate(expression: object) -> tuple[bool, str | None]:
                if expression in (None, [], {}):
                    return True, None
                if isinstance(expression, list):
                    for child in expression:
                        passed, reason = await evaluate(child)
                        if not passed:
                            return False, reason
                    return True, None
                if not isinstance(expression, dict):
                    return False, "This content has an invalid requirement."

                group_keys = {"all", "any", "not"}.intersection(expression)
                if group_keys:
                    if len(group_keys) != 1:
                        return False, "This content has an invalid condition group."
                    group_key = next(iter(group_keys))
                    authored_reason = str(expression.get("description") or "").strip()
                    if group_key == "all":
                        passed, reason = await evaluate(expression.get("all") or [])
                        return passed, None if passed else authored_reason or reason
                    if group_key == "not":
                        passed, _reason = await evaluate(expression.get("not"))
                        return (
                            (False, authored_reason or "A forbidden story condition is active.")
                            if passed
                            else (True, None)
                        )

                    failure_reasons = []
                    for child in expression.get("any") or []:
                        passed, reason = await evaluate(child)
                        if passed:
                            return True, None
                        if reason and reason not in failure_reasons:
                            failure_reasons.append(reason)
                    fallback = "Meet at least one of the available story requirements."
                    return False, authored_reason or "\n".join(failure_reasons[:3]) or fallback

                return await self._evaluate_campaign_condition(
                    user_id,
                    expression,
                    conn=conn,
                    campaign_key=campaign_key,
                    run_id=run_id,
                )

            return await evaluate(conditions)
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _user_meets_custom_access(self, user_id: int, custom_def: dict, *, conn=None) -> tuple[bool, str | None]:
        access = custom_def.get("access") or {}
        factions = self.bot.get_cog("Factions")
        if factions is not None:
            allowed, reason = await factions.check_content_access(
                user_id,
                scope="quest",
                target_key=custom_def.get("quest_key"),
                conn=conn,
            )
            if not allowed:
                return False, reason
        event_flag = self._normalize_event_flag(access.get("event_flag"))
        if event_flag and not self._event_flag_enabled(event_flag):
            return False, f"This quest is disabled until event flag **{self._event_flag_label(event_flag)}** is enabled."
        if access.get("gm_only") and not await self._user_is_gm(user_id, conn=conn):
            return False, "This quest is locked to game masters."
        if access.get("booster_only") and not await self._user_has_booster_role(user_id):
            return False, "This quest is locked to support server boosters."
        patreon_tier = self._normalize_patreon_tier(access.get("patreon_tier"))
        if patreon_tier:
            rank = await self.bot.get_donator_rank_safe(user_id)
            required_rank = getattr(DonatorRank, patreon_tier)
            if not rank or rank < required_rank:
                return False, f"This quest requires Patreon tier **{patreon_tier}** or higher."

        prerequisites = custom_def.get("prerequisites") or []
        for prereq_key in prerequisites:
            if prereq_key and not await self.is_quest_completed(user_id, str(prereq_key), conn=conn):
                return False, f"You must complete **{prereq_key}** first."
        campaign_key = normalize_campaign_key(access.get("campaign_key"))
        campaign_node_key = normalize_campaign_key(access.get("campaign_node_key"))
        access_run_id = None
        if campaign_key and campaign_node_key:
            access_run = await self._selected_campaign_run(
                conn,
                user_id,
                campaign_key=campaign_key,
                statuses=("active", "entering"),
            )
            access_run_id = str(access_run["run_id"]) if access_run else None
            if not access_run or access_run["current_node_key"] != campaign_node_key:
                return False, "This quest is not your current campaign chapter."
        conditions_ok, condition_reason = await self._evaluate_campaign_conditions(
            user_id,
            access.get("conditions") or [],
            conn=conn,
            campaign_key=campaign_key,
            run_id=access_run_id,
        )
        if not conditions_ok:
            return False, condition_reason
        return True, None

    async def _story_quest_visible_to_user(self, user_id: int, quest_def: QuestDef, *, conn=None) -> tuple[bool, str | None]:
        if not self._quest_available(quest_def.key):
            return False, "That quest is not currently available."
        if self._requires_greg_intro_cutscene(quest_def.key):
            return await self._ensure_greg_intro_seen(user_id, conn=conn)
        return True, None

    async def _custom_quest_visible_to_user(self, user_id: int, custom_def: dict, *, conn=None) -> tuple[bool, str | None]:
        if not custom_def or not custom_def.get("is_active"):
            return False, "That quest is not currently active."
        visible, reason = await self._user_meets_custom_access(user_id, custom_def, conn=conn)
        if not visible:
            return visible, reason
        if self._requires_greg_intro_cutscene(custom_def.get("quest_key")):
            return await self._ensure_greg_intro_seen(user_id, conn=conn)
        return True, None

    async def _custom_turnin_status(self, user_id: int, custom_def: dict, progress: dict, *, conn=None) -> tuple[bool, list[str], str]:
        objective = custom_def.get("objective") or {}
        turnin = custom_def.get("turnin") or {}
        turnin_type = str(turnin.get("type") or "progress").lower()
        required_count = max(0, int(objective.get("required_count") or 0))
        current_count = int(progress.get("count", 0))
        progress_ready = current_count >= required_count if required_count > 0 else True
        target_name = str(objective.get("target_name") or "").strip()
        objective_lines = []

        if required_count > 0:
            source_label = self._source_label(objective.get("source"))
            target_text = f" ({target_name})" if target_name else ""
            objective_lines.append(
                f"{source_label} Progress{target_text}: **{current_count} / {required_count}**"
            )

        if turnin_type == "key_item":
            item_key = str(objective.get("key_item_key") or "")
            item_qty = await self._get_key_item_quantity(user_id, item_key, conn=conn)
            required_item_qty = max(1, int(objective.get("key_item_required_quantity") or 1))
            ready = progress_ready and item_qty >= required_item_qty
            objective_lines.append(
                f"{objective.get('key_item_name', 'Key Item')}: **{item_qty} / {required_item_qty}**"
            )
            return ready, objective_lines, "Ready to turn in" if ready else "In progress"

        if turnin_type == "progress":
            ready = progress_ready
            return ready, objective_lines or ["No additional collection required."], "Ready to turn in" if ready else "In progress"

        if turnin_type == "crate":
            rarity = self._normalize_crate_rarity(turnin.get("rarity")) or "common"
            amount = int(turnin.get("amount") or 0)
            crate_count = int(
                await conn.fetchval(
                    f'SELECT crates_{rarity} FROM profile WHERE "user" = $1;',
                    user_id,
                )
                or 0
            )
            objective_lines.append(f"{rarity.capitalize()} Crates: **{crate_count} / {amount}**")
            ready = progress_ready and crate_count >= amount
            return ready, objective_lines, "Ready to turn in" if ready else "In progress"

        if turnin_type == "money":
            amount = int(turnin.get("amount") or 0)
            money = int(
                await conn.fetchval(
                    'SELECT money FROM profile WHERE "user" = $1;',
                    user_id,
                )
                or 0
            )
            objective_lines.append(f"Gold on hand: **${money:,} / ${amount:,}**")
            ready = progress_ready and money >= amount
            return ready, objective_lines, "Ready to turn in" if ready else "In progress"

        if turnin_type == "egg":
            egg_name = str(turnin.get("egg_name") or "").strip()
            amount = int(turnin.get("amount") or 0)
            egg_count = int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM monster_eggs
                    WHERE user_id = $1
                      AND hatched = FALSE
                      AND LOWER(egg_type) = LOWER($2)
                    """,
                    user_id,
                    egg_name,
                )
                or 0
            )
            objective_lines.append(f"{egg_name} Eggs: **{egg_count} / {amount}**")
            ready = progress_ready and egg_count >= amount
            return ready, objective_lines, "Ready to turn in" if ready else "In progress"

        return False, objective_lines or ["Quest requirements are not configured correctly."], "In progress"

    async def _custom_snapshot(self, user_id: int, quest_row, custom_def: dict, *, conn=None) -> dict:
        progress = self._load_progress(quest_row["progress_json"])
        ready, progress_lines, status_label = await self._custom_turnin_status(
            user_id,
            custom_def,
            progress,
            conn=conn,
        )
        if not custom_def.get("is_active"):
            status_label = "Inactive"
        elif not self._event_flag_enabled((custom_def.get("access") or {}).get("event_flag")):
            status_label = "Frozen"
        elif not ready:
            meets_access, _reason = await self._user_meets_custom_access(user_id, custom_def, conn=conn)
            if not meets_access:
                status_label = "Locked"
        turnin = custom_def.get("turnin") or {}
        turnin_type = str(turnin.get("type") or "progress").lower()
        required_item_qty = max(1, int((custom_def.get("objective") or {}).get("key_item_required_quantity") or 1))
        turnin_hint = {
            "key_item": f"Use `$quests turnin {custom_def['quest_key']}` once `{required_item_qty}` matching key item(s) show up in `$inv`.",
            "progress": f"Use `$quests turnin {custom_def['quest_key']}` once the objective is complete.",
            "crate": f"Use `$quests turnin {custom_def['quest_key']}` once you have the required crates.",
            "money": f"Use `$quests turnin {custom_def['quest_key']}` once you have the gold ready.",
            "egg": f"Use `$quests turnin {custom_def['quest_key']}` once the required egg is in your collection.",
        }.get(turnin_type, f"Use `$quests turnin {custom_def['quest_key']}` when ready.")
        custom_turnin_text = str(custom_def.get("turnin_text") or "").strip()
        return {
            "status_label": status_label,
            "objective": self._custom_objective_text(custom_def),
            "progress_lines": progress_lines,
            "ready_to_turn_in": ready,
            "turn_in_text": custom_turnin_text or turnin_hint,
            "current_chapter": custom_def["name"],
        }

    async def _consume_custom_turnin(self, user_id: int, custom_def: dict, *, conn) -> tuple[bool, str | None]:
        objective = custom_def.get("objective") or {}
        turnin = custom_def.get("turnin") or {}
        turnin_type = str(turnin.get("type") or "progress").lower()

        if turnin_type == "progress":
            return True, None
        if turnin_type == "key_item":
            item_key = str(objective.get("key_item_key") or "")
            required_item_qty = max(1, int(objective.get("key_item_required_quantity") or 1))
            consumed = await self._consume_key_item(
                user_id,
                item_key,
                conn=conn,
                quantity_needed=required_item_qty,
            )
            return consumed, None if consumed else "You do not have enough of that key item."
        if turnin_type == "crate":
            rarity = self._normalize_crate_rarity(turnin.get("rarity")) or "common"
            amount = int(turnin.get("amount") or 0)
            current = int(
                await conn.fetchval(
                    f'SELECT crates_{rarity} FROM profile WHERE "user" = $1;',
                    user_id,
                )
                or 0
            )
            if current < amount:
                return False, "You do not have enough crates."
            await conn.execute(
                f'UPDATE profile SET crates_{rarity} = crates_{rarity} - $1 WHERE "user" = $2;',
                amount,
                user_id,
            )
            return True, None
        if turnin_type == "money":
            amount = int(turnin.get("amount") or 0)
            current = int(
                await conn.fetchval(
                    'SELECT money FROM profile WHERE "user" = $1;',
                    user_id,
                )
                or 0
            )
            if current < amount:
                return False, "You do not have enough money."
            await conn.execute(
                'UPDATE profile SET money = money - $1 WHERE "user" = $2;',
                amount,
                user_id,
            )
            return True, None
        if turnin_type == "egg":
            egg_name = str(turnin.get("egg_name") or "").strip()
            amount = int(turnin.get("amount") or 0)
            egg_rows = await conn.fetch(
                """
                SELECT id
                FROM monster_eggs
                WHERE user_id = $1
                  AND hatched = FALSE
                  AND LOWER(egg_type) = LOWER($2)
                ORDER BY id ASC
                LIMIT $3
                """,
                user_id,
                egg_name,
                amount,
            )
            if len(egg_rows) < amount:
                return False, "You do not have enough matching eggs."
            egg_ids = [row["id"] for row in egg_rows]
            await conn.execute(
                "DELETE FROM monster_eggs WHERE id = ANY($1::bigint[]) AND user_id = $2;",
                egg_ids,
                user_id,
            )
            return True, None
        return False, "This quest turn-in is not configured correctly."

    async def _grant_custom_reward(self, user_id: int, custom_def: dict, *, conn) -> str:
        reward = custom_def.get("reward") or {}
        reward_type = str(reward.get("type") or "").lower()
        if reward_type == "bundle":
            granted = []
            for bundled_reward in reward.get("rewards") or []:
                if not isinstance(bundled_reward, dict) or str(bundled_reward.get("type") or "").lower() == "bundle":
                    continue
                granted.append(
                    await self._grant_custom_reward(
                        user_id,
                        {
                            "reward": bundled_reward,
                            "quest_key": custom_def.get("quest_key"),
                        },
                        conn=conn,
                    )
                )
            if not granted:
                raise ValueError("Configured quest reward bundle is empty.")
            return ", ".join(granted)
        if reward_type == "money":
            amount = int(reward.get("amount") or 0)
            await conn.execute(
                'UPDATE profile SET money = money + $1 WHERE "user" = $2;',
                amount,
                user_id,
            )
            return f"**${amount:,}**"
        if reward_type == "crate":
            rarity = self._normalize_crate_rarity(reward.get("rarity")) or "common"
            amount = int(reward.get("amount") or 0)
            await conn.execute(
                f'UPDATE profile SET crates_{rarity} = crates_{rarity} + $1 WHERE "user" = $2;',
                amount,
                user_id,
            )
            return f"**{amount} {rarity.capitalize()} Crate(s)**"
        if reward_type == "item":
            item_type_raw = str(reward.get("item_type") or "")
            item_type = next(
                (
                    item_type
                    for item_type in ItemType
                    if item_type.value.lower() == item_type_raw.strip().lower()
                    or item_type.name.lower() == item_type_raw.strip().lower()
                ),
                None,
            )
            if item_type is None:
                raise ValueError("Configured quest item reward has an invalid item type.")
            stat_value = int(reward.get("stat") or 0)
            await self.bot.create_item(
                name=str(reward.get("name") or "Quest Reward"),
                value=int(reward.get("value") or 0),
                type_=item_type.value,
                damage=0 if item_type == ItemType.Shield else stat_value,
                armor=stat_value if item_type == ItemType.Shield else 0,
                owner=user_id,
                hand=item_type.get_hand().value,
                element=str(reward.get("element") or "Light"),
                equipped=False,
                conn=conn,
            )
            return f"**{reward.get('name', 'Quest Reward')}**"
        if reward_type == "egg":
            monster = await self._find_monster_by_name(str(reward.get("monster_name") or ""))
            if not monster:
                raise ValueError("Configured quest egg reward points at an unknown monster.")

            egg_hatch_time = datetime.utcnow() + timedelta(minutes=2160)
            await conn.execute(
                """
                INSERT INTO monster_eggs (
                    user_id, egg_type, hp, attack, defense, element, url, hatch_time,
                    "IV", hp_iv, attack_iv, defense_iv
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);
                """,
                user_id,
                monster["name"],
                int(monster.get("hp") or 0),
                int(monster.get("attack") or 0),
                int(monster.get("defense") or 0),
                str(monster.get("element") or "Nature"),
                str(monster.get("url") or ""),
                egg_hatch_time,
                0,
                0,
                0,
                0,
            )
            return f"**{monster['name']} Egg**"
        if reward_type in COLLECTION_REWARD_TYPES:
            reward_key = normalize_campaign_key(reward.get("key"))
            if not reward_key:
                raise ValueError(f"Configured {reward_type} reward needs a key.")
            display_name = str(
                reward.get("name")
                or reward.get("display_name")
                or reward_key.replace("_", " ").title()
            )
            source = f"quest:{custom_def.get('quest_key') or 'custom'}"
            if reward_type == "system_unlock":
                await self.grant_system_unlock(
                    user_id,
                    reward_key,
                    source=source,
                    metadata={"reward": reward},
                    conn=conn,
                )
            await self.fable_state.grant_reward(
                conn,
                user_id=user_id,
                reward_type=reward_type,
                reward_key=reward_key,
                display_name=display_name,
                source=source,
                metadata={"reward": reward},
            )
            return f"**{display_name}**"
        if reward_type == "none":
            return "**no material reward**"
        raise ValueError("This quest reward is not configured correctly.")

    async def _resolve_quest_definition(self, quest_key: str, *, conn=None) -> tuple[QuestDef | None, dict | None]:
        quest_def = QUEST_DEFINITIONS.get(quest_key)
        if quest_def:
            return quest_def, None
        custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)
        return None, custom_def

    def _new_story_progress(self) -> dict:
        return {
            "total_pve_wins": 0,
            "step_pve_wins": 0,
            "total_high_tier_wins": 0,
            "step_high_tier_wins": 0,
        }

    def _new_custom_progress(self) -> dict:
        return {
            "count": 0,
        }

    async def _accept_quest_for_user(self, user_id: int, raw_quest_key: str) -> dict:
        normalized_input = str(raw_quest_key).strip()
        quest_key = normalized_input.lower()
        if quest_key not in QUEST_DEFINITIONS:
            quest_key = self._normalize_custom_quest_key(normalized_input)

        async with self.bot.pool.acquire() as conn:
            quest_def, custom_def = await self._resolve_quest_definition(
                quest_key,
                conn=conn,
            )
            if not quest_def and not custom_def:
                raise ValueError("That quest does not exist.")

            if quest_def:
                visible, reason = await self._story_quest_visible_to_user(
                    user_id,
                    quest_def,
                    conn=conn,
                )
                if not visible:
                    raise ValueError(reason or "That quest is not currently available.")
            else:
                visible, reason = await self._custom_quest_visible_to_user(
                    user_id,
                    custom_def,
                    conn=conn,
                )
                if not visible:
                    raise ValueError(reason or "That quest is not currently available.")

            existing = await conn.fetchrow(
                """
                SELECT status, completion_count
                FROM player_quests
                WHERE user_id = $1 AND quest_key = $2
                """,
                user_id,
                quest_key,
            )
            if existing:
                if existing["status"] == "active":
                    raise ValueError("You already accepted that quest.")
                if (
                    (quest_def or (custom_def and not custom_def["repeatable"]))
                    and (
                        existing["status"] == "completed"
                        or int(existing["completion_count"] or 0) > 0
                    )
                ):
                    raise ValueError("You have already completed that quest.")

            if quest_def:
                progress = self._new_story_progress()
                category = quest_def.category
                title = quest_def.name
                description = quest_def.start_text
                objective_text = quest_def.steps[0].objective
                reward_text = quest_def.reward_text
                footer_text = f"Turn in progress with $quests turnin {quest_def.key}"
                accept_cutscene_key = ""
                quest_key = quest_def.key
            else:
                progress = self._new_custom_progress()
                category = custom_def["category"]
                title = custom_def["name"]
                description = custom_def["offer_text"] or custom_def["short_description"]
                objective_text = self._custom_objective_text(custom_def)
                reward_text = self._custom_reward_text(custom_def)
                footer_text = f"Turn in progress with $quests turnin {custom_def['quest_key']}"
                accept_cutscene_key = custom_def.get("accept_cutscene_key", "")
                quest_key = custom_def["quest_key"]

            await conn.execute(
                """
                INSERT INTO player_quests (user_id, quest_key, category, status, step_index, completion_count, progress_json, started_at)
                VALUES ($1, $2, $3, 'active', 0, 0, $4, NOW())
                ON CONFLICT (user_id, quest_key)
                DO UPDATE SET category = EXCLUDED.category,
                              status = 'active',
                              step_index = 0,
                              progress_json = EXCLUDED.progress_json,
                              started_at = NOW(),
                              completed_at = NULL,
                              turned_in_at = NULL
                """,
                user_id,
                quest_key,
                category,
                self._dump_progress(progress),
            )

        return {
            "quest_key": quest_key,
            "title": title,
            "description": description,
            "objective_text": objective_text,
            "reward_text": reward_text,
            "footer_text": footer_text,
            "accept_cutscene_key": accept_cutscene_key,
        }

    async def _send_quest_accept_messages(
        self,
        ctx,
        accept_data: dict,
        *,
        wait_for_cutscene: bool = False,
    ) -> bool:
        embed = discord.Embed(
            title=f"Quest Accepted: {accept_data['title']}",
            description=accept_data["description"],
            color=0x5D2E12,
        )
        embed.add_field(
            name="Current Objective",
            value=accept_data["objective_text"],
            inline=False,
        )
        embed.add_field(name="Reward", value=accept_data["reward_text"], inline=False)
        embed.set_footer(text=accept_data["footer_text"])
        await ctx.send(embed=embed)

        accept_cutscene_key = str(accept_data.get("accept_cutscene_key") or "").strip()
        if accept_cutscene_key:
            return await self.play_cutscene(
                ctx,
                accept_cutscene_key,
                wait_for_completion=wait_for_cutscene,
            )
        return True

    def _parse_bool(self, raw: str | None) -> bool | None:
        if raw is None:
            return None
        value = str(raw).strip().lower()
        if value in {"on", "true", "enable", "enabled", "1", "yes", "y"}:
            return True
        if value in {"off", "false", "disable", "disabled", "0", "no", "n"}:
            return False
        return None

    async def _ensure_custom_quest_exists(self, quest_key: str, *, conn=None) -> dict:
        custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)
        if not custom_def:
            raise ValueError("That custom quest does not exist.")
        return custom_def

    async def _update_custom_quest_fields(self, quest_key: str, fields: dict, *, conn, created_by: int | None = None) -> dict:
        existing = await self._fetch_custom_quest_definition(quest_key, conn=conn)
        if not existing:
            await conn.execute(
                """
                INSERT INTO custom_quests (
                    quest_key, name, category, short_description, offer_text, turnin_text, objective_json,
                    turnin_json, reward_json, access_json, prerequisite_keys_json,
                    accept_cutscene_key, turnin_cutscene_key, repeatable, is_active, created_by, updated_at
                )
                VALUES ($1, $2, 'General', '', '', '', '{}', '{}', '{}', '{}', '[]', NULL, NULL, FALSE, FALSE, $3, NOW())
                ON CONFLICT (quest_key) DO NOTHING
                """,
                quest_key,
                quest_key.replace("_", " ").title(),
                created_by or 0,
            )
        if not fields:
            return await self._ensure_custom_quest_exists(quest_key, conn=conn)
        assignments = []
        values = []
        for index, (column, value) in enumerate(fields.items(), start=2):
            assignments.append(f"{column} = ${index}")
            values.append(value)
        assignments.append("updated_at = NOW()")
        await conn.execute(
            f"""
            UPDATE custom_quests
            SET {', '.join(assignments)}
            WHERE quest_key = $1
            """,
            quest_key,
            *values,
        )
        return await self._ensure_custom_quest_exists(quest_key, conn=conn)

    def _build_custom_quest_admin_embed(self, custom_def: dict) -> discord.Embed:
        objective = custom_def.get("objective") or {}
        turnin = custom_def.get("turnin") or {}
        access = custom_def.get("access") or {}
        prerequisites = custom_def.get("prerequisites") or []

        embed = discord.Embed(
            title=f"GM Quest: {custom_def['name']}",
            description=custom_def["short_description"] or "No journal description set.",
            color=0x5D2E12,
        )
        embed.add_field(name="Key", value=custom_def["quest_key"], inline=True)
        embed.add_field(name="Category", value=custom_def["category"], inline=True)
        embed.add_field(
            name="State",
            value=("Active" if custom_def["is_active"] else "Draft")
            + (" • Repeatable" if custom_def["repeatable"] else " • One-time"),
            inline=True,
        )
        embed.add_field(
            name="Offer Text",
            value=custom_def["offer_text"] or "Not set.",
            inline=False,
        )
        embed.add_field(
            name="Turn-In Text",
            value=custom_def.get("turnin_text") or "Auto-generated from turn-in requirements.",
            inline=False,
        )
        embed.add_field(
            name="Objective",
            value=self._custom_objective_text(custom_def),
            inline=False,
        )
        embed.add_field(
            name="Turn In",
            value=json.dumps(turnin, indent=2)[:1000] if turnin else "Not set.",
            inline=False,
        )
        embed.add_field(
            name="Reward",
            value=self._custom_reward_text(custom_def),
            inline=False,
        )
        access_lines = []
        if access.get("event_flag"):
            access_lines.append(f"Event Flag: {self._event_flag_label(access.get('event_flag'))}")
        if access.get("gm_only"):
            access_lines.append("GM only")
        if access.get("booster_only"):
            access_lines.append("Support booster only")
        if access.get("patreon_tier"):
            access_lines.append(f"Patreon: {access['patreon_tier']}")
        if not access_lines:
            access_lines.append("Open to everyone")
        if prerequisites:
            access_lines.append("Prerequisites: " + ", ".join(str(key) for key in prerequisites))
        embed.add_field(name="Access", value="\n".join(access_lines), inline=False)
        embed.add_field(
            name="Cutscenes",
            value=(
                f"Accept: `{custom_def.get('accept_cutscene_key') or 'none'}`\n"
                f"Turn In: `{custom_def.get('turnin_cutscene_key') or 'none'}`"
            ),
            inline=False,
        )
        return embed

    def _create_story_pages(self, story_pages, footer_prefix: str):
        pages = []
        page_total = len(story_pages)

        for index, page in enumerate(story_pages, start=1):
            description = str(page.get("text") or "")
            subtitle = str(page.get("subtitle") or "").strip()
            if subtitle:
                description = f"**{subtitle}**\n\n{description}"
            embed = discord.Embed(
                title=str(page.get("title") or footer_prefix or "Story Scene"),
                description=description,
                color=0x1F0D0D,
            )
            image_url = str(page.get("image") or "").strip()
            if image_url:
                embed.set_image(url=image_url)
            embed.set_footer(text=f"{footer_prefix} {index}/{page_total}")
            pages.append(embed)

        return pages

    def _create_cutscene_pages(self, cutscene_pages, footer_prefix: str, ctx):
        """Render narrative pages and Battle Tower-style dialogue in one scene."""
        pages = []
        page_total = len(cutscene_pages)
        author = ctx.author
        player_name = str(
            getattr(author, "display_name", None)
            or getattr(author, "name", "Player")
        )
        display_avatar = getattr(author, "display_avatar", None)
        avatar_url = str(getattr(display_avatar, "url", "") or "")

        for index, page in enumerate(cutscene_pages, start=1):
            is_dialogue = (
                str(page.get("presentation") or "").strip().lower() == "dialogue"
                or bool(str(page.get("speaker") or "").strip())
            )
            if not is_dialogue:
                story_page = self._create_story_pages([page], footer_prefix)[0]
                story_page.set_footer(text=f"{footer_prefix} {index}/{page_total}")
                pages.append(story_page)
                continue

            speaker = str(page.get("speaker") or page.get("title") or "Storyteller")
            text = str(page.get("text") or "")
            speaker = speaker.replace("{PLAYER}", player_name)
            text = text.replace("{PLAYER}", player_name)
            speaker = re.sub(r"\bPLAYER\b", player_name, speaker)
            text = re.sub(r"\bPLAYER\b", player_name, text)
            thumbnail = str(page.get("thumbnail") or page.get("avatar") or "").strip()
            if thumbnail == "PLAYER_AVATAR":
                thumbnail = avatar_url

            embed = discord.Embed(
                title=speaker,
                description=text,
                color=0x003366,
            )
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            embed.set_footer(text=f"{footer_prefix} {index}/{page_total}")
            pages.append(embed)

        return pages

    async def _fetch_quest_row(self, user_id: int, quest_key: str, *, conn=None):
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            return await conn.fetchrow(
                """
                SELECT user_id, quest_key, category, status, step_index, completion_count,
                       progress_json, started_at, completed_at, turned_in_at
                FROM player_quests
                WHERE user_id = $1 AND quest_key = $2
                """,
                user_id,
                quest_key,
            )
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _get_greg_skulls(self, user_id: int, *, conn=None) -> int:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            try:
                value = await conn.fetchval(
                    """
                    SELECT skulls
                    FROM greg_event_players
                    WHERE user_id = $1
                    """,
                    user_id,
                )
            except Exception:
                value = 0
            return int(value or 0)
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _get_key_item_quantity(self, user_id: int, item_key: str, *, conn=None) -> int:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            value = await conn.fetchval(
                """
                SELECT quantity
                FROM player_key_items
                WHERE user_id = $1 AND item_key = $2
                """,
                user_id,
                item_key,
            )
            return int(value or 0)
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _grant_key_item(self, user_id: int, item_key: str, source_quest: str, *, conn, quantity: int = 1):
        quantity = max(1, int(quantity or 1))
        await conn.execute(
            """
            INSERT INTO player_key_items (user_id, item_key, quantity, source_quest, obtained_at)
            VALUES ($1, $2, $4, $3, NOW())
            ON CONFLICT (user_id, item_key)
            DO UPDATE SET quantity = player_key_items.quantity + $4,
                          source_quest = EXCLUDED.source_quest,
                          obtained_at = NOW()
            """,
            user_id,
            item_key,
            source_quest,
            quantity,
        )

    async def _consume_key_item(self, user_id: int, item_key: str, *, conn, quantity_needed: int = 1) -> bool:
        quantity_needed = max(1, int(quantity_needed or 1))
        quantity = await conn.fetchval(
            """
            SELECT quantity
            FROM player_key_items
            WHERE user_id = $1 AND item_key = $2
            FOR UPDATE
            """,
            user_id,
            item_key,
        )
        quantity = int(quantity or 0)
        if quantity < quantity_needed:
            return False
        if quantity == quantity_needed:
            await conn.execute(
                """
                DELETE FROM player_key_items
                WHERE user_id = $1 AND item_key = $2
                """,
                user_id,
                item_key,
            )
        else:
            await conn.execute(
                """
                UPDATE player_key_items
                SET quantity = quantity - $3,
                    obtained_at = NOW()
                WHERE user_id = $1 AND item_key = $2
                """,
                user_id,
                item_key,
                quantity_needed,
            )
        return True

    def _step_requirements_met(
        self,
        step: QuestStepDef,
        *,
        progress: dict,
        greg_skulls: int,
    ) -> bool:
        if step.required_pve_wins and int(progress.get("step_pve_wins", 0)) < step.required_pve_wins:
            return False
        if step.required_high_tier_wins and int(progress.get("step_high_tier_wins", 0)) < step.required_high_tier_wins:
            return False
        if step.required_greg_skulls and greg_skulls < step.required_greg_skulls:
            return False
        return True

    async def _quest_step_snapshot(self, user_id: int, quest_row, quest_def: QuestDef, *, conn=None) -> dict:
        progress = self._load_progress(quest_row["progress_json"])
        step_index = int(quest_row["step_index"] or 0)
        if step_index >= len(quest_def.steps):
            return {
                "status_label": "Completed",
                "objective": "This quest has been completed.",
                "key_item_name": None,
                "has_key_item": False,
                "progress_lines": [],
                "ready_to_turn_in": False,
                "current_chapter": None,
                "turn_in_text": "Already completed.",
            }

        step = quest_def.steps[step_index]
        greg_skulls = await self._get_greg_skulls(user_id, conn=conn)
        item_qty = await self._get_key_item_quantity(user_id, step.key_item_key, conn=conn)
        ready_to_turn_in = item_qty > 0

        progress_lines = []
        if step.required_greg_skulls:
            progress_lines.append(
                f"Greg Skulls: **{greg_skulls} / {step.required_greg_skulls}**"
            )
        if step.required_pve_wins:
            progress_lines.append(
                f"PvE Wins: **{int(progress.get('step_pve_wins', 0))} / {step.required_pve_wins}**"
            )
        if step.required_high_tier_wins:
            progress_lines.append(
                f"Tier {step.high_tier_min}+ PvE Wins: **{int(progress.get('step_high_tier_wins', 0))} / {step.required_high_tier_wins}**"
            )
        progress_lines.append(
            f"{step.key_item_name}: **{'Ready to turn in' if ready_to_turn_in else 'Not yet recovered'}**"
        )

        if quest_row["status"] == "completed":
            status_label = "Completed"
        elif ready_to_turn_in:
            status_label = "Ready to turn in"
        elif not self._quest_available(quest_def.key):
            status_label = "Frozen"
        else:
            status_label = "In progress"

        return {
            "status_label": status_label,
            "objective": step.objective,
            "key_item_name": step.key_item_name,
            "has_key_item": ready_to_turn_in,
            "progress_lines": progress_lines,
            "ready_to_turn_in": ready_to_turn_in,
            "current_chapter": step.title,
            "turn_in_text": (
                f"Use `$quests turnin {quest_def.key}` once **{step.key_item_name}** shows up in `$inv`."
            ),
        }

    async def is_quest_completed(self, user_id: int, quest_key: str, *, conn=None) -> bool:
        row = await self._fetch_quest_row(user_id, quest_key, conn=conn)
        return bool(
            row
            and (
                row["status"] == "completed"
                or int(row["completion_count"] or 0) > 0
            )
        )

    async def get_key_items_for_display(self, user_id: int, *, conn=None) -> list[dict]:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            rows = await conn.fetch(
                """
                SELECT item_key, quantity, source_quest, obtained_at
                FROM player_key_items
                WHERE user_id = $1 AND quantity > 0
                ORDER BY obtained_at ASC, item_key ASC
                """,
                user_id,
            )
            results = []
            for row in rows:
                definition = KEY_ITEM_DEFINITIONS.get(str(row["item_key"]))
                if not definition and row["source_quest"]:
                    custom_def = await self._fetch_custom_quest_definition(
                        str(row["source_quest"]),
                        conn=conn,
                    )
                    objective = (custom_def or {}).get("objective") or {}
                    if (
                        custom_def
                        and str(objective.get("mode") or "").lower() == "key_item"
                        and str(objective.get("key_item_key") or "") == str(row["item_key"])
                    ):
                        definition = {
                            "name": str(objective.get("key_item_name") or row["item_key"]),
                            "description": str(objective.get("key_item_description") or "Quest item."),
                            "quest_key": custom_def["quest_key"],
                            "quest_name": custom_def["name"],
                        }
                if not definition:
                    continue
                results.append(
                    {
                        "key": row["item_key"],
                        "name": definition["name"],
                        "description": definition["description"],
                        "quantity": int(row["quantity"] or 0),
                        "quest_key": definition["quest_key"],
                        "quest_name": definition["quest_name"],
                    }
                )
            return results
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _get_journal_entries(self, user_id: int, *, conn=None) -> list[dict]:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            rows = await conn.fetch(
                """
                SELECT user_id, quest_key, category, status, step_index, completion_count,
                       progress_json, started_at, completed_at, turned_in_at
                FROM player_quests
                WHERE user_id = $1 AND status = ANY($2::text[])
                ORDER BY category ASC, started_at ASC
                """,
                user_id,
                ["active"],
            )

            entries = []
            for row in rows:
                quest_key = str(row["quest_key"])
                quest_def = QUEST_DEFINITIONS.get(quest_key)
                custom_def = None
                if quest_def:
                    snapshot = await self._quest_step_snapshot(
                        user_id,
                        row,
                        quest_def,
                        conn=conn,
                    )
                    name = quest_def.name
                    category = quest_def.category
                    short_description = quest_def.short_description
                    reward_text = quest_def.reward_text
                else:
                    custom_def = await self._fetch_custom_quest_definition(
                        quest_key,
                        conn=conn,
                    )
                    if not custom_def:
                        continue
                    snapshot = await self._custom_snapshot(
                        user_id,
                        row,
                        custom_def,
                        conn=conn,
                    )
                    name = custom_def["name"]
                    category = custom_def["category"]
                    short_description = custom_def["short_description"]
                    reward_text = self._custom_reward_text(custom_def)
                entries.append(
                    {
                        "row": row,
                        "quest_def": quest_def,
                        "custom_def": custom_def,
                        "snapshot": snapshot,
                        "quest_key": quest_key,
                        "name": name,
                        "category": category,
                        "short_description": short_description,
                        "reward_text": reward_text,
                    }
                )
            return entries
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _get_available_greg_quest_entries(self, user_id: int, *, conn=None) -> list[dict]:
        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            owned_rows = await conn.fetch(
                """
                SELECT quest_key, status, completion_count
                FROM player_quests
                WHERE user_id = $1
                """,
                user_id,
            )
            custom_defs = await self._fetch_custom_quest_definitions(
                conn=conn,
                active_only=True,
            )
            owned_statuses = {
                str(row["quest_key"]): {
                    "status": str(row["status"]),
                    "completion_count": int(row["completion_count"] or 0),
                }
                for row in owned_rows
            }

            entries = []
            for quest_def in QUEST_DEFINITIONS.values():
                if not self._requires_greg_intro_cutscene(quest_def.key):
                    continue
                quest_state = owned_statuses.get(quest_def.key)
                if quest_state and (
                    quest_state["status"] == "active"
                    or quest_state["completion_count"] > 0
                ):
                    continue
                visible, _reason = await self._story_quest_visible_to_user(
                    user_id,
                    quest_def,
                    conn=conn,
                )
                if not visible:
                    continue
                entries.append(
                    {
                        "quest_key": quest_def.key,
                        "name": quest_def.name,
                        "category": quest_def.category,
                        "short_description": quest_def.short_description,
                        "offer_text": quest_def.start_text,
                        "objective_text": quest_def.steps[0].objective,
                        "reward_text": quest_def.reward_text,
                        "repeatable": False,
                    }
                )

            for custom_def in custom_defs:
                quest_key = str(custom_def["quest_key"])
                if not self._requires_greg_intro_cutscene(quest_key):
                    continue
                quest_state = owned_statuses.get(quest_key)
                if quest_state and quest_state["status"] == "active":
                    continue
                if (
                    quest_state
                    and quest_state["completion_count"] > 0
                    and not custom_def["repeatable"]
                ):
                    continue
                visible, _reason = await self._custom_quest_visible_to_user(
                    user_id,
                    custom_def,
                    conn=conn,
                )
                if not visible:
                    continue
                entries.append(
                    {
                        "quest_key": quest_key,
                        "name": custom_def["name"],
                        "category": custom_def["category"],
                        "short_description": custom_def["short_description"],
                        "offer_text": custom_def["offer_text"] or custom_def["short_description"],
                        "objective_text": self._custom_objective_text(custom_def),
                        "reward_text": self._custom_reward_text(custom_def),
                        "repeatable": bool(custom_def["repeatable"]),
                    }
                )

            return sorted(
                entries,
                key=lambda entry: (entry["category"].lower(), entry["name"].lower()),
            )
        finally:
            if local:
                await self.bot.pool.release(conn)

    async def _greg_quest_board_empty_text(self, user_id: int, *, conn=None) -> str:
        intro_seen = await self.has_seen_cutscene(
            user_id,
            self.GREG_INTRO_CUTSCENE_KEY,
            conn=conn,
        )
        if self._greg_mode_enabled() and not intro_seen:
            return (
                "No Greg quests are visible yet.\n\n"
                "Watch the Gregapocalypse intro with `$greg` first."
            )
        return "No Greg quests are available right now."

    async def _build_greg_quest_board(self, ctx, *, has_active_entries: bool = False):
        entries = await self._get_available_greg_quest_entries(ctx.author.id)
        empty_text = await self._greg_quest_board_empty_text(ctx.author.id)
        view = QuestBoardView(
            cog=self,
            ctx=ctx,
            entries=entries,
            empty_text=empty_text,
            has_active_entries=has_active_entries,
        )
        return view.build_embed(), view

    async def _build_journal_display(self, ctx):
        entries = await self._get_journal_entries(ctx.author.id)
        if not entries:
            return None, None
        view = QuestJournalView(cog=self, ctx=ctx, entries=entries)
        return view.build_embed(), view

    async def _build_no_active_quest_summary(self, user_id: int) -> discord.Embed:
        async with self.bot.pool.acquire() as conn:
            owned_rows = await conn.fetch(
                """
                SELECT quest_key, status, completion_count
                FROM player_quests
                WHERE user_id = $1
                """,
                user_id,
            )
            custom_defs = await self._fetch_custom_quest_definitions(
                conn=conn,
                active_only=True,
            )

            owned_statuses = {
                str(row["quest_key"]): {
                    "status": str(row["status"]),
                    "completion_count": int(row["completion_count"] or 0),
                }
                for row in owned_rows
            }

            available = []
            completed = []
            for quest_def in QUEST_DEFINITIONS.values():
                quest_state = owned_statuses.get(quest_def.key)
                if quest_state and quest_state["completion_count"] > 0:
                    completed.append(f"**{quest_def.name}**")
                    continue
                if quest_state and quest_state["status"] == "active":
                    continue
                visible, _reason = await self._story_quest_visible_to_user(
                    user_id,
                    quest_def,
                    conn=conn,
                )
                if not visible:
                    continue
                available.append(
                    f"**{quest_def.name}**\n{quest_def.short_description}\nStart with `$quests accept {quest_def.key}`."
                )

            for custom_def in custom_defs:
                quest_state = owned_statuses.get(custom_def["quest_key"])
                if (
                    quest_state
                    and quest_state["completion_count"] > 0
                    and not custom_def["repeatable"]
                ):
                    completed.append(f"**{custom_def['name']}**")
                    continue
                if quest_state and quest_state["status"] == "active":
                    continue
                visible, _reason = await self._custom_quest_visible_to_user(
                    user_id,
                    custom_def,
                    conn=conn,
                )
                if not visible:
                    continue
                repeatable_text = "Repeatable. " if custom_def["repeatable"] else ""
                available.append(
                    f"**{custom_def['name']}**\n{custom_def['short_description']}\n"
                    f"{repeatable_text}Start with `$quests accept {custom_def['quest_key']}`."
                )

        embed = discord.Embed(
            title="Quest Journal",
            description="You have no accepted or ongoing quests right now.",
            color=0x3E2617,
        )
        if completed:
            embed.add_field(
                name="Completed",
                value="\n".join(completed),
                inline=False,
            )
        if available:
            embed.add_field(
                name="Available",
                value="\n\n".join(available),
                inline=False,
            )
        else:
            embed.add_field(
                name="Available",
                value="No event quests are currently available.",
                inline=False,
            )
        embed.set_footer(
            text="Use $quests accept <quest> to begin one, or $quests greg for the Greg dropdown."
        )
        return embed

    async def _process_custom_source_completion(
        self,
        ctx,
        source: str,
        *,
        candidate_names: tuple[str | None, ...] = (),
        metadata: dict | None = None,
    ) -> None:
        notifications: list[tuple[dict, dict, int]] = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                event_metadata = metadata if isinstance(metadata, dict) else {}
                event_id = str(event_metadata.get("event_id") or "").strip()
                if event_id:
                    inserted_event = await conn.fetchval(
                        """
                        INSERT INTO quest_objective_events (
                            user_id, source, event_id, metadata_json, occurred_at
                        ) VALUES ($1,$2,$3,$4,NOW())
                        ON CONFLICT (user_id, source, event_id) DO NOTHING
                        RETURNING event_id
                        """,
                        ctx.author.id,
                        source,
                        event_id,
                        json.dumps(event_metadata, allow_nan=False, sort_keys=True),
                    )
                    if not inserted_event:
                        return
                rows = await conn.fetch(
                    """
                    SELECT pq.progress_json, pq.completion_count, cq.quest_key, cq.name, cq.category,
                           cq.short_description, cq.offer_text, cq.turnin_text, cq.objective_json, cq.turnin_json,
                           cq.reward_json, cq.access_json, cq.prerequisite_keys_json,
                           cq.accept_cutscene_key, cq.turnin_cutscene_key, cq.repeatable,
                           cq.is_active, cq.created_by, cq.updated_at
                    FROM player_quests pq
                    JOIN custom_quests cq ON cq.quest_key = pq.quest_key
                    WHERE pq.user_id = $1
                      AND pq.status = 'active'
                      AND cq.is_active = TRUE
                    """,
                    ctx.author.id,
                )

                for row in rows:
                    custom_def = self._load_custom_quest_definition(row)
                    meets_access, _reason = await self._user_meets_custom_access(
                        ctx.author.id,
                        custom_def,
                        conn=conn,
                    )
                    if not meets_access:
                        continue

                    objective = custom_def.get("objective") or {}
                    if self._normalize_source(objective.get("source")) != source:
                        continue
                    if not self._match_name_filter(
                        objective.get("target_name"),
                        *candidate_names,
                    ):
                        continue
                    access = custom_def.get("access") or {}
                    campaign_key = normalize_campaign_key(access.get("campaign_key"))
                    campaign_node_key = normalize_campaign_key(access.get("campaign_node_key"))
                    if campaign_key and campaign_node_key:
                        campaign = await self._fetch_campaign_definition(
                            campaign_key,
                            user_id=ctx.author.id,
                            conn=conn,
                        )
                        campaign_node = node_by_id(campaign or {}, campaign_node_key)
                        encounter = (campaign_node or {}).get("encounter") or {}
                        party = encounter.get("party") or {}
                        party_size = int((metadata or {}).get("party_size") or 1)
                        minimum_party = max(1, int(party.get("min") or 1))
                        maximum_party = max(minimum_party, int(party.get("max") or minimum_party))
                        if not minimum_party <= party_size <= maximum_party:
                            continue

                    progress = self._load_progress(row["progress_json"])
                    if bool(objective.get("distinct_targets", False)):
                        target_key = normalize_campaign_key(
                            event_metadata.get("target_key")
                            or next(
                                (
                                    candidate
                                    for candidate in candidate_names
                                    if str(candidate or "").strip()
                                ),
                                "",
                            )
                        )
                        if not target_key:
                            logger.warning(
                                "Distinct-target quest %s received an event without a target key",
                                custom_def["quest_key"],
                            )
                            continue
                        seen_targets = [
                            normalize_campaign_key(value)
                            for value in progress.get("distinct_targets") or []
                            if normalize_campaign_key(value)
                        ]
                        if target_key in seen_targets:
                            continue
                        seen_targets.append(target_key)
                        progress["distinct_targets"] = seen_targets
                    progress["count"] = int(progress.get("count", 0)) + 1

                    await conn.execute(
                        """
                        UPDATE player_quests
                        SET progress_json = $3
                        WHERE user_id = $1 AND quest_key = $2
                        """,
                        ctx.author.id,
                        custom_def["quest_key"],
                        self._dump_progress(progress),
                    )

                    if str(objective.get("mode") or "").lower() != "key_item":
                        continue

                    required_count = int(objective.get("required_count") or 0)
                    existing_qty = await self._get_key_item_quantity(
                        ctx.author.id,
                        str(objective.get("key_item_key") or ""),
                        conn=conn,
                    )
                    required_item_qty = max(1, int(objective.get("key_item_required_quantity") or 1))
                    if existing_qty >= required_item_qty or progress["count"] < required_count:
                        continue

                    drop_chance_percent = max(0.0, min(100.0, float(objective.get("drop_chance_percent") or 100)))
                    if drop_chance_percent <= 0:
                        continue
                    if random.uniform(0, 100) > drop_chance_percent:
                        continue

                    drop_quantity_min = max(1, int(objective.get("drop_quantity_min") or 1))
                    drop_quantity_max = max(drop_quantity_min, int(objective.get("drop_quantity_max") or drop_quantity_min))
                    quantity_found = random.randint(drop_quantity_min, drop_quantity_max)
                    quantity_found = min(quantity_found, required_item_qty - existing_qty)
                    if quantity_found <= 0:
                        continue

                    await self._grant_key_item(
                        ctx.author.id,
                        str(objective.get("key_item_key") or ""),
                        custom_def["quest_key"],
                        conn=conn,
                        quantity=quantity_found,
                    )
                    notifications.append((custom_def, objective, quantity_found))

        for custom_def, objective, quantity_found in notifications:
            embed = discord.Embed(
                title=f"Key Item Found: {objective.get('key_item_name', 'Quest Item')}",
                description=str(objective.get("key_item_description") or "A quest item has been recovered."),
                color=0x6B1717,
            )
            embed.add_field(
                name="Quest Update",
                value=(
                    f"You recovered **{quantity_found}x** {objective.get('key_item_name', 'Quest Item')}.\n\n"
                    f"Check `$inv`, then use `$quests turnin {custom_def['quest_key']}`."
                ),
                inline=False,
            )
            await ctx.send(embed=embed)

    async def process_external_source_completion(
        self,
        ctx,
        source: str,
        *,
        candidate_names: tuple[str | None, ...] = (),
        metadata: dict | None = None,
    ) -> bool:
        return await self.process_external_source_completion_for_user(
            ctx,
            getattr(ctx, "author", None),
            source,
            candidate_names=candidate_names,
            metadata=metadata,
        )

    async def process_external_source_completion_for_user(
        self,
        ctx,
        user,
        source: str,
        *,
        candidate_names: tuple[str | None, ...] = (),
        metadata: dict | None = None,
    ) -> bool:
        normalized_source = self._normalize_source(source)
        if normalized_source is None or normalized_source == "none":
            return False
        if user is None or getattr(user, "id", None) is None:
            return False
        proxy_ctx = ctx
        if getattr(ctx, "author", None) is not user:
            proxy_ctx = SimpleNamespace(author=user, send=ctx.send)
        await self._process_custom_source_completion(
            proxy_ctx,
            normalized_source,
            candidate_names=candidate_names,
            metadata=metadata,
        )
        return True

    async def has_active_custom_source_objective(
        self,
        user_id: int,
        source: str,
        *,
        candidate_names: tuple[str | None, ...] = (),
        conn=None,
    ) -> bool:
        normalized_source = self._normalize_source(source)
        if normalized_source is None or normalized_source == "none":
            return False

        local = conn is None
        if local:
            conn = await self.bot.pool.acquire()
        try:
            rows = await conn.fetch(
                """
                SELECT cq.quest_key, cq.name, cq.category, cq.short_description, cq.offer_text,
                       cq.turnin_text, cq.objective_json, cq.turnin_json, cq.reward_json,
                       cq.access_json, cq.prerequisite_keys_json, cq.accept_cutscene_key,
                       cq.turnin_cutscene_key, cq.repeatable, cq.is_active, cq.created_by
                FROM player_quests pq
                JOIN custom_quests cq ON cq.quest_key = pq.quest_key
                WHERE pq.user_id = $1
                  AND pq.status = 'active'
                  AND cq.is_active = TRUE
                """,
                user_id,
            )

            for row in rows:
                custom_def = self._load_custom_quest_definition(row)
                meets_access, _reason = await self._user_meets_custom_access(
                    user_id,
                    custom_def,
                    conn=conn,
                )
                if not meets_access:
                    continue

                objective = custom_def.get("objective") or {}
                if self._normalize_source(objective.get("source")) != normalized_source:
                    continue
                if not self._match_name_filter(
                    objective.get("target_name"),
                    *candidate_names,
                ):
                    continue
                return True

            return False
        finally:
            if local:
                await self.bot.pool.release(conn)

    @commands.Cog.listener()
    async def on_PVE_completion(
        self,
        ctx,
        success,
        monster_name=None,
        element=None,
        levelchoice=None,
        battle_id=None,
    ):
        if not success:
            return

        if levelchoice is not None:
            await self._process_custom_source_completion(
                ctx,
                "pve",
                candidate_names=(monster_name,),
            )

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, success):
        if not success:
            return
        await self._process_custom_source_completion(
            ctx,
            "adventure",
        )

    @commands.Cog.listener()
    async def on_battletower_completion(
        self,
        ctx,
        success,
        level=None,
        level_name=None,
        enemy_name=None,
        minion1_name=None,
        minion2_name=None,
    ):
        if not success:
            return
        await self._process_custom_source_completion(
            ctx,
            "battletower",
            candidate_names=(
                level_name,
                enemy_name,
                minion1_name,
                minion2_name,
                str(level) if level is not None else None,
            ),
        )

    @commands.group(name="quests", aliases=["quest", "journal"], invoke_without_command=True)
    @has_char()
    async def quests(self, ctx):
        embed, view = await self._build_journal_display(ctx)
        if embed is None or view is None:
            summary = await self._build_no_active_quest_summary(ctx.author.id)
            return await ctx.send(embed=summary)
        await ctx.send(embed=embed, view=view)

    @quests.command(name="greg", aliases=["gregquests"])
    @has_char()
    async def quests_greg(self, ctx):
        active_entries = await self._get_journal_entries(ctx.author.id)
        embed, view = await self._build_greg_quest_board(
            ctx,
            has_active_entries=bool(active_entries),
        )
        await ctx.send(embed=embed, view=view)

    @quests.command(name="accept", aliases=["start", "take"])
    @has_char()
    async def quests_accept(self, ctx, *, quest_key: str):
        try:
            accept_data = await self._accept_quest_for_user(
                ctx.author.id,
                quest_key,
            )
        except ValueError as exc:
            return await ctx.send(str(exc))
        await self._send_quest_accept_messages(ctx, accept_data)

    @quests.command(name="turnin", aliases=["continue", "advance"])
    @has_char()
    async def quests_turnin(self, ctx, *, quest_key: str):
        raw_quest_key = str(quest_key).strip()
        quest_key = raw_quest_key.lower()
        if quest_key not in QUEST_DEFINITIONS:
            quest_key = self._normalize_custom_quest_key(raw_quest_key)
        greg_badge_granted = False
        greg_badge_already = False
        async with self.bot.pool.acquire() as conn:
            quest_def, custom_def = await self._resolve_quest_definition(quest_key, conn=conn)
            if not quest_def and not custom_def:
                return await ctx.send("That quest does not exist.")
            if quest_def and not self._quest_available(quest_key):
                return await ctx.send("That quest is currently frozen until Greg mode returns.")
            if custom_def:
                visible, reason = await self._custom_quest_visible_to_user(
                    ctx.author.id,
                    custom_def,
                    conn=conn,
                )
                if not visible:
                    return await ctx.send(reason or "That quest is not currently available.")

            try:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """
                        SELECT user_id, quest_key, category, status, step_index, completion_count, progress_json
                        FROM player_quests
                        WHERE user_id = $1 AND quest_key = $2
                        FOR UPDATE
                        """,
                        ctx.author.id,
                        quest_key,
                    )
                    if not row:
                        quest_name = quest_def.name if quest_def else custom_def["name"]
                        return await ctx.send(
                            f"You have not accepted **{quest_name}**. Use `$quests accept {quest_key}` first."
                        )
                    if row["status"] == "completed" and not custom_def:
                        return await ctx.send("You already completed that quest.")
                    if quest_def:
                        step_index = int(row["step_index"] or 0)
                        if step_index >= len(quest_def.steps):
                            return await ctx.send("That quest has no remaining steps.")

                        step = quest_def.steps[step_index]
                        item_qty = await self._get_key_item_quantity(ctx.author.id, step.key_item_key, conn=conn)
                        if item_qty <= 0:
                            snapshot = await self._quest_step_snapshot(ctx.author.id, row, quest_def, conn=conn)
                            return await ctx.send(
                                f"You are not ready to turn in **{step.title}** yet.\n"
                                + "\n".join(snapshot["progress_lines"])
                            )

                        consumed = await self._consume_key_item(ctx.author.id, step.key_item_key, conn=conn)
                        if not consumed:
                            return await ctx.send("That key item is missing.")

                        progress = self._load_progress(row["progress_json"])
                        progress["step_pve_wins"] = 0
                        progress["step_high_tier_wins"] = 0

                        next_step_index = step_index + 1
                        completed = next_step_index >= len(quest_def.steps)
                        await conn.execute(
                            """
                            UPDATE player_quests
                            SET step_index = $3,
                                status = $4,
                                completion_count = completion_count + CASE WHEN $4 = 'completed' THEN 1 ELSE 0 END,
                                progress_json = $5,
                                completed_at = CASE WHEN $4 = 'completed' THEN NOW() ELSE completed_at END,
                                turned_in_at = NOW()
                            WHERE user_id = $1 AND quest_key = $2
                            """,
                            ctx.author.id,
                            quest_key,
                            next_step_index,
                            "completed" if completed else "active",
                            self._dump_progress(progress),
                        )
                    else:
                        if row["status"] == "completed" and not custom_def["repeatable"]:
                            return await ctx.send("You already completed that quest.")
                        snapshot = await self._custom_snapshot(ctx.author.id, row, custom_def, conn=conn)
                        if not snapshot["ready_to_turn_in"]:
                            return await ctx.send(
                                f"You are not ready to turn in **{custom_def['name']}** yet.\n"
                                + "\n".join(snapshot["progress_lines"])
                            )

                        consumed, error_text = await self._consume_custom_turnin(
                            ctx.author.id,
                            custom_def,
                            conn=conn,
                        )
                        if not consumed:
                            return await ctx.send(error_text or "That turn-in could not be completed.")

                        reward_text = await self._grant_custom_reward(
                            ctx.author.id,
                            custom_def,
                            conn=conn,
                        )
                        if quest_key == "greg_finale":
                            greg_cog = self.bot.get_cog("Greg")
                            if greg_cog is not None and hasattr(greg_cog, "award_finale_badge"):
                                greg_badge_granted, greg_badge_already = await greg_cog.award_finale_badge(
                                    ctx.author.id,
                                    conn=conn,
                                )
                        await conn.execute(
                            """
                            UPDATE player_quests
                            SET status = $3,
                                step_index = 0,
                                completion_count = completion_count + 1,
                                progress_json = $4,
                                completed_at = NOW(),
                                turned_in_at = NOW()
                            WHERE user_id = $1 AND quest_key = $2
                            """,
                            ctx.author.id,
                            quest_key,
                            "completed",
                            self._dump_progress(self._new_custom_progress()),
                        )
            except ValueError as exc:
                return await ctx.send(str(exc))

        if quest_def:
            pages = self._create_story_pages(step.turn_in_pages, quest_def.name)
            view = QuestPageView(pages, ctx.author.id)
            await ctx.send(embed=pages[0], view=view)

            if completed:
                await ctx.send(
                    "The investigation is complete. When the community breaks the final seal, descend with `$greg boss`."
                )
            else:
                next_step = quest_def.steps[next_step_index]
                await ctx.send(
                    f"Next objective for **{quest_def.name}**: {next_step.objective}"
                )
        else:
            embed = discord.Embed(
                title=f"Quest Turned In: {custom_def['name']}",
                description=f"You receive {reward_text}.",
                color=0x2F6B3F,
            )
            embed.add_field(
                name="Reward",
                value=self._custom_reward_text(custom_def),
                inline=False,
            )
            if custom_def["repeatable"]:
                embed.set_footer(
                    text=f"This quest is repeatable. Accept it again with `$quests accept {custom_def['quest_key']}`."
                )
            else:
                embed.set_footer(text="This quest is now complete.")
            await ctx.send(embed=embed)
            if custom_def.get("turnin_cutscene_key"):
                access = custom_def.get("access") or {}
                is_campaign_quest = bool(
                    normalize_campaign_key(access.get("campaign_key"))
                    and normalize_campaign_key(access.get("campaign_node_key"))
                )
                cutscene_completed = await self.play_cutscene(
                    ctx,
                    custom_def["turnin_cutscene_key"],
                    wait_for_completion=is_campaign_quest,
                )
                if is_campaign_quest and not cutscene_completed:
                    await ctx.send(
                        "Your campaign is paused after this scene. Use `$campaign` to resume it."
                    )
                    return
            await self._advance_campaign_after_quest(ctx, custom_def)
            if quest_key == "greg_finale":
                if greg_badge_granted:
                    await ctx.send("**Gregapocalypse Survivor** has been added to your profile.")
                elif greg_badge_already:
                    await ctx.send("Your Gregapocalypse badge was already on your profile.")

    @commands.group(name="campaign", aliases=["chronicle"], invoke_without_command=True)
    @has_char()
    async def campaign(self, ctx):
        state = await self.bot.pool.fetchrow(
            """
            SELECT pc.run_id, pc.run_kind, pc.is_canonical, pc.campaign_key,
                   pc.status, pc.current_node_key, pc.history_json,
                   cc.title, pc.campaign_json_snapshot AS campaign_json
            FROM fable_campaign_runs pc
            JOIN campaign_content cc ON cc.campaign_key = pc.campaign_key
            LEFT JOIN fable_player_preferences fp ON fp.user_id = pc.user_id
            WHERE pc.user_id=$1
              AND pc.status IN ('entering', 'active', 'awaiting_choice', 'awaiting_scenario', 'awaiting_warfront')
            ORDER BY (pc.run_id = fp.selected_run_id) DESC, pc.updated_at DESC
            LIMIT 1
            """,
            ctx.author.id,
        )
        if not state:
            campaigns = await self.bot.pool.fetch(
                "SELECT campaign_key, title, description FROM campaign_content WHERE is_active=TRUE ORDER BY title LIMIT 10"
            )
            if not campaigns:
                return await ctx.send("No campaigns are currently available.")
            embed = discord.Embed(
                title="Available Campaigns",
                description="Start one with `$campaign start <key>`.",
                color=0x5D2E12,
            )
            for available in campaigns:
                embed.add_field(
                    name=available["title"],
                    value=f"`{available['campaign_key']}`\n{available['description'] or 'No description.'}",
                    inline=False,
                )
            return await ctx.send(embed=embed)

        campaign = self._load_progress(state["campaign_json"])
        node = node_by_id(campaign, state["current_node_key"])
        if not node:
            return await ctx.send("Your campaign is pointing at a missing node. Please notify a GM.")
        if state["status"] == "entering":
            await ctx.send("Resuming your last campaign transition…")
            return await self._enter_campaign_node(
                ctx,
                campaign,
                node["id"],
                run_id=str(state["run_id"]),
            )
        if state["status"] == "awaiting_scenario" and node.get("type") == "scenario":
            return await self._send_campaign_scenario_stage(
                ctx,
                campaign,
                node,
                run_id=str(state["run_id"]),
            )
        if state["status"] == "awaiting_warfront" and node.get("type") == "warfront":
            return await self._send_campaign_warfront_plan(
                ctx,
                campaign,
                node,
                run_id=str(state["run_id"]),
            )
        if state["status"] == "active" and node.get("type") == "quest":
            quest_key = self._campaign_quest_key(campaign, node)
            quest_status = await self.bot.pool.fetchval(
                "SELECT status FROM player_quests WHERE user_id=$1 AND quest_key=$2",
                ctx.author.id,
                quest_key,
            )
            if str(quest_status or "") == "completed":
                if not await self._play_campaign_node_cutscene(
                    ctx,
                    campaign,
                    node,
                    "turnin",
                ):
                    return
                await self._advance_campaign_after_quest(
                    ctx,
                    quest_record_from_node(campaign, node),
                )
                return
        embed = discord.Embed(
            title=state["title"],
            description=node.get("description") or "Your story continues.",
            color=0x5D2E12,
        )
        if not state["is_canonical"]:
            embed.description = (
                "**Chronicle replay — alternate history.**\n\n" + embed.description
            )
        embed.add_field(name="Current Chapter", value=node.get("title") or node["id"], inline=False)
        embed.add_field(name="Progress", value=f"{len(self._load_progress(state['history_json']) or [])} chapter(s) completed")
        choice_view = None
        if state["status"] == "awaiting_choice":
            raw_edges = (
                node.get("options")
                if node.get("type") in CHOICE_NODE_TYPES
                else node.get("next")
            )
            async with self.bot.pool.acquire() as conn:
                edges = await self._available_campaign_edges(
                    ctx.author.id,
                    raw_edges or [],
                    conn=conn,
                    campaign_key=state["campaign_key"],
                    run_id=str(state["run_id"]),
                    campaign=campaign,
                )
            embed.add_field(
                name="Decision",
                value="\n".join(f"{index}. {edge.get('label', 'Continue')}" for index, edge in enumerate(edges, 1)) or "No paths are currently unlocked.",
                inline=False,
            )
            embed.set_footer(text="Choose with $campaign choose <number>")
            if edges:
                choice_view = CampaignActionView(
                    cog=self,
                    ctx=ctx,
                    run_id=str(state["run_id"]),
                    campaign_key=campaign["key"],
                    node_key=node["id"],
                    options=edges,
                    action_kind="choose",
                )
        elif node.get("type") == "quest":
            quest_key = self._campaign_quest_key(campaign, node)
            embed.add_field(name="Quest", value=f"`$quests` or `$quests turnin {quest_key}`", inline=False)
            encounter = node.get("encounter") or {}
            if encounter.get("launch_command"):
                embed.add_field(name="Encounter", value=f"`{encounter['launch_command']}`", inline=False)
        else:
            edges = node.get("options") or node.get("next") or []
            embed.add_field(
                name="Decision",
                value="\n".join(f"{index}. {edge.get('label', 'Continue')}" for index, edge in enumerate(edges, 1)),
                inline=False,
            )
            embed.set_footer(text="Choose with $campaign choose <number>")
        message = await ctx.send(embed=embed, view=choice_view)
        if choice_view is not None:
            choice_view.message = message

    @campaign.command(name="start", aliases=["begin"])
    @has_char()
    async def campaign_start(self, ctx, campaign_key: str):
        campaign_key = normalize_campaign_key(campaign_key)
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT campaign_json, is_active, content_version
                FROM campaign_content WHERE campaign_key=$1
                """,
                campaign_key,
            )
            if not row or not row["is_active"]:
                return await ctx.send("That campaign is not currently available.")
            factions = self.bot.get_cog("Factions")
            if factions is not None:
                gate_allowed, gate_reason = await factions.check_content_access(
                    ctx.author.id,
                    scope="campaign",
                    target_key=campaign_key,
                    conn=conn,
                )
                if not gate_allowed:
                    return await ctx.send(
                        gate_reason or "Your faction standing does not unlock this campaign."
                    )
            existing = await conn.fetchrow(
                """
                SELECT status FROM fable_campaign_runs
                WHERE user_id=$1 AND campaign_key=$2 AND is_canonical=TRUE
                """,
                ctx.author.id,
                campaign_key,
            )
            if existing:
                if existing["status"] == "completed":
                    return await ctx.send("You have already completed that campaign.")
                return await ctx.send("That campaign is already in progress. Use `$campaign` to continue it.")
            campaign = self._load_progress(row["campaign_json"])
            start_node = node_by_id(campaign, campaign.get("start_node"))
            if not start_node:
                return await ctx.send("That campaign has an invalid starting node.")
            allowed, reason = await self._evaluate_campaign_conditions(
                ctx.author.id,
                campaign.get("requirements") or [],
                conn=conn,
                campaign_key=campaign_key,
            )
            if not allowed:
                return await ctx.send(reason or "You do not meet this campaign's requirements.")
            run_id = self.fable_state.new_run_id()
            await conn.execute(
                """
                INSERT INTO fable_campaign_runs (
                    run_id, user_id, campaign_key, run_kind, is_canonical,
                    content_version, status, current_node_key,
                    history_json, choices_json, unlocks_json,
                    campaign_json_snapshot, started_at, updated_at
                ) VALUES ($1,$2,$3,'canonical',TRUE,$4,'entering',$5,'[]','{}','[]',$6,NOW(),NOW())
                """,
                run_id,
                ctx.author.id,
                campaign_key,
                int(row["content_version"] or 1),
                campaign["start_node"],
                json.dumps(campaign, allow_nan=False, sort_keys=True),
            )
            await conn.execute(
                """
                INSERT INTO fable_player_preferences (user_id, selected_run_id, updated_at)
                VALUES ($1,$2,NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    selected_run_id=EXCLUDED.selected_run_id,
                    updated_at=NOW()
                """,
                ctx.author.id,
                run_id,
            )
        await ctx.send(f"You began **{campaign['title']}**.")
        await self._enter_campaign_node(
            ctx,
            campaign,
            campaign["start_node"],
            run_id=run_id,
        )

    @campaign.command(name="replay", aliases=["newchronicle"])
    @has_char()
    async def campaign_replay(self, ctx, campaign_key: str):
        """Begin an isolated alternate-history run after canonical completion."""
        campaign_key = normalize_campaign_key(campaign_key)
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                canonical = await conn.fetchrow(
                    """
                    SELECT campaign_json_snapshot, content_version
                    FROM fable_campaign_runs
                    WHERE user_id=$1 AND campaign_key=$2
                      AND is_canonical=TRUE AND status='completed'
                    FOR UPDATE
                    """,
                    ctx.author.id,
                    campaign_key,
                )
                if not canonical:
                    return await ctx.send(
                        "Complete that campaign canonically before opening an alternate Chronicle."
                    )
                active_replay = await conn.fetchval(
                    """
                    SELECT run_id FROM fable_campaign_runs
                    WHERE user_id=$1 AND campaign_key=$2 AND is_canonical=FALSE
                      AND status IN ('entering','active','awaiting_choice','awaiting_scenario','awaiting_warfront')
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    ctx.author.id,
                    campaign_key,
                )
                if active_replay:
                    return await ctx.send(
                        f"An alternate Chronicle is already active. Focus it with "
                        f"`$campaign select {str(active_replay)[:8]}`."
                    )
                campaign = self._load_progress(canonical["campaign_json_snapshot"])
                start_node = node_by_id(campaign, campaign.get("start_node"))
                if not start_node:
                    return await ctx.send("The saved campaign snapshot has no valid start node.")
                run_id = self.fable_state.new_run_id()
                await conn.execute(
                    """
                    INSERT INTO fable_campaign_runs (
                        run_id, user_id, campaign_key, run_kind, is_canonical,
                        content_version, status, current_node_key,
                        history_json, choices_json, unlocks_json,
                        campaign_json_snapshot, started_at, updated_at
                    ) VALUES ($1,$2,$3,'chronicle',FALSE,$4,'entering',$5,
                              '[]','{}','[]',$6,NOW(),NOW())
                    """,
                    run_id,
                    ctx.author.id,
                    campaign_key,
                    int(canonical["content_version"] or 1),
                    campaign["start_node"],
                    json.dumps(campaign, allow_nan=False, sort_keys=True),
                )
                await conn.execute(
                    """
                    INSERT INTO fable_player_preferences (user_id, selected_run_id, updated_at)
                    VALUES ($1,$2,NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        selected_run_id=EXCLUDED.selected_run_id, updated_at=NOW()
                    """,
                    ctx.author.id,
                    run_id,
                )
        await ctx.send(
            f"You opened an alternate Chronicle for **{campaign.get('title') or campaign_key}**. "
            "Canonical choices and state will not be rewritten."
        )
        await self._enter_campaign_node(
            ctx,
            campaign,
            campaign["start_node"],
            run_id=run_id,
        )

    @campaign.command(name="runs", aliases=["histories"])
    @has_char()
    async def campaign_runs(self, ctx):
        rows = await self.bot.pool.fetch(
            """
            SELECT fcr.run_id, fcr.campaign_key, fcr.run_kind, fcr.is_canonical,
                   fcr.status, fcr.current_node_key,
                   (fcr.run_id=fp.selected_run_id) AS selected
            FROM fable_campaign_runs fcr
            LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
            WHERE fcr.user_id=$1
            ORDER BY selected DESC, fcr.updated_at DESC
            LIMIT 20
            """,
            ctx.author.id,
        )
        if not rows:
            return await ctx.send("Your Chronicle has no campaign runs yet.")
        embed = discord.Embed(
            title="Chronicle Histories",
            description="Focus one with `$campaign select <campaign key or run prefix>`. ",
            color=0x5D2E12,
        )
        for run in rows:
            kind = "Canonical" if run["is_canonical"] else "Alternate"
            marker = " · Focused" if run["selected"] else ""
            embed.add_field(
                name=f"{run['campaign_key']} · {kind}{marker}",
                value=(
                    f"`{str(run['run_id'])[:8]}` · {str(run['status']).replace('_', ' ').title()}\n"
                    f"Current: `{run['current_node_key']}`"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @campaign.command(name="select", aliases=["focus"])
    @has_char()
    async def campaign_select(self, ctx, campaign_key: str):
        """Select which active campaign Chronicle and choice commands control."""
        selector = str(campaign_key or "").strip().lower()
        normalized_key = normalize_campaign_key(selector)
        async with self.bot.pool.acquire() as conn:
            run = await conn.fetchrow(
                """
                SELECT fcr.run_id, fcr.is_canonical, cc.title
                FROM fable_campaign_runs fcr
                JOIN campaign_content cc ON cc.campaign_key=fcr.campaign_key
                WHERE fcr.user_id=$1
                  AND (fcr.run_id=$2 OR fcr.run_id LIKE $2 || '%' OR fcr.campaign_key=$3)
                  AND fcr.status IN ('entering', 'active', 'awaiting_choice', 'awaiting_scenario', 'awaiting_warfront')
                ORDER BY (fcr.run_id=$2) DESC, (fcr.run_id LIKE $2 || '%') DESC,
                         (fcr.campaign_key=$3 AND fcr.is_canonical) DESC,
                         fcr.updated_at DESC
                LIMIT 1
                """,
                ctx.author.id,
                selector,
                normalized_key,
            )
            if not run:
                return await ctx.send("That campaign is not currently active in your Chronicle.")
            await conn.execute(
                """
                INSERT INTO fable_player_preferences (user_id, selected_run_id, updated_at)
                VALUES ($1,$2,NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    selected_run_id=EXCLUDED.selected_run_id,
                    updated_at=NOW()
                """,
                ctx.author.id,
                run["run_id"],
            )
        kind = "canonical history" if run["is_canonical"] else "alternate history"
        await ctx.send(f"Your Chronicle is now focused on **{run['title']}** ({kind}).")

    @campaign.command(name="debugstate", aliases=["statejson"])
    @is_gm()
    async def campaign_debug_state(self, ctx, campaign_key: str = ""):
        """Export the caller's focused V2 run and typed state for development."""
        normalized_key = normalize_campaign_key(campaign_key)
        async with self.bot.pool.acquire() as conn:
            run = await conn.fetchrow(
                """
                SELECT fcr.*
                FROM fable_campaign_runs fcr
                LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
                WHERE fcr.user_id=$1
                  AND ($2='' OR fcr.campaign_key=$2)
                ORDER BY (fcr.run_id=fp.selected_run_id) DESC, fcr.updated_at DESC
                LIMIT 1
                """,
                ctx.author.id,
                normalized_key,
            )
            if not run:
                return await ctx.send("No matching Fable run was found.")
            story_state = await self.fable_state.snapshot(conn, str(run["run_id"]))
        payload = {
            "run_id": str(run["run_id"]),
            "user_id": int(run["user_id"]),
            "campaign_key": str(run["campaign_key"]),
            "run_kind": str(run["run_kind"]),
            "content_version": int(run["content_version"] or 1),
            "status": str(run["status"]),
            "current_node_key": str(run["current_node_key"]),
            "history": self._load_progress(run["history_json"]),
            "choices": self._load_progress(run["choices_json"]),
            "unlocks": self._load_progress(run["unlocks_json"]),
            "state": story_state,
            "ending_snapshot": self._load_progress(run["ending_snapshot_json"]),
        }
        body = json.dumps(payload, indent=2, allow_nan=False, sort_keys=True).encode("utf-8")
        filename = f"fable-state-{payload['campaign_key']}.json"
        await ctx.send(file=discord.File(io.BytesIO(body), filename=filename))

    @campaign.command(name="act", aliases=["scenario"])
    @has_char()
    async def campaign_act(self, ctx, option: int):
        """Take an action in the focused campaign scenario."""
        await self._resolve_campaign_act(ctx, option)

    async def _resolve_campaign_act(
        self,
        ctx,
        option: int,
        *,
        expected_prompt: tuple[str, str, str, str] | None = None,
    ):
        consequence_messages = []
        outcome = None
        result_text = ""
        target_node = ""
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                attempt = await conn.fetchrow(
                    """
                    SELECT fsa.attempt_id, fsa.run_id, fsa.current_stage_key,
                           fsa.history_json, fcr.campaign_key,
                           fcr.campaign_json_snapshot AS campaign_json,
                           fcr.current_node_key
                    FROM fable_scenario_attempts fsa
                    JOIN fable_campaign_runs fcr ON fcr.run_id=fsa.run_id
                    LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
                    WHERE fcr.user_id=$1
                      AND fcr.status='awaiting_scenario'
                      AND fsa.status='active'
                    ORDER BY (fcr.run_id=fp.selected_run_id) DESC, fcr.updated_at DESC
                    LIMIT 1
                    FOR UPDATE OF fsa, fcr
                    """,
                    ctx.author.id,
                )
                if not attempt:
                    return await ctx.send("You do not currently have a scenario action waiting.")
                campaign = self._load_progress(attempt["campaign_json"])
                node = node_by_id(campaign, attempt["current_node_key"])
                if not node or node.get("type") != "scenario":
                    return await ctx.send("The active scenario points to invalid campaign content.")
                scenario = node.get("scenario") or {}
                stage = self._scenario_stage(scenario, attempt["current_stage_key"])
                if not stage:
                    return await ctx.send("The active scenario stage is missing.")
                if expected_prompt is not None and expected_prompt != (
                    str(attempt["run_id"]),
                    attempt["campaign_key"],
                    node["id"],
                    stage["id"],
                ):
                    return await ctx.send(
                        "That scenario button belongs to an earlier stage. Use `$campaign` to continue."
                    )
                actions = await self._available_scenario_actions(
                    ctx.author.id,
                    attempt["campaign_key"],
                    scenario,
                    stage,
                    conn=conn,
                    run_id=str(attempt["run_id"]),
                    campaign=campaign,
                )
                if not actions:
                    return await ctx.send(
                        "No scenario actions are currently available; another story condition must change."
                    )
                if option < 1 or option > len(actions):
                    return await ctx.send(f"Choose an action from 1 to {len(actions)}.")
                action = actions[option - 1]
                history = list(self._load_progress(attempt["history_json"]) or [])
                action_event = (
                    f"scenario:{attempt['attempt_id']}:{stage['id']}:"
                    f"{len(history)}:{normalize_campaign_key(action.get('label')) or option}"
                )
                consequence_messages.extend(
                    await self._apply_campaign_effects(
                        ctx.author.id,
                        attempt["campaign_key"],
                        effects=action.get("effects") or [],
                        unlocks=action.get("unlocks") or [],
                        event_key=action_event,
                        source=f"scenario:{scenario.get('key') or node['id']}",
                        run_id=str(attempt["run_id"]),
                        conn=conn,
                    )
                )
                result_text = str(action.get("result_text") or "").strip()
                history.append(
                    {
                        "stage": stage["id"],
                        "action": str(action.get("label") or "Act"),
                        "at": datetime.utcnow().isoformat() + "Z",
                    }
                )

                if action.get("next_stage"):
                    await conn.execute(
                        """
                        UPDATE fable_scenario_attempts
                        SET current_stage_key=$2, history_json=$3, updated_at=NOW()
                        WHERE attempt_id=$1
                        """,
                        attempt["attempt_id"],
                        action["next_stage"],
                        json.dumps(history, sort_keys=True),
                    )
                else:
                    outcome = self._scenario_outcome(scenario, action.get("outcome"))
                    if not outcome:
                        return await ctx.send("This scenario action has an invalid outcome.")
                    consequence_messages.extend(
                        await self._apply_campaign_effects(
                            ctx.author.id,
                            attempt["campaign_key"],
                            effects=outcome.get("effects") or [],
                            unlocks=outcome.get("unlocks") or [],
                            event_key=f"{action_event}:outcome:{outcome['id']}",
                            source=f"scenario:{scenario.get('key') or node['id']}",
                            run_id=str(attempt["run_id"]),
                            conn=conn,
                        )
                    )
                    result = {
                        "outcome": outcome["id"],
                        "title": outcome.get("title") or outcome["id"],
                        "history": history,
                    }
                    await conn.execute(
                        """
                        UPDATE fable_scenario_attempts
                        SET status='completed', history_json=$2, result_json=$3,
                            completed_at=NOW(), updated_at=NOW()
                        WHERE attempt_id=$1
                        """,
                        attempt["attempt_id"],
                        json.dumps(history, sort_keys=True),
                        json.dumps(result, sort_keys=True),
                    )
                    run_history = await conn.fetchval(
                        "SELECT history_json FROM fable_campaign_runs WHERE run_id=$1",
                        attempt["run_id"],
                    )
                    completed_nodes = list(self._load_progress(run_history) or [])
                    if node["id"] not in completed_nodes:
                        completed_nodes.append(node["id"])
                    await conn.execute(
                        """
                        UPDATE fable_campaign_runs
                        SET status='entering', current_node_key=$3,
                            history_json=$2, updated_at=NOW()
                        WHERE run_id=$1
                        """,
                        attempt["run_id"],
                        json.dumps(completed_nodes),
                        str(outcome.get("target") or ""),
                    )
                    target_node = str(outcome.get("target") or "")

        if result_text:
            await ctx.send(result_text)
        if consequence_messages:
            await ctx.send("\n".join(consequence_messages))
        if outcome:
            embed = discord.Embed(
                title=outcome.get("title") or "Scenario Resolved",
                description=outcome.get("description") or "Your actions changed the story.",
                color=0x2F6B3F,
            )
            await ctx.send(embed=embed)
            await self._enter_campaign_node(
                ctx,
                campaign,
                target_node,
                run_id=str(attempt["run_id"]),
            )
            return
        await self._send_campaign_scenario_stage(
            ctx,
            campaign,
            node,
            run_id=str(attempt["run_id"]),
        )

    @campaign.command(name="choose", aliases=["choice"])
    @has_char()
    async def campaign_choose(self, ctx, option: int):
        await self._resolve_campaign_choice(ctx, option)

    async def _resolve_campaign_choice(
        self,
        ctx,
        option: int,
        *,
        expected_prompt: tuple[str, str, str] | None = None,
    ):
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                state = await conn.fetchrow(
                    """
                    SELECT pc.run_id, pc.campaign_key, pc.current_node_key,
                           pc.choices_json,
                           pc.history_json,
                           pc.campaign_json_snapshot AS campaign_json
                    FROM fable_campaign_runs pc
                    JOIN campaign_content cc ON cc.campaign_key=pc.campaign_key
                    LEFT JOIN fable_player_preferences fp ON fp.user_id=pc.user_id
                    WHERE pc.user_id=$1
                      AND pc.status='awaiting_choice'
                    ORDER BY (pc.run_id = fp.selected_run_id) DESC, pc.updated_at DESC
                    LIMIT 1
                    FOR UPDATE OF pc
                    """,
                    ctx.author.id,
                )
                if not state:
                    return await ctx.send("You do not currently have a campaign decision waiting.")
                campaign = self._load_progress(state["campaign_json"])
                node = node_by_id(campaign, state["current_node_key"])
                if not node:
                    return await ctx.send("This campaign choice points to a missing node.")
                if expected_prompt is not None and expected_prompt != (
                    str(state["run_id"]),
                    state["campaign_key"],
                    node["id"],
                ):
                    return await ctx.send(
                        "That choice button belongs to an earlier decision. Use `$campaign` to continue."
                    )
                choices = self._load_progress(state["choices_json"])
                history = list(self._load_progress(state["history_json"]) or [])
                is_authored_choice = node.get("type") in CHOICE_NODE_TYPES
                if is_authored_choice and node["id"] in choices:
                    return await ctx.send("You have already made this campaign decision.")
                raw_edges = (
                    node.get("options")
                    if node.get("type") in CHOICE_NODE_TYPES
                    else node.get("next")
                )
                edges = await self._available_campaign_edges(
                    ctx.author.id,
                    raw_edges or [],
                    conn=conn,
                    campaign_key=state["campaign_key"],
                    run_id=str(state["run_id"]),
                    campaign=campaign,
                )
                if not edges:
                    return await ctx.send("No campaign paths are currently unlocked.")
                if option < 1 or option > len(edges):
                    return await ctx.send(f"Choose a number from 1 to {len(edges)}.")
                edge = edges[option - 1]
                if is_authored_choice:
                    choices[node["id"]] = edge["target"]
                if node["id"] not in history:
                    history.append(node["id"])
                await conn.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET choices_json=$2, history_json=$3,
                        current_node_key=$4, status='entering', updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    state["run_id"],
                    json.dumps(choices, sort_keys=True),
                    json.dumps(history),
                    edge["target"],
                )
                consequence_messages = await self._apply_campaign_effects(
                    ctx.author.id,
                    state["campaign_key"],
                    effects=edge.get("effects") or [],
                    unlocks=edge.get("unlocks") or [],
                    event_key=(
                        f"campaign:{state['campaign_key']}:choice:"
                        f"{node['id']}:{edge['target']}"
                    ),
                    run_id=str(state["run_id"]),
                    conn=conn,
                )
        await ctx.send(f"You chose **{edge.get('label') or 'Continue'}**.")
        if consequence_messages:
            await ctx.send("\n".join(consequence_messages))
        await self._enter_campaign_node(
            ctx,
            campaign,
            edge["target"],
            run_id=str(state["run_id"]),
        )

    @campaign.command(name="reputation", aliases=["rep"])
    @has_char()
    async def campaign_reputation(self, ctx):
        factions = self.bot.get_cog("Factions")
        if factions is None:
            return await ctx.send("Faction standing is temporarily unavailable.")
        await factions.send_overview(ctx)

    async def _selected_campaign_state(self, user_id: int) -> tuple[object | None, dict]:
        async with self.bot.pool.acquire() as conn:
            run = await conn.fetchrow(
                """
                SELECT fcr.run_id, fcr.campaign_key, fcr.status,
                       fcr.is_canonical, fcr.campaign_json_snapshot
                FROM fable_campaign_runs fcr
                LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
                WHERE fcr.user_id=$1
                ORDER BY (fcr.run_id=fp.selected_run_id) DESC, fcr.updated_at DESC
                LIMIT 1
                """,
                user_id,
            )
            state = (
                await self.fable_state.snapshot(conn, str(run["run_id"]))
                if run
                else {}
            )
        return run, state

    async def _selected_campaign_context(
        self,
        user_id: int,
        *,
        statuses: tuple[str, ...] | None = None,
    ) -> tuple[object | None, dict, dict]:
        async with self.bot.pool.acquire() as conn:
            run = await self._selected_campaign_run(
                conn,
                user_id,
                statuses=statuses,
            )
            if not run:
                return None, {}, {}
            campaign = self._load_progress(run["campaign_json_snapshot"])
            state = await self.fable_state.snapshot(conn, str(run["run_id"]))
        return run, campaign, state

    async def _campaign_companion_available(
        self,
        user_id: int,
        campaign: dict,
        companion: dict,
        *,
        conn,
        run_id: str,
        state: dict,
    ) -> bool:
        status = str(
            state.get(f"companion.{companion['key']}.status", "active")
        ).lower()
        if status in {"left", "captured", "dead", "unavailable"}:
            return False
        allowed, _reason = await self._evaluate_campaign_conditions(
            user_id,
            companion.get("conditions") or [],
            conn=conn,
            campaign_key=campaign["key"],
            run_id=run_id,
        )
        return allowed

    @staticmethod
    def _group_story_model_state(state: dict, prefix: str) -> dict[str, dict]:
        grouped: dict[str, dict] = {}
        namespace = f"{prefix}."
        for state_key, value in state.items():
            if not str(state_key).startswith(namespace):
                continue
            remainder = str(state_key)[len(namespace):]
            entity_key, separator, field = remainder.partition(".")
            if not separator or not entity_key or not field:
                continue
            grouped.setdefault(entity_key, {})[field] = value
        return grouped

    @staticmethod
    def _story_state_display(value) -> str:
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(str(entry).replace("_", " ").title() for entry in value) or "None"
        if isinstance(value, dict):
            return ", ".join(
                f"{str(key).replace('_', ' ').title()}: {item}"
                for key, item in list(value.items())[:8]
            ) or "None"
        return str(value).replace("_", " ").title()

    async def _send_story_model_overview(
        self,
        ctx,
        *,
        prefix: str,
        title: str,
        empty_text: str,
    ) -> None:
        run, state = await self._selected_campaign_state(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history was found.")
        grouped = self._group_story_model_state(state, prefix)
        if not grouped:
            return await ctx.send(empty_text)
        embed = discord.Embed(
            title=title,
            description=f"Campaign: `{run['campaign_key']}`",
            color=0x5D2E12,
        )
        for entity_key, fields in list(sorted(grouped.items()))[:20]:
            lines = [
                f"**{field.replace('_', ' ').title()}:** {self._story_state_display(value)}"
                for field, value in sorted(fields.items())
            ]
            embed.add_field(
                name=entity_key.replace("_", " ").title(),
                value="\n".join(lines)[:1024],
                inline=False,
            )
        await ctx.send(embed=embed)

    @campaign.command(name="companions", aliases=["relationships"])
    @has_char()
    async def campaign_companions(self, ctx):
        """Show companion relationship, growth, status, and romance state."""
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        companions = [
            companion
            for companion in campaign.get("companions") or []
            if isinstance(companion, dict) and companion.get("key")
        ]
        if not companions:
            return await self._send_story_model_overview(
                ctx,
                prefix="companion",
                title="Campaign Companions",
                empty_text="This campaign has not recorded any companion relationships yet.",
            )
        grouped = self._group_story_model_state(state, "companion")
        active_party = set(state.get("party.active") or [])
        embed = discord.Embed(
            title="Campaign Companions",
            description=f"Campaign: `{run['campaign_key']}`",
            color=0x6B4C8A,
        )
        async with self.bot.pool.acquire() as conn:
            for companion in companions[:20]:
                available = await self._campaign_companion_available(
                    ctx.author.id,
                    campaign,
                    companion,
                    conn=conn,
                    run_id=str(run["run_id"]),
                    state=state,
                )
                fields = grouped.get(companion["key"], {})
                lines = [
                    f"**Role:** {companion.get('role') or 'Companion'}",
                    f"**Status:** {'Available' if available else 'Unavailable'}",
                ]
                if companion["key"] in active_party:
                    lines.append("**Party:** Travelling with you")
                lines.extend(
                    f"**{field.replace('_', ' ').title()}:** {self._story_state_display(value)}"
                    for field, value in sorted(fields.items())
                    if field != "status"
                )
                if companion.get("description"):
                    lines.append(str(companion["description"]))
                embed.add_field(
                    name=companion.get("name") or companion["key"].replace("_", " ").title(),
                    value="\n".join(lines)[:1024],
                    inline=False,
                )
        await ctx.send(embed=embed)

    @campaign.group(name="party", invoke_without_command=True)
    @has_char()
    async def campaign_party(self, ctx):
        """Show the companions currently travelling with this run."""
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        definitions = {
            companion["key"]: companion
            for companion in campaign.get("companions") or []
            if isinstance(companion, dict) and companion.get("key")
        }
        active = list(state.get("party.active") or [])
        embed = discord.Embed(
            title="Travelling Party",
            description=(
                "No companions selected."
                if not active
                else "\n".join(
                    f"• **{definitions.get(key, {}).get('name') or key.replace('_', ' ').title()}**"
                    for key in active
                )
            ),
            color=0x6B4C8A,
        )
        embed.set_footer(
            text=(
                f"Up to {int(campaign.get('party_size') or 2)} companions · "
                "$campaign party add/remove <companion>"
            )
        )
        await ctx.send(embed=embed)

    @campaign_party.command(name="add")
    @has_char()
    async def campaign_party_add(self, ctx, *, companion_key: str):
        key = normalize_campaign_key(companion_key)
        run, campaign, state = await self._selected_campaign_context(
            ctx.author.id,
            statuses=("entering", "active", "awaiting_choice", "awaiting_scenario", "awaiting_warfront"),
        )
        if not run:
            return await ctx.send("No active campaign run is focused.")
        companion = next(
            (
                value for value in campaign.get("companions") or []
                if isinstance(value, dict) and value.get("key") == key
            ),
            None,
        )
        if not companion:
            return await ctx.send("That companion is not defined for this campaign.")
        active = list(state.get("party.active") or [])
        if key in active:
            return await ctx.send(f"**{companion['name']}** is already travelling with you.")
        if len(active) >= int(campaign.get("party_size") or 2):
            return await ctx.send("Your travelling party is full. Remove someone first.")
        async with self.bot.pool.acquire() as conn:
            if not await self._campaign_companion_available(
                ctx.author.id,
                campaign,
                companion,
                conn=conn,
                run_id=str(run["run_id"]),
                state=state,
            ):
                return await ctx.send("That companion is not currently available to travel.")
            active.append(key)
            await self.fable_state.apply_effects(
                conn,
                user_id=ctx.author.id,
                campaign_key=campaign["key"],
                effects=[{"type": "state_set", "key": "party.active", "value": active}],
                event_key=f"party:{self.fable_state.new_run_id()}",
                source="campaign_party",
                run_id=str(run["run_id"]),
            )
        await ctx.send(f"**{companion['name']}** joined your travelling party.")

    @campaign_party.command(name="remove")
    @has_char()
    async def campaign_party_remove(self, ctx, *, companion_key: str):
        key = normalize_campaign_key(companion_key)
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        active = list(state.get("party.active") or [])
        if key not in active:
            return await ctx.send("That companion is not in your travelling party.")
        active.remove(key)
        async with self.bot.pool.acquire() as conn:
            await self.fable_state.apply_effects(
                conn,
                user_id=ctx.author.id,
                campaign_key=campaign["key"],
                effects=[{"type": "state_set", "key": "party.active", "value": active}],
                event_key=f"party:{self.fable_state.new_run_id()}",
                source="campaign_party",
                run_id=str(run["run_id"]),
            )
        await ctx.send(f"**{key.replace('_', ' ').title()}** left your travelling party.")

    @campaign.command(name="camp", aliases=["campfire"])
    @has_char()
    async def campaign_camp(self, ctx, *, scene_key: str = ""):
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        active_party = set(state.get("party.active") or [])
        seen = set(state.get("camp.seen_scenes") or [])
        available = []
        async with self.bot.pool.acquire() as conn:
            for companion in campaign.get("companions") or []:
                if not isinstance(companion, dict):
                    continue
                for scene in companion.get("scenes") or []:
                    if not isinstance(scene, dict):
                        continue
                    if scene.get("once", True) and scene.get("id") in seen:
                        continue
                    participants = set(scene.get("participants") or [])
                    if scene.get("requires_party") and not participants.issubset(active_party):
                        continue
                    allowed, _reason = await self._evaluate_campaign_conditions(
                        ctx.author.id,
                        scene.get("conditions") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=str(run["run_id"]),
                    )
                    if allowed:
                        available.append(scene)
            available.sort(key=lambda scene: (int(scene.get("order") or 0), scene["id"]))
            selected_key = normalize_campaign_key(scene_key)
            if not selected_key:
                if not available:
                    return await ctx.send("No new camp scenes are currently available.")
                embed = discord.Embed(
                    title="Available Camp Scenes",
                    description="Play one with `$campaign camp <scene id>`.",
                    color=0x6B4C8A,
                )
                for scene in available[:20]:
                    embed.add_field(
                        name=scene.get("title") or scene["id"],
                        value=f"`{scene['id']}`",
                        inline=False,
                    )
                return await ctx.send(embed=embed)
            scene = next((value for value in available if value.get("id") == selected_key), None)
            if not scene:
                return await ctx.send("That camp scene is unavailable or has already played.")
            effects = list(scene.get("effects") or [])
            if scene.get("once", True):
                effects.append(
                    {"type": "state_add", "key": "camp.seen_scenes", "value": scene["id"]}
                )
            messages = await self._apply_campaign_effects(
                ctx.author.id,
                campaign["key"],
                effects=effects,
                unlocks=scene.get("unlocks") or [],
                event_key=(
                    f"camp:{scene['id']}"
                    if scene.get("once", True)
                    else f"camp:{scene['id']}:{self.fable_state.new_run_id()}"
                ),
                source=f"camp:{scene['id']}",
                run_id=str(run["run_id"]),
                conn=conn,
            )
        embed = discord.Embed(
            title=scene.get("title") or "Camp Scene",
            description=scene.get("text") or "The party shares a quiet moment.",
            color=0x6B4C8A,
        )
        if messages:
            embed.add_field(name="Consequences", value="\n".join(messages)[:1024], inline=False)
        await ctx.send(embed=embed)

    @campaign.command(name="locations", aliases=["map", "regions"])
    @has_char()
    async def campaign_locations(self, ctx):
        """Show persistent location and regional-control state."""
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        locations = [
            location
            for location in campaign.get("locations") or []
            if isinstance(location, dict)
        ]
        if not locations:
            return await self._send_story_model_overview(
                ctx,
                prefix="location",
                title="Campaign Locations",
                empty_text="This campaign has not recorded any location changes yet.",
            )
        current = str(state.get("world.current_location") or "")
        embed = discord.Embed(
            title="Campaign Locations",
            description="Inspect with `$campaign location <key>` or travel with `$campaign travel <key>`.",
            color=0x3F6A52,
        )
        async with self.bot.pool.acquire() as conn:
            for location in locations[:20]:
                allowed, _reason = await self._evaluate_campaign_conditions(
                    ctx.author.id,
                    location.get("conditions") or [],
                    conn=conn,
                    campaign_key=campaign["key"],
                    run_id=str(run["run_id"]),
                )
                if not allowed:
                    continue
                marker = " · Current" if location["key"] == current else ""
                embed.add_field(
                    name=f"{location['name']}{marker}",
                    value=f"`{location['key']}`\n{location.get('description') or 'No description.'}"[:1024],
                    inline=False,
                )
        if not embed.fields:
            embed.description = "No authored locations are currently unlocked."
        await ctx.send(embed=embed)

    @campaign.command(name="location", aliases=["region"])
    @has_char()
    async def campaign_location(self, ctx, *, location_key: str):
        key = normalize_campaign_key(location_key)
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        location = next(
            (
                value for value in campaign.get("locations") or []
                if isinstance(value, dict) and value.get("key") == key
            ),
            None,
        )
        if not location:
            return await ctx.send("That location is not defined in this campaign.")
        async with self.bot.pool.acquire() as conn:
            allowed, reason = await self._evaluate_campaign_conditions(
                ctx.author.id,
                location.get("conditions") or [],
                conn=conn,
                campaign_key=campaign["key"],
                run_id=str(run["run_id"]),
            )
            if not allowed:
                return await ctx.send(reason or "That location is not currently available.")
            available_services = []
            for service in location.get("services") or []:
                service_allowed, _service_reason = await self._evaluate_campaign_conditions(
                    ctx.author.id,
                    service.get("conditions") or [],
                    conn=conn,
                    campaign_key=campaign["key"],
                    run_id=str(run["run_id"]),
                )
                if service_allowed:
                    available_services.append(service)
        embed = discord.Embed(
            title=location["name"],
            description=location.get("description") or "No description.",
            color=0x3F6A52,
        )
        location_state = self._group_story_model_state(state, "location").get(key, {})
        if location_state:
            embed.add_field(
                name="Current State",
                value="\n".join(
                    f"**{field.replace('_', ' ').title()}:** {self._story_state_display(value)}"
                    for field, value in sorted(location_state.items())
                )[:1024],
                inline=False,
            )
        for service in available_services[:12]:
            embed.add_field(
                name=service.get("name") or service["key"],
                value=(
                    f"{service.get('description') or 'Available service.'}\n"
                    f"Open: `$campaign service {service['key']}`"
                )[:1024],
                inline=False,
            )
        await ctx.send(embed=embed)

    async def check_campaign_service_access(
        self,
        user_id: int,
        service_key: str,
        *,
        campaign_key: str = "",
        conn=None,
    ) -> tuple[bool, str | None, dict | None]:
        owns_connection = conn is None
        if owns_connection:
            conn = await self.bot.pool.acquire()
        try:
            run = await self._selected_campaign_run(
                conn,
                user_id,
                campaign_key=campaign_key,
            )
            if not run:
                return False, "No matching campaign history was found.", None
            campaign = self._load_progress(run["campaign_json_snapshot"])
            state = await self.fable_state.snapshot(conn, str(run["run_id"]))
            current = str(state.get("world.current_location") or "")
            normalized_service = normalize_campaign_key(service_key)
            for location in campaign.get("locations") or []:
                for service in location.get("services") or []:
                    if service.get("key") != normalized_service:
                        continue
                    if current != location.get("key"):
                        return False, f"Travel to **{location.get('name')}** first.", service
                    location_allowed, location_reason = await self._evaluate_campaign_conditions(
                        user_id,
                        location.get("conditions") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=str(run["run_id"]),
                    )
                    if not location_allowed:
                        return False, location_reason or "That location is currently unavailable.", service
                    allowed, reason = await self._evaluate_campaign_conditions(
                        user_id,
                        service.get("conditions") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=str(run["run_id"]),
                    )
                    return allowed, reason, service
            return False, "That campaign service does not exist.", None
        finally:
            if owns_connection:
                await self.bot.pool.release(conn)

    @campaign.command(name="service")
    @has_char()
    async def campaign_service(self, ctx, *, service_key: str):
        allowed, reason, service = await self.check_campaign_service_access(
            ctx.author.id,
            service_key,
        )
        if not allowed or not service:
            return await ctx.send(reason or "That service is not currently available.")
        embed = discord.Embed(
            title=service.get("name") or service["key"],
            description=service.get("description") or "Campaign service unlocked.",
            color=0x3F6A52,
        )
        embed.add_field(name="Open", value=f"`{service['command']}`", inline=False)
        await ctx.send(embed=embed)

    @campaign.command(name="travel")
    @has_char()
    async def campaign_travel(self, ctx, *, location_key: str):
        key = normalize_campaign_key(location_key)
        run, campaign, _state = await self._selected_campaign_context(
            ctx.author.id,
            statuses=("awaiting_choice",),
        )
        if not run:
            return await ctx.send(
                "Travel is available only while the focused campaign is waiting for a story decision."
            )
        location = next(
            (
                value for value in campaign.get("locations") or []
                if isinstance(value, dict) and value.get("key") == key
            ),
            None,
        )
        if not location or not location.get("travel_node"):
            return await ctx.send("That location is not an available travel destination.")
        target_node = node_by_id(campaign, location["travel_node"])
        if not target_node:
            return await ctx.send("That destination points to a missing story beat.")
        messages = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                allowed, reason = await self._evaluate_campaign_conditions(
                    ctx.author.id,
                    location.get("conditions") or [],
                    conn=conn,
                    campaign_key=campaign["key"],
                    run_id=str(run["run_id"]),
                )
                if allowed:
                    allowed, reason = await self._evaluate_campaign_conditions(
                        ctx.author.id,
                        target_node.get("requirements") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=str(run["run_id"]),
                    )
                if not allowed:
                    return await ctx.send(reason or "That route is currently locked.")
                messages = await self._apply_campaign_effects(
                    ctx.author.id,
                    campaign["key"],
                    effects=[
                        {
                            "type": "state_set",
                            "key": "world.current_location",
                            "value": location["key"],
                        },
                        {
                            "type": "state_add",
                            "key": "world.visited_locations",
                            "value": location["key"],
                        },
                    ],
                    event_key=f"travel:{location['key']}:{self.fable_state.new_run_id()}",
                    source=f"travel:{location['key']}",
                    run_id=str(run["run_id"]),
                    conn=conn,
                )
                await conn.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET current_node_key=$2, status='entering', updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    run["run_id"],
                    location["travel_node"],
                )
        await ctx.send(f"You travel toward **{location['name']}**.")
        if messages:
            await ctx.send("\n".join(messages))
        await self._enter_campaign_node(
            ctx,
            campaign,
            location["travel_node"],
            run_id=str(run["run_id"]),
        )

    @campaign.command(name="home", aliases=["cottage"])
    @has_char()
    async def campaign_home(self, ctx):
        run, campaign, state = await self._selected_campaign_context(ctx.author.id)
        if not run:
            return await ctx.send("No campaign history is currently focused.")
        home = next(
            (
                location for location in campaign.get("locations") or []
                if isinstance(location, dict) and location.get("home")
            ),
            None,
        )
        async with self.bot.pool.acquire() as conn:
            upgrades = await self.fable_state.list_rewards(
                conn,
                user_id=ctx.author.id,
                reward_type="home_upgrade",
            )
        embed = discord.Embed(
            title=(home or {}).get("name") or "Campaign Home",
            description=(home or {}).get("description") or "Your persistent campaign home.",
            color=0x8A6541,
        )
        if upgrades:
            embed.add_field(
                name="Permanent Upgrades",
                value="\n".join(
                    f"• {str(upgrade.get('display_name') or upgrade.get('reward_key')).replace('_', ' ').title()}"
                    for upgrade in upgrades[:20]
                ),
                inline=False,
            )
        home_state = {
            key: value
            for key, value in state.items()
            if key.startswith("home.") or key.startswith("village.")
        }
        if home_state:
            embed.add_field(
                name="Current State",
                value="\n".join(
                    f"**{key.replace('.', ' ').replace('_', ' ').title()}:** {self._story_state_display(value)}"
                    for key, value in sorted(home_state.items())[:15]
                )[:1024],
                inline=False,
            )
        await ctx.send(embed=embed)

    @campaign.command(name="war", aliases=["warstate"])
    @has_char()
    async def campaign_war(self, ctx):
        """Show authored faction-war values for the selected campaign."""
        await self._send_story_model_overview(
            ctx,
            prefix="war",
            title="Faction War State",
            empty_text="This campaign has not recorded any faction-war state yet.",
        )

    async def _focused_warfront_attempt(self, conn, user_id: int, *, for_update: bool = False):
        lock = " FOR UPDATE OF fwa, fcr" if for_update else ""
        return await conn.fetchrow(
            f"""
            SELECT fwa.attempt_id, fwa.run_id, fwa.player_front_key,
                   fwa.assignments_json, fwa.result_json,
                   fcr.campaign_key, fcr.current_node_key,
                   fcr.campaign_json_snapshot AS campaign_json
            FROM fable_warfront_attempts fwa
            JOIN fable_campaign_runs fcr ON fcr.run_id=fwa.run_id
            LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
            WHERE fcr.user_id=$1 AND fcr.status='awaiting_warfront'
              AND fwa.status='planning'
            ORDER BY (fcr.run_id=fp.selected_run_id) DESC, fcr.updated_at DESC
            LIMIT 1{lock}
            """,
            user_id,
        )

    @campaign.command(name="warplan", aliases=["fronts"])
    @has_char()
    async def campaign_warplan(self, ctx):
        async with self.bot.pool.acquire() as conn:
            attempt = await self._focused_warfront_attempt(conn, ctx.author.id)
        if not attempt:
            return await ctx.send("No warfront is currently awaiting assignments.")
        campaign = self._load_progress(attempt["campaign_json"])
        node = node_by_id(campaign, attempt["current_node_key"])
        if not node or node.get("type") != "warfront":
            return await ctx.send("The focused warfront points to invalid campaign content.")
        await self._send_campaign_warfront_plan(
            ctx,
            campaign,
            node,
            run_id=str(attempt["run_id"]),
        )

    @campaign.command(name="assign")
    @has_char()
    async def campaign_assign(self, ctx, asset_key: str, front_key: str):
        asset_key = normalize_campaign_key(asset_key)
        front_key = normalize_campaign_key(front_key)
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                attempt = await self._focused_warfront_attempt(
                    conn,
                    ctx.author.id,
                    for_update=True,
                )
                if not attempt:
                    return await ctx.send("No warfront is currently awaiting assignments.")
                campaign = self._load_progress(attempt["campaign_json"])
                node = node_by_id(campaign, attempt["current_node_key"])
                warfront = (node or {}).get("warfront") or {}
                available_fronts = await self._available_warfront_fronts(
                    ctx.author.id,
                    campaign,
                    warfront,
                    conn=conn,
                    run_id=str(attempt["run_id"]),
                )
                front = next(
                    (value for value in available_fronts if value.get("id") == front_key),
                    None,
                )
                if not front:
                    return await ctx.send("That front is not available in this operation.")
                if asset_key == "player":
                    await conn.execute(
                        """
                        UPDATE fable_warfront_attempts
                        SET player_front_key=$2, updated_at=NOW()
                        WHERE attempt_id=$1
                        """,
                        attempt["attempt_id"],
                        front_key,
                    )
                    return await ctx.send(f"You will personally lead **{front['title']}**.")
                asset = self._warfront_asset(warfront, asset_key)
                if not asset:
                    return await ctx.send("That companion or allied force is not defined here.")
                available = await self._available_warfront_assets(
                    ctx.author.id,
                    campaign,
                    warfront,
                    conn=conn,
                    run_id=str(attempt["run_id"]),
                )
                if asset_key not in {value["key"] for value in available}:
                    return await ctx.send("That force is not currently available.")
                assignments = self._load_progress(attempt["assignments_json"])
                for assigned_front, values in list(assignments.items()):
                    assignments[assigned_front] = [
                        value for value in values or [] if value != asset_key
                    ]
                target_assets = list(assignments.get(front_key) or [])
                if len(target_assets) >= int(front.get("max_assets") or 1):
                    return await ctx.send("That front has no remaining assignment slots.")
                target_assets.append(asset_key)
                assignments[front_key] = target_assets
                await conn.execute(
                    """
                    UPDATE fable_warfront_attempts
                    SET assignments_json=$2, updated_at=NOW()
                    WHERE attempt_id=$1
                    """,
                    attempt["attempt_id"],
                    json.dumps(assignments, sort_keys=True),
                )
        await ctx.send(
            f"Assigned **{asset.get('name') or asset_key}** to **{front['title']}**."
        )

    @campaign.command(name="unassign")
    @has_char()
    async def campaign_unassign(self, ctx, *, asset_key: str):
        asset_key = normalize_campaign_key(asset_key)
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                attempt = await self._focused_warfront_attempt(
                    conn,
                    ctx.author.id,
                    for_update=True,
                )
                if not attempt:
                    return await ctx.send("No warfront is currently awaiting assignments.")
                if asset_key == "player":
                    await conn.execute(
                        """
                        UPDATE fable_warfront_attempts
                        SET player_front_key='', updated_at=NOW()
                        WHERE attempt_id=$1
                        """,
                        attempt["attempt_id"],
                    )
                    return await ctx.send("Your personal front assignment was cleared.")
                assignments = self._load_progress(attempt["assignments_json"])
                removed = False
                for front_key, values in list(assignments.items()):
                    filtered = [value for value in values or [] if value != asset_key]
                    removed = removed or len(filtered) != len(values or [])
                    assignments[front_key] = filtered
                if not removed:
                    return await ctx.send("That force is not currently assigned.")
                await conn.execute(
                    """
                    UPDATE fable_warfront_attempts
                    SET assignments_json=$2, updated_at=NOW()
                    WHERE attempt_id=$1
                    """,
                    attempt["attempt_id"],
                    json.dumps(assignments, sort_keys=True),
                )
        await ctx.send(f"Unassigned **{asset_key.replace('_', ' ').title()}**.")

    @campaign.command(name="deploy", aliases=["resolvefronts"])
    @has_char()
    async def campaign_deploy(self, ctx):
        consequence_messages = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                attempt = await self._focused_warfront_attempt(
                    conn,
                    ctx.author.id,
                    for_update=True,
                )
                if not attempt:
                    return await ctx.send("No warfront is currently awaiting deployment.")
                campaign = self._load_progress(attempt["campaign_json"])
                node = node_by_id(campaign, attempt["current_node_key"])
                if not node or node.get("type") != "warfront":
                    return await ctx.send("The focused warfront points to invalid campaign content.")
                warfront = node.get("warfront") or {}
                player_front = str(attempt["player_front_key"] or "")
                if not self._warfront_front(warfront, player_front):
                    return await ctx.send(
                        "Choose the front you will personally lead with `$campaign assign player <front>`."
                    )
                assignments = self._load_progress(attempt["assignments_json"])
                available_assets = await self._available_warfront_assets(
                    ctx.author.id,
                    campaign,
                    warfront,
                    conn=conn,
                    run_id=str(attempt["run_id"]),
                )
                available_fronts = await self._available_warfront_fronts(
                    ctx.author.id,
                    campaign,
                    warfront,
                    conn=conn,
                    run_id=str(attempt["run_id"]),
                )
                active_front_keys = {front["id"] for front in available_fronts}
                if player_front not in active_front_keys:
                    return await ctx.send(
                        "Choose an available front with `$campaign assign player <front>`."
                    )
                assignments = {
                    front_key: values
                    for front_key, values in assignments.items()
                    if front_key in active_front_keys
                }
                active_warfront = {**warfront, "fronts": available_fronts}
                eligible_outcome_ids = set()
                for candidate in warfront.get("outcomes") or []:
                    allowed, _reason = await self._evaluate_campaign_conditions(
                        ctx.author.id,
                        candidate.get("conditions") or [],
                        conn=conn,
                        campaign_key=campaign["key"],
                        run_id=str(attempt["run_id"]),
                    )
                    if allowed:
                        eligible_outcome_ids.add(candidate["id"])
                try:
                    resolution = resolve_warfront(
                        active_warfront,
                        assignments,
                        player_front,
                        available_assets,
                        eligible_outcome_ids=eligible_outcome_ids,
                    )
                except ValueError as exc:
                    return await ctx.send(
                        f"This warfront cannot deploy yet: {exc}"
                    )
                results = resolution["fronts"]
                success_count = resolution["successes"]
                outcome = resolution["outcome"]
                for result in results:
                    front = self._warfront_front(warfront, result["front"])
                    result_kind = "success" if result["success"] else "failure"
                    consequence_messages.extend(
                        await self._apply_campaign_effects(
                            ctx.author.id,
                            campaign["key"],
                            effects=front.get(f"{result_kind}_effects") or [],
                            unlocks=front.get(f"{result_kind}_unlocks") or [],
                            event_key=(
                                f"warfront:{attempt['attempt_id']}:{front['id']}:{result_kind}"
                            ),
                            source=f"warfront:{warfront.get('key') or node['id']}",
                            run_id=str(attempt["run_id"]),
                            conn=conn,
                        )
                    )
                consequence_messages.extend(
                    await self._apply_campaign_effects(
                        ctx.author.id,
                        campaign["key"],
                        effects=outcome.get("effects") or [],
                        unlocks=outcome.get("unlocks") or [],
                        event_key=f"warfront:{attempt['attempt_id']}:outcome:{outcome['id']}",
                        source=f"warfront:{warfront.get('key') or node['id']}",
                        run_id=str(attempt["run_id"]),
                        conn=conn,
                    )
                )
                history = list(
                    self._load_progress(
                        await conn.fetchval(
                            "SELECT history_json FROM fable_campaign_runs WHERE run_id=$1",
                            attempt["run_id"],
                        )
                    ) or []
                )
                if node["id"] not in history:
                    history.append(node["id"])
                result_payload = {
                    "outcome": outcome["id"],
                    "target": outcome["target"],
                    "successes": success_count,
                    "fronts": results,
                }
                await conn.execute(
                    """
                    UPDATE fable_warfront_attempts
                    SET status='completed', result_json=$2,
                        completed_at=NOW(), updated_at=NOW()
                    WHERE attempt_id=$1
                    """,
                    attempt["attempt_id"],
                    json.dumps(result_payload, sort_keys=True),
                )
                await conn.execute(
                    """
                    UPDATE fable_campaign_runs
                    SET status='entering', current_node_key=$2,
                        history_json=$3, updated_at=NOW()
                    WHERE run_id=$1
                    """,
                    attempt["run_id"],
                    outcome["target"],
                    json.dumps(history),
                )
        embed = discord.Embed(
            title=outcome.get("title") or "Warfront Resolved",
            description=outcome.get("description") or "The operation changes the war.",
            color=0x2F6B3F,
        )
        for result in results:
            embed.add_field(
                name=f"{'Victory' if result['success'] else 'Loss'} · {result['title']}",
                value=f"Power {result['power']} / Difficulty {result['difficulty']}",
                inline=False,
            )
        if consequence_messages:
            embed.add_field(
                name="Consequences",
                value="\n".join(consequence_messages)[:1024],
                inline=False,
            )
        await ctx.send(embed=embed)
        await self._enter_campaign_node(
            ctx,
            campaign,
            outcome["target"],
            run_id=str(attempt["run_id"]),
        )

    @campaign.command(name="ending", aliases=["epilogue"])
    @has_char()
    async def campaign_ending(self, ctx):
        """Replay the immutable ending summary for the selected campaign."""
        run = await self.bot.pool.fetchrow(
            """
            SELECT fcr.campaign_key, fcr.is_canonical, fcr.ending_snapshot_json
            FROM fable_campaign_runs fcr
            LEFT JOIN fable_player_preferences fp ON fp.user_id=fcr.user_id
            WHERE fcr.user_id=$1
              AND fcr.status='completed'
            ORDER BY (fcr.run_id=fp.selected_run_id) DESC, fcr.completed_at DESC
            LIMIT 1
            """,
            ctx.author.id,
        )
        if not run:
            return await ctx.send("Complete a campaign before revisiting its epilogue.")
        snapshot = self._load_progress(run["ending_snapshot_json"])
        embed = discord.Embed(
            title=str(snapshot.get("ending_title") or "Campaign Epilogue"),
            description=(
                f"Campaign: `{run['campaign_key']}` · "
                f"{'Canonical' if run['is_canonical'] else 'Alternate Chronicle'}"
            ),
            color=0x2F6B3F,
        )
        for fragment in list(snapshot.get("epilogue") or [])[:12]:
            if not isinstance(fragment, dict):
                continue
            embed.add_field(
                name=str(fragment.get("title") or "Aftermath")[:256],
                value=str(fragment.get("text") or "No record.")[:1024],
                inline=False,
            )
        if not embed.fields:
            embed.description += "\n\nThis ending predates modular epilogue records."
        await ctx.send(embed=embed)

    @campaign.command(name="rewards", aliases=["legacy", "collection"])
    @has_char()
    async def campaign_rewards(self, ctx):
        rows = await self.bot.pool.fetch(
            """
            SELECT reward_type, reward_key, display_name, source, unlocked_at
            FROM player_fable_rewards
            WHERE user_id=$1
            ORDER BY reward_type, unlocked_at, reward_key
            """,
            ctx.author.id,
        )
        if not rows:
            return await ctx.send("Your Fable legacy collection is still empty.")
        grouped = {}
        for row in rows:
            grouped.setdefault(str(row["reward_type"]), []).append(
                str(row["display_name"] or row["reward_key"]).replace("_", " ").title()
            )
        embed = discord.Embed(
            title="Fable Legacy Collection",
            description="Permanent rewards earned through campaigns and story quests.",
            color=0x5D2E12,
        )
        for reward_type, names in list(grouped.items())[:12]:
            value = "\n".join(f"• {name}" for name in names[:12])
            if len(names) > 12:
                value += f"\n…and {len(names) - 12} more"
            embed.add_field(
                name=reward_type.replace("_", " ").title(),
                value=value,
                inline=False,
            )
        await ctx.send(embed=embed)

    @quests.command(name="abandon", aliases=["cancel", "drop"])
    @has_char()
    async def quests_abandon(self, ctx, *, quest_key: str):
        raw_quest_key = str(quest_key).strip()
        quest_key = raw_quest_key.lower()
        if quest_key not in QUEST_DEFINITIONS:
            quest_key = self._normalize_custom_quest_key(raw_quest_key)

        async with self.bot.pool.acquire() as conn:
            quest_def, custom_def = await self._resolve_quest_definition(quest_key, conn=conn)
            if not quest_def and not custom_def:
                return await ctx.send("That quest does not exist.")

            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT status, completion_count
                    FROM player_quests
                    WHERE user_id = $1 AND quest_key = $2
                    FOR UPDATE
                    """,
                    ctx.author.id,
                    quest_key,
                )
                if not row or str(row["status"]) != "active":
                    quest_name = quest_def.name if quest_def else custom_def["name"]
                    return await ctx.send(
                        f"**{quest_name}** is not currently active."
                    )

                progress = (
                    self._new_story_progress()
                    if quest_def
                    else self._new_custom_progress()
                )
                await conn.execute(
                    """
                    UPDATE player_quests
                    SET status = 'abandoned',
                        step_index = 0,
                        progress_json = $3,
                        completed_at = NULL,
                        turned_in_at = NULL
                    WHERE user_id = $1 AND quest_key = $2
                    """,
                    ctx.author.id,
                    quest_key,
                    self._dump_progress(progress),
                )
                await conn.execute(
                    """
                    DELETE FROM player_key_items
                    WHERE user_id = $1 AND source_quest = $2
                    """,
                    ctx.author.id,
                    quest_key,
                )

        quest_name = quest_def.name if quest_def else custom_def["name"]
        await ctx.send(
            f"You abandoned **{quest_name}**. "
            f"Use `$quests accept {quest_key}` if you want to start it again."
        )

    @is_gm()
    @commands.group(name="gmquest", aliases=["gmquests"], invoke_without_command=True)
    async def gmquest(self, ctx):
        view = GMQuestBuilderView(cog=self, ctx=ctx)
        await view.refresh_data()
        view._sync_controls()
        view.message = await ctx.send(embed=view.build_embed(), view=view)

    @gmquest.command(name="list")
    async def gmquest_list(self, ctx):
        async with self.bot.pool.acquire() as conn:
            custom_defs = await self._fetch_custom_quest_definitions(conn=conn, active_only=False)
        if not custom_defs:
            return await ctx.send("No custom quests exist yet. Create one with `$gmquest create key | category | name`.")

        lines = []
        for custom_def in custom_defs[:25]:
            state = "active" if custom_def["is_active"] else "draft"
            repeatable = "repeatable" if custom_def["repeatable"] else "one-time"
            lines.append(f"`{custom_def['quest_key']}` - **{custom_def['name']}** ({custom_def['category']}, {state}, {repeatable})")
        await ctx.send("Custom quests:\n" + "\n".join(lines))

    @gmquest.command(name="export", aliases=["download"])
    async def gmquest_export(self, ctx):
        package = await self._build_campaign_export_package()
        payload = json.dumps(package, indent=2, ensure_ascii=True).encode("utf-8")
        filename = f"fablereborn-content-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
        await ctx.send(
            content=(
                "Import this file into `assets/html/campaign_editor.html`. "
                "It contains campaigns, standalone quests, cutscenes, monsters, and editor references."
            ),
            file=discord.File(io.BytesIO(payload), filename=filename),
        )

    @gmquest.command(name="import", aliases=["upload"])
    async def gmquest_import(self, ctx):
        attachments = list(getattr(ctx.message, "attachments", []) or [])
        if not attachments:
            return await ctx.send("Attach a JSON file exported by the campaign editor to `$gmquest import`.")
        attachment = attachments[0]
        if not str(attachment.filename).lower().endswith(".json"):
            return await ctx.send("The attached content package must be a `.json` file.")
        if int(getattr(attachment, "size", 0) or 0) > 8 * 1024 * 1024:
            return await ctx.send("That content package is larger than 8 MB.")
        try:
            raw = await attachment.read()
            package = json.loads(raw.decode("utf-8-sig"))
            summary = await self._import_campaign_package(
                package,
                created_by=ctx.author.id,
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return await ctx.send("That attachment is not valid UTF-8 JSON.")
        except CampaignPackageError as exc:
            details = "\n".join(f"- {error}" for error in exc.errors[:12])
            if len(exc.errors) > 12:
                details += f"\n- ...and {len(exc.errors) - 12} more error(s)."
            return await ctx.send(f"Import rejected:\n{details}")
        except Exception as exc:
            return await ctx.send(f"Import failed before any changes were committed: `{exc}`")
        await ctx.send(
            "Content imported successfully:\n"
            f"- Campaigns: **{summary['campaigns']}**\n"
            f"- Quests: **{summary['quests']}**\n"
            f"- Cutscenes: **{summary['cutscenes']}**\n"
            f"- Custom monsters: **{summary['monsters']}**"
        )

    @gmquest.command(name="create")
    async def gmquest_create(self, ctx, *, data: str):
        try:
            quest_key_raw, category, name = self._split_pipe_args(data, 3, 3)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest create fisher_job | Events | The Fisher's Request`")

        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        if not quest_key:
            return await ctx.send("Quest key must contain letters or numbers.")
        if quest_key in QUEST_DEFINITIONS:
            return await ctx.send("That quest key is already used by a built-in quest.")

        async with self.bot.pool.acquire() as conn:
            existing = await self._fetch_custom_quest_definition(quest_key, conn=conn)
            if existing:
                return await ctx.send("That custom quest key already exists.")
            await conn.execute(
                """
                INSERT INTO custom_quests (
                    quest_key, name, category, short_description, offer_text, turnin_text, objective_json,
                    turnin_json, reward_json, access_json, prerequisite_keys_json,
                    accept_cutscene_key, turnin_cutscene_key, repeatable, is_active, created_by, updated_at
                )
                VALUES ($1, $2, $3, '', '', '', '{}', '{}', '{}', '{}', '[]', NULL, NULL, FALSE, FALSE, $4, NOW())
                """,
                quest_key,
                name,
                category,
                ctx.author.id,
            )
            custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)

        await ctx.send(embed=self._build_custom_quest_admin_embed(custom_def))

    @gmquest.command(name="show", aliases=["view"])
    async def gmquest_show(self, ctx, quest_key: str):
        quest_key = self._normalize_custom_quest_key(quest_key)
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)
        if not custom_def:
            return await ctx.send("That custom quest does not exist.")
        await ctx.send(embed=self._build_custom_quest_admin_embed(custom_def))

    @gmquest.command(name="publish", aliases=["active"])
    async def gmquest_publish(self, ctx, quest_key: str, enabled: str):
        parsed = self._parse_bool(enabled)
        if parsed is None:
            return await ctx.send("Use `on` or `off`.")
        quest_key = self._normalize_custom_quest_key(quest_key)
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"is_active": parsed},
                conn=conn,
                created_by=ctx.author.id,
            )
        status = "active" if parsed else "draft"
        await ctx.send(f"**{custom_def['name']}** is now **{status}**.")

    @gmquest.command(name="repeatable")
    async def gmquest_repeatable(self, ctx, quest_key: str, enabled: str):
        parsed = self._parse_bool(enabled)
        if parsed is None:
            return await ctx.send("Use `on` or `off`.")
        quest_key = self._normalize_custom_quest_key(quest_key)
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"repeatable": parsed},
                conn=conn,
            )
        label = "repeatable" if parsed else "one-time"
        await ctx.send(f"**{custom_def['name']}** is now **{label}**.")

    @gmquest.command(name="text")
    async def gmquest_text(self, ctx, *, data: str):
        try:
            parts = self._split_pipe_args(data, 3, 4)
        except ValueError as exc:
            return await ctx.send(
                f"{exc} Example: `$gmquest text fisher_job | Bring the abbey what it needs. | Brother Halric presses a sealed note into your hand... | Return to Halric once the ash is recovered.`"
            )
        quest_key_raw, short_description, offer_text = parts[:3]
        turnin_text = parts[3] if len(parts) > 3 else None
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        fields = {
            "short_description": short_description,
            "offer_text": offer_text,
        }
        if turnin_text is not None:
            fields["turnin_text"] = turnin_text
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                fields,
                conn=conn,
            )
        await ctx.send(f"Updated quest text for **{custom_def['name']}**.")

    @gmquest.command(name="access")
    async def gmquest_access(self, ctx, *, data: str):
        try:
            parts = self._split_pipe_args(data, 4, 5)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest access fisher_job | off | off | none | april:greg_mode`")
        quest_key_raw, gm_only_raw, booster_only_raw, patreon_raw = parts[:4]
        event_flag_raw = parts[4] if len(parts) > 4 else "none"
        gm_only = self._parse_bool(gm_only_raw)
        booster_only = self._parse_bool(booster_only_raw)
        patreon_tier = None if patreon_raw.strip().lower() == "none" else self._normalize_patreon_tier(patreon_raw)
        event_flag = self._normalize_event_flag(event_flag_raw)
        if gm_only is None or booster_only is None:
            return await ctx.send("GM-only and booster-only values must be `on` or `off`.")
        if patreon_raw.strip().lower() != "none" and patreon_tier is None:
            tiers = ", ".join(sorted(QUEST_PATREON_TIERS))
            return await ctx.send(f"Unknown Patreon tier. Use one of: {tiers}, or `none`.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        access_json = {
            "gm_only": gm_only,
            "booster_only": booster_only,
            "patreon_tier": patreon_tier or "",
            "event_flag": event_flag,
        }
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"access_json": json.dumps(access_json, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Updated access rules for **{custom_def['name']}**.")

    @gmquest.command(name="prereq", aliases=["prereqs", "requires"])
    async def gmquest_prereq(self, ctx, *, data: str):
        try:
            quest_key_raw, prereq_raw = self._split_pipe_args(data, 2, 2)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest prereq fisher_job | greg_ledger, greg_bells`")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        if prereq_raw.strip().lower() == "none":
            prerequisites = []
        else:
            prerequisites = []
            for raw_value in [part.strip() for part in prereq_raw.split(",") if part.strip()]:
                normalized_value = raw_value.lower()
                if normalized_value not in QUEST_DEFINITIONS:
                    normalized_value = self._normalize_custom_quest_key(raw_value)
                prerequisites.append(normalized_value)
        async with self.bot.pool.acquire() as conn:
            for prereq_key in prerequisites:
                if prereq_key not in QUEST_DEFINITIONS:
                    custom = await self._fetch_custom_quest_definition(prereq_key, conn=conn)
                    if not custom:
                        return await ctx.send(f"Unknown prerequisite quest: `{prereq_key}`.")
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"prerequisite_keys_json": json.dumps(prerequisites)},
                conn=conn,
            )
        if prerequisites:
            await ctx.send(f"Updated prerequisites for **{custom_def['name']}**: {', '.join(prerequisites)}")
        else:
            await ctx.send(f"Cleared prerequisites for **{custom_def['name']}**.")

    @gmquest.group(name="objective", invoke_without_command=True)
    async def gmquest_objective(self, ctx):
        await ctx.send("Use `$gmquest objective progress ...`, `$gmquest objective keyitem ...`, or `$gmquest objective drops ...`.")

    @gmquest_objective.command(name="progress")
    async def gmquest_objective_progress(self, ctx, *, data: str):
        try:
            parts = self._split_pipe_args(data, 3, 4)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest objective progress fisher_job | pve | 10 | slime`")
        quest_key = self._normalize_custom_quest_key(parts[0])
        source = self._normalize_source(parts[1])
        if source is None:
            return await ctx.send(f"Source must be one of: {CUSTOM_QUEST_SOURCE_HELP}.")
        try:
            required_count = max(0, int(parts[2]))
        except ValueError:
            return await ctx.send("Required count must be a number.")
        target_name = parts[3] if len(parts) > 3 and parts[3].lower() != "any" else ""
        if source == "adventure" and target_name:
            return await ctx.send("Adventure objectives currently support count-only progress. Leave the target blank or use `any`.")
        objective = {
            "source": source,
            "mode": "progress",
            "required_count": required_count,
            "target_name": target_name,
        }
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {
                    "objective_json": json.dumps(objective, sort_keys=True),
                    "turnin_json": json.dumps({"type": "progress"}, sort_keys=True),
                },
                conn=conn,
            )
        await ctx.send(f"Updated progress objective for **{custom_def['name']}**.")

    @gmquest_objective.command(name="keyitem", aliases=["item"])
    async def gmquest_objective_keyitem(self, ctx, *, data: str):
        try:
            parts = self._split_pipe_args(data, 5, 6)
        except ValueError as exc:
            return await ctx.send(
                f"{exc} Example: `$gmquest objective keyitem fisher_job | pve | 5 | Burnt Ledger Scrap | A scrap of cursed parchment. | slime`"
            )
        quest_key = self._normalize_custom_quest_key(parts[0])
        source = self._normalize_source(parts[1])
        if source is None or source == "none":
            return await ctx.send(f"Key item objectives need a real source: {CUSTOM_QUEST_REAL_SOURCE_HELP}.")
        try:
            required_count = max(0, int(parts[2]))
        except ValueError:
            return await ctx.send("Required count must be a number zero or greater.")
        key_item_name = parts[3]
        key_item_description = parts[4]
        target_name = parts[5] if len(parts) > 5 and parts[5].lower() != "any" else ""
        if source == "adventure" and target_name:
            return await ctx.send("Adventure objectives currently support count-only progress. Leave the target blank or use `any`.")
        key_item_key = self._normalize_custom_quest_key(f"{quest_key}_{key_item_name}")
        objective = {
            "source": source,
            "mode": "key_item",
            "required_count": required_count,
            "target_name": target_name,
            "key_item_key": key_item_key,
            "key_item_name": key_item_name,
            "key_item_description": key_item_description,
            "drop_chance_percent": 100,
            "drop_quantity_min": 1,
            "drop_quantity_max": 1,
            "key_item_required_quantity": 1,
        }
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {
                    "objective_json": json.dumps(objective, sort_keys=True),
                    "turnin_json": json.dumps({"type": "key_item"}, sort_keys=True),
                },
                conn=conn,
            )
        await ctx.send(f"Updated key-item objective for **{custom_def['name']}**.")

    @gmquest_objective.command(name="drops", aliases=["droprules", "loot"])
    async def gmquest_objective_drops(self, ctx, *, data: str):
        try:
            quest_key_raw, chance_raw, min_raw, max_raw, required_qty_raw = self._split_pipe_args(data, 5, 5)
        except ValueError as exc:
            return await ctx.send(
                f"{exc} Example: `$gmquest objective drops fisher_job | 35 | 1 | 3 | 5`"
            )
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        try:
            drop_chance_percent = float(str(chance_raw).replace(",", "").strip())
        except ValueError:
            return await ctx.send("Drop chance must be a number between 0 and 100.")
        if drop_chance_percent < 0 or drop_chance_percent > 100:
            return await ctx.send("Drop chance must be between 0 and 100.")
        try:
            drop_quantity_min = max(1, int(min_raw))
            drop_quantity_max = max(1, int(max_raw))
            key_item_required_quantity = max(1, int(required_qty_raw))
        except ValueError:
            return await ctx.send("Drop minimum, drop maximum, and turn-in quantity must be numbers.")
        if drop_quantity_max < drop_quantity_min:
            return await ctx.send("Drop maximum must be greater than or equal to drop minimum.")

        async with self.bot.pool.acquire() as conn:
            custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)
            if not custom_def:
                return await ctx.send("That custom quest does not exist.")
            objective = custom_def.get("objective") or {}
            if str(objective.get("mode") or "").lower() != "key_item":
                return await ctx.send("Set a key-item objective first.")
            objective.update(
                {
                    "drop_chance_percent": drop_chance_percent,
                    "drop_quantity_min": drop_quantity_min,
                    "drop_quantity_max": drop_quantity_max,
                    "key_item_required_quantity": key_item_required_quantity,
                }
            )
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"objective_json": json.dumps(objective, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Updated key-item drop rules for **{custom_def['name']}**.")

    @gmquest.group(name="turnin", invoke_without_command=True)
    async def gmquest_turnin_group(self, ctx):
        await ctx.send("Use `$gmquest turnin keyitem|progress|crate|money|egg ...`.")

    @gmquest_turnin_group.command(name="keyitem", aliases=["key_item", "item"])
    async def gmquest_turnin_keyitem(self, ctx, quest_key: str):
        quest_key = self._normalize_custom_quest_key(quest_key)
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._fetch_custom_quest_definition(quest_key, conn=conn)
            if not custom_def:
                return await ctx.send("That custom quest does not exist.")
            objective = custom_def.get("objective") or {}
            if str(objective.get("mode") or "").lower() != "key_item":
                return await ctx.send("Set a key-item objective first.")
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"turnin_json": json.dumps({"type": "key_item"}, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Turn-in for **{custom_def['name']}** now requires the quest key item.")

    @gmquest_turnin_group.command(name="progress")
    async def gmquest_turnin_progress(self, ctx, quest_key: str):
        quest_key = self._normalize_custom_quest_key(quest_key)
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"turnin_json": json.dumps({"type": "progress"}, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Turn-in for **{custom_def['name']}** now uses progress only.")

    @gmquest_turnin_group.command(name="crate")
    async def gmquest_turnin_crate(self, ctx, *, data: str):
        try:
            quest_key_raw, rarity_raw, amount_raw = self._split_pipe_args(data, 3, 3)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest turnin crate fisher_job | rare | 2`")
        rarity = self._normalize_crate_rarity(rarity_raw)
        if rarity is None:
            return await ctx.send("Unknown crate rarity.")
        try:
            amount = max(1, int(amount_raw))
        except ValueError:
            return await ctx.send("Amount must be a number.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        turnin = {"type": "crate", "rarity": rarity, "amount": amount}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"turnin_json": json.dumps(turnin, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Turn-in for **{custom_def['name']}** now requires crates.")

    @gmquest_turnin_group.command(name="money", aliases=["gold"])
    async def gmquest_turnin_money(self, ctx, *, data: str):
        try:
            quest_key_raw, amount_raw = self._split_pipe_args(data, 2, 2)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest turnin money fisher_job | 5000`")
        try:
            amount = max(1, int(amount_raw.replace(",", "")))
        except ValueError:
            return await ctx.send("Amount must be a number.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        turnin = {"type": "money", "amount": amount}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"turnin_json": json.dumps(turnin, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Turn-in for **{custom_def['name']}** now requires gold.")

    @gmquest_turnin_group.command(name="egg")
    async def gmquest_turnin_egg(self, ctx, *, data: str):
        try:
            quest_key_raw, egg_name, amount_raw = self._split_pipe_args(data, 3, 3)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest turnin egg fisher_job | Sneevil | 1`")
        try:
            amount = max(1, int(amount_raw))
        except ValueError:
            return await ctx.send("Amount must be a number.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        turnin = {"type": "egg", "egg_name": egg_name, "amount": amount}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"turnin_json": json.dumps(turnin, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Turn-in for **{custom_def['name']}** now requires eggs.")

    @gmquest.group(name="reward", invoke_without_command=True)
    async def gmquest_reward_group(self, ctx):
        await ctx.send("Use `$gmquest reward none|money|crate|item|egg ...`.")

    @gmquest_reward_group.command(name="none", aliases=["story"])
    async def gmquest_reward_none(self, ctx, quest_key_raw: str):
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        reward = {"type": "none"}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"reward_json": json.dumps(reward, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Reward for **{custom_def['name']}** is now story-only.")

    @gmquest_reward_group.command(name="money", aliases=["gold"])
    async def gmquest_reward_money(self, ctx, *, data: str):
        try:
            quest_key_raw, amount_raw = self._split_pipe_args(data, 2, 2)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest reward money fisher_job | 15000`")
        try:
            amount = max(1, int(amount_raw.replace(",", "")))
        except ValueError:
            return await ctx.send("Amount must be a number.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        reward = {"type": "money", "amount": amount}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"reward_json": json.dumps(reward, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Reward for **{custom_def['name']}** now grants gold.")

    @gmquest_reward_group.command(name="crate")
    async def gmquest_reward_crate(self, ctx, *, data: str):
        try:
            quest_key_raw, rarity_raw, amount_raw = self._split_pipe_args(data, 3, 3)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest reward crate fisher_job | rare | 2`")
        rarity = self._normalize_crate_rarity(rarity_raw)
        if rarity is None:
            return await ctx.send("Unknown crate rarity.")
        try:
            amount = max(1, int(amount_raw))
        except ValueError:
            return await ctx.send("Amount must be a number.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        reward = {"type": "crate", "rarity": rarity, "amount": amount}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"reward_json": json.dumps(reward, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Reward for **{custom_def['name']}** now grants crates.")

    @gmquest_reward_group.command(name="egg")
    async def gmquest_reward_egg(self, ctx, *, data: str):
        try:
            quest_key_raw, monster_name = self._split_pipe_args(data, 2, 2)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest reward egg fisher_job | Sneevil`")
        monster = await self._find_monster_by_name(monster_name)
        if not monster:
            return await ctx.send("Unknown monster name for egg reward.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        reward = {"type": "egg", "monster_name": monster["name"]}
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"reward_json": json.dumps(reward, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Reward for **{custom_def['name']}** now grants a **{monster['name']} Egg**.")

    @gmquest_reward_group.command(name="item")
    async def gmquest_reward_item(self, ctx, *, data: str):
        try:
            quest_key_raw, name, item_type_raw, stat_raw, value_raw, element = self._split_pipe_args(data, 6, 6)
        except ValueError as exc:
            return await ctx.send(
                f"{exc} Example: `$gmquest reward item fisher_job | Halric's Buckler | Shield | 220 | 45000 | Light`"
            )
        item_type = next(
            (
                item_type
                for item_type in ItemType
                if item_type.value.lower() == item_type_raw.strip().lower()
                or item_type.name.lower() == item_type_raw.strip().lower()
            ),
            None,
        )
        if item_type is None:
            valid_types = ", ".join(item.value for item in ItemType)
            return await ctx.send(f"Unknown item type. Valid types: {valid_types}")
        try:
            stat = max(0, int(stat_raw))
            value = max(0, int(value_raw.replace(",", "")))
        except ValueError:
            return await ctx.send("Stat and value must be numbers.")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        reward = {
            "type": "item",
            "name": name,
            "item_type": item_type.value,
            "stat": stat,
            "value": value,
            "element": element,
        }
        async with self.bot.pool.acquire() as conn:
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {"reward_json": json.dumps(reward, sort_keys=True)},
                conn=conn,
            )
        await ctx.send(f"Reward for **{custom_def['name']}** now grants a custom item.")

    @gmquest.group(name="cutscene", invoke_without_command=True)
    async def gmquest_cutscene(self, ctx):
        await ctx.send("Use `$gmquest cutscene list|create|addpage|clearpages|attach|preview ...`.")

    @gmquest_cutscene.command(name="list")
    async def gmquest_cutscene_list(self, ctx):
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cutscene_key, title
                FROM quest_cutscenes
                ORDER BY cutscene_key ASC
                """
            )
        if not rows:
            return await ctx.send("No cutscenes exist yet.")
        lines = [f"`{row['cutscene_key']}` - {row['title']}" for row in rows[:40]]
        await ctx.send("Cutscenes:\n" + "\n".join(lines))

    @gmquest_cutscene.command(name="create")
    async def gmquest_cutscene_create(self, ctx, *, data: str):
        try:
            cutscene_key_raw, title = self._split_pipe_args(data, 2, 2)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest cutscene create abbey_warning | Warning Beneath the Bells`")
        cutscene_key = self._normalize_custom_quest_key(cutscene_key_raw)
        if not cutscene_key:
            return await ctx.send("Cutscene key must contain letters or numbers.")
        async with self.bot.pool.acquire() as conn:
            existing = await self._fetch_cutscene_row(cutscene_key, conn=conn)
            if existing:
                return await ctx.send("That cutscene key already exists.")
            await conn.execute(
                """
                INSERT INTO quest_cutscenes (cutscene_key, title, pages_json, created_by, updated_at)
                VALUES ($1, $2, '[]', $3, NOW())
                """,
                cutscene_key,
                title,
                ctx.author.id,
            )
        await ctx.send(f"Created cutscene **{cutscene_key}**.")

    @gmquest_cutscene.command(name="addpage", aliases=["pageadd"])
    async def gmquest_cutscene_addpage(self, ctx, *, data: str):
        try:
            parts = self._split_pipe_args(data, 3, 5)
        except ValueError as exc:
            return await ctx.send(
                f"{exc} Example: `$gmquest cutscene addpage abbey_warning | The Bells Toll | The bells will not stop. | https://image.url | Arrival`"
            )
        cutscene_key = self._normalize_custom_quest_key(parts[0])
        page_title = parts[1]
        text = parts[2]
        image = parts[3] if len(parts) > 3 else ""
        subtitle = parts[4] if len(parts) > 4 else ""
        async with self.bot.pool.acquire() as conn:
            row = await self._fetch_cutscene_row(cutscene_key, conn=conn)
            if not row:
                return await ctx.send("That cutscene does not exist.")
            pages = self._load_progress(row["pages_json"])
            if not isinstance(pages, list):
                pages = []
            pages.append(
                {
                    "title": page_title,
                    "subtitle": subtitle,
                    "text": text,
                    "image": image,
                }
            )
            await conn.execute(
                """
                UPDATE quest_cutscenes
                SET pages_json = $2,
                    updated_at = NOW()
                WHERE cutscene_key = $1
                """,
                cutscene_key,
                json.dumps(pages),
            )
        await ctx.send(f"Added page **{len(pages)}** to `{cutscene_key}`.")

    @gmquest_cutscene.command(name="clearpages")
    async def gmquest_cutscene_clearpages(self, ctx, cutscene_key: str):
        cutscene_key = self._normalize_custom_quest_key(cutscene_key)
        async with self.bot.pool.acquire() as conn:
            row = await self._fetch_cutscene_row(cutscene_key, conn=conn)
            if not row:
                return await ctx.send("That cutscene does not exist.")
            await conn.execute(
                """
                UPDATE quest_cutscenes
                SET pages_json = '[]',
                    updated_at = NOW()
                WHERE cutscene_key = $1
                """,
                cutscene_key,
            )
        await ctx.send(f"Cleared all pages from `{cutscene_key}`.")

    @gmquest_cutscene.command(name="attach")
    async def gmquest_cutscene_attach(self, ctx, *, data: str):
        try:
            quest_key_raw, slot_raw, cutscene_raw = self._split_pipe_args(data, 3, 3)
        except ValueError as exc:
            return await ctx.send(f"{exc} Example: `$gmquest cutscene attach fisher_job | turnin | greg_black_ledger`")
        quest_key = self._normalize_custom_quest_key(quest_key_raw)
        slot = str(slot_raw).strip().lower()
        if slot not in {"accept", "turnin"}:
            return await ctx.send("Cutscene slot must be `accept` or `turnin`.")
        cutscene_key = "" if cutscene_raw.strip().lower() == "none" else self._normalize_custom_quest_key(cutscene_raw)
        async with self.bot.pool.acquire() as conn:
            if cutscene_key:
                row = await self._fetch_cutscene_row(cutscene_key, conn=conn)
                if not row:
                    return await ctx.send("That cutscene does not exist.")
            column = "accept_cutscene_key" if slot == "accept" else "turnin_cutscene_key"
            custom_def = await self._update_custom_quest_fields(
                quest_key,
                {column: cutscene_key or None},
                conn=conn,
            )
        await ctx.send(
            f"{slot.capitalize()} cutscene for **{custom_def['name']}** is now `{cutscene_key or 'none'}`."
        )

    @gmquest_cutscene.command(name="preview", aliases=["show"])
    async def gmquest_cutscene_preview(self, ctx, cutscene_key: str):
        cutscene_key = self._normalize_custom_quest_key(cutscene_key)
        if not await self.play_cutscene(ctx, cutscene_key, mark_seen=False):
            await ctx.send("That cutscene does not exist or has no pages.")

async def setup(bot):
    await bot.add_cog(Quests(bot))
