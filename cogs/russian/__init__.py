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

# Extra comedy packs use one compact schema so every selectable theme ships
# with complete turn, round, survival, death, and winner narration.
ADDITIONAL_THEME_MESSAGES: dict[str, dict[str, list[str]]] = {
    "corporate": {
        "taunt": [
            "Please remain calm. HR has classified the loaded chamber as an opportunity for growth.",
            "The cylinder spins with the confidence of a manager who has never done the actual job.",
            "Your life is now a key deliverable with no allocated budget.",
            "The gun would like to circle back and put a pin in your continued employment.",
            "This meeting could have been an email. The funeral cannot.",
            "Legal reminds everyone that screaming constitutes acceptance of the terms.",
        ],
        "round_start": [
            "New quarter, same chamber, reduced headcount.",
            "The all-hands meeting begins. Attendance may decline sharply.",
            "Management has reloaded the performance-improvement revolver.",
            "Another round of restructuring is now chambered.",
            "Please take your seats; layoffs will be conducted ballistically.",
            "The cylinder spins as leadership explores involuntary offboarding.",
        ],
        "survival": [
            "{player} survives and is expected back at their desk by nine.",
            "HR congratulates {player} on meeting the minimum pulse requirement.",
            "{player} remains employed, pending another lethal performance review.",
            "The chamber clicks. {player}'s leave request is still denied.",
            "{player} survives; management calls this proof the system works.",
            "{player} retains their position and all associated trauma.",
        ],
        "death": [
            "{victim} has been permanently offboarded. Their access badge stopped working first.",
            "{victim}'s position has been eliminated, along with the position holder.",
            "HR regrets to announce {victim} has pursued an opportunity outside the living.",
            "{victim} failed the performance review with terminal efficiency.",
            "The company thanks {victim} for their years of service and three minutes of notice.",
            "{victim} achieved perfect work-life balance by having neither.",
        ],
        "winner": [
            "{winner} is the sole remaining employee and therefore acting CEO.",
            "Congratulations, {winner}. Your prize is everyone else's workload.",
            "{winner} survived the restructure. Shareholders are cautiously erect.",
            "The company promotes {winner} and freezes their salary.",
            "{winner} wins. HR calls the body count a successful efficiency drive.",
            "{winner} receives a certificate, a lanyard, and six new trauma responses.",
        ],
    },
    "reaper_office": {
        "taunt": [
            "Death has your file open and is making disappointed little noises.",
            "The Reaper is on lunch, but the gun agreed to cover the desk.",
            "Your mortality ticket has been escalated to someone with a scythe.",
            "Death says this appointment should only take the rest of your life.",
            "The afterlife is understaffed, so please die in an orderly fashion.",
            "The Reaper sharpened the scythe, then remembered this department has a revolver.",
        ],
        "round_start": [
            "The Department of Inevitable Outcomes opens another case.",
            "Death clocks in. The chamber clocks someone out.",
            "A fresh round begins under fluorescent lights in the afterlife.",
            "The Reaper calls the next appointment and spins the cylinder.",
            "Another mortality audit begins. Receipts will not be required.",
            "The dead queue politely while the living make terrible decisions.",
        ],
        "survival": [
            "The Reaper stamps RETURN TO SENDER on {player}.",
            "{player}'s death appointment was cancelled due to clerical incompetence.",
            "Death checks the wrong box. {player} lives.",
            "{player} survives because the Reaper's printer jammed.",
            "The chamber clicks. {player}'s case has been placed back in the pending tray.",
            "{player} is not dead, merely pre-approved.",
        ],
        "death": [
            "The Reaper finds {victim}'s file and mutters, 'There you fucking are.'",
            "{victim}'s mortality ticket has been resolved and permanently closed.",
            "Death welcomes {victim} with the enthusiasm of a clerk five minutes from home time.",
            "{victim} is processed, stamped, and forwarded to whichever basement handles idiots.",
            "The chamber fires. {victim}'s out-of-office reply activates forever.",
            "{victim} dies at level {level}. Death rounds that down to zero.",
        ],
        "winner": [
            "{winner} survives the audit. Death has scheduled a follow-up.",
            "The Reaper loses {winner}'s paperwork and pretends this was intentional.",
            "{winner} wins and receives a complimentary extension on mortality.",
            "Death closes the office. {winner} is tomorrow's problem.",
            "{winner} leaves alive while the Reaper quietly updates the watchlist.",
            "The last file standing belongs to {winner}. It is now marked URGENT.",
        ],
    },
    "insurance": {
        "taunt": [
            "Your policy covers accidental death, not whatever the fuck this is.",
            "The assessor has labelled the revolver a pre-existing condition.",
            "Please hold. Your remaining lifespan is important to us.",
            "The premium just went up because the gun looked at you funny.",
            "Actuarial science calls this an avoidable spike in stupidity.",
            "The fine print says the chamber is always right.",
        ],
        "round_start": [
            "A new claim period begins with one bullet and no coverage.",
            "The cylinder spins. Your deductible becomes existential.",
            "Another round begins under the comprehensive idiocy policy.",
            "The assessor reloads and prepares to deny everything.",
            "Coverage resets. Common sense remains excluded.",
            "The underwriter sees the table and simply starts drinking.",
        ],
        "survival": [
            "{player} survives. The insurer classifies breathing as an optional extra.",
            "The chamber clicks and {player}'s premium triples anyway.",
            "{player} lives, subject to excess, exclusions, and lifelong shaking.",
            "The claim against {player}'s life has been denied on a technicality.",
            "{player} remains alive but is no longer considered insurable by God.",
            "The bullet fails to lodge a claim against {player}.",
        ],
        "death": [
            "{victim}'s claim is denied: policy excludes acts of catastrophic dipshittery.",
            "{victim} is now fully covered by the ground.",
            "The insurer offers {victim}'s family thoughts, prayers, and a twelve-page rejection letter.",
            "{victim} dies. The paperwork is somehow the real tragedy.",
            "Cause of death: ballistic. Cause of non-payment: paragraph 8, subsection fuck-you.",
            "{victim}'s life policy pays out one branded pen and a sincere voicemail menu.",
        ],
        "winner": [
            "{winner} wins and is immediately denied renewal.",
            "The actuaries predicted everyone but {winner}. They have been promoted.",
            "{winner} receives the grand prize: a slightly lower deductible on therapy.",
            "The insurer confirms {winner} is alive but refuses to put that in writing.",
            "{winner} survives the risk assessment and becomes the risk.",
            "Congratulations, {winner}. Your no-claims bonus is morally indefensible.",
        ],
    },
    "true_crime": {
        "taunt": [
            "Investigators would later describe this decision as extremely fucking useful evidence.",
            "Nobody knew the warning signs, except everyone in the room and the loaded gun.",
            "The host lowers their voice because apparently whispering makes exploitation tasteful.",
            "Stay tuned: after the gunshot, we rank the suspects by podcast potential.",
            "A neighbour says you seemed quiet. You were asleep, but the edit is already locked.",
            "This preventable nightmare is sponsored by a mattress nobody asked about.",
        ],
        "round_start": [
            "Episode one: The Cylinder That Everyone Absolutely Saw Coming.",
            "A new round begins, reconstructed through ominous stock footage.",
            "The host says 'what happened next shocked the town' for the ninth time.",
            "Another episode starts with rain sounds and several ethical violations.",
            "The chamber spins beneath a tasteful amount of piano music.",
            "Tonight: six chambers, one bullet, and forty-seven ad breaks.",
        ],
        "survival": [
            "{player} survives, devastating producers who already bought the episode title.",
            "The gun clicks. {player} is upgraded from victim to unreliable witness.",
            "{player} lives, so the podcast invents a suspicious childhood instead.",
            "The narrator calls {player}'s survival chilling, haunting, and available on Patreon.",
            "{player} survives. Investigators have no comment; the host has three hours of comments.",
            "The chamber spares {player}. Season two is now in serious trouble.",
        ],
        "death": [
            "{victim} dies. Before we continue, a word from our sponsor.",
            "The case of {victim} is solved immediately, ruining a perfectly good twelve-part series.",
            "{victim}'s final mistake is remastered in immersive audio.",
            "The chamber fires. Three podcasters simultaneously describe the room as sleepy.",
            "{victim} becomes a tragedy, a thumbnail, and eventually a tasteful tote bag.",
            "At level {level}, {victim} had their whole life ahead of them and six ads behind them.",
        ],
        "winner": [
            "{winner} survives and signs an exclusive interview deal before the bodies cool.",
            "The season finale reveals {winner} was alive the entire time.",
            "{winner} wins. The podcast calls this closure because accuracy tested poorly.",
            "All evidence points to {winner}, mostly because everyone else is evidence.",
            "{winner} leaves with a book deal and the thousand-yard stare of a bestseller.",
            "The host thanks {winner}, the victims, and listeners on the premium tier.",
        ],
    },
    "reality_tv": {
        "taunt": [
            "The producers insist the loaded gun is here for the right reasons.",
            "Please stare into camera three when your dignity leaves your body.",
            "The audience loves authenticity, so try to scream naturally.",
            "Your tragic backstory tested well. Your survival did not.",
            "One chamber contains a bullet. The others contain brand partnerships.",
            "The host pauses for eleven seconds because suspense has a contractual minimum.",
        ],
        "round_start": [
            "Previously on People Making Fucking Terrible Choices...",
            "A new elimination ceremony begins, now with legally distinct gunfire.",
            "The cameras roll. The cylinder rolls. Standards continue to fall.",
            "Another round begins with a shocking twist everyone saw in the trailer.",
            "Contestants, take your marks. Medics, pretend this is normal.",
            "The host welcomes everyone back with suspiciously dry hands.",
        ],
        "survival": [
            "{player} survives and immediately cries in the confessional for screen time.",
            "The chamber clicks. {player} receives immunity and a deeply invasive close-up.",
            "{player} lives. The judges praise their courage and cheekbone definition.",
            "The audience saves {player}; the gun was apparently outvoted.",
            "{player} advances to next week's trauma challenge.",
            "The bullet does not choose {player}. The producers look fucking furious.",
        ],
        "death": [
            "{victim}, you have been eliminated. Extremely eliminated.",
            "The chamber sends {victim} home in several production-approved containers.",
            "{victim}'s journey ends here, but their reaction GIF is forever.",
            "The judges wanted more vulnerability. {victim} has now provided all of it.",
            "{victim} loses the challenge and gains a memorial montage.",
            "The host calls {victim}'s death the most dramatic exit in franchise history.",
        ],
        "winner": [
            "{winner} wins the season, a cash prize, and an unusable nervous system.",
            "The audience crowns {winner}, mostly because the other phone lines are dead.",
            "{winner} gets the final rose. It smells strongly of gunpowder.",
            "Congratulations, {winner}. Your trauma airs Tuesdays at eight.",
            "{winner} survives and is contractually obligated to return for All-Stars.",
            "The host hugs {winner} after confirming there will be a second season.",
        ],
    },
    "family_game_night": {
        "taunt": [
            "Nan brought biscuits. Uncle Barry brought unresolved rage and a revolver.",
            "Nobody is leaving until someone wins or Dad admits he cheated at Monopoly.",
            "The family that plays together stays together, except for whoever gets ventilated.",
            "Mum says put the gun down. Mum has been ignored since 1997.",
            "The rules are simple: spin, pull, and never mention the inheritance.",
            "This is still healthier than discussing politics at Christmas.",
        ],
        "round_start": [
            "Another wholesome family round begins with active resentment.",
            "Dad reloads. Mum pours wine. The children update the will.",
            "Game night continues because apparently Uno was not ruining enough lives.",
            "The cylinder spins beside the good china nobody is allowed to use.",
            "Everyone gathers close. The therapist gathers billable material.",
            "A new round begins and the inheritance gets mathematically simpler.",
        ],
        "survival": [
            "{player} survives. Their mother says not to make a fuss.",
            "The gun clicks and {player} remains the family's second-biggest disappointment.",
            "{player} lives. Uncle Barry accuses the chamber of favouritism.",
            "Nan slips {player} another biscuit and whispers, 'Your turn will come.'",
            "{player} survives and is still expected to help with the dishes.",
            "The chamber spares {player}. The family group chat does not.",
        ],
        "death": [
            "{victim} dies. Mum asks whether anyone thought to put newspaper down.",
            "The family loses {victim} and gains an awkwardly available chair.",
            "{victim} is removed from the game and, more importantly, the Christmas seating plan.",
            "The gun fires. Dad mutters that this never happened when he was a kid.",
            "{victim}'s inheritance is divided before the echo finishes.",
            "Nan looks at {victim}, sips her tea, and says, 'Bit dramatic.'",
        ],
        "winner": [
            "{winner} wins game night and is never invited to Christmas again.",
            "The estate now belongs to {winner}. So does the cleanup.",
            "{winner} is the last relative standing and finally controls the thermostat.",
            "Mum congratulates {winner}, then asks why they could not just play Scrabble.",
            "{winner} takes the family trophy and several incriminating casserole dishes.",
            "The family group chat has one member left: {winner}, typing furiously.",
        ],
    },
    "hell_bureaucracy": {
        "taunt": [
            "Please take a number. Damnation is experiencing higher than usual demand.",
            "The gun is infernal, but the processing fee is worse.",
            "Satan outsourced torment to a contractor with one revolver and no supervision.",
            "Your soul has been pre-declined for reasons listed on a form you cannot access.",
            "The ninth circle is just this lobby with harsher fluorescent lighting.",
            "Hell is other people, but the bullet is doing most of the heavy lifting.",
        ],
        "round_start": [
            "Infernal Intake begins another round of mandatory processing.",
            "The cylinder spins while the damned complete Form 666-B.",
            "A new round opens at Window Thirteen. The clerk does not look up.",
            "The queue advances by one soul and several centuries.",
            "Another chamber is loaded under the Eternal Efficiency Initiative.",
            "Hell freezes over briefly; the paperwork remains warm.",
        ],
        "survival": [
            "{player} survives because Hell misplaced the original death certificate.",
            "The chamber clicks. {player} is redirected to another department.",
            "{player}'s damnation request is rejected for insufficient suffering.",
            "A demon stamps {player} NOT DEAD YET and goes on break.",
            "{player} lives after presenting three forms of infernal identification.",
            "Hell cannot process {player} until the manager returns, sometime after eternity.",
        ],
        "death": [
            "{victim} arrives in Hell and is told death was only the first queue.",
            "The chamber fires. {victim}'s soul is assigned a case number and immediately lost.",
            "{victim} is damned for eternity, plus six to eight business eternities for processing.",
            "A demon welcomes {victim}, then charges a convenience fee for the screaming.",
            "{victim}'s appeal is denied before their body finishes falling.",
            "Hell receives {victim} at level {level} and downgrades them to unpaid intern.",
        ],
        "winner": [
            "{winner} escapes Hell on a technicality. Legal is furious.",
            "The infernal clerk marks {winner} RETURNED: TOO DIFFICULT TO PROCESS.",
            "{winner} survives and receives one complimentary sin waiver.",
            "Hell closes for the day. {winner} remains somebody else's nightmare.",
            "{winner} beats the system by being more exhausting than eternal punishment.",
            "Congratulations, {winner}. Your soul remains conditionally yours.",
        ],
    },
    "doomed_circus": {
        "taunt": [
            "The clown is holding the gun correctly. Somehow that makes this worse.",
            "Ladies and gentlemen, prepare for the least talented death-defying act alive.",
            "The ringmaster promises refunds to anyone who survives long enough to complain.",
            "The cannon was too safe, so the clowns found a revolver.",
            "Under the big top, every seat has a splash-zone disclaimer.",
            "The calliope plays faster whenever the gun points at you.",
        ],
        "round_start": [
            "The spotlight rises on another catastrophic performance.",
            "A fresh act begins. The clowns have already notified next of kin.",
            "The ringmaster reloads and calls it audience participation.",
            "Another round enters the ring on a tiny, deeply cursed bicycle.",
            "The band strikes up something cheerful and legally inadmissible.",
            "Welcome back to the greatest shitshow on earth.",
        ],
        "survival": [
            "The gun clicks. {player} receives a sad balloon and no explanation.",
            "{player} survives while seventeen clowns boo from one impossibly small car.",
            "The ringmaster calls {player}'s survival a rehearsal mistake.",
            "{player} lives. The trapeze artist quietly cuts the backup rope anyway.",
            "The bullet misses {player}; a cream pie completes the humiliation.",
            "{player} survives and is promoted to Head of Unscheduled Screaming.",
        ],
        "death": [
            "The clown honks once. The coroner understands. {victim} is gone.",
            "{victim}'s final act receives a standing ovation from people trying to leave.",
            "The ringmaster announces {victim} will not return after intermission.",
            "{victim} is fired from the cannon of life directly into the gift shop memorial range.",
            "The gun bangs, the cymbals crash, and {victim} absolutely fucking doesn't get up.",
            "A clown places one tiny flower on {victim}. It squirts embalming fluid.",
        ],
        "winner": [
            "{winner} wins the circus and inherits all seventeen clowns. Condolences.",
            "The ringmaster crowns {winner} beneath a tasteful shower of liability waivers.",
            "{winner} survives the big top. The small print says the circus follows them home.",
            "The crowd cheers {winner}; the empty seats are significantly louder.",
            "{winner} takes a bow while the clown car reverses over the evidence.",
            "The circus leaves town. {winner}'s nightmares stay for an encore.",
        ],
    },
    "mad_scientist": {
        "taunt": [
            "The hypothesis is that you will die. Peer review has loaded the gun.",
            "Science asks questions. This revolver removes the people asking them.",
            "The control group went home. You are the entertaining group.",
            "The ethics committee sent a strongly worded letter, so naturally we burned it.",
            "Please hold still. The data gets messy when the subjects beg.",
            "The scientist assures everyone the screaming is statistically insignificant.",
        ],
        "round_start": [
            "Trial begins. Variables controlled; consequences absolutely fucking not.",
            "A new experiment starts with one bullet and several grant violations.",
            "The laboratory resets. The stains have not.",
            "Another round enters phase three human regretting.",
            "The scientist spins the cylinder and writes down a result in advance.",
            "Test subjects ready. Medical staff fictional. Begin.",
        ],
        "survival": [
            "{player} survives, disproving the theory and infuriating the funding body.",
            "The chamber clicks. {player} is marked ANOMALY: annoyingly alive.",
            "{player} lives, so the scientist adds more exclamation marks to the notes.",
            "The experiment fails to kill {player}. Further experiments are immediately approved.",
            "{player} survives with a statistically significant amount of trauma.",
            "The bullet avoids {player}. The scientist blames contamination.",
        ],
        "death": [
            "{victim} validates the hypothesis by ceasing all measurable activity.",
            "The experiment kills {victim}. The paper calls this a promising result.",
            "{victim}'s final words are recorded as miscellaneous lab noise.",
            "The chamber fires. {victim} moves from participant to figure 4B.",
            "{victim} dies for science. Science does not remember asking.",
            "At level {level}, {victim} discovers the terminal velocity of bad methodology.",
        ],
        "winner": [
            "{winner} survives and is promoted from subject to unexplained contamination.",
            "The scientist awards {winner} a certificate printed on the ethics complaint.",
            "{winner} wins. The conclusion reads: somehow, the idiot persists.",
            "The surviving sample is {winner}. Refrigerate after opening.",
            "{winner} escapes the lab carrying several organs, mostly their own.",
            "Peer review confirms {winner} is alive and the methodology is fucking horrifying.",
        ],
    },
    "aussie": {
        "taunt": [
            "Spin the cylinder, ya mad cunt. Centrelink won't cover this.",
            "This has gone from she'll be right to call the fucking coroner.",
            "The pub has stopped taking bets and started measuring coffins.",
            "One bullet, six chambers, zero fucking adult supervision.",
            "The gun's hotter than a servo pie left on the dashboard.",
            "Somewhere a magpie is watching this and thinking, 'Bit aggressive.'",
            "Yeah nah, this is cooked beyond recognition.",
            "If this goes wrong, tell the ambos it was a workplace incident.",
        ],
        "round_start": [
            "Righto, new round. Somebody hold the beer and somebody call emergency.",
            "The cylinder spins like a Commodore leaving a Bunnings car park.",
            "Another round begins because nobody here knows when to fuck off home.",
            "Fresh chamber, warm beer, absolutely rooted decision-making.",
            "The pub goes quiet. Even the pokies reckon this is irresponsible.",
            "Yeah nah, she'll be right. Statistically, she absolutely will not.",
            "The gun comes back around like a dodgy kebab at three in the morning.",
            "Round starts. The local ambo crew sighs in perfect unison.",
        ],
        "survival": [
            "{player} survives. Yeah nah, lucky cunt.",
            "The chamber clicks. {player} remains a happy little Vegemite.",
            "{player} lives and immediately claims it was all part of the plan. Bullshit.",
            "No bang. {player} is still upright, unlike the pub's last plastic chair.",
            "{player} survives by the width of a bee's dick and twice the luck.",
            "The gun says nah. {player} says fuck yeah. The ambos remain unconvinced.",
            "{player} lives to make another decision this catastrophically cooked.",
            "The bullet misses {player}. A magpie has volunteered to finish the job.",
        ],
        "death": [
            "Yeah nah, shit's fucked, cunt. {victim} is cactus.",
            "{victim} became a happy little Vegemite. Mostly little bits.",
            "The gun said 'oi cunt' and {victim} answered. Fatal communication error.",
            "{victim} is deader than a roo on the Hume and twice as inconvenient.",
            "Ripper of a shot. Absolutely dogshit outcome for {victim}.",
            "Tell {victim}'s mum they died doing what they loved: being a complete fucking drongo.",
            "{victim} has been promoted from loose unit to permanent cemetery resident.",
            "The chamber went off like a servo pie in a microwave. So did {victim}.",
        ],
        "winner": [
            "{winner} wins and immediately claims it was skill, the lying cunt.",
            "Last drongo standing: {winner}. Somebody buy the bastard a beer.",
            "{winner} survives. The pub names a sticky patch of carpet in their honour.",
            "Against all odds and basic common sense, {winner} fucking wins.",
            "{winner} takes the crown, the cash, and absolutely no lessons from this.",
            "The ambos pack up. {winner} cracks a cold one and calls that character development.",
            "{winner} is the last happy little Vegemite in a room full of paperwork.",
            "Yeah nah, fair play: {winner} survived the most cooked game in the country.",
        ],
    },
    "nature_doc": {
        "taunt": [
            "The young male, inexperienced, approaches the chamber. The herd does not intervene.",
            "He has no natural predators. He has compensated admirably.",
            "The display is intended to attract a mate. It will attract an ambulance.",
            "Observe: a species that invented the tool, the trigger, and no reason to combine them.",
            "In forty years of filming, we have never seen this behaviour survive.",
            "The male puffs his chest to appear larger. The bullet is unmoved by theatre.",
            "Note the confidence. Note the total absence of anything justifying it.",
            "Here at the watering hole, the dominant male drinks first and dies first.",
            "The species is not endangered. It is trying very hard to correct this.",
            "He has survived drought, famine, and predation. He will not survive his own idea.",
            "The pack has learned to hunt cooperatively. It has not learned to stop.",
            "Evolution spent four million years on this brain. Tonight it takes the evening off.",
            "The chamber turns. Somewhere a distant relative of this creature is using a rock correctly.",
            "In the wild, the sick and the old are taken. Here, the volunteers are.",
            "The herd watches in silence. Not from respect. From a complete absence of concern.",
            "He was raised by the group and will be buried by them, both with equal enthusiasm.",
            "The mating call has changed over generations. It now sounds like a hammer being cocked.",
            "This behaviour appears in no other species. There is a reason for that.",
            "The creature grooms itself before the pull. Vanity outlives judgement.",
            "Note how the group has arranged itself in a circle. This is not strategy. It is seating.",
            "The young learn by example. Tonight's lesson is unusually final.",
            "He believes he is the apex. The chamber uses a different taxonomy.",
            "Nature is not cruel. Nature is indifferent. Nature is, however, taking notes.",
            "The species mourns its dead. Briefly. Then it does this again on Thursday.",
            "The revolver is not a natural object. The stupidity is entirely natural.",
            "Watch closely. Behaviour this maladaptive rarely survives long enough to be filmed.",
            "The crew have been instructed not to intervene. The crew are relieved.",
            "In the dry season the weak gather at the last remaining source of water. Or bullets.",
            "He is at the peak of his physical condition and the trough of everything else.",
            "The camera cannot look away. The camera has tried.",
        ],
        "round_start": [
            "The dry season returns. The herd gathers at the only chamber for miles.",
            "Dawn. The colony stirs, unaware one of them has already been selected.",
            "A new season begins. The population will not survive it intact.",
            "The migration continues. Some of the herd will not complete it.",
            "The light fails. The predators do not.",
            "Another cycle begins as it has for millennia, though usually with fewer firearms.",
            "The savannah is quiet. The revolver is patient.",
            "Breeding season resumes. So does the culling.",
            "The waterhole fills. The herd returns. The arithmetic changes.",
            "Night falls across the plain. Something metallic clicks in the dark.",
            "The pack reassembles, minus its contributions to the soil.",
            "A fresh round begins. Nature keeps no scoreboard. We do.",
            "The seasons turn without sentiment. The cylinder does the same.",
            "The flock settles. One of them is already, statistically, meat.",
            "The territory is contested again. The contest is idiotic.",
            "Morning. The survivors groom. The dead do not.",
            "The herd thins each cycle. This is not tragedy. This is Tuesday.",
            "The great plain stretches out, indifferent and faintly bored.",
            "Another round. The scavengers have learned this sound and are already circling.",
            "The colony returns to the nesting ground, which is also the dying ground.",
            "The hunt resumes. Unusually, the prey has volunteered.",
            "The ecosystem rebalances. Loudly.",
            "A new round opens under a sky that has watched this for four billion years.",
            "The tide of the season turns. So does the cylinder.",
            "Fresh chamber. Same doomed genus.",
            "The animals gather again, drawn by instinct and a total lack of alternatives.",
            "The rains come late this year. The deaths are punctual.",
            "The plain wakes. Something on it will not sleep again.",
            "The group re-forms its circle, a ritual older than sense.",
            "Another round begins. The soil is patient and very well fed.",
        ],
        "survival": [
            "{player} lives to breed another season. The females remain unconvinced.",
            "The chamber spares {player}. Nature, briefly, looks away.",
            "{player} survives, and the gene pool registers a formal complaint.",
            "Against all selective pressure, {player} continues.",
            "{player} lives. The scavengers disperse, muttering.",
            "The herd absorbs {player} back in. Nobody looks pleased about it.",
            "{player} survives and immediately resumes the behaviour that nearly ended them.",
            "Nature selects {player} for another few minutes. It is not an endorsement.",
            "{player} walks away. Four million years of evolution exhale.",
            "The chamber clicks. {player} remains, technically, a success story.",
            "{player} endures. The species does not improve.",
            "{player} lives, and somewhere a narrator sighs into a warm microphone.",
            "The predator passes over {player}. Even it has standards.",
            "{player} survives the encounter and learns nothing from it whatsoever.",
            "{player} is spared. The soil will simply wait.",
            "The herd parts for {player}, less from respect than from ongoing disbelief.",
            "{player} lives. Their contribution to the species remains theoretical.",
            "The chamber declines {player}. So, historically, has everything else.",
            "{player} survives, and the crew stop reaching for the good lens.",
            "{player} continues. Evolution files this under pending.",
            "The bullet passes {player} by, as does most opportunity.",
            "{player} lives. The circling begins again shortly.",
            "{player} remains upright, which is the only measurable achievement here.",
            "Nature spares {player} on a technicality nobody wishes to examine.",
            "{player} survives. The herd's average intelligence holds steady, regrettably.",
            "{player} lives another day in a habitat that has actively tried to prevent it.",
            "The chamber is merciful. The species remains a work in progress.",
            "{player} escapes predation, mostly by not being worth the effort.",
            "{player} survives, and the vultures return to whatever vultures do.",
            "{player} lives. The narrator declines to call this a triumph.",
        ],
        "death": [
            "{victim} is culled. The herd is measurably smarter within seconds.",
            "The weak are taken first. {victim} was not weak, merely stupid. Nature makes no distinction.",
            "And so {victim} returns to the soil, contributing more in death than in life.",
            "{victim} falls. The scavengers had been waiting with visible impatience.",
            "The chamber selects {victim}. Selection is, after all, the mechanism.",
            "{victim} drops. The herd resumes grazing within four seconds.",
            "Nature has corrected an error. The error was {victim}.",
            "{victim} reached level {level} and then reached the ground.",
            "The species loses {victim} and gains, on balance, quite a lot.",
            "{victim} is taken. The crew were told not to intervene and are quietly relieved.",
            "A life ends. The plain does not pause to acknowledge it.",
            "{victim} joins the soil, the roots, and the general downward trend.",
            "{victim} falls. Somewhere a slightly better-adapted cousin thrives.",
            "The bullet finds {victim}. It did not have to look hard.",
            "{victim} has been removed from the breeding population, permanently and loudly.",
            "The herd steps over {victim} on the way to the water.",
            "{victim} dies as they lived: confidently, and incorrectly.",
            "Level {level}, and every one of those levels now belongs to the worms.",
            "{victim} expires. The ecosystem thanks them for the protein.",
            "The camera holds on {victim}. The narrator says nothing kind.",
            "{victim} is claimed. Four billion years of life on this planet produced that.",
            "Nature's ledger balances. {victim} was the entry.",
            "{victim} falls, and the flies arrive with indecent speed.",
            "The gene line ends here. Most would call that a mercy.",
            "{victim} is dead. The documentary will not be dedicating an episode.",
            "{victim} goes down. The pack does not mourn; the pack redistributes.",
            "The chamber fires. {victim} completes their transition into fertiliser.",
            "{victim} dies at level {level}, having climbed a long way to fall a very short one.",
            "{victim} is taken by the only predator that ever really mattered: themselves.",
            "The plain accepts {victim} without comment, as it accepts everything.",
        ],
        "winner": [
            "{winner} inherits the territory, the resources, and an empty savannah.",
            "The dominant male stands alone. This is not triumph. This is what is left.",
            "{winner} survives the season. The season was not impressed.",
            "{winner} claims the watering hole and every corpse around it.",
            "The last of the herd is {winner}, who now has nobody to warn them about anything.",
            "{winner} wins. Evolution grudgingly permits it.",
            "{winner} holds the territory. The territory is mostly bodies.",
            "The species continues through {winner}, which is a genuinely alarming sentence.",
            "{winner} outlasts the group. Loneliness is the prize nature always offers.",
            "{winner} stands. The narrator lowers his voice for no particular reason.",
            "The strongest survives. In this case the luckiest, which nature counts identically.",
            "{winner} takes the plain, the pot, and a lifetime of hearing that click.",
            "{winner} endures. The credits roll over an empty landscape.",
            "One creature remains. The ecosystem will regrow around {winner} eventually.",
            "{winner} is the last of their group. The soil holds the rest of it.",
            "Nature crowns {winner}. Nature crowns whoever is standing; it is not fussy.",
            "{winner} survives to pass on genes that clearly should not be passed on.",
            "The crew pack up. {winner} is left alone with the flies and the winnings.",
            "{winner} wins the territory and every unpleasant memory in it.",
            "The herd is gone. {winner} grazes alone, which is not how this species works.",
            "{winner} triumphs, and four million years of evolution quietly reconsiders.",
            "{winner} remains standing. The narrator declines to explain why.",
            "The apex is {winner}, by process of elimination and nothing else.",
            "{winner} wins. There is nobody left to establish dominance over.",
            "{winner} claims everything, which now consists of dirt and silence.",
            "The season ends with {winner}, a full pot, and a thoroughly reduced population.",
            "{winner} lives. The documentary ends here, mercifully.",
            "The final specimen is {winner}. Preservation efforts are not recommended.",
            "{winner} survives. Nature will get to them eventually; it is very patient.",
            "{winner} stands alone at the waterhole, king of absolutely nothing.",
        ],
    },
    "airline": {
        "taunt": [
            "Cabin crew, doors to manual, cross-check, and prepare for fatalities.",
            "In the unlikely event of a loss of cabin pressure, a revolver will drop from the ceiling.",
            "We know you have a choice when you fly, and we are delighted you chose this.",
            "You have been selected for random additional screening. The screening is ballistic.",
            "Your chamber is now in the upright and locked position.",
            "Boarding is now open for Group 6, the doomed.",
            "Please ensure your tray table is stowed and your affairs are in order.",
            "This is a non-smoking flight. The barrel is exempt.",
            "For your safety, please remain seated while the aircraft is killing you.",
            "The captain has switched on the seatbelt sign. The captain has also stopped caring.",
            "Your seat is a flotation device. It is not a bullet device. We checked.",
            "Please locate your nearest exit, bearing in mind it may be behind you and metaphysical.",
            "We are currently experiencing light turbulence and heavy mortality.",
            "Your ticket is non-refundable, non-transferable, and increasingly irrelevant.",
            "Duty free is now open. Nothing on the trolley will help.",
            "This aircraft is equipped with six chambers and no reasonable explanation.",
            "Please review the safety card, which this year is just a photograph of a grave.",
            "Overhead lockers may have shifted during the flight. So may your priorities.",
            "We apologise for the wait. The gun does not apologise for anything.",
            "You did not pay for extra legroom, and now you will not need it.",
            "Ground staff have confirmed your final destination. You were not consulted.",
            "Please switch all devices to flight mode and your expectations to zero.",
            "Our loyalty programme awards one point per mile and none for surviving.",
            "The emergency lighting will guide you to the exit. The bullet is faster.",
            "Priority boarding is available for anyone in a genuine hurry to die.",
            "Cabin crew are trained in first aid, evacuation, and pretending not to hear screaming.",
            "There is no meal service on this route. There is, however, a service.",
            "Your carry-on exceeds the size limit. Your lifespan does not.",
            "We are pleased to announce this flight is operating with a full complement of idiots.",
            "The safety demonstration is now complete. It was, as always, entirely pointless.",
        ],
        "round_start": [
            "We are third in the queue for the runway and second in the queue for the morgue.",
            "Cabin crew, prepare the next round. Arm doors and cross-check.",
            "Welcome aboard. This service terminates for at least one of you.",
            "We have been cleared for another round by a tower that is not paying attention.",
            "Boarding continues. The manifest continues to shorten.",
            "Ladies and gentlemen, we are experiencing a slight delay in your deaths.",
            "The cabin is being prepared for the next departure. Bring a mop.",
            "This is the final call for the next chamber. Final in every sense.",
            "The fasten seatbelt sign is illuminated for a reason nobody will enjoy.",
            "We begin our descent. The aircraft does not. Someone else will.",
            "Another round begins on schedule, which for this airline is unprecedented.",
            "The gate has changed. The gun has not.",
            "Cabin crew take their seats. They know what this bit sounds like.",
            "We are cruising at thirty-six thousand feet and one very short lifespan.",
            "The next round begins. Please accept this voucher for one free bereavement.",
            "The aircraft has been refuelled, re-catered, and re-loaded.",
            "Another round. Your patience during this ongoing massacre is appreciated.",
            "The captain has turned off the seatbelt sign. Move freely about the carnage.",
            "We are next for departure. Someone is next for something considerably worse.",
            "Push-back complete. Cylinder rotation complete.",
            "The safety demonstration begins again for people who will not watch it again.",
            "Round two. Same aircraft, fewer passengers, identical catering.",
            "Air traffic control has released us. Nobody has released you.",
            "We apologise for the delay, which was caused by paperwork and a body.",
            "The cabin lights are dimmed for the next round, for atmosphere and spatter reasons.",
            "Doors are closed. Nobody is getting off this thing intact.",
            "The next chamber is now boarding by row number, back to front, as usual.",
            "We have a short window for this round. The window is not an exit.",
            "The trolley comes down the aisle. So does the revolver.",
            "Another sector begins. Crew are on hour fourteen and cannot be held responsible.",
        ],
        "survival": [
            "{player} has been rebooked onto the 06:40 with no compensation whatsoever.",
            "{player} survives. Their seat does not recline and never will.",
            "The chamber clicks. {player} remains on standby for death.",
            "{player} lives. Their upgrade request has again been declined.",
            "{player} survives, and is entitled to absolutely nothing under any regulation.",
            "The gun clicks. {player}'s connection is still going to be tight.",
            "{player} lives. Cabin crew move on without breaking eye contact.",
            "{player} survives and immediately reclines into the knees of a stranger.",
            "{player} is spared. Their luggage remains missing.",
            "The chamber is empty. {player} returns to their middle seat.",
            "{player} lives, having been bumped from this death to a later one.",
            "{player} survives. The airline notes this was not covered anyway.",
            "{player} makes it. The captain sounds mildly disappointed over the intercom.",
            "{player} lives and is awarded four hundred air miles, expiring Tuesday.",
            "The bullet declines {player}. So did the upgrade desk, twice.",
            "{player} survives, still holding a boarding pass for a flight that will not depart.",
            "{player} lives. Please remain seated until the aircraft has come to a complete stop.",
            "{player} is spared and immediately asks for a second gin.",
            "The chamber clicks. {player}'s tray table remains, inexplicably, still down.",
            "{player} survives. Ground staff mark them as pending.",
            "{player} lives. There is no meal left by the time the trolley reaches them.",
            "{player} makes it through, in the brace position, unnecessarily.",
            "{player} survives, and the seatbelt sign switches off in what feels like sarcasm.",
            "The gun spares {player}, who was already writing a strongly worded complaint.",
            "{player} lives. Their status has been downgraded to Silver regardless.",
            "{player} survives with one bag, one nerve, and no dignity.",
            "The chamber passes {player} by, much like the drinks trolley did.",
            "{player} lives. They will still be charged for the seat selection.",
            "{player} survives, which the airline is treating as a schedule irregularity.",
            "{player} makes it. The overhead locker above them opens ominously anyway.",
        ],
        "death": [
            "{victim} has reached their final destination ahead of schedule.",
            "We apologise for the delay to {victim}, caused by a bullet arriving on time.",
            "{victim}'s remains will be available at carousel four. Eventually.",
            "{victim} has been offloaded. Their bag continues to Lisbon without them.",
            "The chamber fires. {victim} is now permanently in flight mode.",
            "{victim} has disembarked through an exit that was not on the safety card.",
            "Cabin crew request that passengers step over {victim} in an orderly fashion.",
            "{victim} is deceased. The airline classifies this as a minor schedule disruption.",
            "{victim} dies at level {level}, having earned enough miles for exactly nothing.",
            "{victim} will not be continuing to the final destination, or any destination.",
            "The seatbelt sign remains on. {victim} is no longer able to comply.",
            "{victim}'s ticket has been marked no-show, which is technically accurate.",
            "{victim} has been removed from the manifest and, more slowly, from the carpet.",
            "The captain announces {victim}'s death in the same voice used for the local time.",
            "{victim} dies. A voucher for eight pounds is issued to their next of kin.",
            "{victim} is gone. Their seat is immediately sold to someone on standby.",
            "The gun fires. {victim} has completed their journey with us today.",
            "{victim}'s emergency exit training has been comprehensively wasted.",
            "{victim} expires. The crew continue the beverage service around them.",
            "{victim} is dead. Please note this does not qualify for a refund.",
            "The chamber fires. {victim} is now the reason for the delay.",
            "{victim} has passed away. Their frequent flyer points die with them, per the terms.",
            "{victim} goes down in row 32B, which is somehow the most tragic detail.",
            "{victim}'s claim is being processed by a department that closed in 2019.",
            "{victim} dies. Ground crew are dispatched with a hose and low morale.",
            "{victim} has been permanently grounded.",
            "The bullet lands. {victim} does not.",
            "{victim} dies at level {level}. The upgrade never came through, and now never will.",
            "{victim} is offloaded for operational reasons, the operation being a revolver.",
            "{victim} has left the aircraft. Not via the door.",
        ],
        "winner": [
            "{winner} disembarks. Their luggage went to Lisbon.",
            "{winner} is upgraded to the only remaining seat.",
            "{winner} survives the flight and is charged for the privilege.",
            "{winner} wins. Please remain seated; there is nobody left to disturb.",
            "The captain thanks {winner} for flying with us and apologises for everyone else.",
            "{winner} takes the pot and a voucher redeemable against a flight that does not exist.",
            "{winner} exits through the front. Everyone else exits through the floor.",
            "{winner} is now the airline's most valued customer, largely by attrition.",
            "{winner} survives. Their claim is denied for a reason not yet invented.",
            "{winner} wins and is bumped to Gold status, which changes nothing.",
            "The cabin is cleared. {winner} is the only thing left worth boarding.",
            "{winner} walks off the aircraft. The others require a trolley.",
            "{winner} takes the winnings, the aisle, and every remaining bread roll.",
            "{winner} survives, and the safety demonstration was once again irrelevant.",
            "{winner} wins. Cabin crew thank them and begin a fourteen-hour turnaround.",
            "{winner} is the last passenger standing and the first to reach the taxi rank.",
            "{winner} takes the pot. Baggage reclaim takes everything else.",
            "The aircraft is empty except for {winner} and a great deal of paperwork.",
            "{winner} wins and is offered a survey about their experience today.",
            "{winner} survives. The airline notes this and quietly raises the fare.",
            "{winner} disembarks alone, which is exactly what they paid for and more.",
            "{winner} wins the pot and the aisle seat, in that order of importance.",
            "{winner} lives. Ground staff wave them through with visible confusion.",
            "{winner} survives and receives priority boarding for the rest of their life.",
            "{winner} takes everything. Everyone else takes the carousel.",
            "{winner} is the sole survivor and will appear in the incident report as the other one.",
            "{winner} wins. The seatbelt sign finally goes off. It means nothing now.",
            "{winner} exits the terminal alive, which puts them well ahead of the group.",
            "{winner} claims the pot. The airline claims no responsibility whatsoever.",
            "{winner} is the last one aboard. The flight is now, at last, on time.",
        ],
    },
    "commentary": {
        "taunt": [
            "He has had a difficult season and he is about to have a difficult afternoon.",
            "Big moment for the lad. Career-defining. Career-ending, potentially, but definitely defining.",
            "You have to fancy the gun here.",
            "The crowd has gone quiet. The commentary box has not, contractually.",
            "The stats overlay says he has never done this before. It is about to be right forever.",
            "He is in the form of his life, which is a phrase we may need to revisit.",
            "No substitutions available at this stage. No substitutions available ever, really.",
            "This is what he trains for. Nobody trains for this. I have misspoken.",
            "The manager cannot watch. The manager has, in fairness, seen the squad list.",
            "He has been quiet all game. He is about to be extremely loud once.",
            "And this is the moment the highlight reel has been waiting for, sadly.",
            "The bench is on its feet. The bench is also entirely full, which tells its own story.",
            "You cannot legislate for this. Legal have confirmed they have tried.",
            "He is a big-game player, and this is certainly a game with a big gun in it.",
            "The pundits picked him for the drop. They rarely mean it this literally.",
            "He has ice in his veins and, shortly, other things.",
            "That is the sound of eighty thousand people realising what they paid for.",
            "The fourth official indicates a minimum of one death added on.",
            "He is going for it. Oh, he is absolutely going for it. Why is he going for it.",
            "The captain's armband will not save him. It never saves anyone.",
            "It has been a rebuilding year, and it is about to require more rebuilding.",
            "He has the crowd behind him, which at this range is the safest place to be.",
            "The gaffer said this squad had no depth. The squad is about to have less.",
            "One in six. Those are the odds. He has not been told the odds.",
            "Both hands on the weapon. Textbook. Utterly pointless, but textbook.",
            "The physio is stretching. The physio knows something.",
            "That is a professional foul against himself, and the rules have nothing for it.",
            "He is playing through the pain. The pain has not started yet.",
            "The commentary team have been told to remain neutral. We have money on this.",
            "Here we go. Absolutely no reason for this to be happening, and here we go.",
        ],
        "round_start": [
            "Second half. Same gun. Fewer players.",
            "We are back after the break, and so is the revolver.",
            "The teams are out. Some of them will not be coming back in.",
            "Kick-off in the next round, and the atmosphere is what I would call medical.",
            "The whistle goes. The cylinder goes with it.",
            "Fresh round, fresh chamber, same appalling decision-making.",
            "We rejoin the action, using the word action generously.",
            "The players take their positions. The undertaker takes notes.",
            "Extra time begins, which for somebody here is a cruel choice of words.",
            "New round. The groundsman has already been warned.",
            "We go again. The medical staff have not sat down since the first round.",
            "The referee checks his watch and, I suspect, his life choices.",
            "Play resumes. So does the bleeding, shortly.",
            "The stadium is full. The squad is not, and shrinking.",
            "Round two of a contest that should never have received a broadcast licence.",
            "The lineup has changed since last round, involuntarily.",
            "The teams have swapped ends. The gun does not care which end.",
            "We are underway again after a lengthy stoppage for the obvious reason.",
            "A new round begins and the sponsors already regret the association.",
            "Here comes the next passage of play, and it is a short one.",
            "The manager makes a tactical change: he sits further from the table.",
            "Play restarts. The scoreboard operator has given up entirely.",
            "New round. The crowd noise drops to something closer to a hospice.",
            "We resume, with the reminder that this competition has no relegation, only removal.",
            "The cylinder spins and the stadium clock starts. Neither is in anyone's favour.",
            "Back underway. Someone in the gantry is quietly updating the obituary graphics.",
            "The next round begins. The commentary box has run out of euphemisms.",
            "Play is live again. So, for now, is everybody.",
            "Another round. The trophy is polished. The floor is not.",
            "And we are off, in a fixture that has already exceeded its casualty projections.",
        ],
        "survival": [
            "Oh, {player} will want that one back. Not the bullet. The decision.",
            "{player} survives, and you can see the relief. And the urine.",
            "{player} gets away with it. Absolutely gets away with it.",
            "The chamber clicks and {player} lives to be substituted another day.",
            "{player} escapes. That is the kind of luck you cannot coach.",
            "{player} survives. The bench erupts, mostly out of surprise.",
            "That is a let-off for {player}, and they know it.",
            "{player} lives. Somewhere a statistician is furiously recalculating.",
            "{player} walks away, and the replay will not be kind about how.",
            "{player} survives, and the manager has aged visibly on the touchline.",
            "The gun clicks. {player} punches the air with hands that will not stop shaking.",
            "{player} makes it. Not through skill. Let us be honest about that.",
            "{player} survives. The crowd cheers someone who has achieved nothing whatsoever.",
            "{player} lives. Expect that face on the front of tomorrow's paper regardless.",
            "{player} survives, and the sponsors breathe out.",
            "That is {player} through to the next passage, on borrowed time and nothing else.",
            "{player} lives. The physio sits back down, cautiously.",
            "{player} survives, and immediately celebrates in front of the away end. Bold.",
            "{player} makes it. That is character. That is also just probability.",
            "The chamber is empty. {player} lives to disappoint us properly later.",
            "{player} survives. Take nothing away from them, because there is nothing to take.",
            "{player} lives, and the commentary box exhales as one.",
            "{player} gets through. The gaffer will call that game management.",
            "{player} survives. The replay runs from four angles and none of them flatter.",
            "{player} lives to play on. Somebody upstairs likes them, which is baffling.",
            "That is a stone-cold escape for {player}, and the fans know it.",
            "{player} survives. Nothing in their technique deserves this.",
            "{player} lives, and the crowd chant their name, which will not help their judgement.",
            "{player} makes it through and looks straight down the camera. Unwise.",
            "{player} survives. We go again, and so, remarkably, does {player}.",
        ],
        "death": [
            "And that is the end of a promising career. And {victim}.",
            "{victim} goes down. The physio is walking, not running. He knows.",
            "Replay in slow motion, and yes, that is exactly as bad as it looked at full speed.",
            "{victim} is down and this one does not look good at all.",
            "The stretcher is out. The stretcher is, frankly, ceremonial at this point.",
            "That is {victim}'s season over. And several other things.",
            "{victim} falls. The crowd falls silent. The sponsors keep the logo up.",
            "Oh, and {victim} has been taken out of the game permanently.",
            "{victim} dies at level {level}, having peaked in the warm-up.",
            "That is a red card, a stretcher, and a funeral, in quick succession.",
            "{victim} is gone. The graphics team already had the career stats ready.",
            "The whistle goes for {victim}, and it is the full-time one.",
            "{victim} does not get up. He is not going to get up.",
            "The fourth official is signalling for something the rulebook does not cover.",
            "{victim}'s number goes up on the board. It is not a substitution.",
            "The commentary box has fallen silent, which for us is unprecedented.",
            "{victim} is dead, and I am obliged to tell you the score is still level.",
            "A devastating blow for {victim} and, more importantly, the squad depth.",
            "{victim} exits the field of play horizontally.",
            "{victim} hits the deck. That is going to be the image of the tournament.",
            "The crowd behind the goal saw it up close and will need counselling.",
            "{victim} is down, and the manager has not looked up from his notes.",
            "A tragic end for {victim}, who was, statistically, always going to be the one.",
            "{victim} at level {level}. All that development, all those minutes, gone in one pull.",
            "{victim} is dead. We will have the highlights for you after the break.",
            "The groundsman is already looking at the state of the six-yard box.",
            "{victim} falls. Somewhere a fantasy manager screams into a cushion.",
            "That is {victim} finished. Talk of a testimonial has already begun.",
            "{victim} goes down and the away end is celebrating, which is poor form frankly.",
            "{victim} is gone. And they said this fixture lacked entertainment.",
        ],
        "winner": [
            "Player of the match, {winner}. Sponsored, as ever, by a bookmaker who saw this coming.",
            "{winner} takes it, and will be doing the rounds on breakfast television explaining this.",
            "{winner} wins, and the trophy is presented on a pitch that needs replacing.",
            "That is the whistle. {winner} has done it. Nobody else has done anything.",
            "{winner} lifts the trophy with hands that will never be steady again.",
            "{winner} wins it. And what a squad they had, briefly.",
            "The final score: {winner} one, everybody else deceased.",
            "{winner} is the champion, in a competition with no surviving runners-up.",
            "{winner} takes the pot, the plaudits, and a lifetime ban from this venue.",
            "They will build a statue of {winner}. Slightly away from the others.",
            "{winner} wins, and the post-match interview is going to be something.",
            "That is {winner}, champion, and a squad list that now fits on a napkin.",
            "{winner} has done it. Against the odds. Against, honestly, all sense.",
            "The trophy goes to {winner}. The paperwork goes to the coroner.",
            "{winner} wins. The manager is already talking about next season, optimistically.",
            "{winner} celebrates alone, which is the only way this could have ended.",
            "{winner} takes it on the final pull, and the gantry erupts.",
            "The champion is {winner}. There will be an open-top bus and very few passengers.",
            "{winner} wins. Cue the confetti, and the hosing down.",
            "{winner} takes the title. The trophy cabinet had space; so does the changing room.",
            "{winner} is the last one standing, and that is the entire report.",
            "{winner} wins, and the pundits are calling it a masterclass. It was one in six.",
            "{winner} claims it. The medal is heavier than the achievement.",
            "That is full time. {winner} survives; the fixture list does not.",
            "{winner} lifts it. Somewhere a kit man looks at the laundry with real fear.",
            "{winner} wins. We will be back next week, staffing permitting.",
            "{winner} takes the trophy home. The rest go somewhere colder.",
            "{winner} is champion. A remarkable achievement in a field of, latterly, one.",
            "{winner} has won it, and the sponsors' banner is unfortunately still legible behind them.",
            "{winner} wins. From all of us in the commentary box: what the hell was that.",
        ],
    },
}

