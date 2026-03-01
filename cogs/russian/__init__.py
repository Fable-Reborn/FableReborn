"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

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
from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from discord.ui import Button, View

from classes.converters import IntFromTo
from utils import misc as rpgtools
from utils.checks import has_char
from utils.i18n import _, locale_doc

SETTINGS_FILE = Path(__file__).parent / "rr_settings.json"
SETTINGS_TABLE = "russian_roulette_settings"

DEFAULT_GIFS = {
    "round_start": "https://media.tenor.com/fklGVnlUSFQAAAAd/russian-roulette.gif",
    "shoot_self": "https://i.ibb.co/kKn0zQs/ezgif-4-51fcaad25e.gif",
    "shoot_other": "https://media.tenor.com/ggBL-mf1-swAAAAC/guns-anime.gif",
    "winner": "",
}

GIF_SLOT_LABELS = {
    "round_start": "Round start",
    "shoot_self": "Shoot self",
    "shoot_other": "Shoot other",
    "winner": "Winner",
}

GIF_SLOT_ALIASES = {
    "round": "round_start",
    "round_start": "round_start",
    "roundstart": "round_start",
    "start": "round_start",
    "shoot_self": "shoot_self",
    "shootself": "shoot_self",
    "self": "shoot_self",
    "self_shot": "shoot_self",
    "selfshot": "shoot_self",
    "shoot_other": "shoot_other",
    "shootother": "shoot_other",
    "other": "shoot_other",
    "other_shot": "shoot_other",
    "othershot": "shoot_other",
    "winner": "winner",
    "win": "winner",
    "victory": "winner",
}

DARK_BASE_TAUNTS = [
    "The house never blinks.",
    "Fate just put a thumb on the scale.",
    "The cylinder is patient. Are you?",
    "The room smells like iron and bad choices.",
    "Every click is a confession.",
    "The reaper runs on a tight schedule.",
    "Hope checks out early around here.",
    "Someone is about to learn a life lesson. Fast.",
    "You can hear the silence grinning.",
    "This is where courage goes to get audited.",
    "There is no safe. Only later.",
    "The gun does not care about your plans.",
    "Luck is a landlord. Rent is due.",
    "The air tastes like consequences.",
    "The table keeps score in bloodless ink.",
]

DARK_PRE_TURN_TAUNTS = [
    "Someone's about to meet their ex's new partner... and Satan.",
    "This is the most excitement some of you will have before the obituary.",
    "At least one person here is about to have their last thought be 'fuck'.",
    "Remember: closed casket funerals are cheaper.",
    "Life insurance companies hate this one simple trick.",
    "Your mom's gonna be so disappointed... again.",
    "Aim for the head, it's not like you're using it.",
    "Hope your browser history auto-deletes.",
    "Fun fact: the average funeral costs $7,000. Good thing you won't have to worry about it.",
    "At least when you're gone, your family can finally use your Netflix account.",
    "Somebody's about to find out if there's WiFi in hell.",
    "Your last meal was gas station sushi, wasn't it?",
    "Don't worry, nobody's gonna cry at your funeral anyway.",
    "Remember to aim away from your good side... oh wait.",
    "This is gonna hurt you more than it'll hurt your disappointed parents.",
    "At least you'll finally be interesting at parties... posthumously.",
    "Somebody's about to become a statistic and a warning label.",
    "Your life flashing before your eyes is gonna be a really short movie.",
    "Think of it as aggressive retirement planning.",
    "At least your student debt dies with you. Silver linings!",
    "Imagine dying in a Discord game. Couldn't be you... right?",
    "Your autopsy is gonna be more interesting than your biography.",
    "Don't worry, your Minecraft dog will understand... eventually.",
    "Somebody's gonna make their therapist rich after this.",
    "This is natural selection with extra steps.",
    "At least you're already sitting down for the bad news.",
    "Your last words better be good, they're going on a shitty meme.",
    "Six feet under is still better than your current KDA.",
    "Dying is just ragequitting life.",
    "Some of you are about to become hashtags.",
    "Remember: you can't respawn IRL.",
    "This is why your mom wanted you to be a doctor.",
    "Somebody's about to get unsubscribed from life.",
    "Your gravestone's gonna say 'Died doing something stupid on Discord'.",
    "Hope you made a will. JK, you're broke anyway.",
    "This is the most action you've gotten all year.",
    "Imagine explaining this to St. Peter at the gates.",
    "Your FBI agent is about to get a new assignment.",
    "At least you won't have to file taxes next year.",
    "Congrats on speedrunning life, any%.",
]

NOIR_PRE_TURN_TAUNTS = [
    "In this city, everybody's got a gun. Only question is who's got the guts.",
    "The chamber spins like a roulette wheel in a back-alley casino. Lady Luck's taking bets.",
    "Rain's falling outside. Someone's falling inside. Tale as old as time.",
    "They say every bullet has a name on it. Let's see whose name's up.",
    "The smoke clears, but the smoke in your future? That's permanent.",
    "In the end, we're all just playing Russian roulette with time. This is just faster.",
    "The gun doesn't care about your story. It only writes endings.",
    "Somewhere, a piano plays. Somewhere else, a trigger pulls. Circle of life, baby.",
    "The city's full of dead men walking. You're just about to stop walking.",
    "Dame Fate's a cruel mistress, and she's about to make someone her bitch.",
    "They always think they'll beat the odds. They never do.",
    "The last thing that goes through your mind... besides the bullet.",
    "In the shadows, Death waits. In your hand, Death weighs about two pounds.",
    "Every man's got a last cigarette. Some of you just don't know you're smoking it.",
    "The night is dark and full of terrible decisions. Exhibit A: This game.",
    "Somewhere, a widow's being made. She just doesn't know it yet.",
    "The gun's not loaded with bullets. It's loaded with consequences.",
    "They say the house always wins. Tonight, the house is Death.",
    "Cold steel. Warm blood. The math always works out.",
    "In the grim arithmetic of the streets, someone's about to be subtracted.",
]

WESTERN_PRE_TURN_TAUNTS = [
    "This town ain't big enough for all of y'all.",
    "High noon somewhere. And somebody's about to meet their maker.",
    "Draw, partner. And pray you draw breath after.",
    "In the Old West, they settled disputes with duels. This is just faster.",
    "Somebody's about to buy the farm, and it ain't got good resale value.",
    "Every cowboy thinks they're the fastest gun. Most of 'em are just the deadest.",
    "The good, the bad, and the about-to-be-dead.",
    "Tumbleweed's rolling. Vultures are circling. They know something you don't.",
    "Out here, we don't call 911. We call the coroner.",
    "Somebody's gonna be pushing up daisies by sundown.",
    "The only thing faster than your draw is gonna be your funeral.",
    "In the wild west, fortune favors the bold. And the undertaker favors all of you.",
    "Saddle up, cowboys. Some of you ain't riding back.",
    "This here's a game of chance, and chance is a cold-hearted bitch.",
    "They say every man dies. Not every man really lives. Y'all are speedrunning both.",
    "The saloon's quiet. Too quiet. Someone's about to break that silence. Permanently.",
    "Six chambers, one bullet. Better odds than most gunfights, worse than most Tuesdays.",
    "Welcome to the deadliest game west of the Mississippi.",
    "Somebody's name's about to go on a wooden cross on boot hill.",
    "The frontier's got no mercy, and neither does this revolver.",
    "Draw your last breath, partner. It might be more useful than your last card.",
    "Your mama wanted you to be a doctor. Now you're gonna need one.",
    "The only thing you're gonna be riding after this is a pine box.",
    "This ain't your first rodeo, but it might be your last.",
    "You can lead a horse to water, but you can't stop a dumbass from pulling that trigger.",
]

WASTELAND_PRE_TURN_TAUNTS = [
    "In the wasteland, only the strong survive. You're about to prove which one you are.",
    "Radiation didn't kill you. Mutants didn't kill you. But stupidity might.",
    "Another day in the apocalypse, another idiot with a gun.",
    "The bombs dropped years ago. You're just cleaning up the leftovers.",
    "In the old world, you had choices. In this one, you've got a bullet.",
    "The Geiger counter's clicking, and so is this trigger.",
    "They said the apocalypse would bring out the best in humanity. They lied.",
    "Vault-Tec didn't prepare you for this, did they?",
    "The wasteland doesn't care about your feelings. Or your pulse.",
    "Another soul for the irradiated earth to claim.",
    "Pre-war, this would've been murder. Now it's just Thursday.",
    "The fallout took civilization. This gun's about to take you.",
    "In the ashes of the old world, new stupidity rises.",
    "War never changes. But your vital signs are about to.",
    "The wasteland giveth, and the wasteland fucking taketh away.",
    "Bottle caps won't save you now, wastelander.",
    "They say cockroaches survive everything. Let's test that theory on you.",
    "The nuclear winter's cold, but this barrel's colder.",
    "Surface world's already dead. You're just joining it.",
    "Another day above ground is a good day. Emphasis on 'another.'",
]

MAFIA_PRE_TURN_TAUNTS = [
    "The family sends its regards. And a bullet.",
    "This is just business. Nothing personal. Actually, it's very personal.",
    "Concrete shoes are so last century. We prefer lead poisoning now.",
    "You're about to sleep with the fishes. The dead fishes.",
    "In our thing, you don't retire. You get retired.",
    "The Don didn't ask for volunteers. He asked for victims.",
    "Snitches get stitches. Idiots get bullets.",
    "You're playing a game you can't win. The house always wins. We ARE the house.",
    "Tonight, someone's making their bones. Tomorrow, someone's fertilizing them.",
    "The commission has voted. Someone's getting whacked.",
    "You mess with the family, you get the family treatment.",
    "This ain't the movies, kid. There's no director yelling 'cut' when you die.",
    "An offer you can't refuse. Because you'll be dead.",
    "The only thing getting clipped tonight is someone's life.",
    "We run this city. And we're about to run you into the ground.",
    "Loyalty's everything in this family. And someone's about to prove it... or disprove it.",
    "Last chance to say your prayers. Make 'em quick.",
    "The boss don't like loose ends. And you're looking pretty loose.",
    "Time to pay the piper. And the piper accepts payment in blood.",
    "You wanted to be made? Congratulations, you're about to be made... into a corpse.",
]

MEDIEVAL_PRE_TURN_TAUNTS = [
    "By sword or sorcery, death comes for all. Tonight it comes by trigger.",
    "The Gods flip a coin when a man is born. Yours just came up tails.",
    "Hear ye, hear ye! Someone's about to be declared dead.",
    "In the realm, peasants die daily. You're just speeding up the process.",
    "The executioner sharpens his blade. This is just more efficient.",
    "Pray to your gods. They won't answer, but it passes the time.",
    "The Dark Lord watches. He's taking bets on who dies first.",
    "Thy end is nigh, and it's packing .38 caliber judgment.",
    "The wheel of fate turns. Someone's about to get crushed beneath it.",
    "In the name of the King, someone's about to meet him. In the afterlife.",
    "The dragons took the old world. This gun's about to take you.",
    "Kneel before your executioner. Or don't. You'll be horizontal soon anyway.",
    "The court jester laughs. Because someone's about to become the joke.",
    "Magic can't save you. Neither can prayer. But good luck trying both.",
    "The dungeon's full, so we're just killing you instead. More efficient.",
    "Ye olde fuck around, meet ye olde find out.",
    "The prophecy foretold someone dies here. Spoiler: it's you.",
    "The kingdom needs fewer mouths to feed. Thanks for volunteering.",
    "Steel and sorcery couldn't kill you. But stupidity might.",
    "The bards will sing of this moment. It's a tragedy, obviously.",
    "The plague couldn't take you, but this bullet will.",
    "Tis but a flesh wound! ...is what you WON'T be saying.",
    "For honor! For glory! For extremely poor decision-making!",
    "The castle walls have seen many deaths. This one's just more stupid than most.",
]

ARCADE_PRE_TURN_TAUNTS = [
    "Insert coin to continue. No continues available.",
    "Achievement unlocked: Terrible Decision Making.",
    "Game Over in 3... 2... 1...",
    "Your K/D ratio is about to become very literal.",
    "RNG says: git gud or get dead.",
    "Speedrunning death%. World record pace.",
    "Save point not found. Respawn disabled.",
    "Press F to pay respects... in advance.",
    "Lag won't save you from this one.",
    "Final boss: a revolver with 1 INT.",
    "The cabinet hums. The cylinder sings.",
    "Extra life not found.",
    "Achievement unlocked: nerves of steel.",
    "High score is temporary. Consequences are not.",
    "The RNG is watching.",
    "Combo breaker? Maybe.",
    "Respawn unavailable.",
    "You can hear the credits tick down.",
    "This is not a tutorial.",
    "A boss fight with a six-shot RNG.",
    "Luck buff expired.",
    "One token, infinite regret.",
    "The game reads: you are not ready.",
    "Press X to accept your fate.",
    "Critical hit incoming. No dodge roll available.",
    "Your health bar is about to deplete. Permanently.",
    "New high score: Fastest Death.",
    "Loading... Death Screen.",
    "Player 1 is about to become Player 0.",
    "Checkpoint corrupted. No save data found.",
    "The final level is just a bullet.",
    "XP gain: 0. Death gain: 100%.",
    "Rage quit denied. You're stuck here.",
    "The developer didn't program a happy ending for you.",
    "DLC: Death's Loving Caress. Already installed.",
    "Beta testing mortality. Results: fatal.",
    "This level is unbeatable. Like, literally.",
    "Glitch detected: your survival.",
    "Multiplayer lobby: You vs Death. He's undefeated.",
    "Your build is trash. Your fate is worse.",
]

GREEK_PRE_TURN_TAUNTS = [
    "The Fates weave your thread. Clotho spins, Lachesis measures, Atropos cuts.",
    "Hades opens his ledger. Someone's name is being written in blood.",
    "The gods watch from Olympus. Zeus is placing bets. You're the underdog.",
    "Charon sharpens his oar. The ferry to the Underworld awaits passage.",
    "Even Achilles had a weakness. Yours is stupidity.",
    "The Oracle of Delphi sees your future. It's short and stupid.",
    "Icarus flew too close to the sun. You're flying too close to a bullet.",
    "The River Styx demands payment. Bring a coin... and a coffin.",
    "Medusa turns men to stone. This gun just turns them off.",
    "The gods are cruel. The cylinder is crueler.",
    "Nemesis, goddess of retribution, has your number. It's up.",
    "Thanatos, god of death, yawns. He's seen this before.",
    "The Hydra had nine heads. You'll have significantly fewer.",
    "Prometheus gave fire to mankind. This is just giving bullets.",
    "Pandora's box released all evils. This chamber releases one.",
    "The Minotaur's labyrinth had an exit. This game doesn't.",
    "Sisyphus pushes his boulder. You're about to push your luck.",
    "Tantalus reaches for fruit he'll never grasp. You reach for survival.",
    "The Furies circle overhead. They smell blood already.",
    "Persephone returns from the Underworld each spring. You won't.",
    "The Golden Fleece brought glory to Jason. This brings death to you.",
    "Odysseus wandered for ten years. Your journey ends in ten seconds.",
    "Athena, goddess of wisdom, is not with you tonight.",
    "Ares, god of war, grins. This is his kind of game.",
    "Dionysus pours wine for the fallen. He's already pouring yours.",
    "The Titans were imprisoned in Tartarus. You'll join them.",
    "Hermes guides souls to the Underworld. He's getting impatient.",
    "Cerberus, the three-headed hound, guards the gates. He's hungry.",
    "The Elysian Fields await heroes. You're not going there.",
    "Kronos devoured his children. This gun devours your chances.",
    "The Trojan Horse was a deception. This trigger is honest.",
    "Narcissus fell in love with his reflection. You'll just fall.",
    "Echo can only repeat. Your mistakes will echo forever.",
    "The Amazons were fierce warriors. You're just fierce idiots.",
    "Pegasus soars through the heavens. You're crashing to earth.",
    "The Golden Apple started a war. This chamber ends one.",
    "Actaeon saw Artemis bathing and became a stag. You'll just become dead.",
    "The Augean stables needed cleaning. So does your gene pool.",
    "Orpheus looked back and lost Eurydice. You look forward and lose everything.",
    "The gods threw dice for mortal fates. Someone just rolled snake eyes.",
]

NORSE_PRE_TURN_TAUNTS = [
    "Odin the All-Father watches from Hlidskjalf. He's not impressed.",
    "The Valkyries circle above. They're not here for you.",
    "Ragnarok comes for all. Yours is just ahead of schedule.",
    "Thor's hammer Mjolnir falls. So will you.",
    "Die with honor in battle, or die like a fool. Choose wisely.",
    "The Norns weave your fate. Urd, Verdandi, and Skuld laugh.",
    "Valhalla has standards. You don't meet them.",
    "Your saga ends here. It was a shit saga anyway.",
    "The frost giants of Jotunheim had better odds than you.",
    "Skal! To death and glory! Mostly death, probably yours.",
    "Fenrir the wolf breaks his chains. Your luck breaks easier.",
    "Yggdrasil, the World Tree, has seen countless deaths. Yours is unremarkable.",
    "The Einherjar feast in Odin's hall. You're not invited.",
    "Loki, the trickster god, would find this hilarious.",
    "Hel, goddess of the underworld, prepares your chamber. The cold one.",
    "The berserkers fought without fear. You should probably find some.",
    "Freya weeps golden tears for fallen warriors. She's saving them for someone worthy.",
    "Tyr sacrificed his hand to bind Fenrir. You're sacrificing your life for stupidity.",
    "The Bifrost bridge connects realms. Yours connects life to death.",
    "Heimdall's horn Gjallarhorn sounds. Someone's time is up.",
    "Sleipnir, Odin's eight-legged horse, gallops. Death rides faster.",
    "The runes foretell your doom. Even the blank ones.",
    "Jormungandr, the World Serpent, encircles Midgard. You're encircled by bad choices.",
    "The mead of poetry flows in Asgard. The blood of idiots flows here.",
    "Frigg knows all fates but speaks none. She's staying quiet about yours. Bad sign.",
    "Baldur the Beautiful died from mistletoe. You'll die from stupidity.",
    "The Wild Hunt rides tonight. They're hunting you.",
    "Skadi, goddess of winter, brings the cold. This barrel brings colder.",
    "Njord controls the seas. This chamber controls your fate.",
    "The dwarves forged Mjolnir and Gungnir. This is just a gun. Still deadly.",
    "Vidar will avenge Odin at Ragnarok. No one will avenge you.",
    "The fire giant Surtr will burn the world. You'll burn out first.",
    "Huginn and Muninn, Odin's ravens, watch. They're already planning to feast.",
    "The hall of Folkvangr receives half the slain. You're going to the other place.",
    "Thor slew countless giants. This gun will slay countless braincells. Yours.",
    "The volva prophesies the end of days. Yours end now.",
    "Warriors earn their place in Valhalla through glory. You earn yours through dumbassery.",
    "The ash tree Yggdrasil supports nine realms. It won't support your decision-making.",
    "Blood eagle was a Viking execution. This is just execution.",
    "Your ancestors conquered lands and seas. You're about to be conquered by a trigger.",
]

