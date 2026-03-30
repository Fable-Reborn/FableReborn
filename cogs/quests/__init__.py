import json
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path

import discord

from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View

from classes.enums import DonatorRank
from classes.items import ItemType
from utils.april_fools import APRIL_FOOLS_GREG_FLAG
from utils.checks import has_char, is_gm


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
CUSTOM_QUEST_SOURCES = {"none", "pve", "adventure", "battletower", "scripted"}
CUSTOM_QUEST_MODES = {"progress", "key_item"}
CUSTOM_QUEST_TURNIN_TYPES = {"progress", "key_item", "crate", "egg", "money"}
CUSTOM_QUEST_REWARD_TYPES = {"money", "crate", "item", "egg", "none"}
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
            emoji="▶️",
            disabled=self.current_page >= len(self.pages) - 1,
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
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self,
        )


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
        self.journal_view.selected_quest_key = quests[0]["quest_def"].key if quests else None
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


class QuestJournalView(View):
    def __init__(self, *, ctx, entries: list[dict]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.entries = entries
        self.categories = sorted({entry["category"] for entry in entries})
        self.selected_category = self.categories[0] if self.categories else None
        first_entry = self.filtered_entries[0] if self.filtered_entries else None
        self.selected_quest_key = first_entry["quest_key"] if first_entry else None
        self._sync_controls()

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
        embed.set_footer(text="Use the dropdowns to switch category or quest.")
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
                    "placeholder": "pve, adventure, battletower, scripted, none",
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
                    "placeholder": "pve, adventure, battletower, scripted",
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
                    raise ValueError("Source must be one of: none, pve, adventure, battletower, scripted.")
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
                    raise ValueError("Key item objectives need a real source: pve, adventure, battletower, or scripted.")
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
        await self.cog.play_cutscene(self.ctx, cutscene_key)

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
        await self.cog.play_cutscene(self.ctx, cutscene_key)

    async def refresh_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.refresh_message()
        await interaction.followup.send("Quest builder refreshed.", ephemeral=True)


class Quests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._monster_cache = None

    async def cog_load(self):
        await self._init_tables()

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
            await self._seed_default_cutscenes(conn)
            await self._attach_default_greg_finale_cutscene(conn)
            await self._remove_legacy_greg_quest_data(conn)

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
        source = str(raw or "").strip().lower()
        return source if source in CUSTOM_QUEST_SOURCES else None

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

    async def play_cutscene(self, ctx, cutscene_key: str) -> bool:
        row = await self._fetch_cutscene_row(cutscene_key)
        if not row:
            return False
        pages_data = self._load_progress(row["pages_json"])
        if not isinstance(pages_data, list) or not pages_data:
            return False
        pages = self._create_story_pages(
            pages_data,
            str(row["title"] or "Quest Scene"),
        )
        view = QuestPageView(pages, ctx.author.id)
        await ctx.send(embed=pages[0], view=view)
        return True

    async def _get_monster_catalog(self) -> list[dict]:
        if self._monster_cache is not None:
            return self._monster_cache
        try:
            with MONSTERS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            self._monster_cache = []
            return self._monster_cache

        catalog = []
        for monsters in data.values():
            if not isinstance(monsters, list):
                continue
            for monster in monsters:
                if isinstance(monster, dict) and monster.get("name"):
                    catalog.append(monster)
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
        if reward_type == "none":
            return "Story progression only. No material reward."
        return "Reward not configured yet."

    def _custom_objective_text(self, custom_def: dict) -> str:
        objective = custom_def.get("objective") or {}
        turnin = custom_def.get("turnin") or {}
        source = str(objective.get("source") or "none").lower()
        required_count = int(objective.get("required_count") or 0)
        key_item_required_quantity = max(1, int(objective.get("key_item_required_quantity") or 1))
        drop_chance_percent = max(0.0, min(100.0, float(objective.get("drop_chance_percent") or 100)))
        drop_quantity_min = max(1, int(objective.get("drop_quantity_min") or 1))
        drop_quantity_max = max(drop_quantity_min, int(objective.get("drop_quantity_max") or drop_quantity_min))
        target_name = str(objective.get("target_name") or "").strip()
        source_label = {
            "none": "anywhere",
            "pve": "PvE",
            "adventure": "Adventure",
            "battletower": "Battle Tower",
            "scripted": "Scripted Encounter",
        }.get(source, source.title())
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

    async def _user_meets_custom_access(self, user_id: int, custom_def: dict, *, conn=None) -> tuple[bool, str | None]:
        access = custom_def.get("access") or {}
        event_flag = self._normalize_event_flag(access.get("event_flag"))
        if event_flag and not self._event_flag_enabled(event_flag):
            return False, f"This quest is disabled until event flag **{self._event_flag_label(event_flag)}** is enabled."
        if access.get("gm_only") and not await self._user_is_gm(user_id, conn=conn):
            return False, "This quest is locked to game masters."
        if access.get("booster_only") and not await self._user_has_booster_role(user_id):
            return False, "This quest is locked to support server boosters."
        patreon_tier = self._normalize_patreon_tier(access.get("patreon_tier"))
        if patreon_tier:
            rank = await self.bot.get_donator_rank(user_id)
            required_rank = getattr(DonatorRank, patreon_tier)
            if not rank or rank < required_rank:
                return False, f"This quest requires Patreon tier **{patreon_tier}** or higher."

        prerequisites = custom_def.get("prerequisites") or []
        for prereq_key in prerequisites:
            if prereq_key and not await self.is_quest_completed(user_id, str(prereq_key), conn=conn):
                return False, f"You must complete **{prereq_key}** first."
        return True, None

    async def _custom_quest_visible_to_user(self, user_id: int, custom_def: dict, *, conn=None) -> tuple[bool, str | None]:
        if not custom_def or not custom_def.get("is_active"):
            return False, "That quest is not currently active."
        return await self._user_meets_custom_access(user_id, custom_def, conn=conn)

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
            source_label = {
                "pve": "PvE",
                "adventure": "Adventure",
                "battletower": "Battle Tower",
                "scripted": "Scripted Encounter",
            }.get(str(objective.get("source") or "").lower(), "Quest")
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
            description = page["text"]
            subtitle = str(page.get("subtitle") or "").strip()
            if subtitle:
                description = f"**{subtitle}**\n\n{description}"
            embed = discord.Embed(
                title=page["title"],
                description=description,
                color=0x1F0D0D,
            )
            image_url = str(page.get("image") or "").strip()
            if image_url:
                embed.set_image(url=image_url)
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

    async def _process_custom_source_completion(
        self,
        ctx,
        source: str,
        *,
        candidate_names: tuple[str | None, ...] = (),
    ) -> None:
        notifications: list[tuple[dict, dict, int]] = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
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
                    if str(objective.get("source") or "").lower() != source:
                        continue
                    if not self._match_name_filter(
                        objective.get("target_name"),
                        *candidate_names,
                    ):
                        continue

                    progress = self._load_progress(row["progress_json"])
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
    ) -> bool:
        normalized_source = self._normalize_source(source)
        if normalized_source is None or normalized_source == "none":
            return False
        await self._process_custom_source_completion(
            ctx,
            normalized_source,
            candidate_names=candidate_names,
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
                if str(objective.get("source") or "").lower() != normalized_source:
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
        entries = await self._get_journal_entries(ctx.author.id)
        if not entries:
            async with self.bot.pool.acquire() as conn:
                owned_rows = await conn.fetch(
                    """
                    SELECT quest_key, status, completion_count
                    FROM player_quests
                    WHERE user_id = $1
                    """,
                    ctx.author.id,
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
            embed = discord.Embed(
                title="Quest Journal",
                description="You have no accepted or ongoing quests right now.",
                color=0x3E2617,
            )
            available = []
            completed = []
            for quest_def in QUEST_DEFINITIONS.values():
                quest_state = owned_statuses.get(quest_def.key)
                if quest_state and quest_state["completion_count"] > 0:
                    completed.append(f"**{quest_def.name}**")
                    continue
                if quest_state and quest_state["status"] == "active":
                    continue
                if self._quest_available(quest_def.key):
                    available.append(
                        f"**{quest_def.name}**\n{quest_def.short_description}\nStart with `$quests accept {quest_def.key}`."
                    )
            for custom_def in custom_defs:
                quest_state = owned_statuses.get(custom_def["quest_key"])
                if quest_state and quest_state["completion_count"] > 0 and not custom_def["repeatable"]:
                    completed.append(f"**{custom_def['name']}**")
                    continue
                if quest_state and quest_state["status"] == "active":
                    continue
                visible, reason = await self._custom_quest_visible_to_user(
                    ctx.author.id,
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
            embed.set_footer(text="Use $quests accept <quest> to begin one.")
            return await ctx.send(embed=embed)

        view = QuestJournalView(ctx=ctx, entries=entries)
        await ctx.send(embed=view.build_embed(), view=view)

    @quests.command(name="accept", aliases=["start", "take"])
    @has_char()
    async def quests_accept(self, ctx, *, quest_key: str):
        raw_quest_key = str(quest_key).strip()
        quest_key = raw_quest_key.lower()
        if quest_key not in QUEST_DEFINITIONS:
            quest_key = self._normalize_custom_quest_key(raw_quest_key)
        async with self.bot.pool.acquire() as conn:
            quest_def, custom_def = await self._resolve_quest_definition(quest_key, conn=conn)
            if not quest_def and not custom_def:
                return await ctx.send("That quest does not exist.")
            if quest_def and not self._quest_available(quest_key):
                return await ctx.send("That quest is not currently available.")
            if custom_def:
                visible, reason = await self._custom_quest_visible_to_user(
                    ctx.author.id,
                    custom_def,
                    conn=conn,
                )
                if not visible:
                    return await ctx.send(reason or "That quest is not currently available.")

            existing = await conn.fetchrow(
                """
                SELECT status, completion_count
                FROM player_quests
                WHERE user_id = $1 AND quest_key = $2
                """,
                ctx.author.id,
                quest_key,
            )
            if existing:
                if existing["status"] == "active":
                    return await ctx.send("You already accepted that quest.")
                if (
                    (quest_def or (custom_def and not custom_def["repeatable"]))
                    and (
                        existing["status"] == "completed"
                        or int(existing["completion_count"] or 0) > 0
                    )
                ):
                    return await ctx.send("You have already completed that quest.")

            if quest_def:
                progress = self._new_story_progress()
                category = quest_def.category
                title = quest_def.name
                description = quest_def.start_text
                objective_text = quest_def.steps[0].objective
                reward_text = quest_def.reward_text
                footer_text = f"Turn in progress with $quests turnin {quest_def.key}"
                accept_cutscene_key = ""
            else:
                progress = self._new_custom_progress()
                category = custom_def["category"]
                title = custom_def["name"]
                description = custom_def["offer_text"] or custom_def["short_description"]
                objective_text = self._custom_objective_text(custom_def)
                reward_text = self._custom_reward_text(custom_def)
                footer_text = f"Turn in progress with $quests turnin {custom_def['quest_key']}"
                accept_cutscene_key = custom_def.get("accept_cutscene_key", "")

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
                ctx.author.id,
                quest_key,
                category,
                self._dump_progress(progress),
            )

        embed = discord.Embed(
            title=f"Quest Accepted: {title}",
            description=description,
            color=0x5D2E12,
        )
        embed.add_field(
            name="Current Objective",
            value=objective_text,
            inline=False,
        )
        embed.add_field(name="Reward", value=reward_text, inline=False)
        embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

        if accept_cutscene_key:
            await self.play_cutscene(ctx, accept_cutscene_key)

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
                await self.play_cutscene(ctx, custom_def["turnin_cutscene_key"])
            if quest_key == "greg_finale":
                if greg_badge_granted:
                    await ctx.send("**Gregapocalypse Survivor** has been added to your profile.")
                elif greg_badge_already:
                    await ctx.send("Your Gregapocalypse badge was already on your profile.")

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
            return await ctx.send("Source must be one of: none, pve, adventure, battletower, scripted.")
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
            return await ctx.send("Key item objectives need a real source: pve, adventure, battletower, or scripted.")
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
        if not await self.play_cutscene(ctx, cutscene_key):
            await ctx.send("That cutscene does not exist or has no pages.")

async def setup(bot):
    await bot.add_cog(Quests(bot))
