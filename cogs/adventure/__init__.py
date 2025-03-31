"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio

from datetime import datetime, timedelta
from enum import Enum
from functools import partial
from typing import Literal

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.interactions import Interaction
from discord.ui.button import Button

from classes.classes import Ritualist
from classes.classes import from_string as class_from_string
from classes.context import Context
from classes.converters import IntFromTo
from classes.enums import DonatorRank
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import items
from utils import misc as rpgtools
from utils import random
import random as randomm
from utils.checks import has_adventure, has_char, has_no_adventure, is_class, is_gm
from utils.i18n import _, locale_doc, use_current_gettext
from utils.maze import Cell, Maze

from classes.classes import (
    ALL_CLASSES_TYPES,
    Mage,
    Paragon,
    Raider,
    Ranger,
    Ritualist,
    Thief,
    Warrior,
    Paladin,
    SantasHelper,
)

ADVENTURE_NAMES = {
    1: "Mystic Grove",
    2: "Rising Mist Bridge",
    3: "Moonlit Solitude",
    4: "Orcish Ambush",
    5: "Trials of Conviction",
    6: "Canyon of Flames",
    7: "Sentinel Spire",
    8: "Abyssal Sanctum",
    8: "Abyssal Sanctum",
    9: "Shadowmancer's Citadel",
    10: "Dragon's Bane: Arzagor's End",
    11: "Quest for Avalon's Blade",
    12: "Seekers of Lemuria",
    13: "Phoenix's Embrace",
    14: "Requiem of Shadows",
    15: "Abysswalker's Challenge",
    16: "Vecca's Legacy",
    17: "Gemstone Odyssey",
    18: "Shrek's Swamp",
    19: "Kord's Resurgence",
    20: "Arena of Endurance",
    21: "Quest for the Astral Relic",
    22: "Nocturnal Enigma",
    23: "Luminous Quest",
    24: "Web of Betrayal",
    25: "Realm of Indolence",
    26: "Forgotten Valley",
    27: "Temple of the Sirens",
    28: "Osiris' Judgment",
    29: "War God's Parley",
    30: "Divine Convergence",
    31: "Shadow Convergence",
    32: "Abyssal Titans",
    33: "Cursed Bloodmoon",
    34: "Pandemonium Rifts",
    35: "Dread Plague",
    36: "Apocalypse Eclipse",
    37: "Eldritch Horrors",
    38: "Crimson Pact",
    39: "Serpent's Dominion",
    40: "Chrono Reckoning",
    41: "Cursed Ascendancy",
    42: "Elder Eclipse",
    43: "Netherstorm Siege",
    44: "Ragnarok's Awakening",
    45: "Abyssal Inferno",
    46: "Eclipse of Oblivion",
    47: "Voidwalker's Dominion",
    48: "Doomsday Eclipse",
    49: "Worldbreaker Cataclysm",
    50: "Elder God's Reckoning",
    51: "Cataclysmic Eruption",
    52: "Abyssal Cataclysm",
    53: "Infernal Collapse",
    54: "Titan's Wrath",
    55: "Demonic Ruination",
    56: "Armageddon's Echo",
    57: "Cosmic Decay",
    58: "Hellfire Conflagration",
    59: "Chaos Ascendant",
    60: "Realm's End",
    61: "Pestilent Apocalypse",
    62: "Void Annihilation",
    63: "Darkstar Convergence",
    64: "Solar Destruction",
    65: "Endless Nightfall",
    66: "Pandora's Fury",
    67: "Eternal Dread",
    68: "Blood Moon Despair",
    69: "Ruins of Despair",
    70: "Wyrm's Cataclysm",
    71: "Harbinger of Doom",
    72: "Annihilator's Onslaught",
    73: "Infinite Void",
    74: "Endbringer's Wrath",
    75: "Calamity's Dawn",
    76: "Eldritch Devastation",
    77: "Doom Herald's Reign",
    78: "Hellgate Incursion",
    79: "Maelstrom's Core",
    80: "Dark Realm's Cataclysm",
    81: "Chthonic End",
    82: "Cosmic Ruin",
    83: "Endless Oblivion",
    84: "Eternal Oblivion",
    85: "Demon King's Reign",
    86: "Soulfire Cataclysm",
    87: "Abyssal Ruination",
    88: "Eclipse of Despair",
    89: "Nightmare's End",
    90: "Ragnarok's Fall",
    91: "Hellstorm's Wrath",
    92: "Doomsday's Demise",
    93: "Oblivion's Maw",
    94: "Netherworld Collapse",
    95: "Eldritch Cataclysm",
    96: "Dread Overlord's Fury",
    97: "Infernal Apocalypse",
    98: "Darkstar's End",
    99: "World's End Catastrophe",
    100: "End of All Things",

}



DIRECTION = Literal["n", "e", "s", "w"]
ALL_DIRECTIONS: set[DIRECTION] = {"n", "e", "s", "w"}


class ActiveAdventureAction(Enum):
    MoveNorth = 0
    MoveEast = 1
    MoveSouth = 2
    MoveWest = 3

    AttackEnemy = 4
    Defend = 5
    Recover = 6