FARMER_PRE_TURN_TAUNTS = [
    "Harvest season's here. Somebody's getting reaped.",
    "The rooster crows at dawn. Someone won't hear tomorrow's.",
    "Time to separate the wheat from the chaff. You're definitely chaff.",
    "The sickle swings. The scythe follows. Death is very agricultural.",
    "Planted in spring, harvested in fall, dead by nightfall.",
    "The crop rotation this year: corn, beans, and corpses.",
    "Out in the pasture, the cows watch. They've seen smarter behavior.",
    "The barn's seen a lot of animals. You're the dumbest one yet.",
    "Farmer's Almanac predicts: chance of death, 16.67% per pull.",
    "The tractor runs. The chickens cluck. Someone's about to kick the bucket.",
    "You reap what you sow. You sowed stupidity. Guess what's coming.",
    "The scarecrow's got more brains than whoever pulls next.",
    "Fertilizer makes things grow. Your grave will be well-fertilized.",
    "The haystack's hiding a needle. The chamber's hiding a bullet.",
    "Milk the cows, feed the pigs, bury the idiot. Daily chores.",
    "The well runs deep. Your intelligence doesn't.",
    "Sunrise, sunset, someone's last breath.",
    "The fields are plowed, the seeds are sown, someone's getting mowed down.",
    "The henhouse is guarded. Your life isn't.",
    "Country roads take you home. This trigger takes you elsewhere.",
    "The grain silo's full. The cemetery's got room.",
    "Plow the field, plant the corn, plant the corpse. Circle of life.",
    "The combine harvester is efficient. So is this bullet.",
    "Fresh eggs, fresh milk, fresh grave. Farm to table.",
    "The livestock's getting fed. The worms will too.",
    "The fence needs mending. Your family needs mourning clothes.",
    "Rain's good for crops. Blood's good for nothing.",
    "The seasons change. Your vital signs won't.",
    "Bless this mess of a game. And bless whoever dies.",
    "The land provides. The land receives. You're about to be received.",
    "Sunset on the farm. Sunset on your life. Very poetic.",
    "The pitchfork's sharp, the scythe is sharper, the bullet is sharpest.",
    "Mother Nature's cruel. This chamber's crueler.",
    "From dust you came, to dust you'll return. Speedrun edition.",
    "The old farm dog's smarter than you. He knows when to quit.",
    "Them chickens got more sense than to play this game.",
    "The barn owl hoots. It's a bad omen. Unlike this game which is a TERRIBLE omen.",
    "Till the soil, reap the harvest, bury the fool. Honest work.",
    "The windmill turns. The wheel of fate turns. Somebody stops turning.",
    "Country living: fresh air, hard work, and sudden death.",
]

SARCASTIC_FARMER_PRE_TURN_TAUNTS = [
    "Well, ain't this just the highlight of the county fair.",
    "Y'all sure know how to make a Tuesday interesting. Stupidly interesting.",
    "The cows have seen smarter decisions. And they eat their own vomit.",
    "Nothing says 'good judgment' like Russian roulette on a Tuesday.",
    "Yep, this is exactly what grandpappy died for. Freedom to be a dumbass.",
    "The crops are watching. They're embarrassed for you.",
    "Well butter my butt and call me a biscuit, someone's about to die.",
    "The scarecrow's got more survival instincts. And it's made of straw.",
    "Oh good, we're doing THIS again. The chickens are taking bets.",
    "This is fine. Everything's fine. Except for whoever dies next.",
    "The harvest moon shines down on this magnificent display of stupidity.",
    "Grandma's rolling in her grave so hard she could power the whole farm.",
    "The pigs are snorting. They think you're all idiots. They're right.",
    "Well, this is one way to thin the herd. Not a GOOD way, but a way.",
    "The rooster's seen some things. This might break him.",
    "Oh sure, THIS is what we're doing with our Saturday night. Great.",
    "The barn owl hoots in disappointment. Even nocturnal birds judge you.",
    "Y'all make the livestock look like Rhodes scholars.",
    "This is gonna look GREAT in the obituary. 'Died doing something real dumb.'",
    "The well's deep, but your collective IQ is deeper. Underground, even.",
    "Farmer's Almanac didn't predict THIS level of stupid.",
    "The tractor's seen a lot of accidents. This one's voluntary, though.",
    "Nothing like a good ol' fashioned game of 'who dies first.' Real wholesome.",
    "The corn's higher than your chances of survival. And your intelligence.",
    "Yep, this beats watching paint dry. Barely.",
    "The manure pile smells better than this decision-making.",
    "Well, at least the buzzards will eat good tonight. Silver linings.",
    "The fence posts have more common sense. They're just wood.",
    "This is why city folk think we're all inbred.",
    "The mule kicked a guy once. Felt bad about it. Won't feel bad about this.",
    "Oh look, it's natural selection with extra steps and a country accent.",
    "The hay baler's seen stupider things. Actually, no it hasn't.",
    "Y'all are making me reconsider this whole 'farming' career choice.",
    "The livestock's worried about YOU. Let that sink in.",
    "Well slap my ass and call me confused, here we go again.",
    "This is what happens when cousins marry. Just saying.",
    "The weather vane's spinning. It's trying to point away from this nonsense.",
    "Grandpappy survived the dust bowl. Y'all can't survive common sense.",
    "The chickens are clucking. It's not encouragement, it's mockery.",
    "This beats doing actual work, I guess. Not by much, though.",
    "Oh boy, here we go. The sheep are literally shaking their heads.",
    "Y'all got less sense than a bag of hammers. And the hammers are offended.",
    "The field mice are taking notes. For their 'what NOT to do' seminar.",
    "This is beautiful. A real Norman Rockwell painting. If he painted idiots.",
    "The combine harvester's less dangerous than y'all. And it has BLADES.",
    "Somewhere, a participation trophy is crying.",
    "The goats are judging you. THE GOATS. They eat tin cans.",
    "This is what peak performance looks like. Peak stupid performance.",
    "Oh, don't mind me. Just watching Darwin's theory in real-time.",
    "The henhouse has better survival strategies. And they're CHICKENS.",
    "Well, this'll be a fun story for the grandkids. If anyone survives to have any.",
    "The corn stalks are whispering. They're saying 'yikes.'",
    "Nothing screams 'good life choices' like this right here.",
    "The outhouse has seen some shit. Literally. This is worse.",
    "Bless your hearts. And I mean that in the MOST Southern way possible.",
    "The tractor manual has better plot than this trainwreck.",
    "This is why aliens don't visit. They saw THIS and noped out.",
    "The milk's gonna curdle from the sheer stupidity in this barn.",
    "Y'all need Jesus. And a helmet. Mostly a helmet.",
    "The pitchfork's got more point to it than this decision.",
    "Well, if brains were dynamite, y'all couldn't blow your nose.",
    "The harvest festival didn't prepare me for THIS kind of reaping.",
    "This is like watching a slow-motion car crash. Except the cars are idiots.",
    "The weather's nice today. Shame someone's gonna miss tomorrow's.",
    "Grandma's quilt took less risk than this game.",
    "The silo's full of grain. Y'all are full of bad ideas.",
    "This is the most excitement this farm's seen since the pig got loose.",
    "Even the tumbleweeds are embarrassed. And they're DEAD PLANTS.",
    "Well, this is certainly... something. Something stupid.",
    "The duck pond has more depth than this plan.",
    "Y'all make a root vegetable look like a MENSA candidate.",
    "This is what happens when you ignore the safety briefing.",
    "The farmer's market sold fresher ideas than this.",
    "Oh good, we're testing the theory of 'how dumb can you get?' Results: very.",
    "The rooster crows at dawn. Someone won't hear tomorrow's. Spoiler alert.",
    "This beats watching grass grow. Not by much. But it's faster.",
    "Well, someone's mama raised a quitter. And a future statistic.",
    "The windmill's seen wind blow. This is hot air. Deadly hot air.",
    "Y'all playing with fire. Except it's bullets. So worse.",
    "The county fair rejected this for 'too dangerous.' Let that sink in.",
    "This is less 'Old MacDonald' and more 'Old MacDonald Had a Funeral.'",
    "The plow turns dirt. Y'all turn stomachs.",
    "Well, this is one way to avoid doing the dishes.",
    "The barn cat's got nine lives. Y'all are speedrunning through your one.",
    "This is what 'hold my beer' looks like in text form.",
    "The feed bag's got better content than this decision-making process.",
    "Y'all are what happens when the gene pool needs chlorine.",
    "This is peak rural entertainment. And by 'peak' I mean 'please stop.'",
    "The horse trailer's safer than this. And it's got WHEELS.",
    "Well, at least you're consistent. Consistently bad at staying alive.",
    "This is gonna age like milk. Left out in the sun. For weeks.",
    # HUNDREDS MORE ADDITIONS:
    "The barn door's got better sense. It stays on its hinges.",
    "Y'all are proof that sometimes the stork makes delivery errors.",
    "This is what happens when you skip the 'common sense' aisle at the store.",
    "The pig trough's got higher standards than this.",
    "Well, this is educational. Teaching us all what NOT to do.",
    "The compost heap's more organized than this strategy.",
    "Y'all are like a tornado. Destructive and full of hot air.",
    "This is gonna win awards. Darwin Awards.",
    "The chicken wire's got better decision-making skills.",
    "Well, someone's mama's disappointed. Probably multiple mamas.",
    "This is what 'hold my moonshine' leads to.",
    "The rain barrel's got more depth than y'all's thought process.",
    "Y'all make the scarecrow look like Einstein.",
    "This is less 'farm life' and more 'farm death.'",
    "The butter churn's seen better uses of energy.",
    "Well, at least the worms will be happy. Someone's gotta be.",
    "Y'all are why warning labels exist.",
    "This is like a PSA. 'Don't do this. Ever.'",
    "The fence gate's got better opening strategies.",
    "Well, this is one for the history books. The dumb history books.",
    "Y'all make the mule look like a Mensa member.",
    "This is what 'seemed like a good idea at the time' looks like.",
    "The milk pail's more useful. And it's EMPTY.",
    "Well, natural selection's got its work cut out tonight.",
    "Y'all are the reason insurance rates are high.",
    "This is gonna be a fun 911 call. 'Yeah, they did it to themselves.'",
    "The hay loft's seen some falls. This is a different kind of falling.",
    "Well, someone's getting haunted by their own ghost for this.",
    "Y'all make the barn swallows look like aeronautical engineers.",
    "This is peak entertainment. If you're a buzzard.",
    "The water pump's got better pressure management than y'all.",
    "Well, this is gonna make the local news. Page 8. Small column.",
    "Y'all are like a bad crop. Should've never been planted.",
    "This is what happens when you let 'curiosity' win over 'survival.'",
    "The tool shed's more organized than these priorities.",
    "Well, at least someone's committed. To stupidity.",
    "Y'all make the morning dew look smart for evaporating.",
    "This is gonna be a GREAT campfire story. Cautionary tale.",
    "The grain storage's got better long-term planning.",
    "Well, Darwin's gonna write y'all a thank-you note.",
    "Y'all are proof that evolution can go backwards.",
    "This is like watching a nature documentary. On idiots.",
    "The chicken coop's got better exit strategies.",
    "Well, someone's family tree's about to lose a branch.",
    "Y'all make the dirt look cultured.",
    "This is what 'famous last words' sound like before they happen.",
    "The irrigation system's got better flow management.",
    "Well, at least the mortician's getting work. Economic stimulus.",
    "Y'all are why alien contact hasn't happened yet.",
    "This is gonna look great on a 'what not to do' poster.",
    "The pasture's got greener grass. And better decision-making.",
    "Well, someone's guardian angel just filed for overtime.",
    "Y'all make the weeds look productive.",
    "This is natural selection's victory lap.",
    "The chicken eggs have more potential than this plan.",
    "Well, this beats boredom. Not by much, but technically.",
    "Y'all are like a country song. Sad and full of bad choices.",
]

HORROR_PRE_TURN_TAUNTS = [
    "The final girl always survives. You're not her.",
    "This isn't a jump scare. This is a jump to conclusions about your mortality.",
    "The call is coming from inside the chamber.",
    "Don't go in the basement. Don't pull that trigger. You will anyway.",
    "The monster under your bed has better survival instincts than you.",
    "Plot armor not detected. Gore filter disabled.",
    "This is the part where you run. Oh wait, you can't.",
    "The killer always comes back. You won't.",
    "Your survival chances: worse than a horror movie teenager.",
    "Scream all you want. It won't help.",
    "The lights flicker. The shadows grow. Someone's time is up.",
    "In the mirror, you see your reflection. And Death behind you.",
    "The music swells. The violins screech. Someone dies.",
    "Don't split up, they said. Don't investigate the noise. Don't pull the trigger. And yet...",
    "The phone rings. No one answers. Because they're dead.",
    "Knock knock. Who's there? Death. Death who? Death for you.",
    "The closet door creaks open. Nothing inside. The real monster's in your hand.",
    "The tape plays backward: 'Seven days.' For you? Seven seconds.",
    "The asylum's been abandoned for years. The screaming never stopped.",
    "The cabin in the woods looked peaceful. The cemetery will too.",
    "The children are singing nursery rhymes. They're singing for you.",
    "The doll's eyes follow you across the room. The bullet will too.",
    "The fog rolls in thick. Someone won't roll out.",
    "The old mansion has a dark history. You're about to add to it.",
    "The seance contacted the dead. You're about to join the conversation.",
    "The cursed videotape kills in seven days. This kills in seven seconds.",
    "The attic stairs creak under your weight. Soon nothing will.",
    "The pentagram on the floor glows faintly. Hell is expecting guests.",
    "The exorcism failed. The possession is permanent. Death is too.",
    "The clown doll moves when you're not looking. Death doesn't need to hide.",
    "The woods are dark and deep. So is your grave.",
    "The scratching at the door stops. Now it's coming from inside.",
    "The blood on the wall spells a name. Yours.",
    "The elevator stops between floors. Between life and death.",
    "The music box plays its haunting tune. Your swan song.",
    "The entity feeds on fear. You're an all-you-can-eat buffet.",
    "The ritual requires a sacrifice. Congratulations, volunteer.",
    "The shadow at the end of the hall grows longer. It's reaching for you.",
    "The heartbeat under the floorboards grows louder. Yours is about to stop.",
    "The door slams shut. The windows won't open. The chamber's loaded.",
    "In horror, everyone makes bad decisions. This is yours.",
]

DETECTIVE_PRE_TURN_TAUNTS = [
    "The butler didn't do it. The bullet will.",
    "Clue: someone dies. Suspect: you. Weapon: obvious.",
    "Elementary, my dear Watson. Someone's fucked.",
    "The case of the missing braincells. Closed.",
    "Whodunit? Spoiler: the gun did it.",
    "The plot thickens. Your blood will too.",
    "This mystery has one solution: death.",
    "The detective always solves the case. This one's easy.",
    "Your alibi won't matter when you're dead.",
    "The smoking gun is literal tonight.",
    "The evidence points to one conclusion: you're an idiot.",
    "The murder weapon: a revolver. The victim: TBD.",
    "Motive, means, opportunity. You've got all three to die.",
    "The autopsy report will read: stupidity.",
    "Cause of death: misadventure. Manner: dumbass.",
    "The crime scene is about to get very interesting.",
    "The investigation concludes: natural selection.",
    "The fingerprints on the trigger? Yours.",
    "The ballistics report is clear: fatal shot, close range, self-inflicted.",
    "The witness testimony: 'They were an idiot.'",
    "The detective's notebook: 'Victim had it coming.'",
    "The magnifying glass reveals: bad decisions.",
    "The footprints lead to one conclusion: the morgue.",
    "Sherlock Holmes solved cases. This case solves itself.",
    "The murderer is always the least suspected. Except this time it's the gun.",
    "The red herring was a distraction. The red mist will be your brain.",
    "The locked room mystery: how did they die? Easily.",
    "The poison was in the wine. The bullet's in the chamber.",
    "The detective puts on reading glasses. 'Yep, they're fucked.'",
    "The case files are open. Yours will be closed.",
    "The interrogation reveals: you have no idea what you're doing.",
    "The final piece of the puzzle: your obituary.",
    "The noir detective narrates: 'They never saw it coming. But I did.'",
    "The case of the Russian Roulette: solved in six shots or less.",
    "The blood spatter pattern indicates: poor life choices.",
    "The coroner's verdict: death by idiocy.",
    "The investigation timeline: click, bang, dead. Simple.",
    "The suspects are gathered. The culprit is chance.",
    "The denouement approaches. You're about to be denounced. As dead.",
    "Hercule Poirot strokes his mustache. 'Zey are imbeciles.'",
]

PIRATE_PRE_TURN_TAUNTS = [
    "Dead men tell no tales. You're about to become exhibit A.",
    "The Kraken's got nothing on this trigger pull.",
    "Yo ho ho and a chamber full of... well, you'll find out.",
    "Walk the plank or pull the trigger. At least this is faster.",
    "Buried treasure stays buried. So will you.",
    "The Black Pearl's crew had better odds than you, mate.",
    "Shiver me timbers, someone's about to shiver their last.",
    "Parley won't save you now, scallywag.",
    "The sea gives and the sea takes. This gun just takes.",
    "Davy Jones' locker is accepting new tenants.",
    "X marks the spot. The spot is your grave.",
    "The Jolly Roger flies high. Someone flies to hell.",
    "Sail ho! Death approaches off the starboard bow.",
    "The rum's gone. Soon you will be too.",
    "Mutiny on the bounty of your stupidity.",
    "The treasure map leads to one place: the cemetery.",
    "Pieces of eight, pieces of you, scattered everywhere.",
    "The cutlass is sharp. The bullet is sharper.",
    "Swab the deck with your bad decisions.",
    "The captain goes down with the ship. You just go down.",
    "Hoist the mainsail! Lower the casket!",
    "The compass points north. Death points at you.",
    "The crow's nest sees land. And your funeral.",
    "Anchors aweigh! Brain cells away!",
    "The plank is narrow. Your chances are narrower.",
    "Batten down the hatches. Button up the coffin.",
    "The tide comes in. Your life goes out.",
    "There be monsters in these waters. And idiots at this table.",
    "The ship's brig holds prisoners. The chamber holds bullets.",
    "The first mate logs the death: 'Natural causes. Naturally stupid.'",
    "Port or starboard? Life or death? You chose poorly.",
    "The barnacles cling to the hull. The bullet clings to the chamber.",
    "The fog horn sounds. It's a warning. You won't heed it.",
    "Sailors tell legends of ghost ships. You're about to become one.",
    "The plunder is divided. Your life is subtracted.",
    "The hurricane comes without warning. So does death.",
    "Three sheets to the wind, six shots in the cylinder.",
    "The mermaid's song lures sailors to doom. This gun needs no song.",
    "The naval battle rages. Casualties: you.",
    "Sail the seven seas or sink in six shots. Your choice.",
]

THEME_TAUNTS: dict[str, list[str]] = {
    "dark": DARK_BASE_TAUNTS + DARK_PRE_TURN_TAUNTS,
    "noir": NOIR_PRE_TURN_TAUNTS,
    "western": WESTERN_PRE_TURN_TAUNTS,
    "wasteland": WASTELAND_PRE_TURN_TAUNTS,
    "mafia": MAFIA_PRE_TURN_TAUNTS,
    "medieval": MEDIEVAL_PRE_TURN_TAUNTS,
    "arcade": ARCADE_PRE_TURN_TAUNTS,
    "greek": GREEK_PRE_TURN_TAUNTS,
    "norse": NORSE_PRE_TURN_TAUNTS,
    "farmer": FARMER_PRE_TURN_TAUNTS,
    "sarcastic_farmer": SARCASTIC_FARMER_PRE_TURN_TAUNTS,
    "horror": HORROR_PRE_TURN_TAUNTS,
    "detective": DETECTIVE_PRE_TURN_TAUNTS,
    "pirate": PIRATE_PRE_TURN_TAUNTS,
}

ALL_TAUNTS: list[str] = [line for lines in THEME_TAUNTS.values() for line in lines]
THEME_TAUNTS["mixed"] = ALL_TAUNTS
THEME_TAUNTS["gallows"] = THEME_TAUNTS["western"]

DARK_SURVIVAL_MESSAGES = [
    "Somehow {player} continues to defy natural selection.",
    "Death said 'not today' to {player}. Probably busy.",
    "{player} lives to disappoint everyone another day.",
    "God's really testing our patience with {player}.",
    "The grim reaper hit snooze on {player}.",
    "{player}'s guardian angel needs a raise.",
    "Congrats {player}, your plot armor held.",
    "{player} survives. Unfortunately.",
    "Death took one look at {player} and said 'nah, too easy'.",
    "{player} lives. Their enemies are devastated.",
    "God has terrible aim apparently.",
    "{player}'s survival is proof we live in a simulation with bugs.",
    "Even the bullet didn't want {player}.",
    "{player} continues to waste oxygen. Inspiring.",
]