ADDITIONAL_THEME_EXPANSIONS: dict[str, dict[str, list[str]]] = {
    "corporate": {
        "taunt": [
            "We are not colleagues; we are a family. Specifically, the kind with a suspicious life-insurance policy.",
            "Your wellness app noticed elevated stress and recommended fewer bullets per quarter.",
            "The team needs your death to be more cross-functional. Please involve Finance.",
            "An AI has already drafted your condolence email. It calls you a valued first-name-placeholder.",
            "Your Teams status says Available. The chamber intends to correct that.",
            "A consultant charged forty grand to put your mortality on a two-by-two matrix.",
        ],
        "round_start": [
            "Daily stand-up begins. Sitting down afterward is increasingly optional.",
            "Quarterly targets reset: one bullet, six chambers, infinite shareholder value.",
            "The town hall opens with transparency, accountability, and a concealed exit strategy.",
            "The merger is complete. Life and death are now one badly managed department.",
            "Sprint planning begins. The sprint is toward the fucking emergency exit.",
            "Leadership unveils a bold new strategy: let the revolver choose the org chart.",
        ],
        "survival": [
            "{player} survives and receives a calendar invite titled Quick Chat.",
            "The chamber clicks. {player}'s manager takes credit for the successful outcome.",
            "{player} lives, but their annual review says they lacked commitment.",
            "Finance confirms {player} remains a depreciating asset.",
            "{player} survives the pull and is rewarded with a mandatory resilience webinar.",
            "The bullet misses {player}. Their promotion does too.",
        ],
        "death": [
            "{victim} is gone, but their inbox has been reassigned to someone cheaper.",
            "The chamber completes {victim}'s exit interview in one very direct question.",
            "{victim} gave one hundred and ten percent. Ballistics took the extra ten.",
            "Payroll removes {victim} before the medic checks for a pulse. Outstanding alignment.",
            "{victim}'s desk is listed on the internal marketplace while still warm.",
            "Management describes {victim}'s death as a difficult but exciting headcount opportunity.",
        ],
        "winner": [
            "{winner} becomes Employee of the Month by process of elimination. Very literal elimination.",
            "The board rewards {winner} with equity worth almost as much as the funeral flowers.",
            "{winner} is now the entire department and still somehow has too many meetings.",
            "Leadership congratulates {winner} in a message clearly written for someone else.",
            "{winner} wins the corporate ladder after everyone above them falls off it.",
            "The CEO shakes {winner}'s hand, then asks whether they can cover the weekend.",
        ],
    },
    "reaper_office": {
        "taunt": [
            "Death cannot come to the gun right now. Please leave your name and last words after the bang.",
            "The Reaper has seen plagues, wars, and empires fall. Your decision still made him say, 'Fucking hell.'",
            "Your estimated wait time is one to six trigger pulls.",
            "Mortality Services values your pulse. That is why they are taking it.",
            "The Reaper checks the roster and draws a tiny coffin beside your name.",
            "Death's office has casual Friday. The corpses are still business casual.",
        ],
        "round_start": [
            "The skeleton staff begins another shift. For once, that phrase is literal.",
            "Death answers the phones, reloads the chamber, and regrets not becoming an accountant.",
            "The mortality help desk opens. Nobody here is getting help.",
            "Another batch of living complaints enters terminal processing.",
            "The Reaper starts a new spreadsheet titled People About To Become Past Tense.",
            "A bell rings in the afterlife. Someone has pressed Take Next Customer.",
        ],
        "survival": [
            "{player} survives because Death accidentally clicked Snooze for Eternity.",
            "The Reaper calls {player}'s number, mispronounces it, and takes someone else.",
            "{player} lives. Their file now has a passive-aggressive red flag on it.",
            "Death reaches for {player}, pulls a hamstring, and files workers' compensation.",
            "The chamber clicks. {player}'s soul remains in quality assurance.",
            "{player} is spared after the Reaper discovers their death requires manager approval.",
        ],
        "death": [
            "{victim} meets Death and immediately asks whether there is parking validation.",
            "The Reaper clocks {victim} out, permanently, then forgets to submit the timesheet.",
            "{victim} becomes another unread notification in Death's overflowing inbox.",
            "The chamber fires. Death whispers, 'Finally, a ticket I can close.'",
            "{victim}'s soul arrives without an appointment and is charged the walk-in fee.",
            "Death files {victim} under F for Fuck Around, Findings Thereof.",
        ],
        "winner": [
            "{winner} survives because Death has exceeded this month's collection quota.",
            "The Reaper grants {winner} an extension, mostly to avoid the paperwork.",
            "{winner}'s file is returned with the note: annoyingly persistent.",
            "Death congratulates {winner}, then adds them on LinkedIn for later.",
            "{winner} leaves the office alive. The exit survey is fucking glowing.",
            "The Reaper watches {winner} go and quietly moves their name to Monday.",
        ],
    },
    "insurance": {
        "taunt": [
            "The insurer would like proof you were alive before this conversation began.",
            "Your policy includes roadside assistance but apparently not table-side stupidity.",
            "The gun is in network. The emergency room is mysteriously not.",
            "An actuary just felt a disturbance in the spreadsheet and bought another yacht.",
            "Your coverage has a bullet-point list. Unfortunately, one bullet is very literal.",
            "Customer service assures you the chamber is working as designed.",
        ],
        "round_start": [
            "Open enrollment begins. Available plans are Bad, Worse, and Loaded.",
            "The risk pool resets and immediately develops a deep red stain.",
            "Another round begins after a brief word from nobody willing to insure it.",
            "The claims department reloads the reason for denial.",
            "A fresh policy period starts with zero grace and one live round.",
            "The cylinder spins while an actuary whispers, 'Oh, this is beautiful.'",
        ],
        "survival": [
            "{player} survives, but the click is billed as an out-of-network procedure.",
            "The gun fails to kill {player}. Insurance calls that unnecessary treatment.",
            "{player} lives and receives a premium increase for reckless continued existence.",
            "The chamber clicks. {player}'s claim remains under review until the heat death of the universe.",
            "{player} keeps breathing, an activity now subject to prior authorization.",
            "The bullet declines {player}; the insurer still charges a projectile co-pay.",
        ],
        "death": [
            "{victim} dies before meeting the deductible. Impeccable cost containment.",
            "The insurer denies {victim}'s claim because being shot is apparently an elective procedure.",
            "{victim}'s beneficiaries receive a sympathy hamper with a bill inside.",
            "The chamber kills {victim}. Customer service asks whether they tried turning life off and on again.",
            "{victim}'s death is covered, but only on alternate Tuesdays in leap years.",
            "An assessor photographs {victim}, circles the bullet hole, and writes normal wear and tear.",
        ],
        "winner": [
            "{winner} survives and becomes the insurer's least favourite data point.",
            "The grand payout goes to {winner}, minus fees, taxes, and the concept of happiness.",
            "{winner} wins. Their reward statement says actual value may be emotionally lower.",
            "The actuary congratulates {winner} through gritted, expensively insured teeth.",
            "{winner} remains alive, forcing the policy to auto-renew at an obscene rate.",
            "The insurer sends {winner} a gold card redeemable for one-third of a therapist.",
        ],
    },
    "true_crime": {
        "taunt": [
            "The documentary opens with your Facebook photo from 2012. You already look guilty.",
            "Detectives found no motive, so the podcast invented three and a secret tunnel.",
            "Your final moments will be reenacted by someone hotter who blinks too much.",
            "The host describes the loaded gun as unassuming. It is visibly a loaded fucking gun.",
            "For bonus episodes, subscribers can hear the scream without tasteful piano.",
            "A Reddit detective has solved your death before it happens and blamed your spouse.",
        ],
        "round_start": [
            "Episode two begins with a map, red string, and absolutely no restraint.",
            "The narrator asks who could have predicted this. The answer is still everybody.",
            "Another round begins after a content warning nobody listens to.",
            "The producer dims the lights and brightens the affiliate links.",
            "The cylinder spins while an amateur sleuth misidentifies three innocent neighbours.",
            "Tonight's episode contains violence, coarse language, and a mattress discount code.",
        ],
        "survival": [
            "{player} survives and immediately receives twelve interview requests from people whispering professionally.",
            "The chamber clicks. {player}'s blurry yearbook photo is returned to storage.",
            "{player} lives, forcing the narrator to use the phrase shocking twist with zero shame.",
            "The podcast spares {player} but doxxes the wrong person for atmosphere.",
            "{player} survives. A six-part miniseries about why is already in pre-production.",
            "The gun clicks and {player} becomes the brave survivor who declined to comment forty-two times.",
        ],
        "death": [
            "{victim} dies. The host mispronounces their name consistently across all eight episodes.",
            "The chamber fires and {victim}'s family learns about it from a push notification.",
            "{victim} becomes a cold case for roughly four seconds before everyone notices the smoking gun.",
            "The podcast honours {victim} by putting their face behind the premium paywall.",
            "{victim}'s death is tragic, senseless, and somehow merch-ready by Friday.",
            "Investigators recover {victim}'s body and seventeen unsolicited theories from TikTok.",
        ],
        "winner": [
            "{winner} survives, but the documentary edits their relief into a suspicious smirk.",
            "The final episode names {winner} the sole survivor and heavily implies tax fraud for spice.",
            "{winner} wins. Online detectives ruin two unrelated marriages while celebrating.",
            "The host thanks {winner} for their bravery and asks them to repeat the crying with better audio.",
            "{winner} leaves alive and spends the next decade correcting the Wikipedia page.",
            "The truth sets {winner} free. The production contract absolutely does not.",
        ],
    },
    "reality_tv": {
        "taunt": [
            "The producers replaced the safety officer with a social-media intern and engagement is up.",
            "Please cry facing the light. Grief looks muddy from camera two.",
            "The gun has immunity this week. You do not.",
            "Your personality scored poorly, so production added a bullet arc.",
            "The host says this is the hardest decision ever made by somebody else's revolver.",
            "A boom mic dips into frame, briefly demonstrating more survival instinct than the cast.",
        ],
        "round_start": [
            "Welcome back. Since last week, legal has tripled and the cast has halved.",
            "Another elimination begins after thirty seconds of footage stretched across two ad breaks.",
            "The challenge resets. Makeup touches up the living and gives up on everyone else.",
            "The director calls action. The medic quietly calls dibs on the least messy one.",
            "A new round begins with a dramatic helicopter shot of a perfectly normal room.",
            "Contestants line up for the final challenge: maintaining eye contact with consequences.",
        ],
        "survival": [
            "{player} survives and whispers, 'I didn't come here to make friends,' to the paramedic.",
            "The gun clicks. {player}'s follower count rises by an ethically concerning amount.",
            "{player} lives and earns a luxury date with an unlicensed trauma counsellor.",
            "The judges save {player} because their breakdown tested exceptionally well with mums aged 34-49.",
            "{player} survives. Production adds a villain sting over their breathing.",
            "The chamber clicks and {player} receives one immunity necklace made of actual evidence.",
        ],
        "death": [
            "{victim} is eliminated and immediately blurred for broadcast standards.",
            "The gun fires. Production asks everyone to hold the reaction until after the sponsor bumper.",
            "{victim}'s final confessional is mostly a producer asking them to say it with more energy.",
            "The audience gasps as {victim} exits through the gift-shop-shaped hole in reality.",
            "{victim} loses the immunity challenge and all remaining immune function.",
            "The host tells {victim} their time is up with breathtaking fucking understatement.",
        ],
        "winner": [
            "{winner} receives a million dollars before tax and approximately nine dollars after therapy.",
            "The finale crowns {winner} while production sweeps the eliminated contestants under a tasteful montage.",
            "{winner} wins and launches a podcast before leaving the stage.",
            "The host congratulates {winner} with the warmth of someone already negotiating the reunion special.",
            "{winner} is America's next top person who happened not to get shot.",
            "The cameras stop. {winner} discovers the prize was exposure and one supermarket voucher.",
        ],
    },
}