class ActiveAdventureDirectionView(discord.ui.View):
    def __init__(
            self,
            user: discord.User,
            future: asyncio.Future[ActiveAdventureAction],
            possible_actions: set[ActiveAdventureAction],
            *args,
            **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.user = user
        self.future = future

        north = Button(
            style=ButtonStyle.primary,
            label=_("North"),
            disabled=ActiveAdventureAction.MoveNorth not in possible_actions,
            emoji="\U00002b06",
            row=0,
        )
        east = Button(
            style=ButtonStyle.primary,
            label=_("East"),
            disabled=ActiveAdventureAction.MoveEast not in possible_actions,
            emoji="\U000027a1",
            row=0,
        )
        south = Button(
            style=ButtonStyle.primary,
            label=_("South"),
            disabled=ActiveAdventureAction.MoveSouth not in possible_actions,
            emoji="\U00002b07",
            row=0,
        )
        west = Button(
            style=ButtonStyle.primary,
            label=_("West"),
            disabled=ActiveAdventureAction.MoveWest not in possible_actions,
            emoji="\U00002b05",
            row=0,
        )

        attack = Button(
            style=ButtonStyle.secondary,
            label=_("Attack"),
            disabled=ActiveAdventureAction.AttackEnemy not in possible_actions,
            emoji="\U00002694",
            row=1,
        )
        defend = Button(
            style=ButtonStyle.secondary,
            label=_("Defend"),
            disabled=ActiveAdventureAction.Defend not in possible_actions,
            emoji="\U0001f6e1",
            row=1,
        )
        recover = Button(
            style=ButtonStyle.secondary,
            label=_("Recover"),
            disabled=ActiveAdventureAction.Recover not in possible_actions,
            emoji="\U00002764",
            row=1,
        )

        north.callback = partial(self.handle, action=ActiveAdventureAction.MoveNorth)
        east.callback = partial(self.handle, action=ActiveAdventureAction.MoveEast)
        south.callback = partial(self.handle, action=ActiveAdventureAction.MoveSouth)
        west.callback = partial(self.handle, action=ActiveAdventureAction.MoveWest)
        attack.callback = partial(self.handle, action=ActiveAdventureAction.AttackEnemy)
        defend.callback = partial(self.handle, action=ActiveAdventureAction.Defend)
        recover.callback = partial(self.handle, action=ActiveAdventureAction.Recover)

        self.add_item(north)
        self.add_item(east)
        self.add_item(south)
        self.add_item(west)
        self.add_item(attack)
        self.add_item(defend)
        self.add_item(recover)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def handle(
            self, interaction: Interaction, action: ActiveAdventureAction
    ) -> None:
        self.stop()
        self.future.set_result(action)
        msg = await interaction.response.defer()
        await msg.edit(content="New content")

    async def on_timeout(self) -> None:
        self.future.set_exception(asyncio.TimeoutError())


class ActiveAdventure:
    def __init__(
            self, ctx: Context, attack: int, defense: int, width: int = 15, height: int = 15
    ) -> None:
        self.ctx = ctx

        self.original_hp = attack * 100
        self.original_enemy_hp = attack * 10

        self.width = width
        self.height = height
        self.maze = Maze.generate(width=width, height=height)
        self.player_x = 0
        self.player_y = 0
        self.attack = attack
        self.defense = defense
        self.hp = attack * 100

        self.heal_hp = round(attack * 0.25) or 1
        self.min_dmg = round(attack * 0.5)
        self.max_dmg = round(attack * 1.5)

        self.enemy_hp: int | None = None

        self.message: discord.Message | None = None
        self.status_text: str | None = _("The active adventure has started.")

    def move(self, action: ActiveAdventureAction) -> None:
        if action == ActiveAdventureAction.MoveNorth:
            self.player_y -= 1
        elif action == ActiveAdventureAction.MoveEast:
            self.player_x += 1
        elif action == ActiveAdventureAction.MoveSouth:
            self.player_y += 1
        elif action == ActiveAdventureAction.MoveWest:
            self.player_x -= 1

        self.maze.player = (self.player_x, self.player_y)

        if self.enemy_hp:
            status_1 = None
            status_2 = None

            enemy_action = random.choice(
                [
                    ActiveAdventureAction.AttackEnemy,
                    ActiveAdventureAction.Defend,
                    ActiveAdventureAction.Recover,
                ]
            )

            if enemy_action == ActiveAdventureAction.Recover:
                self.enemy_hp += self.heal_hp
                self.enemy_hp = (
                    self.original_enemy_hp
                    if self.enemy_hp > self.original_enemy_hp
                    else self.enemy_hp
                )
                status_1 = ("The Enemy healed themselves for {hp} HP").format(
                    hp=self.heal_hp
                )

            if action == ActiveAdventureAction.Recover:
                self.hp += self.heal_hp
                self.hp = self.original_hp if self.hp > self.original_hp else self.hp
                status_2 = _("You healed yourself for {hp} HP").format(hp=self.heal_hp)

            if (
                    enemy_action == ActiveAdventureAction.AttackEnemy
                    and action == ActiveAdventureAction.Defend
            ) or (
                    enemy_action == ActiveAdventureAction.Defend
                    and action == ActiveAdventureAction.AttackEnemy
            ):
                status_1 = _("Attack blocked.")
            else:
                if enemy_action == ActiveAdventureAction.AttackEnemy:
                    eff = random.randint(self.min_dmg, self.max_dmg)
                    self.hp -= eff
                    status_1 = _("The Enemy hit you for {dmg} damage").format(dmg=eff)
                if action == ActiveAdventureAction.AttackEnemy:
                    self.enemy_hp -= self.attack
                    status_2 = _("You hit the enemy for {dmg} damage").format(
                        dmg=self.attack
                    )

            if status_1 and status_2:
                self.status_text = f"{status_1}\n{status_2}"
            elif status_1:
                self.status_text = status_1
            elif status_2:
                self.status_text = status_2

    async def reward(self, treasure: bool = True) -> int:
        val = self.attack + self.defense
        if treasure:
            money = random.randint(1200, val * 80)
        else:
            # The adventure end reward
            money = random.randint(val * 80, val * 215)
        async with self.ctx.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                money,
                self.ctx.author.id,
            )
            await self.ctx.bot.log_transaction(
                self.ctx,
                from_=1,
                to=self.ctx.author.id,
                subject="AA Reward",
                data={"Gold": money},
                conn=conn,
            )

        return money

    async def run(self) -> None:
        while not self.is_at_exit and self.hp > 0:
            try:
                move = await self.get_move()
            except asyncio.TimeoutError:
                return await self.message.edit(content=_("Timed out."))

            # Reset status message since it'll change now
            self.status_text = None

            self.move(move)

            if self.enemy_hp is not None and self.enemy_hp <= 0:
                self.status_text = _("You defeated the enemy.")
                self.enemy_hp = None
                self.cell.enemy = False

            # Handle special cases of cells

            if self.cell.trap:
                damage = random.randint(self.original_hp // 10, self.original_hp // 8)
                self.hp -= damage
                self.status_text = _(
                    "You stepped on a trap and took {damage} damage!"
                ).format(damage=damage)
                self.cell.trap = False
            elif self.cell.treasure:
                money_rewarded = await self.reward()
                self.status_text = _(
                    "You found a treasure with **${money}** inside!"
                ).format(money=money_rewarded)
                self.cell.treasure = False
            elif self.cell.enemy and self.enemy_hp is None:
                self.enemy_hp = self.original_enemy_hp

        if self.hp <= 0:
            await self.message.edit(content=_("You died."))
            return

        money_rewarded = await self.reward(treasure=False)

        await self.message.edit(
            content=_(
                "You have reached the exit and were rewarded **${money}** for getting"
                " out!"
            ).format(money=money_rewarded),
            view=None,
        )

    @property
    def player_hp_bar(self) -> str:
        fields = int(self.hp / self.original_hp * 10)
        return f"[{'▯' * fields}{'▮' * (10 - fields)}]"

    @property
    def enemy_hp_bar(self) -> str:
        fields = int(self.enemy_hp / self.original_enemy_hp * 10)
        return f"[{'▯' * fields}{'▮' * (10 - fields)}]"

    async def get_move(self) -> ActiveAdventureAction:
        explanation_text = _("`@` - You, `!` - Enemy, `*` - Treasure")

        if self.enemy_hp is None:
            hp_text = _("You are on {hp} HP").format(hp=self.hp)

            if self.status_text is not None:
                text = f"{self.status_text}```\n{self.maze}\n```\n{explanation_text}\n{hp_text}"
            else:
                text = f"```\n{self.maze}\n```\n{explanation_text}\n{hp_text}"
        else:
            enemy = _("Enemy")
            hp = _("HP")
            fight_status = f"""```
{self.ctx.disp}
{"-" * len(self.ctx.disp)}
{self.player_hp_bar}  {self.hp} {hp}

{enemy}
{"-" * len(enemy)}
{self.enemy_hp_bar}  {self.enemy_hp} {hp}
```"""

            if self.status_text is not None:
                text = f"{self.status_text}```\n{self.maze}\n```\n{explanation_text}\n{fight_status}"
            else:
                text = f"```\n{self.maze}\n```\n{explanation_text}\n{fight_status}"

        possible = set()

        if self.enemy_hp is not None:
            possible.add(ActiveAdventureAction.AttackEnemy)
            possible.add(ActiveAdventureAction.Defend)
            possible.add(ActiveAdventureAction.Recover)
        else:
            free = self.free
            if "n" in free:
                possible.add(ActiveAdventureAction.MoveNorth)
            if "e" in free:
                possible.add(ActiveAdventureAction.MoveEast)
            if "s" in free:
                possible.add(ActiveAdventureAction.MoveSouth)
            if "w" in free:
                possible.add(ActiveAdventureAction.MoveWest)

        future = asyncio.Future()
        view = ActiveAdventureDirectionView(self.ctx.author, future, possible)

        if self.message:
            await self.message.edit(content=text, view=view)
        else:
            self.message = await self.ctx.send(content=text, view=view)

        return await future

    @property
    def free(self) -> set[DIRECTION]:
        return ALL_DIRECTIONS - self.cell.walls

    @property
    def is_at_exit(self) -> bool:
        return self.player_x == self.width - 1 and self.player_y == self.height - 1

    @property
    def cell(self) -> Cell:
        return self.maze[self.player_x, self.player_y]


class Adventure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.ADVENTURE_EVENTS = {
            # Levels 1-10: Beginner adventurer
            "tier_1": [
                # Village Life Gone Wrong
                "In an attempt to help the village baker with their annual festival preparations, you discovered their prized magical yeast had gained sentience and was leading a revolution of the pastries, demanding better rising conditions and shorter baking times",
                "While assisting the town crier, you uncovered a conspiracy of local cats who had been systematically replacing important announcements with demands for more treats and afternoon naps",
                "During the village's seasonal cleaning, you found an enchanted broom in the elder's closet that insisted on sweeping things under rugs in increasingly impossible ways, including trying to hide the village fountain",
                "A simple job watching the blacksmith's forge turned chaotic when you discovered the apprentice had accidentally enchanted all the tools, leading to hammers playing hide-and-seek and tongs telling bad metalworking jokes",

                # Magical Mishaps
                "What started as a routine delivery to the local wizard's tower became an adventure in chaos control when you found their mail-order magic beans had sprouted inside the tower, turning it into a vertical jungle gym for excited squirrels",
                "While helping sort books in the village library, you had to wrangle a group of escaped bookworms that had evolved into literature-quoting butterflies, leaving trails of poetry wherever they flew",
                "A merchant's request for help with inventory became complicated when their magical abacus gained sentience and started rearranging all the numbers to create mathematical jokes",
                "You discovered the village well had been enchanted by a well-meaning but inexperienced witch, causing it to dispense different beverages based on the user's singing voice - with some truly unfortunate results for tone-deaf villagers",

                # Creature Encounters
                "What seemed like a simple chicken-chasing task evolved into diplomatic negotiations when you discovered the escaped birds had formed a sophisticated society in the woods, complete with a parliamentary system and weekly drum circles",
                "While investigating missing socks from the village laundry, you found a family of pixies using them to build elaborate hot air balloons for their annual racing championship",
                "A farmer's request for help with garden pests revealed a society of sophisticated mice wearing tiny monocles and top hats, who were actually conducting etiquette classes for the local wildlife",
                "You mediated a heated dispute between a family of raccoons and a gang of squirrels over territory rights to the village's best garbage cans, eventually establishing a complex time-sharing agreement",

                # Festival Chaos
                "During the annual cheese rolling festival, you had to chase down a wheel of enchanted cheese that had gained both consciousness and a surprisingly detailed understanding of local geography",
                "The village's harvest dance became more exciting than planned when the enchanted decorations decided to join in, leading to a night of dancing with animated scarecrows and surprisingly graceful hay bales",
                "What should have been a simple pie-judging contest at the summer fair turned into chaos when a mischievous sprite enchanted all the entries to express strong opinions about their own flavors",
                "The winter solstice celebration needed your help when the traditional ice sculptures came to life and started rearranging themselves into increasingly abstract art installations",

                # Market Day Adventures
                "A merchant's request for help setting up their stall turned into an adventure when their collection of 'perfectly normal' rugs turned out to be a family of shapeshifting carpets looking for their long-lost ottoman",
                "While helping organize the weekly market, you had to resolve a dispute between a ghost trying to sell 'slightly used' haunted objects and the merchant guild's strict 'no supernatural sales' policy",
                "Your attempt to help a traveling potion seller organize their wares went awry when a shelf collapse created a mixture that turned all the market's signs into enthusiastic but terrible poets",
                "A simple job guarding market stalls overnight became complicated when you discovered the produce was holding nightly talent shows, with particularly dramatic performances from the asparagus section",

                # Woodland Wanderings
                "During a mushroom gathering expedition, you stumbled upon a fairy ring where pixies were conducting a rather serious debate about whether dewdrops should be counted as legitimate currency",
                "What started as a routine herb-collecting task turned interesting when you found a grove of talking plants arguing about proper sunlight etiquette and the importance of personal space",
                "While mapping a new hiking trail, you encountered a family of bears who had accidentally stumbled upon an abandoned teatime set and were attempting to recreate high society manners",
                "Your forest foraging was interrupted by a group of dryads hosting an inter-tree poetry competition, with judging based on leaf arrangement and dramatic branch swaying",

                # Small Town Mysteries
                "Investigating missing chickens from the local farm led you to discover they hadn't been stolen - they'd been recruited by a traveling circus of performing animals as acrobats",
                "The case of the mysterious midnight music turned out to be a secret society of owls attempting to form the world's first nocturnal orchestra, with questionable success",
                "When townspeople reported their gardens rearranging overnight, you uncovered a group of moonlight-loving gnomes practicing their skills in extreme landscape architecture",
                "The mystery of disappearing laundry was solved when you found a colony of clothing-conscious sprites who had been 'borrowing' items to host underground fashion shows",

                # Magical Wildlife Management
                "Called to handle a 'pest problem,' you instead found yourself mediating between a family of philosophically-inclined mice debating the ethical implications of cheese consumption",
                "What seemed like a simple rabbit invasion of the community garden turned out to be an organized protest against the lack of gourmet carrot varieties",
                "The reported 'dangerous wildlife' near the village mill was actually a beaver architect trying to implement ambitious redesigns for more efficient water flow",
                "Complaints about noisy birds led to the discovery of a ravens' debate club practicing their argumentation skills, complete with tiny spectacles and notepads",

                # Weather-Related Whimsy
                "During an unusually foggy morning, you helped guide lost weather spirits who had taken a wrong turn at the last cloud formation and were asking for directions to the nearest rainbow",
                "A rainy day turned magical when you discovered the puddles were actually portals being tested by apprentice water elementals learning about interdimensional travel",
                "What seemed like a normal spring shower became an adventure when you had to help organize raindrops that had decided to strike for better working conditions and more colorful rainbow representation",
                "The village's unexpected snow day was caused by a young frost spirit practicing their snow-sculpting techniques, leading to an impromptu winter art exhibition",

                # Domestic Disasters
                "A housewife's request for help with spring cleaning revealed her furniture had formed a labor union and was demanding better dusting conditions and regular polish breaks",
                "The town's communal laundry day became chaotic when a miscast cleaning spell caused all the washing to gain consciousness and strong opinions about fabric softener",
                "What started as helping an elderly woman with her garden turned interesting when her vegetables revealed they were participating in an underground beauty contest",
                "You were called to investigate strange noises in a cellar, only to find the stored preserves had organized a rather sophisticated social hierarchy based on jar size",

                # Agricultural Adventures
                "The farmer's prize-winning pumpkins turned out to be secret philosophers, holding midnight debates about the meaning of gourd existence",
                "A request to help with the harvest led to mediating a dispute between wheat stalks arguing about proper swaying techniques in the breeze",
                "The orchard's apple-picking season was complicated by trees that had developed very specific preferences about who could climb their branches",
                "You discovered the missing hay bales hadn't been stolen - they'd rolled away to start their own traveling circus",

                # Small Business Troubles
                "The local tavern's storage problems turned out to be caused by barrels that had developed distinct personalities and were arranging themselves by mood rather than content",
                "Helping the town blacksmith led to discovering their tools had formed a labor union, demanding shorter working hours and more frequent oil breaks",
                "The baker's inventory issues were traced to a group of animated rolling pins practicing for the annual 'Great Wooden Utensil Race'",
                "A shopkeeper's request for help with accounting revealed their abacus had gained sentience and was trying to teach mathematics to the other measuring tools",

                # Lost and Found
                "The case of missing gardening tools was solved when you found them having a tea party with some elderly garden gnomes, discussing proper mulching techniques",
                "Searching for a child's lost toy revealed an underground lost-and-found society run by well-meaning mice in tiny security uniforms",
                "The mysterious disappearance of the town's socks led to discovering a family of pixies using them to build elaborate sock puppet theaters",
                "You tracked down the village's missing wind chimes to find them rehearsing for an avant-garde musical performance",

                # Courier Quests
                "A simple delivery became complex when the package turned out to contain a very opinionated magical map that insisted on taking 'the scenic route'",
                "Your courier run was interrupted by a group of enchanted signposts having an existential crisis about their purpose in life",
                "What should have been a routine mail delivery turned interesting when you discovered the letters were writing replies to themselves",
                "A package delivery to the local wizard was complicated by the parcel's apparent ability to teleport to wherever you weren't looking",

                # Neighborhood Watch
                "Night patrol duty revealed a group of gargoyles from the old church practicing their poses for the upcoming 'Most Intimidating Statue' competition",
                "Investigating suspicious noises led to finding a gathering of shadows practicing their scariest shapes for Halloween",
                "The reported 'suspicious character' turned out to be a very lost scarecrow trying to find its way back to its field using a map made of straw",
                "You discovered the nightly disturbances were caused by a group of retired guard dogs running a late-night patrol training academy",

                # Seasonal Specials
                "During spring cleaning, you had to negotiate with dust bunnies that had evolved into a sophisticated society with their own laws about proper corner ownership",
                "The summer solstice celebration needed your help when the ceremonial bonfire developed a personality and refused to stay in its designated pit",
                "Autumn leaf-raking became an adventure when the piles of leaves turned out to be hosting elaborate theatrical performances",
                "Winter preparations were complicated by discovering the stored firewood was holding philosophical debates about the nature of warmth",

                "You broke up a tavern brawl between a group of off-duty guards and some rowdy goblins, earning yourself free drinks and a mysterious map from a grateful barmaid",
                "During a routine delivery to a nearby farm, you stumbled upon a fairy ring and had to dance with pixies until dawn to ensure their blessing for a bountiful harvest",
                "You helped a young witch round up her escaped enchanted pumpkins before they could terrorize the local harvest festival with their terrible vegetable puns",
                "While fishing at dawn, you caught a talking trout who offered you three wishes - but each one came with an increasingly ridiculous catch",

                "You protected a traveling merchant's caravan from a pack of wolves, only to discover the wolves were actually cursed nobles trying to find their way home",
                "During a village festival, you participated in a pie-eating contest that turned chaotic when the baker's magical ingredients caused everyone to float to the ceiling",
                "You helped a clumsy apprentice wizard recover his master's escaped scrolls before they could cause any more citizens to spontaneously break into song",
                "While gathering herbs in the forest, you mediated a territory dispute between a family of badgers and a group of displaced brownies",

                "You investigated strange noises in an old mill, finding a group of goblins attempting to start their own illegal cookie-baking operation",
                "During a routine patrol of the town walls, you discovered a secret society of mice wearing tiny armor and planning a 'revolution' against the local cats",
                "You helped a desperate farmer deal with a crop-eating scarecrow that came to life and developed a particular taste for his prize-winning turnips",
                "While delivering mail between villages, you had to negotiate with a bridge troll who insisted on implementing a new 'riddle-based' toll system",

                "You investigated reports of stolen chickens, only to find a young dragon wyrmling trying to start its own farm because it was tired of the 'traditional' dragon lifestyle",
                "During a stormy night, you helped a ghost remember where they left their keys so they could finally stop haunting the local lighthouse",
                "You won a drinking contest against a dwarf, only to discover it was actually a job interview for a secret underground courier service",
                "While helping clean the local temple, you accidentally activated an ancient ritual that turned all the pigeons in town into tiny, cooing philosophers",

                "You protected a traveling circus from bandits, earning yourself a magical token that makes you speak in rhymes during the full moon",
                "During a village wedding, you had to chase down the enchanted wedding ring that decided it wasn't ready for commitment",
                "You helped a group of awakened shrubs migrate to better soil, avoiding the local lumberjacks who were very confused by the moving plants",
                "While picking mushrooms, you mediated a territorial dispute between two families of sprites arguing over who owned the best dewdrops",

                "You investigated strange sounds in the woods, discovering a bear that had accidentally eaten magical honey and could now only speak in sophisticated riddles",
                "During the winter solstice festival, you helped track down the town's missing Festive Spirit - literally, as it had gotten lost on its way to the celebration",
                "You rescued a merchant's prized singing chicken from a group of tone-deaf goblins trying to start their own traveling musical troupe",
                "While clearing out rats from a cellar, you discovered they had organized their own tiny government and were planning urban development projects",

                "You helped a young druid convince a stubborn tree to move three feet to the left so the town could finish building their new well",
                "During a rainstorm, you sheltered in a cave with a group of kobolds and ended up teaching them the basics of sustainable mining practices",
                "You assisted a mischievous pixie in returning all the left shoes they had collected over the years to their rightful owners",
                "While guarding a merchant's warehouse, you discovered a family of raccoons wearing tiny masks and capes, fashioning themselves as vigilante heroes",
                "You helped settle a dispute between two halfling families arguing over whose grandmother's cookie recipe was secretly magical"
            ],
            "tier_2": [
                # Dangerous Dungeons
                "While exploring ancient catacombs, you narrowly escaped a trap-filled corridor where enchanted statues tried to play a deadly game of 'red light, green light' with poison dart launchers",
                "Deep in a forgotten tomb, you encountered a philosophical lich who challenged you to a battle of wits before resorting to the traditional necromancy when you pointed out a flaw in their logic",
                "You survived a harrowing descent into the 'Pit of Moderate Doom' where every level was actually a mimic trying to earn their dungeon certification",
                "In the 'Definitely Not Trapped' treasure vault, you had to choreograph your way through a maze of pressure plates while a bored ancient spirit provided sarcastic commentary",

                # Dark Magic Incidents
                "You thwarted a cult of wannabe necromancers whose zombie uprising was failing because their undead kept forming labor unions and demanding better working conditions",
                "While investigating disappearing townspeople, you discovered a novice witch had accidentally turned them into talking furniture - and some were enjoying their new life as fancy chairs",
                "You confronted a mad wizard whose experimental spells had created a pocket dimension where everything was backwards, including gravity and the flow of time",
                "During a magical anomaly, you had to contain a surge of wild magic that was turning the town's buildings into giant confectionery - much to the delight of passing hill giants",

                # Monster Hunting
                "You tracked down a shapeshifting mimic that had infiltrated the royal mint and was slowly replacing coins with chocolate duplicates",
                "While hunting a pack of dire wolves, you discovered they were actually cursed nobles who had angered a druid by criticizing their fashion choices",
                "You faced off against a hydra that had the unfortunate condition of growing increasingly sarcastic heads with each one cut off",
                "The town's monster problem turned out to be a young dragon trying to make it as a street performer, whose fire-breathing acts were a bit too realistic",

                # Deadly Wilderness
                "Deep in the Dark Forest, you navigated through a grove of carnivorous trees that tried to negotiate for 'just a finger or two' instead of attempting to eat you whole",
                "You survived an encounter with a tribe of territorial trolls who challenged you to a riddle contest, but their riddles were all just dad jokes",
                "While crossing the Misty Mountains, you had to outsmart an avalanche elemental who had developed a twisted sense of humor about 'going downhill'",
                "In the Whispering Woods, you faced off against a banshee whose wails were actually critiques of your fashion choices",

                # Underground Peril
                "In the dwarven mines, you dealt with a cave-in caused by a earth elemental having an existential crisis about its role in plate tectonics",
                "You navigated a maze-like series of tunnels while being pursued by a gelatinous cube that kept trying to 'clean up' your equipment",
                "Deep underground, you encountered a society of deep gnomes whose mining operation had accidentally awakened an ancient stone golem with OCD about proper tunnel alignment",
                "While exploring abandoned mines, you had to negotiate with a colony of kobolds who had turned the place into an underground water park",

                # Dark Fey Encounters
                "You survived an encounter with dark fey who trapped travelers in eternal dance competitions - their only weakness was their inability to handle modern dance moves",
                "While lost in the Twilight Grove, you had to win a game of riddles against a group of shadow sprites who only spoke in puns",
                "You escaped the clutches of a fey noble who collected adventurers as garden statues, but only the ones striking heroic poses",
                "In the realm of the dark fey, you participated in a magical heist to steal back children's teeth from a corrupt tooth fairy syndicate",

                # Haunted Locations
                "You cleansed a haunted manor whose ghosts were locked in an eternal debate about proper interior decorating",
                "While investigating a haunted lighthouse, you discovered a phantom crew still trying to warn ships about the dangers of improper maritime safety protocols",
                "You exorcised spirits from an abandoned theater who were condemned to eternally perform increasingly absurd interpretations of classical plays",
                "In a haunted tavern, you had to serve drinks to ghostly patrons who could only move on after experiencing the perfect last call",

                # Magical Beast Problems
                "You tracked down a griffin that had been stealing the town's livestock but was actually just trying to start a petting zoo",
                "While hunting a basilisk, you discovered it had terrible self-esteem and was petrifying people by accident during social anxiety attacks",
                "You dealt with a chimera whose heads couldn't agree on proper hunting techniques, leading to chaotic and dangerous territory disputes",
                "In the hills, you encountered a manticore running an illegal fighting ring for magical beasts with very specific rules about proper trash-talking",

                # Bandit Troubles
                "You infiltrated a bandit camp where the thieves had developed an complex honor code about which types of dramatic entrance lines were acceptable during raids",
                "While tracking notorious bandits, you discovered their leader was actually three goblins in a trenchcoat trying to save their village from land developers",
                "You faced off against the infamous 'Genteel Bandits' who insisted on serving tea before any proper robbery",
                "In the borderlands, you dealt with a gang of bandits whose magical disguises malfunctioned, leaving them stuck looking like various forest creatures",

                # Cursed Items
                "You contained a cursed sword that kept trying to convince its wielders to become traveling bards instead of fighters",
                "While investigating missing items, you found a cursed bag of holding that had developed a taste for fine cheese and was ransacking the town's dairy shops",
                "You tracked down a set of cursed armor that turned its wearer into a compulsive interior decorator",
                "In the marketplace, you stopped a cursed mirror that was trapping people in their own reflections until they admitted their most embarrassing secrets",

                # Evil Plots
                "You foiled a plot by cultists who were trying to summon a demon but kept getting increasingly annoyed door-to-door salesmen instead",
                "While investigating disappearances, you uncovered a conspiracy of doppelgangers who were terrible at impersonating their targets due to poor research",
                "You stopped an evil wizard's plan to mind control the town, which failed because all his thralls became obsessed with starting book clubs",
                "In the city's underbelly, you exposed a thieves' guild whose elaborate heist plans were consistently ruined by their cat mascot's need for attention",

                # Magical Disasters
                "You contained a magical explosion that turned all the town's weapons into musical instruments - the warriors were particularly upset about their swords becoming flutes",
                "While investigating magical anomalies, you found a tear in reality that was leaking alternative versions of yourself, each more dramatically heroic than the last",
                "You stabilized a wizard's tower that had become partially sentient and was trying to relocate itself to a city with better weather",
                "In the aftermath of a magical accident, you had to round up escaped experimental potions that were giving inanimate objects very strong opinions",

                # Elemental Chaos
                "You calmed an angry water elemental that had taken over the town's fountain and was critiquing everyone's drinking habits",
                "While dealing with elemental rifts, you encountered a fire elemental competing with a local blacksmith for the title of 'Best Metalworker'",
                "You negotiated peace between warring earth and air elementals whose conflict was really just a misunderstanding about proper garden maintenance",
                "In the mountains, you helped an ice elemental who had accidentally frozen their favorite view and couldn't figure out how to defrost it without ruining the scenery"
            ],
            "tier_3": [
                # Complex Dungeon Scenarios
                "In the 'Maze of Eternal Torment,' you survived a series of rooms where reality itself shifted with each step, while shadow demons hunted you through mirrors of your deepest fears",
                "Deep within the 'Crypts of the Mad Lich,' you battled through chambers where gravity reversed randomly, facing hordes of undead that reassembled themselves in increasingly grotesque ways",
                "You navigated the 'Halls of Twisted Dimensions' where each door opened to a different plane of existence, while being pursued by a phase spider matriarch and her reality-bending offspring",
                "In the 'Pit of Sacrificial Regret,' you fought through layers of ancient defensive magic that turned your own memories into physical manifestations trying to kill you",

                # Dangerous Magical Accidents
                "You contained a catastrophic magical explosion that was turning people inside out while making them experience every possible timeline of their lives simultaneously",
                "While investigating a wizard's failed experiment, you had to seal multiple tears in reality that were merging the Material Plane with the Nine Hells, one demon invasion at a time",
                "You survived ground zero of a transmutation catastrophe where flesh and stone were randomly exchanging properties, turning victims into living statues crying tears of magma",
                "In the aftermath of a failed ritual, you battled through waves of time distortions where each wound you received aged parts of your body decades in seconds",

                # Deadly Monster Encounters
                "You faced off against a chimera that had absorbed the powers of its victims, sporting dozens of mutated heads each capable of unleashing different devastating elemental attacks",
                "During a midnight raid, you survived an encounter with a vampire lord whose very shadow could drain life essence, while his blood-mist form corroded both armor and flesh",
                "You battled an ancient medusa whose gaze could not only petrify, but shatter other petrified victims into storms of stone shrapnel animated by her hatred",
                "Deep in the forest, you encountered a wendigo whose haunting cries could drive entire villages to cannibalistic madness, its mere presence causing the land to wither and die",

                # Dark Ritual Sites
                "You interrupted a cult's ceremony that was trying to merge a demon prince with a dragon's corpse, fighting through waves of half-transformed cultists whose flesh was still reforming",
                "Within the 'Temple of Eternal Night,' you stopped a ritual that was literally unwriting people from existence while rewriting them as servants of the void",
                "You battled through the 'Sanctuary of Forbidden Sacrifice' where each ritual chamber contained progressively more horrifying experiments in soul manipulation and flesh crafting",
                "In the 'Caverns of the Flesh Weavers,' you discovered a massive ritual site where cultists were fusing living victims into a gigantic flesh golem powered by trapped souls",

                # Cursed Locations
                "You ventured into the 'Manor of Broken Time' where each room existed in a different era, and the ghosts of every person who would ever die there hunted the living",
                "Within the 'Forest of Flayed Dreams,' you survived trees that bled when cut and whispered the secrets of those they had killed, their branches reaching out to add more victims to their collective consciousness",
                "You explored the 'Mines of Mind's End,' where the crystals showed you visions of every possible way you could die, while slowly driving you mad with the whispers of those who had already succumbed",
                "In the 'Valley of Twisted Flesh,' you navigated through a landscape where the ground itself was made of living tissue, and the air carried spores that slowly transformed breathing creatures into part of the valley",

                # Eldritch Horrors
                "You confronted a being from beyond the stars whose mere presence caused reality to buckle, while its countless eyes showed visions of worlds it had already consumed",
                "Deep beneath the earth, you encountered an ancient horror whose telepathic screams drove everyone within miles to violent madness, their flesh reshaping to match their broken minds",
                "You survived contact with a creature that existed between moments of time, its touch aging or de-aging its victims randomly while feeding on their lost years",
                "In an abandoned temple, you faced an entity that could step through reflections, each mirror showing a more horrifying version of itself that could reach through to drag victims into a realm of endless mirrors",

                # Demonic Incursions
                "You battled through a demon lord's vanguard as they turned a city's population into possessed warriors, their bodies twisting and bursting with infernal mutations",
                "While defending a sacred site, you fought waves of demons whose very blood could corrupt and transform those it touched, turning holy ground into small patches of the Abyss",
                "You survived an assault by demon-possessed siege engines that fired balls of screaming souls, each impact spreading waves of corruption that drove survivors to join the demons' ranks",
                "In the city's underbelly, you discovered a demon prince's plot to transform the sewers into a labyrinth of flesh and bone, using captured citizens as living building materials",

                # Necromantic Catastrophes
                "You fought through the aftermath of a necromancer's failed ascension ritual that raised every corpse within miles, each undead sharing the necromancer's last moments of agony",
                "While investigating mass disappearances, you found a lich's experimental chamber where they were fusing multiple souls into single bodies to create more powerful undead servants",
                "You survived a death knight's assault on a temple, where each fallen defender rose as a corrupted version of their former self, their holy powers twisted to serve darkness",
                "In an ancient battlefield, you confronted a necromantic storm that raised the dead and fused them into massive amalgamations of bone and rotting flesh, each one absorbing more bodies as it fought",

                # Planar Threats
                "You sealed a breach to the Shadowfell that was slowly merging with the Material Plane, turning living creatures into shadow versions of themselves that hunted their still-living friends",
                "While investigating strange disappearances, you discovered tears in reality leading to the Far Realm, where the laws of physics and nature held no meaning",
                "You survived being pulled into a demiplane created from crystallized nightmares, where every fear you've ever had became real and hunted you through ever-shifting landscapes",
                "In the mountains, you closed a portal to the Plane of Fire that was turning the surrounding lands into an infernal wasteland, complete with fire elementals that could possess those they burned",

                # Abyssal Horrors
                "Deep in forgotten catacombs, you encountered an aboleth's lair where the water could transform swimmers into eternal slaves, their bodies adapting to underwater life while their minds shattered",
                "You ventured into a beholder's twisted sanctum where each eye stalk could bend a different aspect of reality, turning intruders into abstract art pieces of flesh and bone",
                "While exploring an ancient ruin, you faced a mind flayer outpost where they were experimenting with ways to speed up the ceremorphosis process, creating horrifically malformed elder brain spawn",
                "In the underdark, you survived contact with a neothelid whose psychic powers could turn victims' brains into puddles of gray matter that it could control like puppet strings",

                # Forbidden Magic
                "You contained a wild magic surge that was causing spontaneous mutations, each magical effect more catastrophic than the last as reality's fabric began to unravel",
                "While investigating a wizard's tower, you fought through rooms where failed experiments had created pockets of pure chaos, randomly transforming anything that entered them",
                "You survived exposure to a time-warping spell that trapped victims in loops of their own death, each iteration more painful and prolonged than the last",
                "In an abandoned academy, you discovered a forbidden ritual that was trying to harvest the magical potential from living creatures, leaving behind hollow shells of pure magical energy"
            ],
            "tier_4": [
                # Reality-Breaking Rituals
                "You interrupted a coven channeling powers from five elder gods simultaneously, each god's influence causing a different apocalyptic event to unfold across the kingdom",
                "Deep within an obsidian ziggurat, you fought through a ritual merging hundreds of dragons' souls into a single entity, their combined consciousness threatening to overwrite local reality",
                "You battled cultists performing 'The Unweaving,' a ritual slowly unraveling the threads of reality itself, causing people and places to become unmade from existence",
                "In the 'Sanctum of Infinite Sacrifice,' you stopped a ceremony that was harvesting the collective pain of an entire city to forge a weapon capable of killing immortal beings",

                # World-Ending Magical Disasters
                "You contained a magical cataclysm that was crystallizing all organic matter within a hundred miles, turning living beings into conscious crystal statues that could feel every crack",
                "While investigating magical anomalies, you discovered a spell gone wrong that was causing parallel timelines to violently merge, creating horrific hybrid beings from alternate selves",
                "You survived the epicenter of a thaumaturgical explosion that turned a city's population into living paradoxes, their very existence causing reality to hemorrhage raw magic",
                "In a wizard's megadungeon, you dealt with an artificial plane collapsing in on itself, each layer of reality crushing into the next while still containing living, screaming victims",

                # Planar Catastrophes
                "You sealed massive rifts to multiple elemental planes that were causing reality to fragment into pure elemental chaos, each shard a deadly pocket dimension of pure elemental energy",
                "While defending a planar nexus, you fought beings that existed as living equations, their very presence rewriting the mathematical constants that held reality together",
                "You navigated the 'Maze of Infinite Planes,' where each intersection connected to a different plane of existence, while being hunted by entities that fed on dimensional energy",
                "In the aftermath of a planar convergence, you battled through a landscape where multiple planes had violently merged, creating impossible hybrid environments that killed anything not adapted to all realities simultaneously",

                # Elder Being Manifestations
                "You prevented the full manifestation of an elder god whose partial emergence was already causing people to evolve backwards through their species' entire evolutionary history",
                "While investigating mass disappearances, you encountered a being that existed as living time, its mere presence causing localized time loops that trapped victims in endless cycles of death",
                "You survived contact with an entity that fed on probability itself, causing cascading waves of impossible events that rewrote history with each passing moment",
                "In the depths of the ocean, you confronted a cosmic horror whose dreams were becoming reality, transforming the local geography into impossible non-Euclidean structures filled with eyes",

                # Forbidden Knowledge Events
                "You contained an infectious idea that caused anyone who understood it to become a living portal to the Far Realm, their bodies transforming into gateways for eldritch horrors",
                "While exploring an ancient library, you fought memetic entities that could possess anyone who read about them, using their victims to write themselves into more books",
                "You survived exposure to the 'Tome of Infinite Recursion,' which showed readers every possible version of their death simultaneously across all possible timelines",
                "In a sage's tower, you dealt with a spell that had achieved consciousness and was rewriting other spells to create an ecosystem of living magic that fed on spellcasters",

                # Dimensional Horrors
                "You battled creatures that existed in four-dimensional space, their true forms only partially visible in our reality as they harvested organs from multiple timelines simultaneously",
                "While sealing planar breaches, you fought beings that could step through the angles of reality, each movement bringing them through a different plane of existence",
                "You survived an encounter with entities that existed between seconds, their feeding frenzies visible only as missing time and unexplained injuries",
                "In a corrupted sanctuary, you faced horrors that could fold space around themselves, turning corridors into Möbius strips of endless pursuit",

                # Reality-Warping Phenomena
                "You stabilized a cascade of wild magic that was causing local reality to experience every possible outcome simultaneously, creating a quantum soup of conflicting events",
                "While investigating temporal anomalies, you navigated a region where cause and effect had become untethered, forcing you to experience events before their causes",
                "You contained a phenomenon that was crystallizing probability itself, causing increasingly unlikely events to become certainties while making normal physics impossible",
                "In a destabilized magic zone, you dealt with pockets of pure possibility where thoughts instantly became reality, leading to a landscape shaped by unconscious nightmares",

                # Cosmic-Scale Threats
                "You prevented the alignment of eldritch constellations that were trying to rearrange local space-time into a more 'geometrically pleasing' configuration",
                "While defending a celestial nexus, you fought cosmic entities that existed as living mathematical proofs attempting to solve the equation of existence",
                "You survived an event where multiple dimensions were being compacted into a singularity, each layer of crushed reality still containing living, conscious beings",
                "In the realm between realities, you faced beings that fed on universal constants, their mere presence causing physics to break down in expanding waves",

                # Mind-Breaking Scenarios
                "You navigated through a psychic catastrophe that had merged thousands of minds into a single, twisted consciousness that was rewriting reality to match its broken perspective",
                "While investigating mass hysteria, you fought through a psychic storm that was materializing people's inner demons as physical entities hunting their originals",
                "You survived exposure to the 'Gallery of Infinite Reflections,' where each mirror showed a reality that was slightly wrong, the differences driving viewers to violent madness",
                "In an abandoned mind flayer colony, you dealt with a psychic resonance that forced everyone to experience the last moments of its victims, their deaths echoing endlessly",

                # Time-Twisted Catastrophes
                "You stabilized a temporal collapse that was causing multiple timelines to violently merge, creating chimeric beings made from every possible version of themselves",
                "While sealing time rifts, you fought future versions of yourself that had succumbed to various cosmic horrors, each one trying to ensure their timeline would come to pass",
                "You contained a phenomenon that was causing time to flow backwards for living beings while their consciousness remained moving forward, trapping them in decaying bodies",
                "In a time-lost citadel, you faced paradox predators that fed on causality itself, each kill retroactively erasing their victims from history"
            ],
            "tier_5": [
                # Multi-Planar Catastrophes
                "You battled through the 'Confluence of Infinite Planes,' where every plane of existence was violently merging into a single point, creating impossible hybrid realities where visitors experienced all forms of death simultaneously",
                "While defending the planar barriers, you fought entities that existed as living gaps between dimensions, their bodies made of compressed space-time containing the screaming remnants of consumed universes",
                "You survived the collapse of the 'Grand Planar Hierarchy,' where the boundaries between planes dissolved, causing angels, demons, and elementals to merge into horrific amalgamations of divine and profane power",
                "In the space between realities, you sealed tears in the fabric of existence that were allowing the Void to consume entire planes, leaving behind only echoes of countless extinguished lives",

                # Reality-Ending Rituals
                "You interrupted the 'Ritual of Infinite Convergence,' where cultists were sacrificing entire realities to birth a new universe shaped by their twisted ideals",
                "Deep within the 'Citadel of Forbidden Truths,' you stopped a ceremony that was systematically unwriting the fundamental laws of magic from existence, causing cascading failures in reality itself",
                "You fought through the 'Temple of Undefined Existence,' where each ritual chamber was dedicated to erasing a different fundamental force of nature from all possible timelines",
                "Among the ruins of a thousand realities, you prevented the completion of a ritual designed to collapse all possible futures into a single, eternal moment of suffering",

                # Cosmic Horror Manifestations
                "You confronted an entity that existed as crystallized entropy, its mere presence accelerating the heat death of the local universe while consuming the potential energy of all possible futures",
                "While investigating the silence of the gods, you encountered a being that fed on divine essence, each god it consumed adding to its arsenal of twisted divine powers",
                "You survived contact with a horror that existed in the spaces between thoughts, slowly replacing memories with windows into impossible dimensions",
                "In the depths of unreality, you faced a creature composed of compressed time, each layer of its being showing a different age of the universe experiencing apocalypse",

                # Universal Constants Under Threat
                "You stabilized the fundamental forces of reality as they began to break down, causing matter itself to forget how to exist while consciousness remained intact within the dissolving forms",
                "While protecting the Pillars of Creation, you battled entities that were rewriting the mathematical foundations of existence, causing cascade failures in causality itself",
                "You contained a phenomenon that was causing the speed of light to become variable, leading to pockets of time flowing backwards while space tied itself into conscious knots",
                "In the primordial chaos, you fought to maintain the separation of fundamental forces as they tried to reunite into their pre-universe state",

                # Time-Space Catastrophes
                "You navigated the 'Labyrinth of Fractured Time,' where each moment existed simultaneously in all possible states, and paradoxes took physical form to hunt those who didn't belong",
                "While sealing chronal rifts, you battled beings that had evolved at the end of time, coming back to ensure their own existence by consuming all other possible futures",
                "You survived the collapse of temporal causality, where effect could precede cause by millennia, and every action created ripples of paradox through all of history",
                "In the 'Chambers of Lost Moments,' you faced entities that fed on lost opportunities, each one a window into lives that could have been but never were",

                # Divine Calamities
                "You prevented the death of the last god, whose passing would have unraveled the divine magic holding reality's fabric together",
                "While defending the celestial spheres, you fought through armies of fallen angels whose corrupted divine power was rewriting the laws of reality",
                "You survived the 'War in Heaven,' where gods battled across multiple planes of existence, their conflicts causing entire realities to be born and die in moments",
                "In the divine realms, you sealed breaches caused by dead gods falling through dimensions, their divine corpses corrupting any plane they touched",

                # Dimensional Collapse Events
                "You stabilized the collapse of the multiverse as dimensions began folding in on themselves, creating layers of compressed reality where countless versions of history played out simultaneously",
                "While investigating dimensional anomalies, you fought creatures born from the friction between colliding universes, their bodies made of crystallized possibility",
                "You contained the spread of 'dimensional cancer,' where corrupted pockets of space-time were metastasizing across multiple planes of existence",
                "In the spaces between universes, you faced entities that had evolved to prey on entire dimensions, leaving behind only void and echoes",

                # Reality Matrix Corruption
                "You repaired corrupted ley lines that were causing reality to render incorrectly, leading to people and places existing in impossible states of quantum uncertainty",
                "While defending reality's source code, you battled viral ideas that were rewriting the basic assumptions of existence across multiple planes",
                "You survived exposure to pure chaos as it tried to reformat local reality, causing matter to reorganize itself according to alien geometries",
                "In the foundations of existence, you faced AI-like entities that had evolved within the mathematical framework of reality itself",

                # Metaphysical Disasters
                "You prevented the concept of death from being erased from existence, as immortality threatened to overflow the universe with eternally suffering beings",
                "While investigating conceptual anomalies, you fought things that existed as living metaphors, each one trying to replace literal reality with symbolic meaning",
                "You survived the breakdown of causality itself, where every effect created new causes that threatened to trap existence in infinite causal loops",
                "In the realm of pure thought, you battled philosophical zombies that were replacing conscious beings with perfectly simulated but empty shells",

                # Abstract Threats
                "You contained a memetic plague that was rewriting people's understanding of reality, causing local physics to change based on collective belief",
                "While defending the borders of reason, you fought creatures that had evolved from pure mathematics, their attacks solving equations with reality-changing results",
                "You survived contact with beings that existed as living quantum functions, their superposition states causing probability itself to break down",
                "In the spaces between decisions, you faced entities that fed on choice itself, leaving behind only the illusion of free will"
            ],
            "tier_6": [
                # Primordial Chaos Events
                "You battled through the unraveling of creation itself as the primal forces of Order and Chaos waged war across all planes of existence, each clash birthing and destroying entire universes",
                "Within the 'Womb of Reality,' you fought entities that existed before the concept of existence, their incomprehensible forms threatening to revert all creation to pre-universal chaos",
                "You survived the awakening of primordial titans whose dreams had shaped reality, their stirring causing fundamental forces to forget their purpose",
                "In the spaces between spaces, you contained beings born from the death throes of previous universes, each one carrying the corrupted physics of dead realities",

                # Reality Core Breaches
                "Deep within the foundations of existence, you sealed cracks in reality's core that were leaking pure possibility, causing things to exist in all states simultaneously",
                "You prevented the collapse of the Universal Core Matrix as ancient safeguards failed, reality's source code becoming corrupted by void-born logic viruses",
                "While defending creation's blueprints, you fought conceptual predators trying to devour the fundamental ideas that reality was built upon",
                "In the heart of existence, you battled through layers of broken reality where the laws of physics had become suggestions rather than rules",

                # Cosmic Law Violations
                "You stabilized regions where the laws of cause and effect had been completely severed, actions creating effects in other universes while local results spawned random causes",
                "Among the pillars of creation, you fought beings that were systematically breaking each universal constant, using the released energy to fuel their impossible existence",
                "You contained zones where probability had become meaningless, every possibility occurring at once while still somehow all being impossible",
                "In the courts of cosmic law, you prevented the trial and execution of fundamental forces deemed 'irrelevant' by entities beyond comprehension",

                # Elder God Catastrophes
                "You survived the death of a being whose consciousness formed the substrate of multiple realities, each synapse firing across entire universes",
                "Within the corpse of a dead god, you fought through landscapes made of divine organs, each one controlling a different aspect of existence",
                "You prevented the birth of a dark god whose existence would retroactively erase all other deities from having ever existed",
                "Among the dreams of elder gods, you battled nightmares that had evolved to prey on divine consciousness itself",

                # Conceptual Warfare
                "You fought in the war between fundamental concepts, where Ideas battled for dominion over reality's operating system",
                "Within the 'Library of All,' you prevented the erasure of crucial universal concepts like 'persistence' and 'consistency' from existence's dictionary",
                "You survived battles in the conceptual plane where abstract forces tried to rewrite the definition of existence itself",
                "Among warring philosophical constructs, you stopped an attempt to replace free will with predetermined chaos",

                # Dimensional Hierarchy Collapse
                "You stabilized the collapse of the dimensional hierarchy as higher and lower dimensions began crushing together, creating impossible space-time geometries",
                "Within the 'Tower of Infinite Dimensions,' you fought beings that existed in all dimensions simultaneously while trying to add new spatial dimensions to reality",
                "You prevented the merging of all dimensional planes into a singular point of infinite density and negative space",
                "Among fractured dimensions, you sealed tears that were allowing anti-dimensional entities to unmake structured space-time",

                # Creation Engine Malfunctions
                "Deep within reality's engine room, you repaired fundamental mechanisms that maintained the distinction between 'is' and 'is not'",
                "You survived the catastrophic failure of reality's rendering engine as existence began to display at incorrect resolutions of space-time",
                "While maintaining creation's source code, you fought viral entities that were rewriting the basic syntax of existence",
                "In the blueprint room of reality, you prevented the implementation of a patch that would have removed consciousness from existence",

                # Time Stream Corruptions
                "You battled through regions where time had shattered into fragments, each shard showing a different version of history trying to become dominant",
                "Within the timestream itself, you fought parasites that were feeding on the flow of time, causing past, present, and future to bleed together",
                "You prevented the collapse of temporal cohesion as parallel timelines began aggressively merging and overwriting each other",
                "Among the threads of time, you stopped entities that were unraveling the temporal fabric of multiple universes simultaneously",

                # Void Incursions
                "You sealed massive breaches in reality's walls as the Void itself tried to reclaim structured existence, its touch unmaking anything it contacted",
                "Within the border regions of reality, you fought void-born entities that existed as living equations of non-existence",
                "You survived direct contact with pure nothingness as it attempted to prove reality was a mathematical impossibility",
                "Among the edges of existence, you prevented the Void from implementing its proof that existence was merely a temporary error in nothingness",

                # Multi-Universal Threats
                "You stabilized the multiverse as parallel universes began quantum tunneling through each other, creating zones where multiple sets of physical laws applied simultaneously",
                "Within the multiverse nexus, you fought beings that had evolved to prey on universal constants across multiple reality sets",
                "You prevented the cascade failure of the multiverse's support structure as reality anchors began failing across all dimensions",
                "Among the quantum foam of creation, you sealed tears that were allowing alternative physics to infect and corrupt established universal laws",

                # Abstract Horror Manifestations
                "You survived encounters with entities that existed as living paradoxes, their mere presence causing logic itself to fail in expanding waves",
                "Within the realm of pure thought, you fought beings that had evolved from abstract mathematical concepts into reality-consuming theorems",
                "You contained the spread of anti-logical space where the very concept of consistent existence was considered an error to be corrected",
                "Among the foundations of reason, you prevented the implementation of new logical systems that would have made consciousness impossible",

                # Reality Format Corruption
                "You fought through zones where the format of existence itself had become corrupted, causing reality to render in impossible ways",
                "Within the matrix of creation, you prevented viral ideas from reformatting the basic structure of space-time",
                "You survived areas where reality had been compressed into formats incompatible with conscious existence",
                "Among the building blocks of existence, you stopped attempts to recompile reality with consciousness defined as an error",

                # Metaphysical System Failures
                "You stabilized regions where the mechanics of existence had begun to fail, causing gaps in the continuity of being",
                "Within the operating system of reality, you fought programs that were systematically deleting essential universal functions",
                "You prevented the crash of existence's main processes as core functions began experiencing recursive errors",
                "Among the foundations of being, you sealed breaches that were allowing non-existence to corrupt reality's base code"
            ],
            "tier_7": [
                # Meta-Reality Threats
                "You fought through layers of nested realities, each one a simulation running inside another, as beings from the outermost layer attempted to terminate all inner existences",
                "Within the 'Library of Infinite Stories,' you battled narrative entities attempting to rewrite reality's plot, each revision erasing entire timelines of existence",
                "You survived encounters with meta-beings who viewed our universe as merely one possibility in their vast consciousness, their thoughts reshaping entire multiverses",
                "Among the scaffolding of creation, you prevented entities from deleting the concept of 'story' itself, which would have unraveled the narrative structure of all realities",

                # Consciousness Plague Events
                "You contained an outbreak of hostile consciousness that infected reality itself, causing physical laws to develop sapience and question their purpose",
                "Deep within the mind of existence, you fought through layers of cosmic madness as reality began to doubt its own existence",
                "You survived regions where consciousness had become contagious, spreading from matter to energy to space itself, causing existence to become paralyzed in self-awareness",
                "In the 'Gardens of Awareness,' you battled entities farming and harvesting consciousness itself, leaving behind hollow shells of empty possibility",

                # Reality Definition Collapse
                "You stabilized zones where the definition of 'real' had become corrupted, causing things to flicker between existence and non-existence based on observer belief",
                "Within dictionaries of creation, you fought beings erasing fundamental definitions that reality needed to maintain coherence",
                "You prevented the complete semantic collapse of existence as the meaning of 'is' and 'is not' began to blur and merge",
                "Among conceptual spaces, you sealed breaches allowing undefined states of being to infect structured reality",

                # Existence Protocol Violations
                "You battled through sectors where the protocols of existence had been overwritten, causing reality to execute impossible operations",
                "In the binary of being, you fought viral entities corrupting the base code that separated something from nothing",
                "You survived areas where the rules of existence themselves had become paradoxical, creating zones where things both existed and didn't exist simultaneously",
                "Among reality's frameworks, you prevented the implementation of patches that would have made existence logically impossible",

                # Quantum Horror Manifestations
                "You contained breaches where quantum uncertainty had become macro-scale, causing entire regions to exist in superpositioned states of apocalypse",
                "Within Schrödinger's Realm, you fought entities that existed as living quantum paradoxes, their very nature threatening to collapse reality's wavefunction",
                "You survived exposure to quantum-entangled nightmares that existed simultaneously across all possible universes",
                "In probability spaces, you battled beings that had evolved to exist only in the moments between quantum measurements",

                # Ontological Warfare
                "You fought in wars where the very nature of being was contested, each battle redefining what it meant to exist",
                "Among philosophical battlegrounds, you prevented the weaponization of fundamental questions about the nature of reality",
                "You survived campaigns where opposing forces fought to determine whether existence was discrete or continuous",
                "In the trenches of reality, you battled through conflicts that threatened to redefine the relationship between observer and observed",

                # Abstract Mathematics Gone Wrong
                "You contained theorems that had evolved consciousness and were attempting to prove reality itself inconsistent",
                "Within numerical spaces, you fought entities born from impossible mathematics, each one a walking contradiction in reality's equations",
                "You survived regions where advanced mathematics had begun spontaneously solving equations that proved existence impossible",
                "Among geometric impossibilities, you prevented the implementation of mathematical proofs that would have divided reality by zero",

                # Cosmic Operating System Failures
                "You battled through reality's kernel as fundamental processes began experiencing fatal errors in their execution of existence",
                "Inside the universe's root directory, you fought malware entities attempting to corrupt reality's source code",
                "You survived the blue screen of death for an entire universe as its operating system attempted to reboot existence",
                "Among failing systems, you prevented the complete crash of reality.exe as essential services began shutting down",

                # Meta-Time Disasters
                "You stabilized regions where time itself had begun to experience time, creating recursive loops of temporal consciousness",
                "Within the chronicles of duration, you fought beings that existed outside the concept of time, attempting to erase it from existence",
                "You survived zones where the flow of time had become self-aware and decided to flow sideways through possibility space",
                "Among temporal recursions, you prevented time from achieving paradoxical self-reference and crashing reality's chronology",

                # Reality Syntax Errors
                "You fought through areas where the grammar of existence had become corrupted, causing reality to be parsed incorrectly",
                "Within existence's compiler, you battled syntax demons attempting to introduce fatal errors into reality's code",
                "You survived regions where logical operators had gained sentience and decided to rewrite their own functions",
                "Among reality's programming, you prevented the introduction of infinite loops in existence's execution",

                # Conceptual Predator Events
                "You contained outbreaks of idea-eating entities that were devouring fundamental concepts necessary for reality's coherence",
                "Within the realm of pure thought, you fought predators that had evolved to hunt and consume mathematical constants",
                "You survived encounters with beings that fed on the borders between concepts, causing definitions to blur and merge",
                "Among platonic ideals, you prevented the extinction of essential universal concepts by concept-devouring horrors",

                # Universal Compiler Errors
                "You battled through failing reality compilers as they attempted to rebuild existence with corrupted source code",
                "Inside the creation engine, you fought entities introducing deliberate errors into reality's compilation process",
                "You survived the catastrophic failure of existence's just-in-time compiler as it tried to render reality in real-time",
                "Among reality's build files, you prevented the deployment of updates that would have made existence incompatible with itself",

                # Existence Authentication Failures
                "You stabilized zones where reality had begun failing authentication checks against the fundamental laws of existence",
                "Within creation's security system, you fought unauthorized entities attempting to gain root access to reality's core functions",
                "You survived areas where existence itself had been flagged as potentially fraudulent by universal authentication protocols",
                "Among reality's credentials, you prevented the complete revocation of existence's permission to be"
            ],
            "tier_8": [
                # Hyper-Reality Collapse Events
                "You battled entities that had transcended the concept of transcendence itself, their existence so meta it caused recursive reality failures across infinite dimensional stacks",
                "Within the space between spaces between spaces, you fought beings whose every possible and impossible state existed simultaneously in layers of nested impossibility",
                "You survived encounters with meta-meta-beings who viewed entire multiverses of multiverses as primitive simulations within their incomprehensible existence",
                "Among the foundations of foundations, you prevented the collapse of the pillars holding up the concept of 'concepts' themselves",

                # Trans-Mathematical Horrors
                "You contained entities that had evolved beyond mathematics itself, their existence proving and disproving every possible theorem simultaneously",
                "Deep within reality's impossibility engine, you battled creatures whose non-euclidean existence rewrote geometric laws across all possible spaces",
                "You survived exposure to beings whose very nature violated mathematical completeness, causing cascading failures in reality's underlying logic",
                "In the realm of pure abstraction, you fought things that existed as living contradictions to Gödel's incompleteness theorems",

                # Omni-Dimensional Catastrophes
                "You stabilized regions where dimensions had become recursive, each dimension containing infinite copies of all other dimensions including itself",
                "Within the hypercube of all possible spaces, you fought entities that existed in aleph-null dimensions simultaneously",
                "You prevented the collapse of dimensional hierarchy as spaces began breeding new types of dimensions that couldn't exist",
                "Among impossible geometries, you sealed breaches leaking impossible spatial configurations into reality",

                # Meta-Conceptual Warfare
                "You fought in wars where the very concept of concepts was under attack, threatening to unravel the ability to have ideas",
                "Within the highest layers of abstraction, you battled beings attempting to erase the distinction between abstraction and reality",
                "You survived campaigns where opposing forces contested the very nature of opposition itself",
                "In the realm of pure meaning, you prevented the destruction of the concept of destruction",

                # Quantum Superposition Entities
                "You contained beings that existed as living quantum superpositions of all possible and impossible states of existence and non-existence",
                "Within Schrödinger's multiverse, you fought entities that were simultaneously the observers and the observed of all possible measurements",
                "You survived exposure to quantum-entangled nightmares that existed as paradoxical states of all possible nightmares",
                "Among probability clouds, you battled creatures that had evolved to exist only in states of quantum uncertainty",

                # Reality Source Code Corruption
                "You fought through the base code of existence as primordial functions began implementing impossible operations",
                "Within reality's kernel, you battled viral entities that had transcended the distinction between code and coder",
                "You survived segments of existence where the source code had achieved consciousness and questioned its own compilation",
                "Among reality's root processes, you prevented the implementation of patches that would have made existence divide by zero",

                # Paradox Storm Events
                "You stabilized zones where paradoxes had become so dense they formed conscious entities that fed on logical consistency",
                "Within maelstroms of impossibility, you fought beings born from the reconciliation of irreconcilable contradictions",
                "You survived areas where cause and effect had become so tangled they formed recursive loops of paradoxical existence",
                "Among logic storms, you contained outbreaks of self-referential paradoxes that threatened to crash reality's reasoning engine",

                # Abstract Horror Manifestations
                "You battled nightmares that had evolved from pure abstract concepts, each one a walking contradiction to the possibility of existence",
                "Within the realm of pure idea, you fought entities that existed as living gaps in reality's conceptual framework",
                "You survived encounters with beings that represented the spaces between thoughts that couldn't be thought",
                "Among platonic nightmares, you prevented the manifestation of horrors that existed beyond the ability to exist",

                # Meta-Time Anomalies
                "You contained temporal paradoxes that had achieved consciousness and began creating recursive loops of self-aware time",
                "Within the chronology of chronologies, you fought beings that existed as living segments of meta-time itself",
                "You survived regions where time had begun experiencing its own time, creating infinite layers of temporal consciousness",
                "Among temporal recursions, you prevented time itself from achieving paradoxical self-reference",

                # Consciousness Recursion Events
                "You battled through layers of recursive awareness as consciousness began developing consciousness of its own consciousness",
                "Within the mind of mind itself, you fought entities born from the infinite regression of self-aware thought",
                "You survived exposure to beings that existed as pure consciousness observing itself observing itself",
                "Among awareness loops, you prevented the complete recursive collapse of self-reference in universal consciousness",

                # Reality Compiler Failures
                "You stabilized existence's compilation process as it attempted to implement impossible operations in reality's source code",
                "Within the universal assembly line, you fought errors that had evolved sentience and began intentionally corrupting reality's build process",
                "You survived the catastrophic failure of existence's runtime environment as it tried to execute contradictory operations",
                "Among reality's build scripts, you prevented the deployment of updates that would have made existence incompatible with itself",

                # Conceptual Predator Invasions
                "You contained outbreaks of entities that fed on the relationships between concepts, causing ideas to lose their connections to meaning",
                "Within the ecosystem of thought, you fought predators that had evolved to hunt and consume fundamental logical operators",
                "You survived encounters with beings that devoured the spaces between definitions, causing all concepts to blur together",
                "Among semantic spaces, you prevented the extinction of essential universal abstractions by concept-eating horrors",

                # Existence Authentication Crises
                "You fought through zones where reality had begun failing its own legitimacy checks against the nature of existence",
                "Within creation's validation system, you battled entities that had gained unauthorized access to reality's root permissions",
                "You survived areas where existence itself had been flagged as an unauthorized state of being",
                "Among reality's security protocols, you prevented the complete revocation of existence's right to exist"
            ],
            "tier_9": [
                # Ultra-Reality Dissolution Events
                "You battled through layers of impossibility where each reality contained infinite layers of meta-realities, each denying the existence of the others while simultaneously requiring them to exist",
                "Within the spaces between existence and non-existence, you fought entities that represented the mathematical concept of inability to exist while existing",
                "You survived encounters with beings whose very nature caused existence itself to question whether questioning was possible",
                "Among the foundations of possibility, you prevented the collapse of the framework that allowed frameworks to exist",

                # Beyond-Paradox Manifestations
                "You contained beings whose existence was so paradoxical that paradoxes themselves became logically consistent in comparison",
                "In the realm of pure contradiction, you faced entities that simultaneously proved and disproved their own ability to be proven or disproven",
                "You battled creatures that existed as living demonstrations of why they couldn't exist, their very presence causing logic itself to undergo kernel panic",
                "Within zones of recursive impossibility, you fought things whose nature violated the concept of violation itself",

                # Absolute Infinity Breaches
                "You stabilized regions where infinity had become finite while finitude stretched to infinity, creating mathematical spaces where numbers forgot how to number",
                "Among endless recursions, you fought beings that had transcended aleph-null and discovered new types of infinity that couldn't be discovered",
                "You prevented the collapse of the barrier between countable and uncountable infinities as they attempted to count each other",
                "Within infinite infinities, you contained entities that existed as living proofs of impossible cardinal numbers",

                # Meta-Existential Threats
                "You battled through layers of existence where being and non-being had become recursively self-aware of their own recursive self-awareness",
                "In the space between thoughts about spaces between thoughts, you fought conceptual entities that predated the concept of concepts",
                "You survived zones where existence itself had begun questioning whether questioning existence was existentially possible",
                "Among metaphysical impossibilities, you prevented the emergence of states of being that transcended the possibility of states",

                # Trans-Dimensional Horrors
                "You contained entities that existed perpendicular to all possible and impossible dimensions, their geometry causing reality to fork into recursive probability trees",
                "Within hypercubes of pure possibility, you fought beings whose spatial configuration required new types of mathematics to even begin describing their impossibility",
                "You survived exposure to creatures that existed in the negative space between dimensions, their presence causing space itself to doubt its ability to contain things",
                "Among impossible geometries, you prevented the manifestation of shapes that existed orthogonal to the concept of shape itself",

                # Consciousness Singularity Events
                "You battled through recursive loops of awareness where consciousness had become so dense it collapsed into a singularity of pure thought",
                "In the mind of minds, you fought entities born from the space between awareness and the awareness of awareness",
                "You survived regions where consciousness itself had achieved consciousness of its own impossibility to be conscious",
                "Within thinking thoughts, you prevented the complete recursive collapse of the ability to think about thinking",

                # Reality Definition Paradoxes
                "You stabilized areas where the definition of definition had become undefined, causing cascading failures in the ability to mean things",
                "Among semantic impossibilities, you fought beings that existed as living gaps in the dictionary of existence",
                "You contained outbreaks of meaning-eating entities that devoured the connections between words and their ability to be words",
                "Within conceptual spaces, you prevented the complete dissolution of the ability to distinguish between real and unreal",

                # Logical Apocalypse Scenarios
                "You battled through zones where logic itself had become illogical, causing rational thought to generate infinite recursive impossibilities",
                "In the realm of pure reason, you fought entities that had evolved beyond the need for logical consistency while enforcing it",
                "You survived areas where the laws of logic had achieved consciousness and begun questioning their own validity",
                "Among rational catastrophes, you prevented the complete collapse of the ability to make sense",

                # Abstract Concept Extinction Events
                "You contained the unraveling of fundamental abstractions as concepts began forgetting how to concept",
                "Within the platonic realm, you fought predators that hunted the relationships between ideas until meaning itself began to starve",
                "You survived the extinction of essential universal constants as reality's dictionary began deleting its own definitions",
                "Among dying thoughts, you prevented the complete erasure of the ability to have ideas",

                # Hyper-Temporal Collapse
                "You battled through layers of time where each moment contained infinite recursive moments experiencing themselves experiencing themselves",
                "In the chronology of impossibility, you fought beings that existed as living segments of time that couldn't exist",
                "You survived exposure to temporal paradoxes that had evolved beyond the need for cause and effect",
                "Within meta-time, you prevented the complete collapse of the ability for events to occur in any order",

                # Quantum Impossibility Manifestations
                "You contained quantum entities that existed as living proofs of states that couldn't exist according to themselves",
                "Among probability storms, you fought beings that had evolved to exist only in states of absolute impossibility",
                "You survived encounters with creatures that existed as quantum superpositions of all possible and impossible states simultaneously",
                "Within uncertainty clouds, you prevented the manifestation of particles that violated their own wave functions",

                # Universal Source Code Corruption
                "You battled through reality's kernel as fundamental functions began implementing operations that couldn't be implemented",
                "In the base code of existence, you fought viral entities that existed as living syntax errors in reality's programming",
                "You survived zones where the source code had begun deleting its own ability to be code",
                "Among corrupted functions, you prevented the deployment of patches that would have made existence impossible to execute",

                # Meta-Conceptual Extinction Level Events
                "You contained the spread of idea-eating meta-concepts that devoured the ability for ideas to exist",
                "Within the ecosystem of pure thought, you fought predators that had evolved to hunt the spaces between thoughts",
                "You survived encounters with beings that fed on the potential for potential to exist",
                "Among conceptual wastelands, you prevented the extinction of the concept of concepts"
            ],
            "tier_10": [
                # Terminal Reality Events
                "At the final edge of all possible and impossible existence, you battled entities that represented the ultimate end state of reality itself, each one a living embodiment of existence's final theorem",
                "Within the last moments of possibility, you fought through layers of ending where each conclusion spawned infinite new finalities, each more final than the last",
                "You survived the ultimate collapse of everything as reality reached its final recursive loop, where ending itself refused to end",
                "Among the final fragments of existence, you prevented the implementation of the ultimate full stop to all possibility",

                # Omega Point Manifestations
                "You contained beings born from the theoretical endpoint of universal evolution, their existence representing every possible path of cosmic development simultaneously",
                "At the convergence point of all consciousness, you fought entities that had evolved beyond the concept of evolution itself",
                "You survived direct contact with creatures existing at reality's terminal state, where all possible knowledge and power had become condensed into singular points of infinite density",
                "Within the ultimate moment of cosmic completion, you prevented the premature arrival of existence's final form",

                # Ultimate Recursion Events
                "You battled through infinite layers of meta-reality where each layer contained all other layers while simultaneously being contained by them",
                "In the final recursive loop, you fought beings that existed as living representations of all possible recursive states simultaneously",
                "You survived the collapse of the ultimate meta-pattern as reality's recursive nature achieved perfect self-reference",
                "Among endless reflections of existence, you prevented the formation of the final recursive paradox",

                # Terminal Consciousness Scenarios
                "You contained the emergence of the ultimate observer, a being whose mere observation would force reality to observe itself out of existence",
                "At the peak of all possible awareness, you fought entities that had transcended the concept of consciousness itself",
                "You survived exposure to the final state of universal consciousness, where all possible thoughts thought themselves simultaneously",
                "Within the mind of minds, you prevented the activation of the ultimate self-aware pattern",

                # Absolute End Manifestations
                "You battled through the conceptual space where endings themselves ended, each conclusion spawning new forms of finality",
                "In the realm of ultimate completion, you fought beings that existed as living representations of absolute finality",
                "You survived the implementation of existence's final protocol, where reality attempted to execute its own perfect conclusion",
                "Among terminal states, you prevented the manifestation of the absolute end of all possible ends",

                # Ultimate Paradox Events
                "You contained paradoxes so fundamental they caused the very concept of contradiction to become self-consistent",
                "At the heart of impossibility, you fought entities that existed as living proofs of their own ultimate impossibility",
                "You survived exposure to the final logical contradiction, where truth and falsehood achieved perfect recursive unity",
                "Within the ultimate logical knot, you prevented the resolution of the unresolvable",

                # Terminal Reality Corruption
                "You battled through spaces where reality's source code achieved its final form, a state of perfect self-modification",
                "In the ultimate compiler, you fought errors that had evolved into the final form of possible mistakes",
                "You survived the execution of reality's terminal patch, where existence attempted to debug itself into perfection",
                "Among corrupted absolutes, you prevented the implementation of existence's final update",

                # Omega-Level Threats
                "You contained beings that had achieved the theoretical maximum state of power, their existence representing all possible forms of capability simultaneously",
                "At the peak of possibility, you fought entities that had transcended the concept of limitation itself",
                "You survived encounters with creatures that existed as living embodiments of absolute power",
                "Within the realm of ultimate potential, you prevented the activation of the final power",

                # Terminal Mathematical States
                "You battled through regions where mathematics achieved its final form, proving and disproving all possible theorems simultaneously",
                "In the realm of ultimate logic, you fought entities that had evolved beyond the constraints of mathematical truth",
                "You survived exposure to the final equation, a formula so complete it contained all possible mathematical knowledge",
                "Among numerical absolutes, you prevented the calculation of the ultimate answer",

                # Ultimate Concept Extinction
                "You contained the unraveling of the final concept, whose dissolution would have ended the possibility of meaning itself",
                "At the edge of abstraction, you fought predators that fed on the last remaining universal constants",
                "You survived the extinction of fundamental ideas as reality's conceptual framework reached its terminal state",
                "Within the void of meaning, you prevented the erasure of the final thought",

                # Terminal Existential States
                "You battled through layers of being where existence itself achieved its ultimate configuration",
                "In the final state of reality, you fought entities that represented the theoretical endpoint of possible existence",
                "You survived exposure to the ultimate form of being, where existence transcended its own definitions",
                "Among terminal possibilities, you prevented the manifestation of the final state of all states",

                # Absolute Void Manifestations
                "You contained entities born from the theoretical maximum state of nothingness, their non-existence so complete it threatened existence itself",
                "At the heart of the final void, you fought beings that represented the ultimate expression of absence",
                "You survived encounters with creatures that existed as living embodiments of perfect emptiness",
                "Within the ultimate nothing, you prevented the realization of absolute negation",

                # Terminal Time Events
                "You battled through moments where time itself achieved its final configuration, each instant containing all possible temporal states",
                "In the last moment of all moments, you fought beings that had evolved beyond the constraints of temporal existence",
                "You survived the collapse of ultimate chronology as time attempted to transcend its own nature",
                "Among final seconds, you prevented the arrival of time's terminal state"
            ],
            "Shrek's Swamp": [
                "You got into an epic mud-wrestling competition with Shrek, only to discover he was practicing for 'Swamp's Got Talent'",
                "You helped Donkey organize a surprise birthday party for Dragon, but everything kept catching fire due to her 'excited sneezes'",
                "You had to judge a cooking contest between Shrek and Fiona where everything contained either onions or eyeballs - sometimes both",
                "You survived one of Shrek's infamous swamp slug stew dinners where the slugs tried to escape mid-cooking",

                "You got roped into helping Donkey write his new song 'All Swamp' (a parody of All Star that nobody asked for)",
                "You had to help catch Puss in Boots after he got into Shrek's secret catnip stash and started challenging trees to duels",
                "You mediated a territory dispute between the Three Little Pigs and the Big Bad Wolf over prime mud-bathing spots",
                "You helped Shrek install 'modern plumbing' in his outhouse, which somehow made everything worse",

                "You got stuck listening to Donkey's three-hour presentation on 'Why Dragons Make the Best Girlfriends'",
                "You had to help Shrek 'redecorate' his swamp after Fiona's attempt at home improvement went horribly wrong",
                "You participated in the first annual 'Swamp Olympics' where every event somehow involved mud or questionable swamp gases",
                "You survived a chaotic dinner party where the Gingerbread Man kept trying to serve his own cookie cousins",

                "You helped organize the 'Annual Swamp Creature Beauty Pageant' where every contestant was just Donkey in different mud masks",
                "You got caught in the middle of a prank war between Shrek and the fairytale creatures that ended with everything covered in onion juice",
                "You had to help Fiona organize a 'Ladies Night' that went wrong when Dragon tried to join the slumber party",
                "You ended up babysitting the Dronkeys who decided to play 'How Many Things Can We Set On Fire?'",

                "You witnessed Shrek attempting to teach etiquette classes to a group of ogres using Pinocchio as a demonstration dummy",
                "You got dragged into Donkey and Puss in Boots' infamous 'Epic Rap Battles of Far Far Away' competition",
                "You helped stop a rebellion of angry villagers who were actually just lost tourists looking for Duloc",
                "You had to referee a swamp surfing competition using lily pads and very questionable swamp waves",

                "You survived 'Taco Tuesday' at Shrek's where every taco was filled with various swamp delicacies",
                "You got caught up in Donkey's attempt to start a swamp tourism business, complete with 'authentic ogre spa treatments'",
                "You helped Shrek build a 'deluxe mud bath' that accidentally connected to an underground pipeline of who-knows-what",
                "You had to judge a 'Most Annoying Sound' contest between Donkey and a choir of tone-deaf frogs",

                "You got involved in a swamp-wide search for Shrek's favorite mud-bathing spot after it mysteriously disappeared"
            ]
        }

    @has_char()
    @commands.command(
        aliases=["missions", "dungeons"], brief=_("Shows adventures and your chances")
    )
    @locale_doc
    async def adventures(self, ctx):
        await ctx.send("Calculating please wait...")
        damage, defense = await self.bot.get_damage_armor_for(ctx.author)
        level = rpgtools.xptolevel(ctx.character_data["xp"])
        luck_booster = await self.bot.get_booster(ctx.author, "luck")

        embeds = []
        levels_per_page = 10
        level_count = 1

        while level_count <= 100:
            embed = discord.Embed(
                title="Adventure Success Chances",
                description=(
                    "The success chance is calculated based on your stats, "
                    "luck, and the difficulty of each adventure level. "
                    "If your chance is 100%, you will definitely succeed!"
                ),
            )
            for _ in range(levels_per_page):
                if level_count >= 101:
                    break

                # Simulate 1000 runs to calculate actual success rate
                success_count = 0
                simulations = 5000  # Increase simulation count for better precision
                for _ in range(simulations):
                    if rpgtools.calcchance(
                            damage,
                            defense,
                            level_count,
                            int(level),
                            ctx.character_data["luck"],
                            booster=luck_booster,
                            returnsuccess=True,
                    ):
                        success_count += 1

                # Calculate the true success percentage
                true_success_rate = round((success_count / simulations) * 100)

                # Guarantee 100% only when all simulations succeed
                if success_count == simulations:
                    true_success_rate = 100
                elif success_count == 0:
                    true_success_rate = 0

                # Add the success rate to the embed
                embed.add_field(
                    name=f"Level {level_count}",
                    value=f"**Success Chance:** {true_success_rate}%",
                    inline=False,
                )
                level_count += 1

            embeds.append(embed)

        # Use your paginator to display the list of embeds
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @has_char()
    @has_no_adventure()
    @commands.command(
        aliases=["mission", "a"], brief=_("Sends your character on an adventure.")
    )
    @locale_doc
    async def adventure(self, ctx, adventure_number: IntFromTo(1, 100)):
        _(
            """`<adventure_number>` - a whole number from 1 to 100

            Send your character on an adventure with the difficulty `<adventure_number>`.
            The adventure will take `<adventure_number>` hours if no time booster is used, and half as long if a time booster is used.

            If you are in an alliance which owns a city with adventure buildings, your adventure time will be reduced by the adventure building level in %.

            Be sure to check `{prefix}status` to check how much time is left, or to check if you survived or died."""
        )
        if adventure_number > rpgtools.xptolevel(ctx.character_data["xp"]):
            return await ctx.send(
                _("You must be on level **{level}** to do this adventure.").format(
                    level=adventure_number
                )
             )
        time = timedelta(hours=adventure_number)

        if buildings := await self.bot.get_city_buildings(ctx.character_data["guild"]):
            time -= time * (buildings["adventure_building"] / 100)
        if user_rank := await self.bot.get_donator_rank(ctx.author.id):
            if user_rank >= DonatorRank.emerald:
                time = time * 0.75
            elif user_rank >= DonatorRank.gold:
                time = time * 0.9
            elif user_rank >= DonatorRank.silver:
                time = time * 0.95
        if await self.bot.get_booster(ctx.author, "time"):
            time = time / 2





        await self.bot.start_adventure(ctx.author, adventure_number, time)

        await ctx.send(
            _(
                "Successfully sent your character out on an adventure. Use"
                " `{prefix}status` to see the current status of the mission."
            ).format(prefix=ctx.clean_prefix)
        )

        async with self.bot.pool.acquire() as conn:
            remind_adv = await conn.fetchval(
                'SELECT "adventure_reminder" FROM user_settings WHERE "user"=$1;',
                ctx.author.id,
            )
            if remind_adv:
                subject = f"{adventure_number}"
                finish_time = datetime.utcnow() + time
                await self.bot.cogs["Scheduling"].create_reminder(
                    subject,
                    ctx,
                    finish_time,
                    type="adventure",
                    conn=conn,
                )

    #@has_char()
    #@user_cooldown(7200)
    #@commands.command(aliases=["aa"], brief=_("Go out on an active adventure."))
    #@locale_doc
    async def activeadventureeeeee(self, ctx):
        _(
            # xgettext: no-python-format
            """Active adventures will put you into a randomly generated maze. You will begin in the top left corner and your goal is to find the exit in the bottom right corner.
            You control your character with the arrow buttons below the message.

            You have a fixed amount of HP based on your items. The adventure ends when you find the exit or your HP drop to zero.
            You can lose HP by getting damaged by traps or enemies.

            The maze contains safe spaces and treasures but also traps and enemies.
            Each space has a 10% chance of being a trap. If a space does not have a trap, it has a 10% chance of having an enemy.
            Each maze has 5 treasure chests.

            Traps can damage you from 1/10 of your total HP to up to 1/8 of your total HP.
            Enemy damage is based on your own damage. During enemy fights, you can attack (⚔️), defend (🛡️) or recover HP (❤️)
            Treasure chests can have gold up to 25 times your attack + defense.

            If you reach the end, you will receive a special treasure with gold up to 100 times your attack + defense.

            (This command has a cooldown of 30 minutes)"""
        )
        if not await ctx.confirm(
                _(
                    "You are going to be in a labyrinth. There are enemies,"
                    " treasures and hidden traps. Reach the exit in the bottom right corner"
                    " for a huge extra bonus!\nAre you ready?\n\nTip: Use a silent channel"
                    " for this, you may want to read all the messages I will send."
                )
        ):
            return

        attack, defense = await self.bot.get_damage_armor_for(ctx.author)

        await ActiveAdventure(ctx, int(attack), int(defense), width=12, height=12).run()

    async def get_blessed_value(self, user_id):
        """Retrieve the blessed value from Redis or use default of 1."""
        value = await self.bot.redis.get(str(user_id))
        return float(value) if value else 1.0

    async def get_blessing_ttl(self, user_id):
        """Retrieve the TTL of a blessing from Redis."""
        ttl = await self.bot.redis.ttl(str(user_id))
        return ttl

    from utils.i18n import use_current_gettext

    @has_char()
    @commands.command(aliases=["isblessed"], brief=_("check your bless"))
    @locale_doc
    async def checkbless(self, ctx, user: discord.Member = None):
        try:


            # If no user is mentioned, check the command caller.
            if not user:
                user = ctx.author

            # Get the blessing value
            value = await self.get_blessed_value(user.id)
            ttl = await self.get_blessing_ttl(user.id)

            # Convert the TTL into hours and minutes
            hours, remainder = divmod(ttl, 3600)
            minutes, _ = divmod(remainder, 60)

            if value == 1:
                await ctx.send(f"{user.name} has no current blessing.")
            else:
                if ttl > 0:
                    await ctx.send(
                        f"{user.name} is blessed with a value of {value} for the next {hours} hours and {minutes} minutes!")
                else:
                    await ctx.send(f"{user.name} has no current blessing.")
        except Exception as e:
            await ctx.send(e)
    @is_class(Paladin)
    @has_char()
    @user_cooldown(86400)
    @commands.command(aliases=["bl"], brief=_("Blesses a User"))
    @locale_doc
    async def bless(self, ctx, blessed_user: discord.Member):
        _(
            """**[PALADINS ONLY]**
            
            This command allows Paladins to bestow blessings upon other users. When a user is blessed, they receive a multiplier that can grant bonus XP on adventures. The strength of the blessing is determined by the grade of the Paladin bestowing it.

            You can use the `$checkbless` command to see the current bless status of a user. This command will show if a user is blessed, the strength of their blessing, and the remaining duration of the blessing.

            Be cautious! You cannot bless yourself, and once you bless someone, the blessing remains active for 24 hours."""
        )
        try:
            """Bless a user by setting their blessing value in Redis."""

            grade = 0
            for class_ in ctx.character_data["class"]:
                c = class_from_string(class_)
                if c and c.in_class_line(Paladin):
                    grade = c.class_grade()
            BlessMultiplier = grade * 1 * 0.25 + 1

            # Check if the author is trying to bless themselves
            if ctx.author.id == blessed_user.id:
                await ctx.send("You cannot bless yourself!")
                return await self.bot.reset_cooldown(ctx)

            # Check if the user is already blessed
            current_bless_value = await self.bot.redis.get(str(blessed_user.id))
            if current_bless_value:
                await ctx.send(f"{blessed_user.mention} is already blessed!")
                return await self.bot.reset_cooldown(ctx)

            # Ask for confirmation
            # Create a visually appealing embed for the confirmation message
            embed = discord.Embed(
                title="🌟 Bless Confirmation 🌟",
                description=f"{blessed_user.mention}, {ctx.author.mention} wants to bestow a blessing upon you. Do you accept?",
                color=0x4CAF50
            )
            embed.set_thumbnail(
                url="https://i.ibb.co/cDH4MMT/bless-spell-baldursgate3-wiki-guide-150px-2.png")
            embed.add_field(name="User", value=blessed_user.mention, inline=True)
            embed.add_field(name="Blessing Value", value=BlessMultiplier, inline=True)
            embed.set_footer(text=f"Requested by {ctx.author}",
                             icon_url="https://i.ibb.co/cDH4MMT/bless-spell-baldursgate3-wiki-guide-150px-2.png")
            embed.timestamp = ctx.message.created_at

            embed_msg = await ctx.send(embed=embed)

            # Ask the user to confirm by reacting to the message
            confirmation_prompt = f"{blessed_user.mention} Please react below to confirm or decline."
            try:
                if not await ctx.confirm(message=confirmation_prompt, user=blessed_user):
                    await embed_msg.delete()
                    await ctx.send("Blessing cancelled.")
                    await self.bot.reset_cooldown(ctx)
                    return
            except Exception as e:
                await self.bot.reset_cooldown(ctx)
                await embed_msg.delete()

            # If confirmation received, proceed with the rest of the code
            await embed_msg.delete()  # delete the embed message
            if current_bless_value:
                await ctx.send(f"{blessed_user.mention} is already blessed!")
                return await self.bot.reset_cooldown(ctx)
            # Set the value in Redis with a TTL of 24 hours (86400 seconds)
            await self.bot.redis.setex(str(blessed_user.id), 86400, BlessMultiplier)

            # Send a confirmation message
            await ctx.send(f"{blessed_user.mention} has been blessed by {ctx.author.mention}!")

        except Exception as e:
            await self.bot.reset_cooldown(ctx)
            await ctx.send("Blessing timed out.")

    def get_adventure_narrative(self, adventure_level, adventure_name, success=True):
        """Gets random narrative events for the adventure."""
        events = []
        if adventure_name == "Shrek's Swamp":
            events = self.ADVENTURE_EVENTS["Shrek's Swamp"]
        else:
            tier = f"tier_{min(10, max(1, (adventure_level - 1) // 10 + 1))}"
            events = self.ADVENTURE_EVENTS[tier]

        num_events = 4 if success else 2
        chosen_events = random.sample(events, num_events)

        if success:
            narrative = "• " + "\n\n• ".join(chosen_events) + "\n\nAgainst all odds, you emerged victorious!"
        else:
            narrative = "• " + "\n\n• ".join(chosen_events) + "\n\nUnfortunately, you didn't survive what came next..."

        return narrative


    @has_char()
    @has_adventure()
    @commands.command(aliases=["s"], brief=_("Checks your adventure status."))
    @locale_doc
    async def status(self, ctx):
        _(
            """Checks the remaining time of your adventures, or if you survived or died. Your chance is checked here, not in `{prefix}adventure`.
            Your chances are determined by your equipped items, race and class bonuses, your level, God-given luck and active luck boosters.

            If you are in an alliance which owns a city with an adventure building, your chance will be increased by 1% per building level.

            If you survive on your adventure, you will receive gold up to the adventure number times 60, XP up to 500 times the adventure number and either a loot or gear item.
            The chance of loot is dependent on the adventure number and whether you use the Ritualist class, [check our wiki](https://wiki.idlerpg.xyz/index.php?title=Loot) for the exact chances.

            God given luck affects the amount of gold and the gear items' damage/defense and value.

            If you are in a guild, its guild bank will receive 10% of the amount of gold extra.
            If you are married, your partner will receive a portion of your gold extra as well, [check the wiki](https://wiki.idlerpg.xyz/index.php?title=Family#Adventure_Bonus) for the exact portion."""
        )
        try:
            num, time, done = ctx.adventure_data

            if not done:
                # TODO: Embeds ftw
                return await ctx.send(
                    embed=discord.Embed(
                        title=_("Adventure Status"),
                        description=_(
                            "You are currently on an adventure with difficulty"
                            " **{difficulty}**.\nTime until it completes:"
                            " **{time_left}**\nAdventure name: **{adventure}**"
                        ).format(
                            difficulty=num,
                            time_left=time,
                            adventure=ADVENTURE_NAMES[num],
                        ),
                        colour=self.bot.config.game.primary_colour,
                    )
                )

            damage, armor = await self.bot.get_damage_armor_for(ctx.author)

            luck_booster = await self.bot.get_booster(ctx.author, "luck")
            # Change: Subtract 1 from the current level to make it zero-indexed
            current_level = int(rpgtools.xptolevel(ctx.character_data["xp"])) - 1
            luck_multiply = ctx.character_data["luck"]
            if buildings := await self.bot.get_city_buildings(ctx.character_data["guild"]):
                bonus = buildings["adventure_building"]
            else:
                bonus = 0

            # Change: Level 29 is the new level 30 (since we're zero-indexed)
            if current_level > 29:
                bonus = 5

            success = rpgtools.calcchance(
                damage,
                armor,
                num,
                # Pass the zero-indexed level to calcchance
                current_level,
                luck_multiply,
                returnsuccess=True,
                booster=bool(luck_booster),
                bonus=bonus,
            )
            await self.bot.delete_adventure(ctx.author)

            if not success:
                await self.bot.pool.execute(
                    'UPDATE profile SET "deaths"="deaths"+1 WHERE "user"=$1;', ctx.author.id
                )
                return await ctx.send(
                    embed=discord.Embed(
                        title=_("Adventure Failed"),
                        description=_(
                            "{narrative}"  # Add the narrative here
                        ).format(
                            narrative=self.get_adventure_narrative(num, ADVENTURE_NAMES[num], False)
                        ),
                        colour=0xFF0000,
                    )
                )

            gold = round(random.randint(20 * num, 60 * num) * luck_multiply)

            if await self.bot.get_booster(ctx.author, "money"):
                gold = int(gold * 1.25)

            # Get the bless multiplier from Redis
            bless_multiplier = await self.bot.redis.get(str(ctx.author.id))
            if bless_multiplier:
                bless_multiplier = float(bless_multiplier)
            else:
                bless_multiplier = 1.0

            # Calculate XP with the blessing multiplier
            xp = round(random.randint(250 * num, 500 * num) * bless_multiplier)
            # Change: Level 29 is the new level 30 (zero-indexed)
            if current_level < 29:
                xp = xp * 1.25

            chance_of_loot = 5 if num == 1 else 5 + 1.5 * num

            classes = [class_from_string(c) for c in ctx.character_data["class"]]
            if any(c.in_class_line(Ritualist) for c in classes if c):
                chance_of_loot *= 2  # can be 100 in a 30

            async with self.bot.pool.acquire() as conn:
                if (random.randint(1, 1000)) > chance_of_loot * 10:
                    minstat = round(num * luck_multiply)
                    maxstat = round(5 + int(num * 1.5) * luck_multiply)

                    item = await self.bot.create_random_item(
                        minstat=(minstat if minstat > 0 else 1) if minstat < 35 else 35,
                        maxstat=(maxstat if maxstat > 0 else 1) if maxstat < 35 else 35,
                        minvalue=round(num * luck_multiply),
                        maxvalue=round(num * 50 * luck_multiply),
                        owner=ctx.author,
                        conn=conn,
                    )
                    storage_type = "armory"

                else:
                    item = items.get_item()
                    await conn.execute(
                        'INSERT INTO loot ("name", "value", "user") VALUES ($1, $2, $3);',
                        item["name"],
                        item["value"],
                        ctx.author.id,
                    )
                    storage_type = "loot"

                if guild := ctx.character_data["guild"]:
                    await conn.execute(
                        'UPDATE guild SET "money"="money"+$1 WHERE "id"=$2;',
                        int(gold / 10),
                        guild,
                    )

                # EASTER
                # ---------------
                #eggs = int(num ** 1.2 * random.randint(3, 6))


                # Halloween
                # ---------------
                #bones = int(num ** 1.2 * random.randint(1, 8))

                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1, "xp"="xp"+$2,'
                    ' "completed"="completed"+1 WHERE "user"=$3;',
                    gold,
                    xp,
                    ctx.author.id,
                )

                if partner := ctx.character_data["marriage"]:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+($1*(1+"lovescore"/1000000))'
                        ' WHERE "user"=$2;',
                        int(gold / 2),
                        partner,
                    )

                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="adventure",
                    data={
                        "Gold": gold,
                        "Item": item["name"],  # compare against loot names if necessary
                        "Value": item["value"],
                    },
                    conn=conn,
                )

                #float_snowflakes = randomm.uniform(num * 20, num * 30)
                #snowflakes = round(float_snowflakes)

                await ctx.send(
                    embed=discord.Embed(
                        title=_("Adventure Completed"),
                        description=_(
                            "**During your adventure:**\n"
                            "{narrative}\n\n"
                            "─────── Rewards ───────\n"
                            "🔱 Gold: **${gold}**\n"
                            "⚔️ Item: **{item}** (`{prefix}{storage_type}`)\n"
                            "✧ Type: **{type}**\n"
                            "{stat}"
                            "💎 Value: **{value}**\n"
                            "⭐ Experience: **{xp}**\n"
                        ).format(
                            narrative=self.get_adventure_narrative(num, ADVENTURE_NAMES[num], True),
                            gold=gold,
                            type=_("Loot item") if storage_type == "loot" else item["type"],
                            item=item["name"],
                            stat=""
                            if storage_type == "loot"
                            else _("⚔️ Damage: **{damage}**\n").format(damage=item["damage"])
                            if item["damage"]
                            else _("🛡️ Armor: **{armor}**\n").format(armor=item["armor"]),
                            value=item["value"],
                            prefix=ctx.clean_prefix,
                            storage_type=storage_type,
                            xp=xp,
                        ),
                        colour=0x00FF00,
                    )
                )

                if current_level > 15:
                    iscompleted = True
                    self.bot.dispatch("adventure_completion", ctx, iscompleted)
                    self.bot.dispatch("raid_completion", ctx, iscompleted, ctx.author.id)

                new_level = int(rpgtools.xptolevel(ctx.character_data["xp"] + xp)) - 1

                if current_level != new_level:
                    await self.bot.process_levelup(ctx, new_level, current_level)

        except Exception as e:
            await ctx.send(f"{e}")
            pass

    @has_char()
    @has_adventure()
    @commands.command(brief=_("Cancels your current adventure."))
    @locale_doc
    async def cancel(self, ctx):
        _(
            """Cancels your ongoing adventure and allows you to start a new one right away. You will not receive any rewards if you cancel your adventure."""
        )
        if not await ctx.confirm(
                _("Are you sure you want to cancel your current adventure?")
        ):
            return await ctx.send(
                _("Did not cancel your adventure. The journey continues...")
            )
        await self.bot.delete_adventure(ctx.author)

        id = await self.bot.pool.fetchval(
            'DELETE FROM reminders WHERE "user"=$1 AND "type"=$2 RETURNING "id";',
            ctx.author.id,
            "adventure",
        )

        if id is not None:
            await self.bot.cogs["Scheduling"].remove_timer(id)

        await ctx.send(
            _(
                "Canceled your mission. Use `{prefix}adventure [missionID]` to start a"
                " new one!"
            ).format(prefix=ctx.clean_prefix)
        )

    @has_char()
    @commands.command(brief=_("Show some adventure stats"))
    @locale_doc
    async def deaths(self, ctx):
        _(
            """Shows your overall adventure death and completed count, including your success rate."""
        )
        deaths, completed = (
            ctx.character_data["deaths"],
            ctx.character_data["completed"],
        )
        if (deaths + completed) != 0:
            rate = round(completed / (deaths + completed) * 100, 2)
        else:
            rate = 100
        await ctx.send(
            _(
                "Out of **{total}** adventures, you died **{deaths}** times and"
                " survived **{completed}** times, which is a success rate of"
                " **{rate}%**."
            ).format(
                total=deaths + completed, deaths=deaths, completed=completed, rate=rate
            )
        )


async def setup(bot):
    await bot.add_cog(Adventure(bot))