DARK_DEATH_MESSAGES = [
    "Well, {victim} won't be needing that brain anymore.",
    "{victim} has left the chat... permanently.",
    "{victim} speedran meeting their maker.",
    "RIP {victim}. They died doing what they loved: being an idiot.",
    "{victim}'s last words were probably 'watch this'.",
    "Darwin award goes to {victim}!",
    "{victim} fucked around and found out.",
    "Say goodbye to {victim}, they're with the angels now... or the other place.",
    "{victim} took the express elevator down.",
    "Congratulations {victim}, you played yourself.",
    "{victim} won a one-way ticket to the shadow realm.",
    "At least {victim}'s student loans died with them.",
    "{victim} has been removed from the gene pool.",
    "{victim} discovered what their face looks like from the inside.",
    "Sending thoughts and prayers to {victim}'s search history.",
    "{victim} rage quit life.",
    "{victim} is now AFK... permanently.",
    "Press F to... actually, don't bother for {victim}.",
    "{victim} found out 'YOLO' has consequences.",
    "{victim} went from player to spectator mode.",
    "{victim}'s K/D ratio just went to shit.",
    "Imagine dying at level {level}, you noob.",
]

DARK_WINNER_MESSAGES = [
    "Congratulations {winner}! You're still as useless as before, just richer.",
    "{winner} wins! Now they can afford therapy for this trauma.",
    "{winner} survives! Time to spend that blood money.",
    "Everyone's dead except {winner}. How underwhelming.",
]

NOIR_DEATH_MESSAGES = [
    "{victim} just wrote their last chapter. It was a short one.",
    "The case of {victim} is now closed. Permanently.",
    "{victim} met their maker. It wasn't a friendly meeting.",
    "Chalk outline's gonna look good on {victim}.",
    "{victim} sang their swan song. It was off-key.",
    "The city claims another soul. {victim}'s name goes in the ledger.",
    "{victim} took the long sleep. No wake-up call scheduled.",
    "Fade to black for {victim}. Roll credits.",
    "{victim} bought it. No refunds.",
    "The last mystery {victim} solved: what's on the other side.",
    "{victim} crossed the river Styx. One-way ticket.",
    "Another statistic. Another story. Another stiff. Name: {victim}.",
    "{victim}'s luck ran out like whiskey at last call.",
    "The Big Sleep claimed {victim}. They won't be waking up.",
    "{victim} checked out. Left their brains as a deposit.",
]

NOIR_SURVIVAL_MESSAGES = [
    "{player} walks through the valley of death and lives to tell the tale. For now.",
    "Death came knocking. {player} didn't answer the door.",
    "{player} dodged the Grim Reaper like a bullet in a firefight. Impressive.",
    "Against all odds, {player} sees another sunrise. Savor it.",
    "The fates smiled on {player}. Don't get used to it, sweetheart.",
    "{player} lives to fight another day in this concrete jungle.",
    "Death blinked first. {player} walks away clean.",
    "Another day above ground for {player}. That's a win in this town.",
    "{player}'s guardian angel earned their wings tonight.",
    "The wheel spins, {player} wins. Sometimes even noir has a happy ending.",
]

NOIR_WINNER_MESSAGES = [
    "{winner} stands alone in the smoke. The last one breathing. That's noir, baby.",
    "When the dust settles, only {winner} remains. Cold, calculated, alive.",
    "{winner} wins. In this city, that's the closest thing to a fairy tale you'll get.",
    "The survivor: {winner}. May their nightmares be brief.",
    "{winner} walks out into the neon-lit streets, pockets heavy, conscience heavier.",
    "Fade out on {winner}, standing in the doorway, cigarette lit. End scene.",
    "{winner} takes the pot and their trauma. Both are heavy.",
    "In a world of losers, {winner} managed not to lose. That's something.",
]

NOIR_ROUND_START = [
    "The cylinder spins. Fate laughs. The game continues.",
    "Another round. Another chance to kiss the void.",
    "Chamber's loaded. Hearts are racing. Death is patient.",
    "The gun passes like a poisoned chalice. Who drinks next?",
    "New round, same old story. Someone lives, someone doesn't.",
]

WESTERN_DEATH_MESSAGES = [
    "{victim} just got sent to the big ranch in the sky.",
    "{victim} died with their boots on. And their brains out.",
    "Well, butter my biscuit, {victim} just bit the dust.",
    "{victim} has gone to meet the great rancher in the sky.",
    "Looks like {victim}'s dancing with the devil now. Hope they know the steps.",
    "{victim} rode into the sunset. Except the sunset is death and they ain't coming back.",
    "Boot Hill just got a new resident: {victim}.",
    "{victim} drew their last card and it was the dead man's hand.",
    "The good Lord called {victim} home. Probably needs someone to clean the stables.",
    "{victim}'s last roundup is complete. They can rest now... forever.",
    "Ashes to ashes, dust to dust, {victim} to the ground like a rusty bucket.",
    "{victim} just got their ticket punched. One way to hell.",
    "Somebody get the preacher. {victim}'s got an appointment underground.",
    "{victim} went out like a candle in a windstorm. Quick and messy.",
    "That's all she wrote for {victim}. And she wrote it in blood.",
    "{victim}'s gone to that great saloon in the sky. Drinks are still overpriced.",
    "The buzzards'll be eating good tonight, thanks to {victim}.",
    "{victim} just learned why they call it dead man's draw.",
    "Yippee-ki-yay, {victim}. And good fucking riddance.",
    "Level {level} and you're about to become level deceased. Yeehaw.",
    "{victim} rode for {level} levels just to get bucked off here. Tragic.",
    "Level {level} gunslinger, level 0 survival skills.",
    "All that time getting to level {level}, just to die like a greenhorn.",
    "{victim} is level {level} but their luck stat is higher than a whiskey price.",
]

WESTERN_SURVIVAL_MESSAGES = [
    "{player} lives to ride another day. Lucky sumbitch.",
    "Well I'll be damned, {player} dodged that bullet like a tumbleweed in a tornado.",
    "{player}'s got more lives than a cat in a cat house.",
    "The Good Lord's looking out for {player}. For now.",
    "{player} walks away clean. Must have horseshoes up their ass.",
    "Fate favors {player} today. Don't spend it all in one place, partner.",
    "{player}'s got the devil's own luck. Hope it holds.",
    "Against all odds, {player} keeps their head. And what's in it.",
    "{player} survives. Their mama must be praying real hard.",
    "Well slap my ass and call me Sally, {player} made it through.",
    "{player}'s still kicking. Like a mule. And twice as stubborn.",
]

WESTERN_WINNER_MESSAGES = [
    "{winner} is the last cowboy standing. The rest are sleeping in boot hill.",
    "The dust settles, and only {winner} remains. That's how legends are born, partner.",
    "{winner} rides off into the sunset with the gold. Classic western ending.",
    "Well, well, well. {winner} wins the whole pot. Time to buy the saloon a round... or don't.",
    "{winner} stands tall while the others lie low. Six feet low.",
    "The sheriff of this here game: {winner}. Fastest gun, luckiest hand.",
    "{winner} cleans up like a dust storm through a ghost town.",
    "All hail {winner}, the rootinest, tootinest, last-one-breathinest cowpoke around.",
]

WESTERN_ROUND_START = [
    "The revolver spins like a wheel of misfortune. Place your bets, lose your life.",
    "New round, new chances to meet your maker. Giddy up.",
    "The cylinder clicks. The chamber turns. The West gets wilder.",
    "Round 'em up, boys. Some won't be around for the next one.",
    "Another spin of the wheel. Another soul gets closer to hell.",
]

WASTELAND_DEATH_MESSAGES = [
    "{victim} has become another statistic in the wasteland. Population: decreasing.",
    "{victim} died as they lived: poorly.",
    "The wasteland claims {victim}. It's hungry like that.",
    "{victim} has been sent to the great vault in the sky. It's still fucking locked.",
    "Looks like {victim} won't need those rad-pills anymore.",
    "{victim}'s corpse will make excellent fertilizer for the mutated crops.",
    "Another body for the wasteland. The crows say thanks, {victim}.",
    "{victim} has left the server. Their loot is up for grabs.",
    "The apocalypse killed billions. {victim} makes it billions and one.",
    "{victim}'s gone. Their caps are contested loot now.",
    "{victim} joined the skeleton crew. Literally.",
    "Post-apocalyptic Darwin award goes to {victim}.",
    "{victim} won't be raiding any more vaults. Or breathing.",
    "The wasteland's motto: 'Fuck around and find out.' {victim} found out.",
    "{victim}'s last save point was birth. Game over.",
    "{victim} got their face rearranged. Post-apocalyptic plastic surgery.",
    "Another corpse for the pile. {victim} blends right in.",
    "{victim}'s suffering is over. Finally, some good news in the apocalypse.",
    "Level {level} and you're about to become level decomposed.",
    "{victim} ground their way to level {level} just to die in a Discord game. The irony is radioactive.",
    "All those bottle caps getting to level {level}, wasted. Like you, {victim}.",
    "Level {level} wastelander, level 0 decision-making skills.",
]

WASTELAND_SURVIVAL_MESSAGES = [
    "{player} survives. Must've found some Rad-X in their pocket.",
    "{player} lives to scavenge another day. Lucky bastard.",
    "Against all wasteland odds, {player} keeps breathing radioactive air.",
    "{player}'s survival instincts kicked in. Unlike their common sense.",
    "The wasteland tried to claim {player}. Not today, radiation.",
    "{player} walks it off like a stimpack to the chest.",
    "{player}'s mutation must be 'incredibly lucky.' It's working.",
    "Even the wasteland doesn't want {player}. Harsh.",
]

WASTELAND_WINNER_MESSAGES = [
    "{winner} stands victorious in the ashes. The strongest survives, as always.",
    "{winner} wins the pot. Time to buy some purified water and forget this ever happened.",
    "In a world of corpses, {winner} remains breathing. That's the dream.",
    "{winner} is the apex predator of this wasteland game. Everyone else is fertilizer.",
    "{winner} takes the caps and the crown. All hail the vault dweller.",
    "Congratulations {winner}. You survived. Your prize: more survival.",
]

MAFIA_DEATH_MESSAGES = [
    "{victim} has been whacked. The family business continues.",
    "Nothing personal, {victim}. Just business. Very fatal business.",
    "{victim} sleeps with the fishes now. Hope they like seafood.",
    "The Don sends his condolences to {victim}'s family. And a bill for the cleanup.",
    "{victim} got clipped. Someone call the cleaners.",
    "{victim} broke the code. Now they're broken. Permanently.",
    "Concrete's drying on {victim}'s new shoes. Size: coffin.",
    "{victim} couldn't pay their debts. Collected in full, with interest.",
    "The family took care of {victim}. Like we take care of all our problems.",
    "{victim} talked too much. Now they ain't talking at all.",
    "{victim} got made. Made into a cautionary tale.",
    "Your next of kin gets a fruit basket, {victim}. It's tradition.",
    "{victim} crossed the family. The family uncrossed {victim}. Violently.",
    "Tell {victim}'s wife she's a widow. Actually, don't bother. She knows.",
    "{victim} was loyal to the end. Shame the end came so quick.",
    "Another body in the river. The fish are eating good tonight, courtesy of {victim}.",
    "{victim} bet against the house. The house collected.",
    "The books are balanced. {victim}'s account is closed. So is their casket.",
    "Level {level} and you're about to get clipped. Shoulda stayed in your lane.",
    "{victim} made it to level {level}. The family made them into a memory.",
    "All those levels, {victim}. And you still couldn't level with death.",
    "Level {level} soldier, level 0 respect for the trigger.",
]

MAFIA_SURVIVAL_MESSAGES = [
    "{player} lives. The Don must like them. For now.",
    "{player} dodged a bullet. The family respects that. Once.",
    "Against all odds, {player} survives. Must be under the boss's protection.",
    "{player} walks away. This time. Don't push your luck, capisce?",
    "The family shows mercy to {player}. Don't make them regret it.",
    "{player}'s got friends in high places. Or low places. Either way, they live.",
    "{player} earned a pass. Use it wisely, it don't come twice.",
    "Look at that, {player} survives. Must've kissed the ring hard enough.",
]

MAFIA_WINNER_MESSAGES = [
    "{winner} stands alone. The new capo of this crew. Salute.",
    "{winner} wins. The family takes care of its winners. And its losers. Differently.",
    "Congratulations, {winner}. You earned your stripes. And everyone else's money.",
    "{winner} is the last one standing. That's how you get respect in this family.",
    "{winner} wins the pot. Don't spend it all in one place. Actually, do. We know where.",
    "All hail {winner}, the newest made man. Or made corpse-maker. Same thing.",
    "{winner} takes the prize. The boss is watching. Don't disappoint.",
]

MEDIEVAL_DEATH_MESSAGES = [
    "{victim} has been slain! The realm mourns. Just kidding, nobody cares.",
    "{victim} has fallen in battle! A short, stupid battle.",
    "Hark! {victim} hath shuffled off this mortal coil. Dramatically.",
    "{victim} is dead. Long live... well, not {victim} obviously.",
    "The Gods have spoken, and {victim} displeases them greatly.",
    "{victim} met their end not by dragon, but by dumbassery.",
    "Another soul for the Dark Lord's collection. He's running out of shelf space thanks to {victim}.",
    "{victim} has perished! The bards will sing songs of how anticlimactic it was.",
    "By royal decree, {victim} is hereby declared: fucking dead.",
    "{victim}'s quest ends here. It was a shit quest anyway.",
    "The executioner's work is done. {victim}'s head remains attached, but their brain doesn't.",
    "{victim} joins the ancestors. The ancestors are disappointed.",
    "Thy life is forfeit, {victim}! The kingdom is slightly less crowded.",
    "{victim} has been vanquished! Rolling for burial plot.",
    "The ravens feast tonight on {victim}'s corpse. It's a medieval thing.",
    "{victim}'s tale ends not with glory, but with a gunshot. Poetic.",
    "Alas, poor {victim}. We knew them, Horatio. They were an idiot.",
    "{victim} took an arrow to the... wait, wrong kind of weapon. Bullet to the brain.",
    "Level {level} knight, level 0 wisdom saves.",
    "Thou hast reached level {level}, only to die at level deceased. Verily, tragic.",
    "{victim} quested to level {level} for this? The Gods are cruel.",
    "A level {level} hero falls. Not to dragon, not to demon, but to RNG.",
    "Level {level} and thy fate is sealed. Should've invested in luck stats.",
]

MEDIEVAL_SURVIVAL_MESSAGES = [
    "{player} lives! The Gods smile upon them. Or they're just incompetent Gods.",
    "By the grace of the Old Gods, {player} survives! Barely.",
    "{player} cheats death! The Reaper is filing a formal complaint.",
    "Huzzah! {player} endures! Their plot armor is impenetrable.",
    "{player} stands strong! Must be blessed by some minor deity nobody's heard of.",
    "The Fates weave kindly for {player}. For now.",
    "{player} remains among the living! The royal court is shocked.",
    "Against all odds and medieval logic, {player} survives!",
]

MEDIEVAL_WINNER_MESSAGES = [
    "{winner} stands victorious! The crown of corpses fits them well.",
    "All hail {winner}, slayer of idiots, keeper of the pot!",
    "{winner} claims victory! The bards will sing of this... or not. Probably not.",
    "Long live {winner}! The only one still living, technically.",
    "{winner} is declared champion! Their prize: gold and trauma.",
    "By royal decree, {winner} is the last one breathing. Congratulations, Your Grace.",
    "{winner} wins! The realm celebrates. Mostly because it's finally over.",
]

ARCADE_DEATH_MESSAGES = [
    "Game Over for {victim}. Insert coin to... oh wait, you can't.",
    "{victim} hit the death screen. No continues available.",
    "Critical hit. {victim} is permanently out.",
    "The cabinet blares: 'YOU DIED.' {victim}'s screen fades to black.",
    "{victim}'s health bar emptied. Status: Deceased.",
    "Fatal error: {victim}.exe has stopped responding. Forever.",
    "Score saved. Player deleted: {victim}.",
    "{victim} got one-shotted by RNG. Massive skill issue.",
    "Speedrun ends here. Final time: {victim}'s entire life.",
    "Level {level} and still no extra life for {victim}. Game Over.",
    "Achievement unlocked: {victim} died stupidly at level {level}.",
    "The boss fight ends with {victim} face-planting into oblivion.",
    "{victim} rage quit. Except it's permanent.",
    "Connection lost: {victim}'s life signal.",
    "Respawn timer: infinite. {victim} is done.",
    "The leaderboard updates: {victim} - DEAD.",
    "{victim} tried to glitch through life. Didn't work.",
    "Your save file is corrupted, {victim}. Start over? No.",
    "{victim} faced the final boss: Death. 0-1.",
    "Player {victim} has been kicked from the server. Reason: Dead.",
    "The arcade machine eats another quarter. And {victim}.",
    "{victim}'s combo is broken. By death.",
    "Level complete: Life. Player lost: {victim}.",
    "The screen flashes red. {victim} didn't make it.",
    "New record! {victim} speedran dying at level {level}.",
]

ARCADE_SURVIVAL_MESSAGES = [
    "Continue? 10... 9... {player} stays in!",
    "The cabinet flashes 'LUCKY!' {player} keeps breathing.",
    "{player} dodged the hitbox like a pro. Invincibility frames activated.",
    "{player} found a 1-UP. Don't ask where they got it.",
    "Checkpoint restored. {player} stays in the game.",
    "RNG smiled on {player}. The dice rolled 'survive'.",
    "{player} lives. The credits do NOT roll yet.",
    "Player {player} takes no damage this round. Combo intact.",
    "The screen flickers... {player} is still there. Still alive.",
    "{player} button-mashes their way to survival.",
    "Extra life activated for {player}. How? Who cares.",
    "{player} perfect-parried Death itself.",
    "The game lags. {player} survives the glitch.",
    "{player} found the cheat code: not dying.",
]

ARCADE_WINNER_MESSAGES = [
    "High score: {winner}. Everyone else rage quit permanently.",
    "{winner} clears the final stage and claims the pot.",
    "Flawless victory. {winner} takes it all.",
    "{winner} is Player 1. Everyone else is Game Over.",
    "{winner} completes the run. GG no re.",
    "Final boss defeated: Everyone Else. Winner: {winner}.",
    "{winner} keeps the token, the glory, and the money.",
    "Game complete. {winner} watches the credits alone.",
    "{winner} wins. All other players: disconnected.",
    "Achievement unlocked: {winner} - Last One Standing.",
]

GREEK_DEATH_MESSAGES = [
    "Hades opens his ledger and writes {victim}'s name in blood.",
    "{victim} pays Charon's toll. One way trip across the Styx.",
    "Atropos cuts the thread. {victim}'s fate is sealed.",
    "The gods have spoken: {victim} displeases them. Fatally.",
    "Nemesis collects her due from {victim}. Interest included.",
    "Thanatos yawns and takes {victim} without ceremony.",
    "The Furies descend and claim {victim}'s soul.",
    "Level {level} hero, felled by hubris. {victim} joins the shades.",
    "{victim} reached level {level} and still couldn't escape the Fates.",
    "The temple doors close. {victim}'s offerings are rejected.",
    "{victim} angered the gods. The gods responded. Violently.",
    "Persephone welcomes {victim} to the Underworld. No return trips.",
    "{victim} challenged fate. Fate won. Easily.",
    "The Oracle was right. {victim} should have listened.",
    "Cerberus gnaws on {victim}'s bones. All three heads are satisfied.",
    "{victim} reaches Elysium's gates. They're closed. Permanently.",
    "The Titans had better odds than {victim}.",
    "Zeus throws a thunderbolt. {victim} stops existing.",
    "Ares laughs as {victim} falls. This pleases the war god.",
    "{victim} flies too close to the sun. And the bullet.",
    "The Minotaur claims another victim: {victim}.",
    "Hera's jealousy is legendary. {victim}'s stupidity more so.",
    "{victim} tries to cheat death. Hades is not amused.",
    "The River Lethe claims {victim}. They're forgotten already.",
    "Kronos devoured his children. This gun devoured {victim}.",
]