ADDITIONAL_THEME_EXPANSIONS.update(
    {
        "family_game_night": {
            "taunt": [
                "Dad says it is house rules. The revolver says it owns the fucking house.",
                "Your aunt brought a casserole, a pyramid scheme, and several unresolved motives.",
                "The family photographer asks the survivors to squeeze together. Planning ahead is lovely.",
                "Tonight's passive aggression has been upgraded to active ballistics.",
                "The thermostat dispute was ugly, but the inheritance dispute brought ammunition.",
                "Everyone agreed not to discuss politics, so now the gun is carrying the conversation.",
            ],
            "round_start": [
                "Charades begins. The answer is generational trauma with a firearm.",
                "The casserole is cooling. The grudges remain piping fucking hot.",
                "Family meeting minutes will be recorded by the coroner.",
                "Monopoly resumes after someone replaces the little silver thimble with live ammunition.",
                "The board resets, Nan updates the will, and nobody makes eye contact.",
                "Game night continues after Mum moves the suspicious rug over the suspicious stain.",
            ],
            "survival": [
                "{player} survives. Mum says their cousin would have handled it more gracefully.",
                "The chamber clicks. Dad calls {player}'s flinch a generational weakness.",
                "{player} lives, but Aunt Carol starts the memorial fundraiser anyway.",
                "Nan congratulates {player}, then reminds them the bins still need taking out.",
                "{player} survives. Their sibling looks genuinely fucking disappointed.",
                "The gun spares {player}; the family group chat removes them from the photo regardless.",
            ],
            "death": [
                "{victim} dies. Dad asks whether anybody wants their leftovers.",
                "The family group chat changes its icon before {victim} is cold.",
                "The priest waits politely while everyone opens the inheritance spreadsheet.",
                "{victim} is remembered forever as the one who always made everything dramatic.",
                "The family removes {victim}'s place setting and asks somebody to pass the salt.",
                "The undertaker finds Nan's loyalty card in {victim}'s pocket. One more funeral and the next is free.",
            ],
            "winner": [
                "{winner} inherits the house and discovers the reverse mortgage was the real loaded weapon.",
                "{winner} finally controls the remote. There is nobody left to watch with them.",
                "Nan congratulates {winner}, then explains their dead sibling was still her favourite.",
                "{winner} is the sole survivor and is somehow still expected to host Christmas.",
                "The family awards {winner} the gravy boat and several generations of fresh trauma.",
                "{winner} leaves with the leftovers, the inheritance, and an exhausting number of police questions.",
            ],
        },
        "hell_bureaucracy": {
            "taunt": [
                "Your soul has been transferred through five departments and nobody knows why it is screaming.",
                "Before damnation, please select every square containing a traffic light.",
                "Hell's hold music is just your loved ones saying they warned you.",
                "The forms require blood, but the printer is out of fucking magenta.",
                "Your appointment is in nine hundred years. Fortunately, the gun accepts walk-ins.",
                "Please consent to eternal torment and twelve thousand pages of infernal cookies.",
            ],
            "round_start": [
                "Infernal quarterly processing begins. Screams may be monitored for quality assurance.",
                "The ticket dispenser catches fire and somehow improves the service.",
                "Break ended four hundred years ago. The demons are still emotionally unavailable.",
                "The eternal queue advances three places sideways.",
                "A demon supervisor stamps the ammunition APPROVED FOR NEEDLESS SUFFERING.",
                "The lift opens at Basement Infinity. Mind the existential gap.",
            ],
            "survival": [
                "{player}'s soul is returned because somebody misspelled the postcode.",
                "The chamber clicks. A demon tells {player} they have waited in the wrong queue.",
                "{player} survives but must resubmit their mortality in triplicate.",
                "Hell's system goes down, leaving {player} inconveniently alive.",
                "The gun clicks. The clerk stamps {player} INCOMPLETE and goes to lunch.",
                "{player} lives because the password-reset raven never arrived.",
            ],
            "death": [
                "{victim} reaches the front of the queue and is told death happened in the other building.",
                "Hell assigns {victim}'s soul a cubicle beside the screaming printer.",
                "{victim} dies and learns their six-century probation starts Monday.",
                "The chamber turns {victim}'s exit interview into an entrance interview.",
                "A demon hands {victim} a survey asking how satisfied they were with the fatality.",
                "At level {level}, {victim} is downgraded from damned to fucking administrative.",
            ],
            "winner": [
                "{winner} survives because Hell closed early for mandatory wellbeing training.",
                "{winner}'s complaint is escalated to Satan, who marks it resolved without reading it.",
                "A demon files {winner} as a duplicate soul and reluctantly lets them leave.",
                "{winner} escapes damnation and receives a parking fine on the way out.",
                "{winner} outlasts the gun, the queue, and three separate lunch breaks.",
                "The infernal audit finds {winner} too stubborn to process and writes the whole thing off.",
            ],
        },
        "doomed_circus": {
            "taunt": [
                "The clown says the gun is unloaded, but his shoes are full of spare bullets.",
                "The lion requested a union representative after seeing your safety briefing.",
                "There is a safety net. It is purely emotional and currently on smoke break.",
                "Your face paint is running. Your survival odds left in the clown car.",
                "The strongman cannot lift the crushing weight of this insurance premium.",
                "A mime is trapped in an invisible coffin and frankly showing off.",
            ],
            "round_start": [
                "The ringmaster proudly presents one bullet and a marquee full of poor judgement.",
                "The calliope starts playing. Every coroner within ten kilometres sighs.",
                "A clown reloads the revolver, honks twice, and violates seventeen safety codes.",
                "Ladies, gentlemen, and future evidence: the next act begins.",
                "The spotlight rises on a breathtaking display of workers' compensation fraud.",
                "The circus resumes beneath a banner reading THIS SEEMED CHEAPER THAN THERAPY.",
            ],
            "survival": [
                "{player} survives. A sad trombone plays from inside the gun.",
                "The chamber clicks and {player} is pelted with legally distinct consolation confetti.",
                "{player} lives, disappointing a clown who had already measured the coffin car.",
                "The bullet misses {player} and hits the last remaining shred of circus dignity.",
                "A trapeze artist catches {player}'s soul and tosses the confused bastard back in.",
                "{player} survives. The bearded lady mutters that fucking amateurs get all the luck.",
            ],
            "death": [
                "{victim} dies beneath the big top. The tiny hearse is somehow already idling.",
                "The cannon misfires correctly and promotes {victim} to permanent audience participation.",
                "{victim}'s death is ruled hilarious by twelve clowns and suspicious by everyone else.",
                "The ringmaster covers {victim} with a handkerchief. They do not come back. Shit magician.",
                "A seal balances the coroner's clipboard while {victim} misses the final bow.",
                "At level {level}, {victim} becomes the only circus ghost with an employee discount.",
            ],
            "winner": [
                "{winner} wins and is awarded one haunted clown car with seventeen previous owners.",
                "The crowd gives {winner} a standing ovation because the seats are covered in evidence.",
                "{winner} takes the trophy. It squirts something the lab refuses to identify.",
                "The ringmaster names {winner} Greatest Survivor on Earth and immediately books a rematch.",
                "{winner} escapes the circus, but the circus now knows their home address.",
                "Confetti falls for {winner}. Half of it is legal paperwork and the rest has teeth.",
            ],
        },
        "mad_scientist": {
            "taunt": [
                "The ethics board said no, so the scientist relabelled you miscellaneous lab equipment.",
                "Your survival has a p-value of who gives a shit; pull the trigger.",
                "The lab rats formed a union after watching the pilot study.",
                "The scientist promises the procedure is double-blind. Nobody can see because of the explosion.",
                "Your consent form was peer reviewed by three people who hate you.",
                "The grant proposal calls you renewable test material. Optimistic little fuckers.",
            ],
            "round_start": [
                "The experiment resumes after a brief evacuation and a much briefer apology.",
                "A new trial begins with rigorous controls and a scientist wearing oven mitts.",
                "The centrifuge stops. The screaming apparatus starts.",
                "Researchers prepare another statistically significant workplace incident.",
                "The professor shouts FOR SCIENCE, which legal confirms is not a defence.",
                "The lab resets the chamber and lowers its expectations for human progress.",
            ],
            "survival": [
                "{player} survives and is immediately asked to join the control group again.",
                "The chamber clicks. Researchers classify {player} as too angry to die.",
                "{player} lives, ruining the graph but dramatically improving the sequel funding.",
                "The bullet avoids {player}; the scientist calls it quantum cowardice.",
                "{player}'s vital signs continue despite several pages of very confident predictions.",
                "The experiment spares {player}. A lab rat gives them a tiny, deeply sarcastic clap.",
            ],
            "death": [
                "{victim} dies and is thanked in the paper somewhere between the mice and the coffee machine.",
                "The scientist records {victim}'s last words as a surprising amount of profanity.",
                "{victim} becomes proof that a larger sample size is not always good news for the sample.",
                "The chamber fires. Peer review requests that {victim} repeat the result twice.",
                "{victim}'s cause of death is listed as methodology with enthusiasm.",
                "At level {level}, {victim} finally achieves statistical insignificance.",
            ],
            "winner": [
                "{winner} survives and receives honorary authorship beneath fourteen people who did nothing.",
                "The Nobel committee blocks {winner}'s number and changes the locks.",
                "{winner} wins. The scientist celebrates by applying for funding to do it again.",
                "The final graph is one hundred percent {winner} and zero percent ethics approval.",
                "{winner} leaves with the prize and a side effect nobody can pronounce.",
                "Science marches forward over everyone except {winner}, the stubborn fucking outlier.",
            ],
        },
        "aussie": {
            "taunt": [
                "The RSL banned this game, and those mad bastards still run meat raffles next to the pokies.",
                "Every galah at the table says she'll be right. Statistically, one of you is full of shit.",
                "The gun has no rego, no roadworthy, and a boot full of terrible decisions.",
                "Call triple zero now and beat the post-trigger rush, you organised little legend.",
                "This chamber is more cooked than a servo pie forgotten behind the demister.",
                "The cylinder is doing a shoey with your remaining life expectancy.",
                "Your pub tab, your search history, and this gun are all about to catch up with you.",
                "A magpie watched you load the revolver and decided humans were the aggressive species.",
            ],
            "round_start": [
                "New round, same pack of galahs, slightly fewer functioning organs.",
                "The sunburnt country proudly presents tonight's dumbest fucking indoor activity.",
                "A tradie spins the chamber and says the safety guard was slowing production.",
                "The RSL raffle is drawn: first prize, a meat tray; second prize, catastrophic ventilation.",
                "The pokies stop jingling just long enough to hear the cylinder spin.",
                "Bunnings has snags. This shed has ballistics and absolutely no adult supervision.",
                "The ute is running, the esky is full, and the emergency plan is apparently fuck it.",
                "Another round starts because nobody wanted to be the soft cunt who went home.",
            ],
            "survival": [
                "The chamber clicks. {player} is luckier than a thong surviving a highway on-ramp.",
                "{player} lives and immediately claims they never flinched, the lying drongo.",
                "The gun spares {player}. A nearby magpie takes personal responsibility for finishing the job.",
                "{player} survives by the same miracle keeping that backyard trampoline out of the neighbour's pool.",
                "Click. {player} is still kicking, unlike the aircon at a rental inspection.",
                "{player} lives. The ambos call that beauty; the landlord calls it pre-existing damage.",
                "The bullet gives {player} a miss, proving even ammunition avoids awkward dickheads at the pub.",
                "{player} survives and celebrates like a seagull stealing chips from a toddler.",
            ],
            "death": [
                "Yeah nah, {victim} is fucked as a screen door on a submarine.",
                "{victim} gives the Darwin Award a Southern Cross and a fucking victory lap.",
                "The chamber fires. {victim} is now flatter than a cane toad on the Bruce Highway.",
                "{victim} has gone to the great Bunnings sausage sizzle in the sky. Onions still underneath.",
                "The ambos look at {victim}, look at each other, and say, 'Yeah nah, smoko first.'",
                "At level {level}, {victim} discovers that 'she'll be right' is not recognised medical treatment.",
                "{victim} is cactus. Even the flies have put on high-vis and clocked off.",
                "The gun turns {victim} from a loose unit into several smaller, administratively difficult units.",
            ],
            "winner": [
                "{winner} wins and is crowned King of the Fuckwits with a Bunnings bucket.",
                "Last drongo standing: {winner}. The prize is a warm beer and lifelong tinnitus.",
                "{winner} survives, shouts 'too easy,' and quietly deletes the footage of them sobbing.",
                "The pub gives {winner} a meat tray, a barring notice, and directions to the nearest therapist.",
                "{winner} walks out luckier than a bin chicken in an unattended kebab shop.",
                "Australia salutes {winner} by charging them double for an ambulance they did not call.",
                "{winner} is the last happy little Vegemite and the first suspect in a very short investigation.",
                "Yeah nah, fair fucking play: {winner} beat death and still has to work Monday.",
            ],
        },
    }
)

for _theme_key, _categories in ADDITIONAL_THEME_EXPANSIONS.items():
    for _category, _lines in _categories.items():
        ADDITIONAL_THEME_MESSAGES[_theme_key][_category].extend(_lines)

THEME_TAUNTS: dict[str, list[str]] = {
    "dark": DARK_BASE_TAUNTS + DARK_PRE_TURN_TAUNTS,
    "noir": NOIR_PRE_TURN_TAUNTS,
    "western": WESTERN_PRE_TURN_TAUNTS,
    "wasteland": WASTELAND_PRE_TURN_TAUNTS,
    "mafia": MAFIA_PRE_TURN_TAUNTS,
    "medieval": MEDIEVAL_PRE_TURN_TAUNTS,
    "arcade": ARCADE_PRE_TURN_TAUNTS,
    "greek": GREEK_PRE_TURN_TAUNTS,
    "sarcastic_farmer": SARCASTIC_FARMER_PRE_TURN_TAUNTS,
    "horror": HORROR_PRE_TURN_TAUNTS,
    "detective": DETECTIVE_PRE_TURN_TAUNTS,
}

for _theme_key, _theme_messages in ADDITIONAL_THEME_MESSAGES.items():
    THEME_TAUNTS[_theme_key] = _theme_messages["taunt"]

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