GREEK_SURVIVAL_MESSAGES = [
    "The Fates spare {player}'s thread. For now.",
    "Athena whispers wisdom to {player}. It works. Barely.",
    "Hermes runs interference. {player} escapes Death's grasp.",
    "{player} slips past Thanatos like Sisyphus on a good day.",
    "The thread holds. {player} lives to see another dawn.",
    "The gods blink. {player} survives in that moment.",
    "{player} avoids the Underworld. Charon's ferry waits empty.",
    "Olympus looks away. {player} breathes another breath.",
    "{player} has divine favor. Or divine luck. Same thing.",
    "Apollo's light shines on {player}. Death retreats.",
    "The Moirai laugh. {player} lives anyway.",
    "{player} dodges fate like Odysseus dodged responsibility.",
]

GREEK_WINNER_MESSAGES = [
    "Only {winner} stands. Even the gods nod in respect.",
    "{winner} survives the trial. A mortal with divine fortune.",
    "The Fates untangle all threads but one: {winner}'s.",
    "{winner} claims the pot and Olympus' favor.",
    "{winner} walks away while Hades keeps the rest.",
    "Victory belongs to {winner}. Zeus approves from on high.",
    "{winner} earns their place in legend. The bards will sing.",
    "The gods gambled. {winner} was the winning bet.",
]

NORSE_DEATH_MESSAGES = [
    "Hel claims {victim}. The gates of the cold hall close.",
    "{victim} falls in battle. The Valkyries pass them by.",
    "The runes go dark for {victim}. Fate is sealed.",
    "Ragnarok claims {victim} ahead of schedule.",
    "The Valkyries circle but do not descend for {victim}.",
    "{victim} meets a cold end. The barrel was colder still.",
    "Level {level} warrior, undone by wyrd. {victim} falls to Hel.",
    "{victim} reached level {level}. The Norns cut the thread anyway.",
    "Gjallarhorn sounds. {victim}'s saga ends.",
    "Yggdrasil shudders. One less soul hangs from its branches.",
    "{victim} sought Valhalla. Found only dirt.",
    "The einherjar feast. {victim} does not join them.",
    "Fenrir's jaws close on {victim}'s fate.",
    "The World Serpent coils tighter. {victim} stops breathing.",
    "{victim} dies without honor. Hel welcomes them coldly.",
    "Odin watches {victim} fall. He does not send ravens.",
    "Thor's hammer misses. {victim} does not.",
    "The Norns weave {victim}'s ending. It is brief and ignoble.",
    "Baldur died from mistletoe. {victim} from stupidity.",
    "The mead hall falls silent for {victim}. Then laughter resumes.",
    "Skadi brings winter to {victim}'s corpse.",
    "The draugr will envy {victim}'s death. At least they walked.",
    "Level {level} and still no glory. {victim} dishonors the ancestors.",
    "The berserkers howl. {victim} whimpers. Then nothing.",
    "The runes were cast. {victim} drew death.",
]

NORSE_SURVIVAL_MESSAGES = [
    "The Norns spare {player}. The thread remains uncut.",
    "{player} cheats Hel and walks among the living still.",
    "Odin looks away. {player} survives in that moment.",
    "{player} lives to drink and boast another day.",
    "The runes favor {player} this round. Barely.",
    "{player} dodges Fenrir's bite. Luck or skill? Both.",
    "Not today, Ragnarok. {player} keeps breathing.",
    "{player} remains in the saga. The skalds take note.",
    "Freya's tears fall elsewhere. {player} lives.",
    "{player} walks the edge of Ginnungagap. And steps back.",
    "The Wild Hunt passes by {player}. This time.",
    "{player} survives. The mead tastes sweeter.",
]

NORSE_WINNER_MESSAGES = [
    "{winner} stands alone. The skalds will sing this saga.",
    "{winner} claims the pot and the glory both.",
    "Only {winner} remains. Valhalla can wait.",
    "{winner} survives the trial of steel and wyrd.",
    "{winner} is the last to draw breath. That is victory.",
    "The Norns write {winner} as the lone survivor.",
    "{winner} drinks from the skulls of the fallen. Metaphorically.",
    "All hail {winner}, who cheated death and the Norns both.",
]

FARMER_DEATH_MESSAGES = [
    "The harvest claims {victim}. Reaped and buried.",
    "{victim} is planted. They won't be growing back.",
    "The Grim Reaper takes {victim}. It's in the name.",
    "Fresh grave dug for {victim}. Six feet deep.",
    "The field gets a new scarecrow: {victim}'s corpse.",
    "The barn falls quiet. {victim} won't be mucking stalls again.",
    "Level {level} farmhand, harvested early. Nature is cruel.",
    "{victim} hit level {level}. Still couldn't outrun the scythe.",
    "The soil accepts {victim}. Good fertilizer, at least.",
    "Sunset falls on {victim}. They don't rise with the sun.",
    "{victim} bought the farm. Literally and fatally.",
    "The chickens peck at {victim}'s grave. Circle of life.",
    "The combine harvester has seen death before. {victim} is just another.",
    "{victim} won't be milking cows tomorrow. Or ever.",
    "The well runs deep. {victim}'s grave runs deeper.",
    "From dirt you came, {victim}. To dirt you return. Fast.",
    "The rooster crows for {victim}. It's a funeral dirge.",
    "The livestock mourn. Just kidding, they don't care about {victim}.",
    "Another body for the back forty. {victim} joins the others.",
    "The thresher takes grain and {victim}. Both are ground down.",
    "Crop rotation: corn, wheat, {victim}'s corpse.",
    "The farmhouse lights go out for {victim}.",
    "Country living, country dying. {victim} chose poorly.",
    "The almanac predicted rain. Got blood instead, courtesy of {victim}.",
    "The plow turns the earth. The earth accepts {victim}.",
]

SARCASTIC_FARMER_DEATH_MESSAGES = [
    "Well, {victim} won't be milking cows tomorrow. Or ever. Shame. Not really.",
    "Oh no. {victim} died. Who could have possibly seen this coming. Besides everyone.",
    "{victim} is now fertilizer. At least they're finally useful.",
    "The harvest claims {victim}. Nature's way of saying 'you're an idiot.'",
    "Well, butter my biscuit, {victim} done gone and died. Shocker.",
    "{victim} bought the farm. Ironic, since we're already ON a farm.",
    "The Good Lord called {victim} home. Probably to ask 'what were you thinking?'",
    "{victim} has passed. The chickens are already planning the memorial. Just kidding.",
    "Rest in peace, {victim}. Or don't. I'm not your supervisor.",
    "Oh look, {victim} discovered the consequences of their actions. Educational.",
    "{victim} is now room temperature. Farm temperature, specifically.",
    "The scarecrow mourns {victim}. Actually, it's just standing there. Like always.",
    "Well, {victim}'s gone and done it now. Done died, that is.",
    "{victim} at level {level}, dead as a doornail. A really stupid doornail.",
    "The cows are devastated about {victim}. JK, they literally don't care.",
    "Another day, another burial. {victim} joins the back forty.",
    "{victim} has kicked the bucket. The bucket's relieved, honestly.",
    "Thoughts and prayers for {victim}. Mostly thoughts like 'what an idiot.'",
    "The barn's seen a lot of death. {victim}'s was the dumbest.",
    "Well, {victim}'s dirt napping now. Permanently.",
    "Ashes to ashes, dust to dust, {victim} to the ground we don't trust.",
    "{victim} made it to level {level} just to die in a barn. Peak performance.",
    "The rooster crows for {victim}. It's not respectful, it's just coincidence.",
    "{victim} won't be seeing another sunrise. Or anything, really.",
    "The pigs are sad. Wait, no, they're just hungry. Never mind about {victim}.",
    "Well, {victim} fucked around. And found out. Mostly found out.",
    "{victim} has left the building. And the mortal plane. Efficient.",
    "Oh no, anyway. {victim}'s gone. Moving on.",
    "{victim} speedran dying. Personal best, I'm sure.",
    "The good news: {victim}'s suffering is over. The bad news: everything else.",
    "{victim} got what they ordered: death. Fast delivery too.",
    "Well, {victim} won't be a problem anymore. Silver linings.",
    "{victim} is with the angels now. The angels are confused.",
    "Breaking news: {victim} is dead. In other news: water is wet.",
    "{victim} at level {level}. Was at level {level}. Past tense is important.",
    "The Lord works in mysterious ways. This wasn't mysterious. This was obvious.",
    "{victim} has officially left the gene pool. Darwin approves.",
    "Well, {victim}'s not coming back from that. Unless zombies are real.",
    "{victim} went to the big farm in the sky. This farm. They just died here.",
    "Congratulations {victim}, you played yourself. And lost. Permanently.",
    "The chickens will miss {victim}. LOL, no they won't.",
    "{victim} has been promoted to fertilizer. It's a lateral move, really.",
    "Well, that's gonna leave a mark. On the ground. Where {victim} fell.",
    "{victim} has ceased to be. They're an ex-person now.",
    "The tractor runs better than {victim} does now. Because {victim} doesn't run. Dead.",
    "{victim}'s family tree just lost a branch. A dumb branch.",
    "Oh well, {victim} tried. Not hard, but they tried.",
    "The barn's one idiot lighter. Thanks, {victim}.",
    "{victim} won the stupid prize. The prize is death.",
    "Well, {victim}'s mama's gonna be upset. Or relieved. Hard to say.",
    "{victim} at level {level}, now at level deceased. Math is simple.",
    "The farm got quieter. {victim} got deader. Equivalent exchange.",
    "{victim} died doing what they loved: being an absolute moron.",
    "Pour one out for {victim}. Actually, save it. They're not thirsty anymore.",
    "The good Lord giveth, and Russian roulette taketh away. Specifically from {victim}.",
    "{victim} went out not with a bang, but with a-- wait, no, it was a bang.",
    "Well, {victim}'s obituary's gonna be interesting. 'Died of stupidity.'",
    "The graveyard's getting a new resident: {victim}. Population: dead.",
    "{victim} has flatlined. Like their decision-making. But more permanent.",
    "Breaking: local idiot {victim} stops being alive. Town unsurprised.",
    "Well, {victim} won't be needing that college fund anymore.",
    "{victim} got their wings. And by wings I mean 'put in the ground.'",
    "The rooster crows. {victim} doesn't. Can't. Dead.",
    "{victim} went to meet their maker. To ask 'why'd you make me stupid?'",
    "Well, someone's chair's gonna be empty at Thanksgiving. {victim}'s.",
    "{victim} achieved room temperature challenge. Permanent difficulty mode.",
    # HUNDREDS MORE ADDITIONS:
    "{victim} has officially unsubscribed from life. Permanently.",
    "Well, {victim}'s not gonna make that dentist appointment.",
    "{victim} proved that stupidity CAN be fatal. Science!",
    "The chickens are updating their records. {victim}: deceased.",
    "Well, {victim}'s parking spot just opened up.",
    "{victim} has logged off. Forever. No respawn.",
    "Another one bites the dust. Specifically, {victim}.",
    "Well, {victim}'s gym membership just became a waste of money.",
    "{victim} went from alive to al-wasn't. Quick transition.",
    "The gene pool just got slightly better. Thanks, {victim}.",
    "Well, {victim}'s life insurance is about to pay out.",
    "{victim} has been yeeted from existence. Violently.",
    "The farm's IQ just went up. {victim}'s contribution: leaving.",
    "Well, {victim} won't be voting in the next election.",
    "{victim} discovered the afterlife. Hope they like it. They're stuck there.",
    "Breaking: {victim} is no longer with us. The cows didn't notice.",
    "Well, {victim}'s New Year's resolutions are cancelled.",
    "{victim} has passed. Like a kidney stone. Painfully.",
    "The mortician sends their regards for {victim}. And their bill.",
    "Well, {victim}'s not gonna finish that Netflix series.",
    "{victim} went to the great beyond. The beyond being: dead.",
    "Another satisfied customer of death. {victim}, everyone.",
    "Well, {victim}'s student loans are someone else's problem now.",
    "{victim} at level {level}, converted to level 6-feet-under.",
    "The local cemetery welcomes {victim}. With open gates.",
    "Well, {victim}'s dating profile just became VERY outdated.",
    "{victim} has achieved maximum deadness. Highscore!",
    "The farm lost a worker. Gained a corpse. Net zero.",
    "Well, {victim}'s shopping cart is gonna get real lonely.",
    "{victim} exited stage left. Into a coffin.",
    "Another one for the history books. The 'idiots who died' books.",
    "Well, {victim}'s Spotify playlist is gonna go stale.",
    "{victim} has been removed from the census. Permanently.",
    "The grim reaper thanks {victim} for making his job easy.",
    "Well, {victim}'s alarm clock is gonna be real confused tomorrow.",
    "{victim} went from player to played. Past tense.",
    "Another candidate for 'dumbest death of the year.' {victim}.",
    "Well, {victim}'s houseplants are about to die too.",
    "{victim} got exactly what they asked for. Death.",
    "The farm's productivity unchanged. {victim} didn't do much anyway.",
    "Well, {victim}'s social security number just became available.",
    "{victim} has been uninstalled from life. No backup available.",
    "Another preventable death that wasn't prevented. {victim}.",
    "Well, {victim}'s coffee's getting cold. And so are they.",
    "{victim} joined the choir eternal. The choir being: worms.",
    "The local florist thanks {victim} for the business.",
    "Well, {victim}'s phone's gonna go straight to voicemail. Forever.",
    "{victim} got their final paycheck. It's from the grim reaper.",
    "Another one down. {victim} specifically.",
    "Well, {victim}'s expired. Like milk. But faster.",
    "{victim} found peace. Or pieces. Hard to tell.",
    "The farm continues. {victim} doesn't.",
    "Well, {victim}'s browser history dies with them. Thank god.",
    "{victim} at level {level} achieved level non-existent.",
    "The obituary section gets longer. Thanks, {victim}.",
    "Well, {victim}'s gym locker is up for grabs.",
    "{victim} made the ultimate sacrifice. Their life. For nothing.",
    "Another statistic in the 'death by stupidity' column. {victim}.",
    "Well, {victim}'s Uber rating stays frozen. At dead.",
    "{victim} went from vertical to horizontal. Permanently.",
]

FARMER_SURVIVAL_MESSAGES = [
    "{player} dodges the reaper. Back to work.",
    "A lucky harvest for {player}. Still got both hands.",
    "{player} stays above ground. The crops still need tending.",
    "The scythe swings wide. {player} ducks.",
    "{player} lives to milk another cow. Thrilling.",
    "The field spares {player}. Somebody's gotta do the work.",
    "{player} keeps their boots on. And their brains in.",
    "{player} survives. The farm still needs a fool.",
    "Mother Nature blinks. {player} lives.",
    "The rooster crows for {player}. Good omen, somehow.",
    "{player} walks back to the barn. Alive and confused.",
    "The harvest moon smiles on {player}. For now.",
]

SARCASTIC_FARMER_SURVIVAL_MESSAGES = [
    "Well, look at {player}, still breathing and everything. Incredible.",
    "{player} survives. The chickens are mildly surprised.",
    "Against all odds and common sense, {player} lives. Good for them, I guess.",
    "{player} dodges death. Must be all that clean country air. Or dumb luck.",
    "The Good Lord protects {player}. Why? No idea.",
    "{player} lives another day. The cows are thrilled. Not really.",
    "Well slap my knee, {player} made it through. Miracles DO happen.",
    "{player} survives. The scarecrow's proud. The scarecrow's also inanimate.",
    "Look at that, {player} still has a pulse. Modern medicine is amazing. Wait, this isn't medicine.",
    "{player} walks away clean. Mostly clean. Bit of blood, but not theirs.",
    "The rooster crows for {player}. It's not a blessing, it's just morning.",
    "{player} lives to disappoint us another day. Heartwarming.",
    "{player} cheats death. Death files a formal complaint.",
    "Well butter my bread, {player}'s still kicking. Like a mule. Just as stubborn too.",
    "Oh, would you look at that. {player} survives. Someone alert the press.",
    "{player} lives. The universe sighs heavily.",
    "Against all logic, {player} keeps breathing. Nature's full of mysteries.",
    "Well, {player} dodged that one. Probably used up their lifetime supply of luck.",
    "{player} survives. The gene pool is... well, it is what it is.",
    "Look at {player}, defying Darwin one click at a time.",
    "{player} lives to make poor decisions another day. Consistency is key.",
    "Well, I'll be damned. {player}'s still here. Unfortunately for all of us.",
    "{player} survives. The chickens didn't see that coming. Neither did anyone.",
    "Oh good, {player} lives. Now we can do this all over again.",
    "{player} dodges the bullet. Literally. Someone give them a medal. Or don't.",
    "Well, {player}'s guardian angel earned their paycheck today.",
    "{player} survives through sheer dumb luck. Emphasis on 'dumb.'",
    "The Good Lord works overtime for {player}. Must be exhausting.",
    "{player} lives. The pigs are shocked. The pigs don't understand probability.",
    "Well, {player} beat the odds. Now if only they could beat their poor judgment.",
    "{player} survives another round. The bar for achievement is real low here.",
    "Look at {player}, still vertical and everything. What a time to be alive.",
    "{player} lives. Someone's mama's prayers are WORKING.",
    "Against all agricultural wisdom, {player} survives. The almanac's confused.",
    "{player} dodges death like they dodge responsibility. Successfully, apparently.",
    "Well, {player} made it. The chickens update their betting pool.",
    "{player} survives. Darwin is personally offended.",
    "Oh, {player} lives. How nice. How very, very... expected? No, wait.",
    "{player} keeps their brains inside their skull. For now.",
    # HUNDREDS MORE SURVIVAL MESSAGES:
    "Well, {player}'s still with us. The jury's still out on whether that's good.",
    "{player} survives. The goats are re-evaluating their betting strategy.",
    "Look at {player}, continuing to exist. Bold strategy.",
    "Well, {player} lives. The farm's average IQ drops accordingly.",
    "{player} dodges death. Death takes notes for next time.",
    "Against all reason, {player} keeps their pulse. Weird flex but okay.",
    "Well, {player}'s mama can breathe easy. For now.",
    "{player} survives. The chickens owe the rooster money now.",
    "Look at that, {player}'s still upright. Gravity's slacking.",
    "Well, {player} lives to regret this later. Probably tonight.",
    "{player} survives another turn. The bar's on the floor and they still tripped.",
    "Against all veterinary science, {player} lives. The livestock are confused.",
    "Well, {player} dodges the reaper. The reaper files for overtime.",
    "{player} lives. The universe checks its math. Twice.",
    "Look at {player}, defying expectations. Low expectations, but still.",
    "Well, {player}'s guardian angel deserves a bonus. Hazard pay, even.",
    "{player} survives. The scarecrow nods approvingly. It's the wind.",
    "Against all farming knowledge, {player} lives. The almanac updates.",
    "Well, {player} beats the odds. Vegas wants to study them.",
    "{player} lives. The pigs are taking notes. For science.",
    "Look at that, {player} survives. Their mama taught them nothing.",
    "Well, {player}'s still here. The barn swallows are impressed. Not really.",
    "{player} dodges death. Death's getting annoyed now.",
    "Against all probability, {player} lives. Math is crying.",
    "Well, {player} survives. The rooster's confused. It's always confused.",
    "{player} lives another day. The cemetery's disappointed.",
    "Look at {player}, continuing to breathe. Overachiever.",
    "Well, {player}'s luck holds. Someone check for horseshoes.",
    "{player} survives. The cows don't care. The cows never care.",
    "Against all sense, {player} lives. Common sense files a complaint.",
    "Well, {player} dodges the bullet. The bullet's offended.",
    "{player} lives. The chickens are recalculating. They're chickens. It's slow.",
    "Look at that, {player} survives. Their ancestors weep. Or cheer. Hard to tell.",
    "Well, {player}'s still kicking. The mule's jealous.",
    "{player} lives to see another day. That day being: more of this.",
    "Against all agricultural precedent, {player} survives. The tractors are confused.",
    "Well, {player} dodges death. Death's getting better at dodgeball though.",
    "{player} lives. The universe shrugs. 'Okay then.'",
    "Look at {player}, defying the odds. The odds are filing paperwork.",
    "Well, {player} survives. The pigs update their will. Just in case.",
    "{player} lives another turn. The turn being: toward more stupidity.",
    "Against all reason and rhyme, {player} lives. Dr. Seuss is confused.",
    "Well, {player}'s still breathing. The air's concerned.",
    "{player} survives. The chickens cluck disapprovingly. Always disapproving.",
    "Look at that, {player} lives. The gene pool sighs in resignation.",
    "Well, {player} dodges the reaper. The reaper needs better aim.",
    "{player} lives. The farm's safety record remains: terrible.",
    "Against all veterinary advice, {player} survives. The vet retires.",
    "Well, {player}'s still here. The barn's structural integrity is jealous.",
    "{player} lives to fight another day. 'Fight' being: lose to RNG.",
    "Look at {player}, continuing to defy death. Death's getting creative.",
    "Well, {player} survives. The rooster crows. It's unrelated.",
    "{player} lives. The cows moo. Also unrelated.",
    "Against all farming wisdom, {player} survives. The wisdom's outdated anyway.",
    "Well, {player} dodges death. Death dodges taxes. Different skills.",
    "{player} lives another round. The round being: shaped like a bullet.",
    "Look at that, {player} survives. The chickens are speechless. They're always speechless.",
    "Well, {player}'s still with us. The 'us' being: idiots.",
    "{player} lives. The pigs snort. It's either laughter or allergies.",
    "Against all logic and reason, {player} survives. Logic quits. Reason follows.",
    "Well, {player} dodges the bullet. The bullet's taking it personally now.",
    "{player} lives to see another sunrise. The sunrise is unimpressed.",
    "Look at {player}, still alive and everything. The everything being: dumb luck.",
    "Well, {player} survives. The goats are updating their actuarial tables.",
    "{player} lives. The barn owl hoots. It's judging.",
    "Against all predictions, {player} survives. The predictions sue for defamation.",
    "Well, {player}'s still kicking. The bucket's relieved it wasn't kicked.",
    "{player} lives another day. That day being: probably their last.",
    "Look at that, {player} survives. Evolution pauses. Reconsiders.",
    "Well, {player} dodges death. Death's schedule is getting backed up.",
    "{player} lives. The chickens lay eggs. Life continues. Somehow.",
    "Against all sense and sensibility, {player} survives. Jane Austen is confused.",
    "Well, {player}'s still breathing. The air's filing a complaint.",
    "{player} lives to make more mistakes. Consistency!",
    "Look at {player}, defying medical science. By not needing it. Yet.",
    "Well, {player} survives. The scarecrow's seen better performances. It's straw.",
    "{player} lives. The universe checks the warranty. It's expired.",
    "Against all agricultural best practices, {player} survives. The practices retire.",
    "Well, {player} dodges the reaper. The reaper's getting a performance review.",
    "{player} lives another turn. The turn being: for the worse.",
    "Look at that, {player} survives. The cows are thoroughly whelmed.",
    "Well, {player}'s still here. The here being: this stupid game.",
    "{player} lives. The pigs are taking bets on how long.",
    "Against all probability and statistics, {player} survives. Statistics drops out of college.",
    "Well, {player} dodges death. Death's dodging responsibilities at this point.",
    "{player} lives to breathe another breath. The breath being: probably their second-to-last.",
    "Look at {player}, continuing to exist. Existence is exhausted.",
    "Well, {player} survives. The rooster's impressed. It's easy to impress.",
    "{player} lives. The farm continues. Both questionably.",
    "Against all reason, logic, and good taste, {player} survives. Good taste left first.",
    "Well, {player}'s still kicking. The hay bale's unimpressed.",
    "{player} lives another day. The day being: full of bad decisions.",
    "Look at that, {player} survives. The chickens are reevaluating everything.",
    "Well, {player} dodges the bullet. The bullet's writing a memoir about it.",
    "{player} lives. The cows are indifferent. As always.",
    "Against all farming traditions, {player} survives. The traditions are outdated anyway.",
    "Well, {player}'s still breathing. Breathing being: overrated but necessary.",
    "{player} lives to see another round. The round being: Russian Roulette.",
    "Look at {player}, defying all expectations. The expectations being: death.",
    "Well, {player} survives. The goats are confused. The goats are always confused.",
]