WASTELAND_ROUND_START = [
    "The Geiger counter clicks. Soon the gun might join in.",
    "A fresh round begins beneath a sky that gave up years ago.",
    "The cylinder spins while the last clean water changes hands.",
    "Another chamber is loaded from the emergency bad-idea reserve.",
    "The wasteland goes quiet. Even the mutants want to watch this shit.",
    "New round. Same apocalypse. Somehow worse planning.",
]

MAFIA_ROUND_START = [
    "The family calls another meeting. Attendance is about to become negotiable.",
    "A new round begins. The gun is loaded; the alibis are not.",
    "The Don spins the cylinder and asks everyone to remain respectful.",
    "Another chamber opens for business. Cash only. No witnesses.",
    "The table is set, the wine is poured, and somebody is absolutely fucked.",
    "New round. Kiss the ring, pull the trigger, mind the carpet.",
]

MEDIEVAL_ROUND_START = [
    "The herald announces another round and immediately hides behind a shield.",
    "A fresh chamber turns beneath the deeply confused gaze of the clergy.",
    "The court gathers for another trial by catastrophically modern weapon.",
    "New round. The king demands entertainment; the undertaker demands a deposit.",
    "The cylinder spins as the village idiot senses professional competition.",
    "Another round begins. The plague doctor calls this preventative medicine.",
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
    "sarcastic_farmer": SARCASTIC_FARMER_SURVIVAL_MESSAGES,
    "horror": HORROR_SURVIVAL_MESSAGES,
    "detective": DETECTIVE_SURVIVAL_MESSAGES,
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
    "sarcastic_farmer": SARCASTIC_FARMER_DEATH_MESSAGES,
    "horror": HORROR_DEATH_MESSAGES,
    "detective": DETECTIVE_DEATH_MESSAGES,
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
    "sarcastic_farmer": SARCASTIC_FARMER_WINNER_MESSAGES,
    "horror": HORROR_WINNER_MESSAGES,
    "detective": DETECTIVE_WINNER_MESSAGES,
}

for _theme_key, _theme_messages in ADDITIONAL_THEME_MESSAGES.items():
    THEME_SURVIVAL[_theme_key] = _theme_messages["survival"]
    THEME_DEATH[_theme_key] = _theme_messages["death"]
    THEME_WINNER[_theme_key] = _theme_messages["winner"]

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
    "wasteland": WASTELAND_ROUND_START,
    "mafia": MAFIA_ROUND_START,
    "medieval": MEDIEVAL_ROUND_START,
    "arcade": ARCADE_ROUND_START,
    "greek": GREEK_ROUND_START,
    "sarcastic_farmer": SARCASTIC_FARMER_ROUND_START,
    "horror": HORROR_ROUND_START,
    "detective": DETECTIVE_ROUND_START,
}
for _theme_key, _theme_messages in ADDITIONAL_THEME_MESSAGES.items():
    THEME_ROUND_START[_theme_key] = _theme_messages["round_start"]
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


RR_SETTINGS_SECTIONS = {
    "Lobby": ["join_timeout", "min_players", "max_players", "allow_start_early"],
    "Speed": [
        "fast_mode",
        "turn_timeout",
        "drama_multiplier",
        "show_status",
        "announce_round",
        "silent_rounds",
    ],
    "Gameplay": [
        "spin_mode",
        "sudden_death_after",
        "sudden_death_bullets",
        "mercy_chance",
    ],
    "Finale": ["allow_last_shot", "brawl_on_misfire", "duel_mode"],
    "Double Down": ["allow_double_down", "allow_pass_on_double_down"],
    "Flavor": ["allow_taunts", "theme", "victory_recap"],
    "Chaos": ["chaos_events", "chaos_chance"],
}