FARMER_WINNER_MESSAGES = [
    "{winner} brings in the harvest and the pot both.",
    "Only {winner} stays standing in the field.",
    "{winner} wins. The rest make good fertilizer.",
    "{winner} walks away with dirty boots and full pockets.",
    "{winner} is the last crop standing. Reap the rewards.",
    "The farm belongs to {winner} now. By right of survival.",
    "{winner} takes the prize. Time to buy more chickens.",
    "Honest work, honest reward. {winner} earned both.",
]

SARCASTIC_FARMER_WINNER_MESSAGES = [
    "Well, I'll be damned. {winner} actually survived. Congratulations on not dying.",
    "{winner} wins the pot. They can finally afford that therapy they're gonna need.",
    "Only {winner} remains. The cows are... still cows. They don't care.",
    "{winner} takes it all. Good for them. Real good. Yep.",
    "Against all agricultural logic, {winner} survives. The almanac's confused.",
    "{winner} is the last one standing. The scarecrow's impressed. Still just straw though.",
    "Well, look at {winner}, all alive and victorious. Must be nice.",
    "{winner} walks away with the prize. And trauma. Mostly trauma.",
    "The harvest ends. {winner} survives. The chickens continue not caring.",
    "{winner} wins. Grandpappy's turning in his grave. From disappointment, not pride.",
    "Well, {winner} won by not dying. Truly, a high bar for success.",
    "{winner} is the last one breathing. Participation trophy for everyone else. Posthumously.",
    "Congratulations {winner}. You're alive. That's... that's about it.",
    "{winner} wins. The chickens are updating their records. 'Least likely to succeed.'",
    "Well, {winner} survived. Against all odds, logic, and agricultural wisdom.",
    "{winner} takes the pot and walks away. The pigs shake their heads.",
    "Only {winner} remains. Everyone else is fertilizer. Circle of life.",
    "{winner} wins! The cows don't care. The pigs don't care. Nobody cares. Congrats.",
    "Well, would you look at that. {winner} actually made it. Someone buy them a lottery ticket.",
    "{winner} is victorious. By default. Because everyone else died. What a legacy.",
    "The last one standing: {winner}. The bar was on the ground and they tripped over it.",
    "{winner} survived. The scarecrow is proud. The scarecrow is still inanimate. Moving on.",
    "Against all sense and reason, {winner} walks away. With money. And nightmares.",
    "{winner} wins the pot. Now they can finally buy that therapy horse they'll need.",
    "Well, {winner} beat the odds. And by 'beat' I mean 'got lucky.' Real lucky.",
    "{winner} takes it all. The goats are judging. They're always judging.",
    "Only {winner} survives. Darwin's theory gets another data point.",
    "{winner} is the champion. Of what? Staying alive. The bar's real low.",
    "Congratulations {winner}. You didn't die. Here's your medal. It's imaginary.",
    "{winner} wins. The rooster crows. It's unrelated but it happened.",
    # MORE WINNER MESSAGES:
    "Well, {winner} wins by process of elimination. The process being: death.",
    "{winner} is the sole survivor. The sole being: dumb luck.",
    "Congratulations {winner}. You outlived idiots. Peak achievement.",
    "Well, {winner} takes it all. All being: money and regret.",
    "{winner} wins. The chickens are mildly surprised. Very mildly.",
    "Only {winner} remains vertical. Everyone else is horizontal. Permanently.",
    "Well, {winner} survived. The pigs are updating their insurance policies.",
    "{winner} wins the pot. The pot being: full of blood money.",
    "Congratulations {winner}. You beat death. Death's requesting a rematch.",
    "Well, {winner} is victorious. Victorious being: not dead.",
    "{winner} survives. The farm's IQ remains stable. Low, but stable.",
    "Only {winner} walks away. Everyone else is carried. In coffins.",
    "Well, {winner} wins. The goats are reconsidering their life choices.",
    "{winner} takes the prize. The prize being: haunted money.",
    "Congratulations {winner}. You're the last fool standing.",
    "Well, {winner} survived. Against all odds and basic probability.",
    "{winner} wins. The cows moo approvingly. It's unrelated.",
    "Only {winner} remains breathing. Breathing being: underrated.",
    "Well, {winner} is victorious. The scarecrow claps. It's the wind.",
    "{winner} survives. The chickens revise their predictions. Again.",
    "Congratulations {winner}. You won at not dying. Low bar, but you cleared it.",
    "Well, {winner} takes it all. All being: the money everyone else left behind.",
    "{winner} wins. The rooster crows in celebration. Or just crows. Hard to tell.",
    "Only {winner} stands. Everyone else is lying down. Six feet down.",
    "Well, {winner} survived. The pigs are impressed. The pigs are easily impressed.",
    "{winner} is victorious. The victory being: pyrrhic at best.",
    "Congratulations {winner}. You beat the odds. The odds are filing an appeal.",
    "Well, {winner} wins. The barn owl hoots. It's judgmental hooting.",
    "{winner} survives. The farm continues. Both barely.",
    "Only {winner} walks away clean. Clean being: relatively.",
]

HORROR_DEATH_MESSAGES = [
    "The screen cuts to black on {victim}. Roll credits.",
    "{victim} is the opening kill. Classic horror trope.",
    "The monster gets {victim}. No final scream, just silence.",
    "Blood spells {victim}'s name on the wall.",
    "The killer smiles. {victim} doesn't. Can't.",
    "The last door slams shut on {victim}. Forever.",
    "Level {level} and still no final girl energy. RIP {victim}.",
    "{victim} made it to level {level} and still died in act one.",
    "The credits would roll for {victim} but nobody's left to watch.",
    "{victim} vanishes into the dark. No one finds the body.",
    "Jump scare! {victim} is dead. The audience knew it was coming.",
    "The basement claimed another victim: {victim}.",
    "Don't go in there, they said. {victim} went anyway.",
    "The music swells. {victim} falls. Popcorn spills.",
    "The phone rings. {victim} doesn't answer. Because dead.",
    "The mirror cracks. {victim}'s reflection doesn't move. Neither do they.",
    "The doll blinks. {victim} stops breathing.",
    "Seven days, the tape said. For {victim}? Seven seconds.",
    "The closet opens. {victim} should have stayed in bed.",
    "The seance went wrong. {victim} is the proof.",
    "The fog hides many things. {victim}'s corpse is one of them.",
    "The asylum claims {victim}. They're part of the walls now.",
    "The ritual required a sacrifice. {victim} volunteered. Accidentally.",
    "The entity is sated. {victim} is the reason why.",
    "Horror movie rules: don't split up. Don't go alone. Don't be {victim}.",
]

HORROR_SURVIVAL_MESSAGES = [
    "The monster misses. {player} survives another scene.",
    "{player} lives. The soundtrack spikes anyway.",
    "{player} makes it to the next act. Barely.",
    "Plot armor flickers to life. {player} survives.",
    "{player} escapes the jump scare with a racing heart.",
    "{player} survives. The killer is visibly annoyed.",
    "{player} finds the exit. It's locked, but they're alive.",
    "The lights flicker back on. {player} is still breathing.",
    "{player} hides in the closet. The monster passes by.",
    "The phone rings. {player} doesn't answer. Smart.",
    "{player} checks the backseat. It's empty. This time.",
    "Final girl energy: {player} has it.",
]

HORROR_WINNER_MESSAGES = [
    "Final survivor: {winner}. Fade to black.",
    "{winner} lives. The sequel is greenlit.",
    "{winner} makes it out. Everyone else is credits.",
    "{winner} stands alone in the last frame. Traumatized but alive.",
    "{winner} wins the pot and lifelong PTSD.",
    "The killer is gone. {winner} remains. For now.",
    "Congratulations {winner}, you survived the horror. Therapy recommended.",
    "Only {winner} walks out of the house. The rest stay inside. Forever.",
]

DETECTIVE_DEATH_MESSAGES = [
    "Case closed: {victim}. Cause of death: stupidity.",
    "{victim} becomes Exhibit A in the morgue.",
    "The culprit is chance. The victim is {victim}.",
    "Ballistics confirm: {victim} is DOA.",
    "The file on {victim} is stamped CLOSED.",
    "The coroner writes {victim}'s name with a sigh.",
    "Level {level} and still no alibi. {victim} is out cold.",
    "{victim} reaches level {level} and still gets solved. By death.",
    "Evidence bag sealed: one corpse, formerly {victim}.",
    "The investigation ends in crimson for {victim}.",
    "The detective's notepad reads: '{victim} - deceased, predictably.'",
    "Motive: stupidity. Means: revolver. Opportunity: now. Victim: {victim}.",
    "The crime scene photographer focuses on {victim}. Last photo.",
    "The autopsy reveals what we all knew: {victim} died from being an idiot.",
    "The witness statement: '{victim} had it coming.'",
    "Elementary, Watson. {victim} fucked up.",
    "The magnifying glass reveals {victim}'s final mistake.",
    "Clue found: {victim}'s corpse. Investigation complete.",
    "The murder board updates: {victim} - DECEASED.",
    "Fingerprints on the trigger: {victim}'s. Case closed.",
    "The detective lights a cigarette over {victim}'s body. 'Shame.'",
    "The red string on the conspiracy board leads to {victim}'s grave.",
    "The last piece of evidence: {victim}'s death certificate.",
    "The cold case files gain one more: {victim}.",
    "Sherlock deduces {victim} is dead. Not his hardest case.",
]

DETECTIVE_SURVIVAL_MESSAGES = [
    "{player} dodges the bullet that would've closed the case.",
    "The investigation stays open. {player} still breathing.",
    "{player} finds the loophole. It's called 'luck.'",
    "Alibi confirmed: {player} is alive.",
    "{player} slips past the detective's gaze. And death's.",
    "The evidence clears {player}. For now.",
    "The detective in charge keeps {player}'s file open.",
    "{player} survives the interrogation. And the bullet.",
    "No case to close. {player} lives.",
    "The smoking gun misfires. {player} walks.",
    "{player} is still a person of interest. Alive interest.",
    "The witness describes {player} as 'lucky bastard.'",
]

DETECTIVE_WINNER_MESSAGES = [
    "{winner} solves the case: everyone else died.",
    "Only {winner} remains. Case permanently closed for the rest.",
    "{winner} walks out of the precinct with the pot.",
    "The culprit is fate. The survivor is {winner}.",
    "{winner} wins. The city can sleep now.",
    "Final report filed: {winner} survived. Everyone else didn't.",
    "The detective closes the notebook. '{winner}. Lucky.'",
    "In the end, only {winner} walks away from the scene.",
]

PIRATE_DEATH_MESSAGES = [
    "Davy Jones claims {victim}. The locker is full.",
    "{victim} walks the plank for the last time.",
    "The sea takes {victim}. No survivors, no refunds.",
    "The Jolly Roger flies at half-mast for {victim}. Just kidding.",
    "The crew marks {victim} as lost at sea. And lost to stupidity.",
    "The cannon roars. {victim} becomes part of the debris.",
    "Level {level} pirate, sunk by fate. {victim} goes down.",
    "{victim} hit level {level} and still got keelhauled by RNG.",
    "Davy Jones' locker opens wide for {victim}.",
    "The tide goes out. {victim} does not return.",
    "X marks the spot where {victim} fell. It's underwater now.",
    "The kraken had nothing to do with this. {victim} managed alone.",
    "Buried treasure stays buried. So does {victim}.",
    "{victim} gets their sea legs. And sea death.",
    "The parrot squawks: '{victim} is dead! Dead!'",
    "The first mate logs it: '{victim} - lost to idiocy.'",
    "The crew divides {victim}'s share. It's not much.",
    "Walk the plank, they said. {victim} ran.",
    "The cutlass is clean. The chamber is not. {victim} chose wrong.",
    "Sailor's superstition: don't play Russian roulette. {victim} disagrees. Disagreed.",
    "The ship's bell tolls for {victim}. Eight bells. Game over.",
    "The barnacles will claim {victim}'s bones.",
    "Rum won't save you, {victim}. Neither will prayer.",
    "Yo ho ho and a corpse named {victim}.",
    "Dead men tell no tales. {victim} won't either.",
]

PIRATE_SURVIVAL_MESSAGES = [
    "{player} stays afloat. The sea is patient.",
    "{player} dodges the broadside and keeps their teeth.",
    "{player} keeps their head above water. Barely.",
    "The kraken misses. {player} celebrates with rum.",
    "{player} lives to spend the booty another day.",
    "{player} slips past Davy Jones. Not today.",
    "{player} keeps their treasure. And their pulse.",
    "{player} survives. The rum ration is safe.",
    "The plank holds. {player} walks back to the deck.",
    "The compass spins. {player} finds north. And survival.",
    "{player} cheats death and the hangman both.",
    "The sea spares {player}. It's feeling generous.",
]

PIRATE_WINNER_MESSAGES = [
    "{winner} takes the treasure, the title, and the ship.",
    "Only {winner} sails away into legend.",
    "{winner} wins the pot and captaincy.",
    "The crew cheers. {winner} is the last pirate standing.",
    "{winner} keeps the booty. The rest sleep with the fishes.",
    "Captain {winner} stands alone at the helm. Victory is theirs.",
    "{winner} claims it all. The seven seas bow.",
    "The pirate's code is clear: {winner} wins, everyone else dies.",
]

DARK_ROUND_START = [
    "Chamber reloaded. Next player is up.",
    "Another round. Another click.",
    "The cylinder resets. The room holds its breath.",
]

ARCADE_ROUND_START = [
    "New round. Insert coin.",
    "Stage select: Death.",
    "Cabinet hums. The next round loads.",
    "Ready? Fight. Or die.",
    "Round start. No tutorials.",
]

GREEK_ROUND_START = [
    "The Fates spin again. New round.",
    "The gods watch. The cylinder turns.",
    "Another trial begins under Olympus.",
    "The Styx runs cold. The next pull starts.",
    "Fate resets the chamber.",
]

NORSE_ROUND_START = [
    "The runes are cast. New round.",
    "The horn sounds. The cylinder turns.",
    "Another verse in the saga begins.",
    "Steel turns. Fate turns.",
    "The next pull starts under a cold sky.",
]

FARMER_ROUND_START = [
    "New round. Time to reap.",
    "The field turns. The chamber turns.",
    "Another harvest begins.",
    "The scythe is sharpened. The round starts.",
    "Sun's up. Somebody's not making sundown.",
]

SARCASTIC_FARMER_ROUND_START = [
    "New round. Y'all ready to make more questionable life choices?",
    "Here we go again. The chickens are watching. Judging.",
    "Another round of 'who's the biggest idiot?' Results pending.",
    "The chamber's loaded. So are y'all, probably.",
    "Round whatever-number-we're-on. The cows have stopped watching.",
    "New round, same stupidity. At least you're consistent.",
    "The wheel turns. Darwin smiles. Y'all frown. Or die.",
    "Well, let's get this over with. The chores ain't gonna do themselves.",
    "New round! Who's ready for more bad decisions? Everyone? Great.",
    "Round starts now. The chickens have already placed their bets.",
    "Here we go. Again. The definition of insanity, right here.",
    "Another round. The pigs are watching. With disappointment.",
    "New round, new chances to die stupidly. How exciting.",
    "The chamber spins. So does my head from all this stupidity.",
    "Round start. The cows have left. They can't watch this anymore.",
    "Well, back at it. The scarecrow's still here. More than I can say for some of y'all soon.",
    "New round! The rooster's crowing. It's not encouragement. It's a warning.",
    "Here we go again. Like a country song, but dumber.",
    # MORE ROUND START:
    "Another round. The goats have seen enough.",
    "New round. The pigs are stress-eating.",
    "Round starts. The barn owl's taken leave.",
    "Well, here we go. The chickens are praying. Chickens don't pray.",
    "Another round. The hay bale's more excited than I am.",
    "New round. The tractor's more reliable than y'all's judgment.",
    "Round starts. The cows are filing complaints.",
    "Well, back to it. The mule's shaking its head.",
    "Another round. The fence posts are embarrassed for you.",
    "New round. The rooster's having second thoughts.",
]
HORROR_ROUND_START = [
    "New scene. The lights flicker.",
    "The door creaks. The round begins.",
    "Another act starts. Nobody's safe.",
    "The camera pans. The gun comes up.",
    "Silence. Then the next pull.",
]