RR_SETTINGS_LIMITS = {
    "join_timeout": (30, 600),
    "min_players": (2, 20),
    "max_players": (0, 50),
    "turn_timeout": (5, 60),
    "sudden_death_after": (0, 50),
    "sudden_death_bullets": (1, 5),
    "mercy_chance": (0.0, 0.5),
    "chaos_chance": (0.0, 0.5),
    "drama_multiplier": (0.2, 3.0),
}

RR_SETTINGS_CHOICES = {
    "spin_mode": ["fixed", "spin_each_pull", "spin_each_turn"],
    "theme": [
        "dark", "noir", "western", "wasteland", "mafia", "medieval", "arcade",
        "greek", "sarcastic_farmer", "horror", "detective", "corporate",
        "reaper_office", "insurance", "true_crime", "reality_tv",
        "family_game_night", "hell_bureaucracy", "doomed_circus",
        "mad_scientist", "aussie", "nature_doc", "airline", "commentary",
        "mixed",
    ],
}

THEME_ALIASES = {
    "gallows": "western",
    "sarcasticfarmer": "sarcastic_farmer",
    "sarcastic-farmer": "sarcastic_farmer",
    "corporate_hr": "corporate",
    "reaper": "reaper_office",
    "grim_reaper": "reaper_office",
    "grim_reaper_office": "reaper_office",
    "truecrime": "true_crime",
    "reality": "reality_tv",
    "family": "family_game_night",
    "hell": "hell_bureaucracy",
    "circus": "doomed_circus",
    "scientist": "mad_scientist",
    "bogan": "aussie",
    "aussie_pub": "aussie",
    "documentary": "nature_doc",
    "attenborough": "nature_doc",
    "nature": "nature_doc",
    "plane": "airline",
    "flight": "airline",
    "cabin_crew": "airline",
    "sports": "commentary",
    "commentator": "commentary",
    "sports_desk": "commentary",
}

RR_SETTINGS_PRESETS = {
    "classic": {
        "fast_mode": False,
        "show_status": False,
        "announce_round": True,
        "spin_mode": "fixed",
        "allow_double_down": False,
        "chaos_events": False,
        "silent_rounds": False,
        "drama_multiplier": 1.0,
    },
    "quick": {
        "fast_mode": True,
        "show_status": False,
        "announce_round": False,
        "turn_timeout": 8,
        "silent_rounds": True,
        "drama_multiplier": 0.35,
    },
    "cinematic": {
        "fast_mode": False,
        "show_status": True,
        "announce_round": True,
        "allow_taunts": True,
        "victory_recap": True,
        "silent_rounds": False,
        "drama_multiplier": 1.5,
    },
    "chaos": {
        "allow_double_down": True,
        "allow_pass_on_double_down": True,
        "chaos_events": True,
        "chaos_chance": 0.3,
        "spin_mode": "spin_each_turn",
        "allow_taunts": True,
        "victory_recap": True,
    },
}


def _rr_pretty_key(key: str) -> str:
    return key.replace("_", " ").title()


class RRSettingValueModal(discord.ui.Modal):
    def __init__(self, panel: "RRSettingsPanelView", setting_key: str):
        super().__init__(title=f"Edit {_rr_pretty_key(setting_key)}")
        self.panel = panel
        self.setting_key = setting_key
        current = getattr(panel.settings, setting_key)
        limits = RR_SETTINGS_LIMITS.get(setting_key)
        label = "New value"
        if limits:
            label = f"Value ({limits[0]} to {limits[1]})"
        self.value_input = discord.ui.TextInput(
            label=label[:45],
            default=str(current),
            required=True,
            max_length=20,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        ok, message = await self.panel.cog.apply_rr_setting_value(
            self.panel.author_id,
            self.setting_key,
            str(self.value_input.value),
        )
        if ok:
            self.panel.reload_settings()
            self.panel.rebuild_components()
            await interaction.response.edit_message(
                embed=self.panel.build_embed(notice=message),
                view=self.panel,
            )
        else:
            await interaction.response.send_message(message, ephemeral=True)


class RRSettingsCategorySelect(discord.ui.Select):
    def __init__(self, panel: "RRSettingsPanelView"):
        options = [
            discord.SelectOption(
                label=category,
                value=category,
                default=category == panel.category,
            )
            for category in RR_SETTINGS_SECTIONS
        ]
        super().__init__(placeholder="Choose a settings category", options=options, row=0)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        self.panel.category = self.values[0]
        self.panel.setting_key = RR_SETTINGS_SECTIONS[self.panel.category][0]
        self.panel.rebuild_components()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)