DETECTIVE_ROUND_START = [
    "New case file. New round.",
    "The suspect list resets. The gun doesn't.",
    "Another clue drops. The cylinder spins.",
    "The investigation continues.",
    "Round start. Evidence pending.",
]

PIRATE_ROUND_START = [
    "New round. Hoist the black.",
    "The tide turns. The cylinder turns.",
    "Another spin o' the wheel, matey.",
    "Round start. Brace for broadside.",
    "The deck goes quiet. The gun goes up.",
]

THEME_SURVIVAL = {
    "dark": DARK_SURVIVAL_MESSAGES,
    "noir": NOIR_SURVIVAL_MESSAGES,
    "western": WESTERN_SURVIVAL_MESSAGES,
    "wasteland": WASTELAND_SURVIVAL_MESSAGES,
    "mafia": MAFIA_SURVIVAL_MESSAGES,
    "medieval": MEDIEVAL_SURVIVAL_MESSAGES,
    "arcade": ARCADE_SURVIVAL_MESSAGES,
    "greek": GREEK_SURVIVAL_MESSAGES,
    "norse": NORSE_SURVIVAL_MESSAGES,
    "farmer": FARMER_SURVIVAL_MESSAGES,
    "sarcastic_farmer": SARCASTIC_FARMER_SURVIVAL_MESSAGES,
    "horror": HORROR_SURVIVAL_MESSAGES,
    "detective": DETECTIVE_SURVIVAL_MESSAGES,
    "pirate": PIRATE_SURVIVAL_MESSAGES,
}
THEME_DEATH = {
    "dark": DARK_DEATH_MESSAGES,
    "noir": NOIR_DEATH_MESSAGES,
    "western": WESTERN_DEATH_MESSAGES,
    "wasteland": WASTELAND_DEATH_MESSAGES,
    "mafia": MAFIA_DEATH_MESSAGES,
    "medieval": MEDIEVAL_DEATH_MESSAGES,
    "arcade": ARCADE_DEATH_MESSAGES,
    "greek": GREEK_DEATH_MESSAGES,
    "norse": NORSE_DEATH_MESSAGES,
    "farmer": FARMER_DEATH_MESSAGES,
    "sarcastic_farmer": SARCASTIC_FARMER_DEATH_MESSAGES,
    "horror": HORROR_DEATH_MESSAGES,
    "detective": DETECTIVE_DEATH_MESSAGES,
    "pirate": PIRATE_DEATH_MESSAGES,
}
THEME_WINNER = {
    "dark": DARK_WINNER_MESSAGES,
    "noir": NOIR_WINNER_MESSAGES,
    "western": WESTERN_WINNER_MESSAGES,
    "wasteland": WASTELAND_WINNER_MESSAGES,
    "mafia": MAFIA_WINNER_MESSAGES,
    "medieval": MEDIEVAL_WINNER_MESSAGES,
    "arcade": ARCADE_WINNER_MESSAGES,
    "greek": GREEK_WINNER_MESSAGES,
    "norse": NORSE_WINNER_MESSAGES,
    "farmer": FARMER_WINNER_MESSAGES,
    "sarcastic_farmer": SARCASTIC_FARMER_WINNER_MESSAGES,
    "horror": HORROR_WINNER_MESSAGES,
    "detective": DETECTIVE_WINNER_MESSAGES,
    "pirate": PIRATE_WINNER_MESSAGES,
}

ALL_SURVIVAL: list[str] = [line for lines in THEME_SURVIVAL.values() for line in lines]
ALL_DEATH: list[str] = [line for lines in THEME_DEATH.values() for line in lines]
ALL_WINNER: list[str] = [line for lines in THEME_WINNER.values() for line in lines]
THEME_SURVIVAL["mixed"] = ALL_SURVIVAL
THEME_DEATH["mixed"] = ALL_DEATH
THEME_WINNER["mixed"] = ALL_WINNER
THEME_SURVIVAL["gallows"] = THEME_SURVIVAL["western"]
THEME_DEATH["gallows"] = THEME_DEATH["western"]
THEME_WINNER["gallows"] = THEME_WINNER["western"]

THEME_ROUND_START = {
    "dark": DARK_ROUND_START,
    "noir": NOIR_ROUND_START,
    "western": WESTERN_ROUND_START,
    "arcade": ARCADE_ROUND_START,
    "greek": GREEK_ROUND_START,
    "norse": NORSE_ROUND_START,
    "farmer": FARMER_ROUND_START,
    "sarcastic_farmer": SARCASTIC_FARMER_ROUND_START,
    "horror": HORROR_ROUND_START,
    "detective": DETECTIVE_ROUND_START,
    "pirate": PIRATE_ROUND_START,
}
ALL_ROUND_START: list[str] = [line for lines in THEME_ROUND_START.values() for line in lines]
THEME_ROUND_START["mixed"] = ALL_ROUND_START
THEME_ROUND_START["gallows"] = THEME_ROUND_START["western"]

BAR_BRAWL_WEAPONS = [
    "bar stool",
    "pool cue",
    "beer bottle",
    "broken bottle",
    "cash register",
    "neon sign",
    "jukebox remote",
    "cue rack",
    "ashtray",
    "bar chair",
    "keg",
    "mop handle",
]


@dataclass
class RRSettings:
    join_timeout: int = 120
    min_players: int = 2
    max_players: int = 0
    fast_mode: bool = False
    show_status: bool = False
    announce_round: bool = True
    spin_mode: str = "fixed"
    allow_double_down: bool = False
    allow_pass_on_double_down: bool = False
    allow_taunts: bool = False
    theme: str = "dark"
    gif_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    victory_recap: bool = False
    allow_start_early: bool = False
    turn_timeout: int = 15
    sudden_death_after: int = 0
    sudden_death_bullets: int = 2
    mercy_chance: float = 0.0
    silent_rounds: bool = False
    drama_multiplier: float = 1.0
    chaos_events: bool = False
    chaos_chance: float = 0.0
    duel_mode: bool = False
    allow_last_shot: bool = True
    brawl_on_misfire: bool = False


class Game:
    def __init__(self, host_id: int, settings: RRSettings, bet: int):
        self.host_id = host_id
        self.settings = settings
        self.bet = bet
        self.participants: list[discord.User] = []
        self.joined_players: set[int] = set()
        self.roundnum = 1
        self.bettotal = 0
        self.is_game_running = False
        self.gamestarted = False
        self.lobby_open = True
        self.lobby_message: Optional[discord.Message] = None
        self.lobby_view: Optional[View] = None
        self.join_lock = asyncio.Lock()
        self.chambers: list[bool] = []
        self.current_index = 0
        self.pass_next_turn: set[int] = set()
        self.stats: dict[int, dict[str, int]] = {}
        self.started_early = False
        self.turn_order: list[discord.User] = []
        self.deaths = 0
        self.temp_bullets = 0
        self.temp_bullets_uses = 0
        self.levels: dict[int, int] = {}

    def reset_chambers(self, bullets: int):
        bullets = max(1, min(5, bullets))
        self.chambers = [False] * (6 - bullets) + [True] * bullets
        random.shuffle(self.chambers)


class TurnDecisionView(View):
    def __init__(self, player_id: int, show_pull: bool, timeout: int):
        super().__init__(timeout=timeout)
        self.player_id = player_id
        self.choice = "pull"

        if show_pull:
            pull_button = Button(label="Shoot", style=discord.ButtonStyle.danger)
            pull_button.callback = self._choose_pull
            self.add_item(pull_button)

        double_button = Button(label="Double Down", style=discord.ButtonStyle.secondary)
        double_button.callback = self._choose_double
        self.add_item(double_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.player_id:
            return True
        await interaction.response.send_message("It's not your turn.", ephemeral=True)
        return False

    async def _choose_pull(self, interaction: discord.Interaction):
        self.choice = "pull"
        await interaction.response.send_message("You pull the trigger...", ephemeral=True)
        self.stop()

    async def _choose_double(self, interaction: discord.Interaction):
        self.choice = "double"
        await interaction.response.send_message("Double down locked in.", ephemeral=True)
        self.stop()


class RussianJoinView(View):
    def __init__(self, cog: "Russian", game: Game, host_id: int):
        super().__init__(timeout=game.settings.join_timeout)
        self.cog = cog
        self.game = game
        self.host_id = host_id
        self.message: Optional[discord.Message] = None

        join_button = Button(label="Join Roulette", style=discord.ButtonStyle.success)
        join_button.callback = self._handle_join
        self.add_item(join_button)

        if game.settings.allow_start_early:
            start_button = Button(label="Start Early", style=discord.ButtonStyle.primary)
            start_button.callback = self._handle_start
            self.add_item(start_button)

    async def _handle_join(self, interaction: discord.Interaction):
        if interaction.user is None:
            return
        error = await self.cog.try_join_lobby(self.game, interaction.user)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.send_message("You joined the roulette!", ephemeral=True)

    async def _handle_start(self, interaction: discord.Interaction):
        if interaction.user is None:
            return
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("Only the host can start early.", ephemeral=True)
            return
        if len(self.game.participants) < self.game.settings.min_players:
            await interaction.response.send_message(
                "Not enough players to start yet.", ephemeral=True
            )
            return
        self.game.started_early = True
        self.game.lobby_open = False
        await interaction.response.send_message("Starting early!", ephemeral=True)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.game.lobby_open = False
        if self.message:
            await self.message.edit(view=self)


class Russian(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, Game] = {}
        self._message_cycles: dict[str, dict[str, list[str]]] = {}
        self._settings_lock = threading.Lock()
        self._settings: dict[str, dict] = self.load_settings()
        self._settings_store_ready = False

    async def cog_load(self):
        await self._initialize_settings_store()

    async def _initialize_settings_store(self) -> None:
        # Keep file-based settings as fallback, but migrate to DB-backed storage
        # so settings survive process restarts and multi-instance deployments.
        if not hasattr(self.bot, "pool"):
            return
        try:
            await self._ensure_settings_table()
            db_settings = await self._load_settings_from_db()
            merged = {**self._settings, **db_settings}
            self._settings = merged
            await self._bulk_upsert_settings_to_db(merged)
            self._settings_store_ready = True
            self.save_settings()
        except Exception:
            self._settings_store_ready = False

    @contextlib.contextmanager
    def _settings_file_lock(self, timeout: float = 2.0):
        lock_path = SETTINGS_FILE.with_suffix(SETTINGS_FILE.suffix + ".lock")
        lock_file = lock_path.open("a+")
        start = time.monotonic()
        msvcrt = None
        fcntl = None
        try:
            try:
                import msvcrt as _msvcrt  # type: ignore
                msvcrt = _msvcrt
            except ImportError:
                msvcrt = None
            if msvcrt is None:
                try:
                    import fcntl as _fcntl  # type: ignore
                    fcntl = _fcntl
                except ImportError:
                    fcntl = None

            while True:
                try:
                    if msvcrt is not None:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    elif fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (OSError, BlockingIOError):
                    if time.monotonic() - start > timeout:
                        break
                    time.sleep(0.05)
            yield
        finally:
            try:
                if msvcrt is not None:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            lock_file.close()

    def load_settings(self) -> dict[str, dict]:
        if not SETTINGS_FILE.exists():
            return {}
        with self._settings_lock, self._settings_file_lock():
            try:
                payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return payload if isinstance(payload, dict) else {}

    def save_settings(self):
        with self._settings_lock, self._settings_file_lock():
            existing: dict[str, dict] = {}
            if SETTINGS_FILE.exists():
                try:
                    payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        existing = payload
                except (json.JSONDecodeError, OSError):
                    existing = {}
            merged = {**existing, **self._settings}
            payload = json.dumps(merged, indent=2, sort_keys=True)
            tmp_path = SETTINGS_FILE.with_suffix(".tmp")
            tmp_path.write_text(payload, encoding="utf-8")
            tmp_path.replace(SETTINGS_FILE)

    async def _ensure_settings_table(self) -> None:
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE} (
                    user_id BIGINT PRIMARY KEY,
                    settings JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    async def _load_settings_from_db(self) -> dict[str, dict]:
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT user_id, settings FROM {SETTINGS_TABLE};")

        loaded: dict[str, dict] = {}
        for row in rows:
            raw = row.get("settings")
            parsed: dict = {}
            if isinstance(raw, dict):
                parsed = raw
            elif isinstance(raw, str):
                try:
                    decoded = json.loads(raw)
                    if isinstance(decoded, dict):
                        parsed = decoded
                except json.JSONDecodeError:
                    parsed = {}
            loaded[str(row["user_id"])] = parsed
        return loaded

    async def _upsert_settings_to_db(self, user_id: int, settings: dict) -> None:
        if not hasattr(self.bot, "pool"):
            return
        payload = json.dumps(settings)
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {SETTINGS_TABLE} (user_id, settings, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW();
                """,
                user_id,
                payload,
            )

    async def _bulk_upsert_settings_to_db(self, settings_by_user: dict[str, dict]) -> None:
        if not hasattr(self.bot, "pool") or not settings_by_user:
            return
        records: list[tuple[int, str]] = []
        for user_id, settings in settings_by_user.items():
            try:
                parsed_user_id = int(user_id)
            except (TypeError, ValueError):
                continue
            records.append((parsed_user_id, json.dumps(settings)))
        if not records:
            return
        async with self.bot.pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {SETTINGS_TABLE} (user_id, settings, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW();
                """,
                records,
            )

    def get_user_settings(self, user_id: int) -> RRSettings:
        defaults = asdict(RRSettings())
        raw = self._settings.get(str(user_id), {})

        if "spin_mode" not in raw and "spin_each_turn" in raw:
            raw = {**raw, "spin_mode": "spin_each_pull" if raw["spin_each_turn"] else "fixed"}
        if "victory_recap" not in raw and "allow_summary" in raw:
            raw = {**raw, "victory_recap": raw["allow_summary"]}

        merged = {**defaults, **{k: raw.get(k, defaults[k]) for k in defaults}}

        def clamp_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return fallback
            return max(minimum, min(maximum, parsed))

        def clamp_float(value: object, minimum: float, maximum: float, fallback: float) -> float:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return fallback
            return max(minimum, min(maximum, parsed))

        merged["join_timeout"] = clamp_int(
            merged["join_timeout"], 30, 600, defaults["join_timeout"]
        )
        merged["min_players"] = clamp_int(merged["min_players"], 2, 20, defaults["min_players"])
        merged["max_players"] = clamp_int(merged["max_players"], 0, 50, defaults["max_players"])
        if merged["max_players"] == 1:
            merged["max_players"] = 2
        if merged["max_players"] and merged["min_players"] > merged["max_players"]:
            merged["min_players"] = merged["max_players"]
        merged["turn_timeout"] = clamp_int(merged["turn_timeout"], 5, 60, defaults["turn_timeout"])
        merged["sudden_death_after"] = clamp_int(
            merged["sudden_death_after"], 0, 50, defaults["sudden_death_after"]
        )
        merged["sudden_death_bullets"] = clamp_int(
            merged["sudden_death_bullets"], 1, 5, defaults["sudden_death_bullets"]
        )
        merged["mercy_chance"] = clamp_float(
            merged["mercy_chance"], 0.0, 0.5, defaults["mercy_chance"]
        )
        merged["chaos_chance"] = clamp_float(
            merged["chaos_chance"], 0.0, 0.5, defaults["chaos_chance"]
        )
        merged["drama_multiplier"] = clamp_float(
            merged["drama_multiplier"], 0.2, 3.0, defaults["drama_multiplier"]
        )

        if merged["spin_mode"] not in {"fixed", "spin_each_pull", "spin_each_turn"}:
            merged["spin_mode"] = "fixed"
        merged["theme"] = self.normalize_theme(str(merged["theme"]))
        merged["gif_overrides"] = self.normalize_gif_overrides(merged.get("gif_overrides"))

        return RRSettings(**merged)

    async def set_user_settings(self, user_id: int, settings: RRSettings):
        self._settings[str(user_id)] = asdict(settings)
        self.save_settings()
        try:
            await self._upsert_settings_to_db(user_id, asdict(settings))
        except Exception:
            # File storage still keeps settings if DB write fails.
            pass

    def ensure_stats(self, game: Game, user_id: int):
        if user_id not in game.stats:
            game.stats[user_id] = {
                "shots": 0,
                "survived": 0,
                "double_downs": 0,
                "passes": 0,
                "kills": 0,
            }

    async def update_lobby_message(self, game: Game):
        if game.lobby_message is None:
            return
        embed = self.build_lobby_embed(game)
        if game.lobby_view is not None:
            await game.lobby_message.edit(embed=embed, view=game.lobby_view)
        else:
            await game.lobby_message.edit(embed=embed)

    async def try_join_lobby(self, game: Game, user: discord.User) -> Optional[str]:
        async with game.join_lock:
            if game.is_game_running:
                return "The game already started."
            if not game.lobby_open:
                return "The lobby is closed."
            if user.id in game.joined_players:
                return "You already joined."
            if game.settings.max_players and len(game.participants) >= game.settings.max_players:
                return "The lobby is full."

            if game.bet > 0:
                ok = await self.charge_entry(user.id, game.bet)
                if not ok:
                    return "You don't have enough money."
                game.bettotal += game.bet

            game.participants.append(user)
            game.joined_players.add(user.id)
            self.ensure_stats(game, user.id)
            await self.update_lobby_message(game)
            return None

    async def load_levels(self, game: Game):
        if not game.participants:
            return
        user_ids = [p.id for p in game.participants]
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT "user", "xp" FROM profile WHERE "user" = ANY($1);',
                user_ids,
            )
        levels: dict[int, int] = {}
        for row in rows:
            levels[row["user"]] = rpgtools.xptolevel(row.get("xp", 0))
        for user_id in user_ids:
            if user_id not in levels:
                levels[user_id] = 0
        game.levels = levels

    def build_lobby_embed(self, game: Game) -> discord.Embed:
        pot = f"${game.bettotal}" if game.bet > 0 else "No bet"
        entry = f"${game.bet}" if game.bet > 0 else "Free"
        cap = f"/ {game.settings.max_players}" if game.settings.max_players else ""
        mode_label = {
            "fixed": "Fixed chamber",
            "spin_each_pull": "Spin each pull",
            "spin_each_turn": "Spin each turn",
        }.get(game.settings.spin_mode, game.settings.spin_mode)
        taunts_label = "On" if game.settings.allow_taunts else "Off"
        theme_label = game.settings.theme if game.settings.allow_taunts else "Off"
        double_label = "On" if game.settings.allow_double_down else "Off"

        embed = discord.Embed(
            title="Russian Roulette Lobby",
            color=discord.Color.dark_red(),
            description=(
                "One bullet. Six chambers. No mercy.\n"
                f"Lobby closes in **{game.settings.join_timeout}s**."
            ),
        )
        embed.add_field(
            name="Price",
            value=f"Entry: **{entry}**\nPot: **{pot}**",
            inline=True,
        )
        embed.add_field(
            name="Settings",
            value=(
                f"Players: **{len(game.participants)}{cap}** (min **{game.settings.min_players}**)\n"
                f"Spin: **{mode_label}**\n"
                f"Double Down: **{double_label}**\n"
                f"Taunts: **{taunts_label}** | Theme: **{theme_label}**"
            ),
            inline=False,
        )
        embed.set_image(url="https://c.tenor.com/SMl9YoM-OEsAAAAC/tenor.gif")
        footer = "Click Join Roulette to play."
        if game.settings.allow_start_early:
            footer += " Host can start early."
        embed.set_footer(text=footer)
        return embed

    def build_status_embed(self, game: Game) -> discord.Embed:
        if game.settings.allow_taunts and not game.settings.silent_rounds:
            description = self.choose_round_start_message(game.settings)
        else:
            description = (
                "Surviving players automatically move to the next round. "
                "Round will start in 5 seconds.."
            )
        embed = discord.Embed(
            title=f"Round {game.roundnum}",
            color=discord.Color.green(),
            description=description,
        )
        embed.set_image(url=self.get_gif_url(game.settings, "round_start"))
        pot = f"${game.bettotal}" if game.bet > 0 else "No bet"
        embed.add_field(name="Players left", value=str(len(game.turn_order)), inline=True)
        embed.add_field(name="Pot", value=pot, inline=True)
        mode_label = {
            "fixed": "Fixed chamber",
            "spin_each_pull": "Spin each pull",
            "spin_each_turn": "Spin each turn",
        }.get(game.settings.spin_mode, game.settings.spin_mode)
        embed.add_field(
            name="Mode",
            value=mode_label,
            inline=True,
        )
        return embed

    async def announce_round(self, ctx, game: Game):
        if not game.settings.announce_round or game.settings.silent_rounds:
            return
        if game.settings.allow_taunts and not game.settings.silent_rounds:
            description = self.choose_round_start_message(game.settings)
        else:
            description = (
                "Surviving players automatically move to the next round. "
                "Round will start in 5 seconds.."
            )
        embed = discord.Embed(
            title=f"Round {game.roundnum}",
            description=description,
            color=discord.Color.green(),
        )
        embed.set_image(url=self.get_gif_url(game.settings, "round_start"))
        await ctx.send(embed=embed)

    def build_summary_embed(self, game: Game, winner: discord.User, initial_count: int) -> discord.Embed:
        embed = discord.Embed(title="Russian Roulette Results", color=discord.Color.gold())
        embed.add_field(name="Winner", value=winner.mention, inline=False)
        embed.add_field(name="Players", value=str(initial_count), inline=True)
        if game.bet > 0:
            embed.add_field(name="Pot", value=f"${game.bettotal}", inline=True)
        stats_lines = []
        for user in game.participants:
            data = game.stats.get(user.id, {})
            stats_lines.append(
                f"{user.display_name}: shots {data.get('shots', 0)}, survived {data.get('survived', 0)}, "
                f"double downs {data.get('double_downs', 0)}, passes {data.get('passes', 0)}, "
                f"kills {data.get('kills', 0)}"
            )
        if stats_lines:
            output_lines = []
            current_len = 0
            for line in stats_lines:
                extra = len(line) + (1 if output_lines else 0)
                if current_len + extra > 1000:
                    break
                output_lines.append(line)
                current_len += extra
            remaining = len(stats_lines) - len(output_lines)
            if remaining > 0:
                suffix = f"...and {remaining} more."
                extra = len(suffix) + (1 if output_lines else 0)
                if current_len + extra > 1000 and output_lines:
                    removed = output_lines.pop()
                    current_len -= len(removed) + (1 if output_lines else 0)
                if current_len + len(suffix) + (1 if output_lines else 0) <= 1000:
                    output_lines.append(suffix)
            embed.add_field(name="Stats", value="\n".join(output_lines), inline=False)
        return embed

    def build_gif_settings_embed(self, settings: RRSettings, theme: str) -> discord.Embed:
        overrides = settings.gif_overrides if isinstance(settings.gif_overrides, dict) else {}
        theme_overrides = overrides.get(theme, {}) if isinstance(overrides, dict) else {}
        embed = discord.Embed(title="Russian Roulette GIFs", color=discord.Color.blue())
        embed.description = f"Theme: **{theme}**"
        for slot, label in GIF_SLOT_LABELS.items():
            custom = ""
            if isinstance(theme_overrides, dict):
                custom = theme_overrides.get(slot, "")
            if custom:
                value = f"Custom: {custom}"
            else:
                default_url = DEFAULT_GIFS.get(slot, "")
                value = f"Default: {default_url}" if default_url else "Default: (none)"
            embed.add_field(name=label, value=value, inline=False)
        embed.set_footer(
            text="Use rrgif set <theme> <slot> and send a Tenor URL. Use rrgif clear <theme> <slot>."
        )
        return embed

    @staticmethod
    def setting_descriptions() -> dict[str, str]:
        return {
            "join_timeout": "Lobby stays open (seconds).",
            "min_players": "Minimum players needed to start.",
            "max_players": "Lobby cap (0 = no cap).",
            "fast_mode": "Faster pacing; uses Shoot/Double Down buttons.",
            "show_status": "Show a round status embed each round.",
            "announce_round": "Show the round announcement embed when status is off.",
            "spin_mode": (
                "Chamber logic: fixed (same cylinder all round), "
                "spin_each_pull (RNG each pull), spin_each_turn (new cylinder each player)."
            ),
            "allow_double_down": "Allow Double Down: player takes two pulls on their turn.",
            "allow_pass_on_double_down": "If they survive Double Down, they skip their next turn.",
            "allow_taunts": "Enable flavor lines for turns, survives, deaths, and winner.",
            "theme": (
                "Flavor theme: dark, noir, western, wasteland, mafia, medieval, arcade, greek, "
                "norse, farmer, sarcastic_farmer, horror, detective, pirate, mixed."
            ),
            "victory_recap": "Show end-of-game stats for all players.",
            "allow_start_early": "Host can start before the lobby timer ends.",
            "turn_timeout": "Seconds to choose Double Down before auto-shoot.",
            "sudden_death_after": "Deaths before extra bullets start (0 = off).",
            "sudden_death_bullets": "Bullets used during sudden death (1-5).",
            "mercy_chance": "Chance a live round misfires and doesn't kill (0.0-0.5).",
            "silent_rounds": "Hide narration; show only results.",
            "drama_multiplier": "Scale all delays (0.2-3.0).",
            "chaos_events": "Enable random chaos events between rounds.",
            "chaos_chance": "Chance of chaos each round (0.0-0.5).",
            "duel_mode": "Special handling when only 2 players remain.",
            "allow_last_shot": "When 2 players remain, a 25% chance to shoot the other player.",
            "brawl_on_misfire": "If a 2-player targeted shot misfires, trigger a bar brawl to decide the winner.",
        }

    @staticmethod
    def parse_bool(value: str) -> Optional[bool]:
        value = value.strip().lower()
        if value in {"1", "true", "yes", "on", "enable", "enabled"}:
            return True
        if value in {"0", "false", "no", "off", "disable", "disabled"}:
            return False
        return None

    @staticmethod
    def parse_float(value: str) -> Optional[float]:
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def normalize_spin_mode(value: str) -> Optional[str]:
        value = value.strip().lower()
        if value in {"fixed"}:
            return "fixed"
        if value in {"spin_each_pull", "spin_pull", "spin_each_turn_pull"}:
            return "spin_each_pull"
        if value in {"spin_each_turn", "spin_turn"}:
            return "spin_each_turn"
        return None

    @staticmethod
    def normalize_theme(value: str) -> str:
        theme = value.strip().lower()
        if theme in {"sarcasticfarmer", "sarcastic-farmer"}:
            theme = "sarcastic_farmer"
        if theme == "gallows":
            theme = "western"
        if theme not in THEME_TAUNTS:
            return "dark"
        return theme

    def next_cycled_message(self, category: str, theme: str, pool: list[str], fallback: str) -> str:
        if not pool:
            return fallback
        cycles = self._message_cycles.setdefault(category, {})
        remaining = cycles.get(theme)
        if not remaining:
            remaining = list(pool)
            random.shuffle(remaining)
            cycles[theme] = remaining
        return remaining.pop()

    @staticmethod
    def normalize_gif_slot(value: str) -> Optional[str]:
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        return GIF_SLOT_ALIASES.get(key)

    @staticmethod
    def resolve_theme_key(value: str) -> Optional[str]:
        raw = value.strip().lower()
        if raw in {"sarcasticfarmer", "sarcastic-farmer"}:
            raw = "sarcastic_farmer"
        if raw == "gallows":
            return "western"
        if raw in THEME_TAUNTS:
            return raw
        return None

    def normalize_gif_overrides(
        self, raw: object
    ) -> dict[str, dict[str, str]]:
        if not isinstance(raw, dict):
            return {}
        cleaned: dict[str, dict[str, str]] = {}
        for theme_key, slots in raw.items():
            if not isinstance(theme_key, str) or not isinstance(slots, dict):
                continue
            resolved_theme = self.resolve_theme_key(theme_key)
            if not resolved_theme:
                continue
            theme_slots: dict[str, str] = {}
            for slot_key, url in slots.items():
                if not isinstance(slot_key, str) or not isinstance(url, str):
                    continue
                normalized_slot = self.normalize_gif_slot(slot_key)
                if not normalized_slot:
                    continue
                url = url.strip()
                if url:
                    theme_slots[normalized_slot] = url
            if theme_slots:
                cleaned[resolved_theme] = theme_slots
        return cleaned

    async def resolve_tenor_gif_url(self, tenor_url: str) -> Optional[str]:
        url = tenor_url.strip().strip("<>")
        if not url or "tenor.com" not in url:
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status >= 400:
                        return None
                    html = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

        match = re.search(r"https://media1\.tenor\.com/m/([^/]+)/", html)
        if not match:
            return None
        gif_id = match.group(1)
        return f"https://c.tenor.com/{gif_id}/tenor.gif"

    def get_gif_url(self, settings: RRSettings, slot: str) -> str:
        theme = self.normalize_theme(settings.theme)
        overrides = settings.gif_overrides if isinstance(settings.gif_overrides, dict) else {}
        theme_overrides = overrides.get(theme, {})
        if isinstance(theme_overrides, dict):
            override = theme_overrides.get(slot)
            if isinstance(override, str):
                override = override.strip()
                if override:
                    return override
        return DEFAULT_GIFS.get(slot, "")

    def choose_taunt(self, settings: RRSettings) -> str:
        theme = self.normalize_theme(settings.theme)
        pool = THEME_TAUNTS.get(theme, THEME_TAUNTS["dark"])
        return self.next_cycled_message("taunt", theme, pool, "The chamber waits.")

    def choose_round_start_message(self, settings: RRSettings) -> str:
        theme = self.normalize_theme(settings.theme)
        pool = THEME_ROUND_START.get(theme)
        if not pool:
            theme = "dark"
            pool = THEME_ROUND_START.get("dark", [])
        return self.next_cycled_message(
            "round_start", theme, pool, "Chamber reloaded. Next player is up."
        )

    def format_message(
        self,
        template: str,
        *,
        player: Optional[discord.User] = None,
        victim: Optional[discord.User] = None,
        winner: Optional[discord.User] = None,
        level: Optional[int] = None,
    ) -> str:
        return template.format(
            player=player.mention if player else "someone",
            victim=victim.mention if victim else "someone",
            winner=winner.mention if winner else "someone",
            level=level if level is not None else "0",
        )

    def choose_survival_message(self, settings: RRSettings, player: discord.User) -> str:
        theme = self.normalize_theme(settings.theme)
        pool = THEME_SURVIVAL.get(theme, THEME_SURVIVAL["dark"])
        return self.format_message(
            self.next_cycled_message("survival", theme, pool, "{player} survives."),
            player=player,
        )

    def choose_death_message(self, settings: RRSettings, victim: discord.User, level: int) -> str:
        theme = self.normalize_theme(settings.theme)
        pool = THEME_DEATH.get(theme, THEME_DEATH["dark"])
        return self.format_message(
            self.next_cycled_message("death", theme, pool, "{victim} has been shot!"),
            victim=victim,
            level=level,
        )

    def choose_winner_message(self, settings: RRSettings, winner: discord.User) -> str:
        theme = self.normalize_theme(settings.theme)
        pool = THEME_WINNER.get(theme, THEME_WINNER["dark"])
        return self.format_message(
            self.next_cycled_message("winner", theme, pool, "{winner} wins!"),
            winner=winner,
        )

    def get_bullet_count(self, game: Game) -> int:
        bullets = 1
        if game.settings.sudden_death_after and game.deaths >= game.settings.sudden_death_after:
            bullets = max(bullets, game.settings.sudden_death_bullets)
        if game.temp_bullets and game.temp_bullets_uses > 0:
            bullets = max(bullets, game.temp_bullets)
        return bullets

    def prepare_round(self, game: Game):
        if game.settings.spin_mode == "spin_each_pull":
            return
        bullets = self.get_bullet_count(game)
        game.reset_chambers(bullets)
        if game.temp_bullets_uses > 0:
            game.temp_bullets_uses -= 1
            if game.temp_bullets_uses <= 0:
                game.temp_bullets = 0

    async def maybe_apply_chaos(self, ctx, game: Game):
        if not game.settings.chaos_events or game.settings.chaos_chance <= 0:
            return
        if random.random() > game.settings.chaos_chance:
            return

        event = random.choice(["reverse", "skip_next", "extra_bullet"])
        if event == "reverse":
            game.turn_order.reverse()
            game.current_index = len(game.turn_order) - 1 - game.current_index
            if not game.settings.silent_rounds:
                await ctx.send("Chaos twist: turn order reverses.")
        elif event == "skip_next":
            if game.turn_order:
                next_player = game.turn_order[game.current_index]
                game.pass_next_turn.add(next_player.id)
                if not game.settings.silent_rounds:
                    await ctx.send(f"Chaos twist: {next_player.mention} loses their next turn.")
        elif event == "extra_bullet":
            game.temp_bullets = max(game.temp_bullets, 2)
            game.temp_bullets_uses = 1
            if not game.settings.silent_rounds:
                await ctx.send("Chaos twist: an extra bullet loads for the next round.")

    def get_delays(self, settings: RRSettings) -> dict[str, int]:
        if settings.fast_mode:
            base = {"pre_turn": 1, "suspense": 1, "post": 1, "between": 1}
        else:
            base = {"pre_turn": 5, "suspense": 7, "post": 2, "between": 3}
        mult = max(0.2, min(3.0, settings.drama_multiplier))
        return {k: max(0, int(round(v * mult))) for k, v in base.items()}

    async def charge_entry(self, user_id: int, amount: int) -> bool:
        async with self.bot.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 AND "money">=$1;',
                amount,
                user_id,
            )
        return result.endswith("UPDATE 1")

    async def refund_entries(self, user_ids: list[int], amount: int):
        if amount <= 0 or not user_ids:
            return
        async with self.bot.pool.acquire() as conn:
            await conn.executemany(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                [(amount, user_id) for user_id in user_ids],
            )

    def draw_chamber(self, game: Game) -> bool:
        bullets = self.get_bullet_count(game)
        if game.settings.spin_mode == "spin_each_pull":
            result = random.random() < (bullets / 6)
            if game.temp_bullets_uses > 0:
                game.temp_bullets_uses -= 1
                if game.temp_bullets_uses <= 0:
                    game.temp_bullets = 0
            return result
        if not game.chambers:
            game.reset_chambers(bullets)
        return game.chambers.pop(0)

    def select_victim(self, game: Game, shooter: discord.User) -> tuple[discord.User, bool]:
        if (
            len(game.turn_order) == 2
            and game.settings.allow_last_shot
            and random.random() < 0.25
        ):
            other_player = [p for p in game.turn_order if p.id != shooter.id][0]
            return other_player, True
        return shooter, False

    def roll_brawl_weapon(self) -> tuple[str, int]:
        return random.choice(BAR_BRAWL_WEAPONS), random.randint(150, 300)

    async def run_bar_brawl(
        self,
        ctx: commands.Context,
        game: Game,
        attacker: discord.User,
        defender: discord.User,
        delays: dict[str, int],
    ) -> tuple[discord.User, discord.User]:
        weapon_a, dmg_a = self.roll_brawl_weapon()
        weapon_b, dmg_b = self.roll_brawl_weapon()
        armor = 100
        hp = 500

        if not game.settings.silent_rounds:
            intro = discord.Embed(
                title="Bar Brawl!",
                description=(
                    f"The chamber clicks. {attacker.mention} tried to shoot {defender.mention}...\n"
                    "Instead the table flips and fists fly."
                ),
                color=discord.Color.dark_orange(),
            )
            intro.add_field(
                name=attacker.display_name,
                value=(
                    f"Weapon: **{weapon_a}**\nDamage: **{dmg_a}**\nArmor: **{armor}**\nHP: **{hp}**"
                ),
                inline=True,
            )
            intro.add_field(
                name=defender.display_name,
                value=(
                    f"Weapon: **{weapon_b}**\nDamage: **{dmg_b}**\nArmor: **{armor}**\nHP: **{hp}**"
                ),
                inline=True,
            )
            await ctx.send(embed=intro)
            await asyncio.sleep(max(1, delays.get("suspense", 2) // 2))

        battles_cog = self.bot.cogs.get("Battles")
        if not battles_cog or not hasattr(battles_cog, "battle_factory"):
            # Fallback to quick resolution if battle system isn't available
            score_a = dmg_a + armor + random.randint(1, 7)
            score_b = dmg_b + armor + random.randint(1, 7)
            if score_a == score_b:
                winner = random.choice([attacker, defender])
            else:
                winner = attacker if score_a > score_b else defender
            loser = defender if winner.id == attacker.id else attacker
            result = discord.Embed(
                title="Brawl Result",
                description=f"{winner.mention} wins the brawl. {loser.mention} goes down hard.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=result)
            return winner, loser

        battle = await battles_cog.battle_factory.create_battle(
            "brawl",
            ctx,
            player1=attacker,
            player2=defender,
            player1_weapon=weapon_a,
            player2_weapon=weapon_b,
            player1_damage=dmg_a,
            player2_damage=dmg_b,
            armor=armor,
            hp=hp,
            luck=75,
            hit_chance=0.75,
            damage_variance=40,
            allow_pets=False,
            class_buffs=False,
            element_effects=False,
            luck_effects=False,
            reflection_damage=False,
            fireball_chance=0.0,
            cheat_death=False,
            tripping=False,
            status_effects=False,
            pets_continue_battle=False,
        )

        await battle.start_battle()
        while not await battle.is_battle_over():
            await battle.process_turn()
        result = await battle.end_battle()
        if result is None:
            winner = random.choice([attacker, defender])
            loser = defender if winner.id == attacker.id else attacker
            return winner, loser
        return result

    async def finish_game(self, ctx, game: Game, winner: discord.User, initial_count: int):
        settings = game.settings
        if game.bettotal > 0:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    game.bettotal,
                    winner.id,
                )
        if settings.allow_taunts and not settings.silent_rounds:
            winner_line = self.choose_winner_message(settings, winner)
        else:
            winner_line = f"Congratulations {winner.mention}! You are the last one standing."

        winner_gif = self.get_gif_url(settings, "winner")
        if winner_gif:
            embed = discord.Embed(description=winner_line, color=discord.Color.gold())
            embed.set_image(url=winner_gif)
            await ctx.send(embed=embed)
        else:
            await ctx.send(winner_line)
        if game.bettotal > 0:
            await ctx.send(f"You won **${game.bettotal}**.")
        if settings.victory_recap:
            await ctx.send(embed=self.build_summary_embed(game, winner, initial_count))
        if ctx.channel.id in self.games:
            del self.games[ctx.channel.id]

    @commands.command(name="join", aliases=["rrjoin"])
    async def rrjoin(self, ctx):
        game = self.games.get(ctx.channel.id)
        if not game:
            return await ctx.send("No Russian Roulette lobby is running in this channel.")
        error = await self.try_join_lobby(game, ctx.author)
        if error:
            return await ctx.send(error)
        await ctx.send("You joined the roulette!")

    @has_char()
    @commands.command(name="rrgif", aliases=["rrgifs"])
    async def rrgif(
        self,
        ctx,
        action: Optional[str] = None,
        theme: Optional[str] = None,
        slot: Optional[str] = None,
        *,
        url: Optional[str] = None,
    ):
        settings = self.get_user_settings(ctx.author.id)
        settings.gif_overrides = self.normalize_gif_overrides(settings.gif_overrides)
        action_key = (action or "show").strip().lower()
        themes_label = ", ".join(sorted(THEME_TAUNTS.keys()))
        slots_label = ", ".join(GIF_SLOT_LABELS.keys())

        def resolve_theme(value: Optional[str]) -> Optional[str]:
            if value is None:
                return self.normalize_theme(settings.theme)
            raw = value.strip().lower()
            if raw in {"current", "here"}:
                return self.normalize_theme(settings.theme)
            if raw in THEME_TAUNTS:
                return self.normalize_theme(raw)
            return None

        if action_key in {"show", "view", "list"}:
            theme_key = resolve_theme(theme)
            if not theme_key:
                return await ctx.send(f"Theme must be one of: {themes_label}.")
            embed = self.build_gif_settings_embed(settings, theme_key)
            return await ctx.send(embed=embed)

        if action_key in {"set", "add"}:
            if theme is None:
                return await ctx.send(
                    "Usage: rrgif set <theme> <slot> or rrgif set <slot>."
                )

            if slot is None:
                maybe_slot = self.normalize_gif_slot(theme)
                if maybe_slot:
                    slot = theme
                    theme = None
                else:
                    return await ctx.send(
                        "Usage: rrgif set <theme> <slot> or rrgif set <slot>."
                    )

            theme_key = resolve_theme(theme)
            if not theme_key:
                return await ctx.send(f"Theme must be one of: {themes_label}.")

            slot_key = self.normalize_gif_slot(slot or "")
            if not slot_key:
                return await ctx.send(f"Slot must be one of: {slots_label}.")

            tenor_url = (url or "").strip()
            if not tenor_url:
                label = GIF_SLOT_LABELS.get(slot_key, slot_key)
                await ctx.send(
                    f"Send a Tenor URL for **{label}** (theme `{theme_key}`) within 120 seconds."
                )

                def check(msg):
                    return msg.author == ctx.author and msg.channel == ctx.channel

                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=120)
                except asyncio.TimeoutError:
                    return await ctx.send("Timed out waiting for a Tenor URL.")
                tenor_url = msg.content.strip()

            direct_url = await self.resolve_tenor_gif_url(tenor_url)
            if not direct_url:
                return await ctx.send(
                    "Could not extract a GIF ID from that Tenor URL. Please try again."
                )

            settings.gif_overrides = self.normalize_gif_overrides(settings.gif_overrides)
            settings.gif_overrides.setdefault(theme_key, {})[slot_key] = direct_url
            await self.set_user_settings(ctx.author.id, settings)
            label = GIF_SLOT_LABELS.get(slot_key, slot_key)
            return await ctx.send(f"Saved {label} GIF for theme `{theme_key}`.")

        if action_key in {"clear", "remove", "reset"}:
            if theme is None:
                return await ctx.send("Usage: rrgif clear <theme> <slot> or rrgif clear <slot>.")

            if slot is None:
                maybe_slot = self.normalize_gif_slot(theme)
                if maybe_slot:
                    slot = theme
                    theme = None
                else:
                    return await ctx.send("Usage: rrgif clear <theme> <slot> or rrgif clear <slot>.")

            theme_key = resolve_theme(theme)
            if not theme_key:
                return await ctx.send(f"Theme must be one of: {themes_label}.")

            if slot and slot.strip().lower() in {"all", "*"}:
                if theme_key in settings.gif_overrides:
                    del settings.gif_overrides[theme_key]
                    await self.set_user_settings(ctx.author.id, settings)
                return await ctx.send(f"Cleared all GIFs for theme `{theme_key}`.")

            slot_key = self.normalize_gif_slot(slot or "")
            if not slot_key:
                return await ctx.send(f"Slot must be one of: {slots_label}.")

            if (
                theme_key in settings.gif_overrides
                and slot_key in settings.gif_overrides[theme_key]
            ):
                del settings.gif_overrides[theme_key][slot_key]
                if not settings.gif_overrides[theme_key]:
                    del settings.gif_overrides[theme_key]
                await self.set_user_settings(ctx.author.id, settings)
                label = GIF_SLOT_LABELS.get(slot_key, slot_key)
                return await ctx.send(f"Cleared {label} GIF for theme `{theme_key}`.")

            return await ctx.send("No custom GIF set for that slot/theme.")

        return await ctx.send(
            "Usage: rrgif show [theme], rrgif set <theme> <slot>, or rrgif clear <theme> <slot>."
        )

    @has_char()
    @commands.command(name="rrsettings", aliases=["rrsetting", "rrset"])
    async def rrsettings(self, ctx, setting: Optional[str] = None, *, value: Optional[str] = None):
        settings = self.get_user_settings(ctx.author.id)
        if setting is None:
            embed = discord.Embed(title="Russian Roulette Settings", color=discord.Color.blue())
            descriptions = self.setting_descriptions()

            sections = [
                ("Lobby", ["join_timeout", "min_players", "max_players", "allow_start_early"]),
                (
                    "Speed",
                    [
                        "fast_mode",
                        "turn_timeout",
                        "drama_multiplier",
                        "show_status",
                        "announce_round",
                        "silent_rounds",
                    ],
                ),
                (
                    "Gameplay",
                    [
                        "spin_mode",
                        "sudden_death_after",
                        "sudden_death_bullets",
                        "mercy_chance",
                    ],
                ),
                ("Finale", ["allow_last_shot", "brawl_on_misfire", "duel_mode"]),
                ("Double Down", ["allow_double_down", "allow_pass_on_double_down"]),
                ("Flavor", ["allow_taunts", "theme", "victory_recap"]),
                ("Chaos", ["chaos_events", "chaos_chance"]),
            ]

            def shorten(text: str, limit: int = 120) -> str:
                if len(text) <= limit:
                    return text
                return text[: limit - 3] + "..."

            def add_section_fields(title: str, keys: list[str]):
                blocks: list[str] = []
                for key in keys:
                    value = getattr(settings, key)
                    desc = descriptions.get(key, "")
                    if key != "theme":
                        desc = shorten(desc)
                    block = f"`{key}`: **{value}**\n{desc}"
                    if len(block) > 1000:
                        block = block[:997] + "..."
                    blocks.append(block)

                current: list[str] = []
                current_len = 0
                chunk_index = 0
                for block in blocks:
                    extra = len(block) + (2 if current else 0)
                    if current_len + extra > 1000 and current:
                        name = title if chunk_index == 0 else f"{title} (cont.)"
                        embed.add_field(name=name, value="\n\n".join(current), inline=False)
                        current = [block]
                        current_len = len(block)
                        chunk_index += 1
                    else:
                        current.append(block)
                        current_len += extra
                if current:
                    name = title if chunk_index == 0 else f"{title} (cont.)"
                    embed.add_field(name=name, value="\n\n".join(current), inline=False)

            for idx, (title, keys) in enumerate(sections):
                add_section_fields(title, keys)
                if idx < len(sections) - 1:
                    embed.add_field(name="\u200b", value="\u200b\n\u200b", inline=False)
            embed.set_footer(text="Use rrsettings <setting> <value> to change.")
            return await ctx.send(embed=embed)

        if value is None:
            return await ctx.send("Usage: rrsettings <setting> <value>")

        key = setting.lower()
        key_map = {
            "join_timeout": "join_timeout",
            "min_players": "min_players",
            "max_players": "max_players",
            "fast_mode": "fast_mode",
            "show_status": "show_status",
            "announce_round": "announce_round",
            "round_announce": "announce_round",
            "round_announcement": "announce_round",
            "spin_mode": "spin_mode",
            "spin": "spin_mode",
            "spin_each_turn": "spin_mode",
            "spin_each_pull": "spin_mode",
            "spin_pull": "spin_mode",
            "double_down": "allow_double_down",
            "allow_double_down": "allow_double_down",
            "pass_on_double_down": "allow_pass_on_double_down",
            "allow_pass_on_double_down": "allow_pass_on_double_down",
            "taunts": "allow_taunts",
            "allow_taunts": "allow_taunts",
            "theme": "theme",
            "host_theme": "theme",
            "victory_recap": "victory_recap",
            "summary": "victory_recap",
            "allow_summary": "victory_recap",
            "start_early": "allow_start_early",
            "allow_start_early": "allow_start_early",
            "turn_timeout": "turn_timeout",
            "sudden_death_after": "sudden_death_after",
            "sudden_death_bullets": "sudden_death_bullets",
            "mercy_chance": "mercy_chance",
            "silent_rounds": "silent_rounds",
            "drama_multiplier": "drama_multiplier",
            "chaos_events": "chaos_events",
            "chaos_chance": "chaos_chance",
            "duel_mode": "duel_mode",
            "allow_last_shot": "allow_last_shot",
            "last_shot": "allow_last_shot",
            "shoot_last": "allow_last_shot",
            "shoot_other": "allow_last_shot",
            "shoot_other_player": "allow_last_shot",
            "brawl_on_misfire": "brawl_on_misfire",
            "bar_brawl": "brawl_on_misfire",
            "brawl": "brawl_on_misfire",
            "brawl_on_empty": "brawl_on_misfire",
        }
        if key not in key_map:
            return await ctx.send("Unknown setting. Try `rrsettings` to view options.")

        attr = key_map[key]
        int_fields = {
            "join_timeout",
            "min_players",
            "max_players",
            "turn_timeout",
            "sudden_death_after",
            "sudden_death_bullets",
        }
        float_fields = {"mercy_chance", "drama_multiplier", "chaos_chance"}
        bool_fields = {
            "fast_mode",
            "show_status",
            "announce_round",
            "allow_double_down",
            "allow_pass_on_double_down",
            "allow_taunts",
            "victory_recap",
            "allow_start_early",
            "silent_rounds",
            "chaos_events",
            "duel_mode",
            "allow_last_shot",
            "brawl_on_misfire",
        }

        if attr in int_fields:
            try:
                parsed = int(value)
            except ValueError:
                return await ctx.send("That setting expects a number.")
            if attr == "join_timeout":
                parsed = max(30, min(600, parsed))
            if attr == "min_players":
                parsed = max(2, min(20, parsed))
            if attr == "max_players":
                parsed = max(0, min(50, parsed))
                if parsed == 1:
                    parsed = 2
            if attr == "turn_timeout":
                parsed = max(5, min(60, parsed))
            if attr == "sudden_death_after":
                parsed = max(0, min(50, parsed))
            if attr == "sudden_death_bullets":
                parsed = max(1, min(5, parsed))
            setattr(settings, attr, parsed)
        elif attr in float_fields:
            parsed = self.parse_float(value)
            if parsed is None:
                return await ctx.send("That setting expects a decimal number.")
            if attr == "mercy_chance":
                parsed = max(0.0, min(0.5, parsed))
            if attr == "chaos_chance":
                parsed = max(0.0, min(0.5, parsed))
            if attr == "drama_multiplier":
                parsed = max(0.2, min(3.0, parsed))
            setattr(settings, attr, parsed)
        elif attr == "spin_mode":
            normalized = self.normalize_spin_mode(value)
            if normalized is None:
                return await ctx.send("Spin mode must be fixed, spin_each_pull, or spin_each_turn.")
            setattr(settings, attr, normalized)
        elif attr == "theme":
            raw_theme = value.strip().lower()
            if raw_theme not in THEME_TAUNTS:
                return await ctx.send(
                    "Theme must be dark, noir, western, wasteland, mafia, medieval, arcade, greek, "
                    "norse, farmer, sarcastic_farmer, horror, detective, pirate, or mixed "
                    "(gallows maps to western)."
                )
            theme = self.normalize_theme(raw_theme)
            setattr(settings, attr, theme)
        elif attr in bool_fields:
            parsed = self.parse_bool(value)
            if parsed is None:
                return await ctx.send("That setting expects true/false.")
            setattr(settings, attr, parsed)
        else:
            return await ctx.send("Unsupported setting type.")

        await self.set_user_settings(ctx.author.id, settings)
        await ctx.send(f"Updated `{attr}` to `{getattr(settings, attr)}`.")

    @has_char()
    @commands.command(name="russianroulette", aliases=["rr", "gungame"], brief=_("Play Russian Roulette"))
    async def russianroulette(self, ctx, bet: IntFromTo(0, 100_000) = 0):
        try:
            if ctx.channel.id in self.games:
                await ctx.send("A game is already running in this channel.")
                return

            if bet < 0:
                await ctx.send(f"{ctx.author.mention} your bet must be above 0!")
                return

            settings = self.get_user_settings(ctx.author.id)
            game = Game(ctx.author.id, settings, bet)
            self.games[ctx.channel.id] = game

            if bet > 0:
                ok = await self.charge_entry(ctx.author.id, bet)
                if not ok:
                    await ctx.send(
                        f"{ctx.author.mention}, you don't have enough money to cover the bet of **${bet}**."
                    )
                    del self.games[ctx.channel.id]
                    return
                game.bettotal = bet

            game.gamestarted = True
            game.participants.append(ctx.author)
            game.joined_players.add(ctx.author.id)
            self.ensure_stats(game, ctx.author.id)

            try:
                embed = self.build_lobby_embed(game)
                view = RussianJoinView(self, game, ctx.author.id)
                message = await ctx.send(embed=embed, view=view)
                view.message = message
                game.lobby_message = message
                game.lobby_view = view

                try:
                    await asyncio.wait_for(view.wait(), timeout=settings.join_timeout)
                except asyncio.TimeoutError:
                    view.stop()
                for item in view.children:
                    item.disabled = True
                await message.edit(view=view)
                game.lobby_open = False

                if len(game.participants) < settings.min_players:
                    await ctx.send("Not enough players to start the game.")
                    await self.refund_entries([p.id for p in game.participants], bet)
                    del self.games[ctx.channel.id]
                    return

                await self.load_levels(game)

                random.shuffle(game.participants)
                game.turn_order = list(game.participants)
                game.current_index = 0
                game.is_game_running = True
                self.prepare_round(game)

                initial_count = len(game.turn_order)
                if not settings.silent_rounds:
                    if settings.show_status:
                        await ctx.send(embed=self.build_status_embed(game))
                    else:
                        await self.announce_round(ctx, game)

                delays = self.get_delays(settings)
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                await self.refund_entries([p.id for p in game.participants], bet)
                if ctx.channel.id in self.games:
                    del self.games[ctx.channel.id]
                return


            try:
                while len(game.turn_order) > 1:
                    player = game.turn_order[game.current_index]
                    duel_active = settings.duel_mode and len(game.turn_order) == 2

                    if settings.spin_mode == "spin_each_turn":
                        self.prepare_round(game)

                    if player.id in game.pass_next_turn:
                        if duel_active:
                            game.pass_next_turn.remove(player.id)
                        else:
                            game.pass_next_turn.remove(player.id)
                            game.stats[player.id]["passes"] += 1
                            if not settings.silent_rounds:
                                await ctx.send(f"{player.mention} uses a pass and skips their turn.")
                            game.current_index = (game.current_index + 1) % len(game.turn_order)
                            continue

                    if settings.allow_taunts and not settings.silent_rounds and random.random() < 0.20:
                        await ctx.send(self.choose_taunt(settings))

                    choice = "pull"
                    if settings.allow_double_down:
                        show_pull = settings.fast_mode
                        view = TurnDecisionView(player.id, show_pull, settings.turn_timeout)
                        if settings.fast_mode:
                            prompt_text = (
                                f"{player.mention}, choose **Shoot** or **Double Down** "
                                f"(auto-shoot in {settings.turn_timeout}s)."
                            )
                        elif settings.silent_rounds:
                            prompt_text = (
                                f"{player.mention}, auto-shoot in {settings.turn_timeout}s. "
                                "Press **Double Down** to risk two pulls."
                            )
                        else:
                            prompt_text = (
                                f"{player.mention}, shooting in {settings.turn_timeout}s. "
                                "Press **Double Down** to risk two pulls and earn a pass if you survive."
                            )
                        prompt = await ctx.send(prompt_text, view=view)
                        start_time = asyncio.get_running_loop().time()
                        await view.wait()
                        choice = view.choice
                        await prompt.edit(view=None)
                        if not settings.fast_mode:
                            elapsed = asyncio.get_running_loop().time() - start_time
                            remaining = settings.turn_timeout - elapsed
                            if remaining > 0:
                                await asyncio.sleep(remaining)

                    await asyncio.sleep(delays["pre_turn"])
                    if not settings.silent_rounds:
                        await ctx.send(
                            f"It's {player.mention}'s turn! They raise the gun and pull the trigger..."
                        )

                    shots = 2 if choice == "double" else 1
                    if choice == "double":
                        game.stats[player.id]["double_downs"] += 1
                        if not settings.silent_rounds:
                            await ctx.send(
                                f"{player.mention} doubles down and takes two pulls if they survive."
                            )

                    eliminated = False
                    victim: Optional[discord.User] = None
                    shot_other = False

                    for _ in range(shots):
                        await asyncio.sleep(delays["suspense"])
                        target, shot_other = self.select_victim(game, player)
                        chamber_drawn = self.draw_chamber(game)
                        game.stats[player.id]["shots"] += 1

                        if chamber_drawn and settings.mercy_chance > 0:
                            if random.random() < settings.mercy_chance:
                                chamber_drawn = False
                                if not settings.silent_rounds:
                                    embed = discord.Embed(
                                        title="Click... misfire.",
                                        description="The round fails to fire. Luck buys a breath.",
                                        color=discord.Color.orange(),
                                    )
                                    await ctx.send(embed=embed)

                        if (
                            not chamber_drawn
                            and shot_other
                            and settings.brawl_on_misfire
                            and len(game.turn_order) == 2
                        ):
                            winner, loser = await self.run_bar_brawl(
                                ctx, game, player, target, delays
                            )
                            if winner.id != loser.id:
                                game.stats[winner.id]["kills"] += 1
                            game.deaths += 1
                            game.turn_order = [winner]
                            await self.finish_game(ctx, game, winner, initial_count)
                            return

                        if chamber_drawn:
                            victim = target
                            eliminated = True
                            victim_level = game.levels.get(victim.id, 0)
                            if settings.allow_taunts and not settings.silent_rounds:
                                death_line = self.choose_death_message(settings, victim, victim_level)
                            else:
                                death_line = (
                                    f"{victim.mention} has been shot!"
                                    if shot_other
                                    else f"{player.mention} has shot themselves in the face!"
                                )
                            embed = discord.Embed(
                                title="BANG!",
                                description=death_line,
                                color=discord.Color.red(),
                            )
                            if shot_other:
                                embed.set_image(url=self.get_gif_url(settings, "shoot_other"))
                            else:
                                embed.set_image(url=self.get_gif_url(settings, "shoot_self"))
                            await asyncio.sleep(delays["post"])
                            await ctx.send(embed=embed)
                            break

                        game.stats[player.id]["survived"] += 1
                        if not settings.silent_rounds:
                            if settings.allow_taunts:
                                survive_line = self.choose_survival_message(settings, player)
                            else:
                                survive_line = (
                                    f"{player.mention} survived this pull and passes the gun on."
                                    if shots == 1
                                    else f"{player.mention} survived a pull."
                                )
                            embed = discord.Embed(
                                title="The Gun Clicks!",
                                description=survive_line,
                                color=discord.Color.green(),
                            )
                            await ctx.send(embed=embed)
                        await asyncio.sleep(delays["between"])

                    if eliminated and victim is not None:
                        victim_index = next(
                            i for i, p in enumerate(game.turn_order) if p.id == victim.id
                        )
                        shooter_index = game.current_index
                        if victim.id != player.id:
                            game.stats[player.id]["kills"] += 1
                        del game.turn_order[victim_index]
                        game.deaths += 1

                        if len(game.turn_order) == 1:
                            winner = game.turn_order[0]
                            await self.finish_game(ctx, game, winner, initial_count)
                            return

                        game.roundnum += 1

                        if victim.id == player.id:
                            if victim_index >= len(game.turn_order):
                                game.current_index = 0
                            else:
                                game.current_index = victim_index
                        else:
                            if victim_index < shooter_index:
                                shooter_index -= 1
                            game.current_index = (shooter_index + 1) % len(game.turn_order)

                        await self.maybe_apply_chaos(ctx, game)
                        if settings.spin_mode != "spin_each_turn":
                            self.prepare_round(game)

                        if not settings.silent_rounds:
                            if settings.show_status:
                                await ctx.send(embed=self.build_status_embed(game))
                            else:
                                await self.announce_round(ctx, game)
                    else:
                        if choice == "double" and settings.allow_pass_on_double_down and not duel_active:
                            game.pass_next_turn.add(player.id)
                            if not settings.silent_rounds:
                                await ctx.send(
                                    f"{player.mention} earned a pass for their next turn."
                                )
                        game.current_index = (game.current_index + 1) % len(game.turn_order)

            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
            finally:
                if ctx.channel.id in self.games:
                    del self.games[ctx.channel.id]
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            await self.refund_entries([p.id for p in game.participants], bet)
            if ctx.channel.id in self.games:
                del self.games[ctx.channel.id]
            return


async def setup(bot):
    await bot.add_cog(Russian(bot))