class RRSettingsSettingSelect(discord.ui.Select):
    def __init__(self, panel: "RRSettingsPanelView"):
        descriptions = panel.cog.setting_descriptions()
        options = [
            discord.SelectOption(
                label=_rr_pretty_key(key),
                value=key,
                description=descriptions.get(key, "")[:100],
                default=key == panel.setting_key,
            )
            for key in RR_SETTINGS_SECTIONS[panel.category]
        ]
        super().__init__(placeholder="Choose a setting", options=options, row=1)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        self.panel.setting_key = self.values[0]
        self.panel.rebuild_components()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)


class RRSettingsChoiceSelect(discord.ui.Select):
    def __init__(self, panel: "RRSettingsPanelView"):
        key = panel.setting_key
        current = str(getattr(panel.settings, key))
        options = [
            discord.SelectOption(
                label=_rr_pretty_key(value),
                value=value,
                default=value == current,
            )
            for value in RR_SETTINGS_CHOICES[key]
        ]
        super().__init__(placeholder=f"Set {_rr_pretty_key(key)}", options=options, row=2)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        ok, message = await self.panel.cog.apply_rr_setting_value(
            self.panel.author_id,
            self.panel.setting_key,
            self.values[0],
        )
        if not ok:
            return await interaction.response.send_message(message, ephemeral=True)
        self.panel.reload_settings()
        self.panel.rebuild_components()
        await interaction.response.edit_message(
            embed=self.panel.build_embed(notice=message),
            view=self.panel,
        )


class RRSettingsPresetSelect(discord.ui.Select):
    def __init__(self, panel: "RRSettingsPanelView"):
        options = [
            discord.SelectOption(label="Classic", value="classic", description="Traditional roulette pacing."),
            discord.SelectOption(label="Quick", value="quick", description="Minimal delays and narration."),
            discord.SelectOption(label="Cinematic", value="cinematic", description="Status, flavor, and recap enabled."),
            discord.SelectOption(label="Chaos", value="chaos", description="Double downs, spins, and chaos events."),
        ]
        super().__init__(placeholder="Apply a settings preset", options=options, row=3)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        preset_name = self.values[0]
        settings = self.panel.cog.get_user_settings(self.panel.author_id)
        for key, value in RR_SETTINGS_PRESETS[preset_name].items():
            setattr(settings, key, value)
        await self.panel.cog.set_user_settings(self.panel.author_id, settings)
        self.panel.reload_settings()
        self.panel.rebuild_components()
        await interaction.response.edit_message(
            embed=self.panel.build_embed(notice=f"Applied the **{preset_name.title()}** preset."),
            view=self.panel,
        )


class RRSettingsPanelView(discord.ui.View):
    def __init__(self, cog: "Russian", author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = int(author_id)
        self.category = next(iter(RR_SETTINGS_SECTIONS))
        self.setting_key = RR_SETTINGS_SECTIONS[self.category][0]
        self.settings = cog.get_user_settings(author_id)
        self.message = None
        self.rebuild_components()

    def reload_settings(self):
        self.settings = self.cog.get_user_settings(self.author_id)

    def rebuild_components(self):
        self.clear_items()
        self.add_item(RRSettingsCategorySelect(self))
        self.add_item(RRSettingsSettingSelect(self))
        value = getattr(self.settings, self.setting_key)
        if isinstance(value, bool):
            toggle = discord.ui.Button(
                label="Disable" if value else "Enable",
                style=discord.ButtonStyle.danger if value else discord.ButtonStyle.success,
                row=2,
            )
            toggle.callback = self.toggle_setting
            self.add_item(toggle)
        elif self.setting_key in RR_SETTINGS_CHOICES:
            self.add_item(RRSettingsChoiceSelect(self))
        else:
            edit = discord.ui.Button(label="Edit Value", style=discord.ButtonStyle.primary, row=2)
            edit.callback = self.edit_setting
            self.add_item(edit)

        reset = discord.ui.Button(label="Reset Setting", style=discord.ButtonStyle.secondary, row=4)
        reset.callback = self.reset_setting
        self.add_item(reset)
        reset_all = discord.ui.Button(label="Reset All", style=discord.ButtonStyle.danger, row=4)
        reset_all.callback = self.reset_all
        self.add_item(reset_all)
        self.add_item(RRSettingsPresetSelect(self))
        close = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, row=4)
        close.callback = self.close_panel
        self.add_item(close)

    def build_embed(self, *, notice: str | None = None) -> discord.Embed:
        descriptions = self.cog.setting_descriptions()
        lines = []
        for key in RR_SETTINGS_SECTIONS[self.category]:
            marker = "▶" if key == self.setting_key else "•"
            lines.append(f"{marker} **{_rr_pretty_key(key)}:** `{getattr(self.settings, key)}`")
        description = "\n".join(lines)
        if notice:
            description = f"✅ {notice}\n\n{description}"
        embed = discord.Embed(
            title=f"Russian Roulette Settings — {self.category}",
            description=description,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=_rr_pretty_key(self.setting_key),
            value=descriptions.get(self.setting_key, "No description available."),
            inline=False,
        )
        limits = RR_SETTINGS_LIMITS.get(self.setting_key)
        if limits:
            embed.add_field(name="Allowed Range", value=f"`{limits[0]}` to `{limits[1]}`", inline=True)
        embed.set_footer(text="Changes save immediately. Existing text commands still work.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This settings panel is not yours.", ephemeral=True)
            return False
        return True

    async def toggle_setting(self, interaction: discord.Interaction):
        value = not bool(getattr(self.settings, self.setting_key))
        ok, message = await self.cog.apply_rr_setting_value(
            self.author_id, self.setting_key, str(value)
        )
        if not ok:
            return await interaction.response.send_message(message, ephemeral=True)
        self.reload_settings()
        self.rebuild_components()
        await interaction.response.edit_message(embed=self.build_embed(notice=message), view=self)

    async def edit_setting(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RRSettingValueModal(self, self.setting_key))

    async def reset_setting(self, interaction: discord.Interaction):
        default_value = getattr(RRSettings(), self.setting_key)
        settings = self.cog.get_user_settings(self.author_id)
        setattr(settings, self.setting_key, default_value)
        await self.cog.set_user_settings(self.author_id, settings)
        self.reload_settings()
        self.rebuild_components()
        await interaction.response.edit_message(
            embed=self.build_embed(notice=f"Reset {_rr_pretty_key(self.setting_key)}."),
            view=self,
        )

    async def reset_all(self, interaction: discord.Interaction):
        await self.cog.set_user_settings(self.author_id, RRSettings())
        self.reload_settings()
        self.rebuild_components()
        await interaction.response.edit_message(
            embed=self.build_embed(notice="Reset all roulette settings."),
            view=self,
        )

    async def close_panel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Roulette settings closed.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException, discord.NotFound):
                await self.message.edit(view=self)


class RRSettingsLaunchView(discord.ui.View):
    def __init__(self, cog: "Russian", author_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = int(author_id)

    @discord.ui.button(label="Open Settings", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def open_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This settings menu is not yours.", ephemeral=True)
        panel = RRSettingsPanelView(self.cog, self.author_id)
        await interaction.response.send_message(embed=panel.build_embed(), view=panel, ephemeral=True)
        panel.message = await interaction.original_response()


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
        self.lobby_ends_at: Optional[float] = None
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

    def _lobby_seconds_left(self, game: Game) -> int:
        if game.lobby_ends_at is None:
            return game.settings.join_timeout
        return max(0, int(game.lobby_ends_at - time.monotonic()))

    def _lobby_players_text(self, game: Game) -> str:
        if not game.participants:
            return "None yet"
        preview_limit = 20
        preview = ", ".join(player.mention for player in game.participants[:preview_limit])
        extra = len(game.participants) - preview_limit
        if extra > 0:
            return f"{preview}, and {extra} more"
        return preview

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
        seconds_left = self._lobby_seconds_left(game)
        minutes, seconds = divmod(seconds_left, 60)

        embed = discord.Embed(
            title="Russian Roulette Lobby",
            color=discord.Color.dark_red(),
            description=(
                "One bullet. Six chambers. No mercy.\n"
                f"Lobby closes in **{minutes:02d}:{seconds:02d}**."
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
        embed.add_field(
            name=f"Joined ({len(game.participants)})",
            value=self._lobby_players_text(game),
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
                "Flavor pack for roulette narration. Choose from the theme dropdown."
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
        theme = THEME_ALIASES.get(theme, theme)
        if theme not in THEME_TAUNTS:
            return "dark"
        return theme

    async def apply_rr_setting_value(
        self,
        user_id: int,
        setting: str,
        value: str,
    ) -> tuple[bool, str]:
        """Validate and persist one roulette setting for commands and UI panels."""
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
        key = str(setting).strip().lower()
        if key not in key_map:
            return False, "Unknown setting. Open `rrsettings` to view the available options."

        attr = key_map[key]
        settings = self.get_user_settings(user_id)
        current_value = getattr(settings, attr)

        if isinstance(current_value, bool):
            parsed = self.parse_bool(value)
            if parsed is None:
                return False, "That setting expects true/false."
        elif attr in {"join_timeout", "min_players", "max_players", "turn_timeout", "sudden_death_after", "sudden_death_bullets"}:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return False, "That setting expects a whole number."
            minimum, maximum = RR_SETTINGS_LIMITS[attr]
            parsed = max(int(minimum), min(int(maximum), parsed))
            if attr == "max_players" and parsed == 1:
                parsed = 2
        elif attr in {"mercy_chance", "drama_multiplier", "chaos_chance"}:
            parsed = self.parse_float(value)
            if parsed is None:
                return False, "That setting expects a decimal number."
            minimum, maximum = RR_SETTINGS_LIMITS[attr]
            parsed = max(float(minimum), min(float(maximum), parsed))
        elif attr == "spin_mode":
            parsed = self.normalize_spin_mode(value)
            if parsed is None:
                return False, "Spin mode must be fixed, spin_each_pull, or spin_each_turn."
        elif attr == "theme":
            raw_theme = value.strip().lower()
            if raw_theme not in THEME_TAUNTS and raw_theme not in THEME_ALIASES:
                return False, "Choose a theme from the dropdown in the settings panel."
            parsed = self.normalize_theme(raw_theme)
        else:
            return False, "Unsupported setting type."

        setattr(settings, attr, parsed)
        if settings.max_players and settings.min_players > settings.max_players:
            if attr == "min_players":
                settings.max_players = settings.min_players
            else:
                settings.min_players = settings.max_players
        await self.set_user_settings(user_id, settings)
        return True, f"Updated `{attr}` to `{getattr(settings, attr)}`."

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
        raw = THEME_ALIASES.get(raw, raw)
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

            sections = list(RR_SETTINGS_SECTIONS.items())

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
            embed.set_footer(text="Use Open Settings below, or rrsettings <setting> <value>.")
            return await ctx.send(
                embed=embed,
                view=RRSettingsLaunchView(self, ctx.author.id),
            )

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
            if raw_theme not in THEME_TAUNTS and raw_theme not in THEME_ALIASES:
                return await ctx.send(
                    "Theme must be one of: "
                    + ", ".join(RR_SETTINGS_CHOICES["theme"])
                    + "."
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
                game.lobby_ends_at = time.monotonic() + settings.join_timeout
                await self.update_lobby_message(game)

                while not view.is_finished():
                    remaining = self._lobby_seconds_left(game)
                    if remaining <= 0:
                        break
                    # Poll on a short interval to refresh the countdown and pick
                    # up a "Start Early" press. Do NOT wrap view.wait() in
                    # asyncio.wait_for: on timeout it cancels the view's shared
                    # internal "stopped" future, which makes is_finished() return
                    # True and closes the lobby after the first interval (the
                    # "lobby ignores its timer" bug).
                    await asyncio.sleep(min(5, remaining))
                    if view.is_finished():
                        break
                    await self.update_lobby_message(game)
                game.lobby_open = False
                game.lobby_ends_at = None
                view.stop()
                for item in view.children:
                    item.disabled = True
                await message.edit(view=view)

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
