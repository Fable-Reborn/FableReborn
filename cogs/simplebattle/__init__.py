<<<<<<< HEAD
import traceback
import time

=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
import discord
import random
import asyncio
import os
import json
from typing import List, Dict, Tuple, Union, Optional

from discord.ui import Button, View
from discord import ButtonStyle
from discord.ext import commands

from utils.checks import has_char, has_money
from cogs.shard_communication import user_on_cooldown as user_cooldown

from utils.i18n import _, locale_doc
from utils.joins import SingleJoinView
from classes.converters import IntGreaterThan

class SimpleBattle(discord.ext.commands.Cog):
    """A gladiator-themed battle system with dynamic commentary and weapon interactions."""

    def __init__(self, bot):
        self.bot = bot
<<<<<<< HEAD
        self.battle_contexts = {}
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        # Battle commentary templates and data
        self.commentaries = {
            "intros": [
                "Ladies and gentlemen! Welcome to the arena! Today, we witness a clash between {p1} and {p2}!",
                "The crowd roars as {p1} and {p2} enter the sacred arena grounds! Two warriors, two destinies, one victor!",
                "The arena gates open! {p1}, wielding {w1}, faces {p2} with {w2}! Blood and glory await!",
                "Citizens of the empire! Today's match pits {p1} against {p2}! May the strongest prevail!",
                "The sands of the colosseum await fresh blood as {p1} and {p2} step forth to claim glory or death!",
                "From the shadows of training grounds to the light of the arena! {p1} and {p2} fight for honor today!",
                "By decree of the emperor, we present {p1} and {p2}! May the gods favor the worthy!",
                "The sacred grounds of Bloodsand Arena in the heart of Fablelands welcomes {p1} and {p2} to today's spectacle!",
                "From the misty forests of northern Fablelands to the scorching deserts of the south, warriors gather to witness {p1} face {p2}!",
                "The ancient wards of Battlemaster Kroll's arena flare to life as {p1} and {p2} prepare for bloodshed!",
                "The twin moons of Fablelands cast an ominous glow as {p1} and {p2} enter the arena of destiny!",
                "The Emperor of Fablelands rises from his gilded throne as champions {p1} and {p2} salute before battle!",
                "The mystical sands of the Crimson Arena shift eagerly, thirsting for the blood of either {p1} or {p2}!",
                "Heralds sound the Dragon Horns of Valoria as {p1} and {p2} march toward their fate in the Grand Colosseum!",
                "The drums of war echo through the Valley of Champions as {p1} challenges {p2} to mortal combat!",
                "Shamans chant ancient battle hymns as {p1} and {p2} circle each other on the hallowed Battle Platform of Durnhelm!",
                "By ancient tradition of the Fablelands, {p1} and {p2} must prove their worth in the eyes of gods and mortals alike!",
                "The Veiled Sisterhood unveils the Orb of Fates, showing two destinies intertwined: {p1} and {p2} must clash today!",
                "The statues of fallen champions seem to watch as {p1} and {p2} prepare to add their names to arena legend!",
                "The magical barriers of Archmage Vortigern's arena shimmer as {p1} and {p2} step into the ring of judgment!",
                "From humble beginnings to this moment of truth, {p1} and {p2} now face each other in the legendary Pit of Trials!",
                "The crowd falls silent as High Priestess Elara blesses the combat between {p1} and {p2}!",
                "The sands of time run red in the Hourglass Arena as {p1} and {p2} prepare to write history with blood and steel!",
                "Storm clouds gather above the open arena as if the sky itself anticipates the clash between {p1} and {p2}!",
                "The ancient stones of Dragonfall Arena resonate with power as {p1} and {p2} prepare for glorious battle!",
                "As tradition dictates, {p1} and {p2} touch weapons before the Elders of War to begin their sacred duel!",
                "The mystic fires of the Eternal Pyre burn brighter as {p1} and {p2} enter the hallowed fighting grounds!"
            ],
            "attacks": [
                "{attacker} lunges forward with their {weapon}, aiming for a vital strike!",
                "{attacker} performs a dazzling maneuver with their {weapon}, drawing cheers from the crowd!",
                "{attacker} channels their energy into their {weapon} for a devastating attack!",
                "{attacker} executes a classic arena technique with their {weapon}!",
                "{attacker} roars with battle fury, unleashing a flurry of strikes with their {weapon}!",
                "{attacker} feints left before striking with their {weapon} from an unexpected angle!",
                "{attacker} leaps high, bringing down their {weapon} with the full force of gravity!",
                "With the speed of a viper, {attacker} strikes with their {weapon}!",
                "{attacker} performs a move that would make their trainer proud, attacking with their {weapon}!",
                "The crowd chants as {attacker} delivers a powerful blow with their {weapon}!",
                "{attacker} executes a perfect combat roll, coming up with {weapon} positioned for a killing blow!",
                "Using a technique passed down through generations of arena champions, {attacker} attacks with their {weapon}!",
                "{attacker} draws upon ancient rage, their {weapon} becoming an extension of their fury!",
                "The shadows of fallen gladiators seem to guide {attacker}'s {weapon} toward their target!",
                "With cold calculation, {attacker} identifies a weakness and drives their {weapon} toward it!",
                "Blood and sand spray as {attacker} powers through the arena, {weapon} poised to claim flesh!",
                "{attacker} performs the outlawed 'Widow Maker' technique with their {weapon}, drawing gasps from the crowd!",
                "Time seems to slow as {attacker}'s {weapon} traces a perfect arc toward their opponent!",
                "Using the infamous footwork of the Shadowport Slayers, {attacker} positions for a lethal {weapon} strike!",
                "The distinctive stance of the Imperial Combat School telegraphs {attacker}'s devastating {weapon} attack!",
                "{attacker} invokes the name of {god} as their {weapon} seeks enemy blood!",
                "The sun glints off {attacker}'s {weapon} as they perform a perfectly timed assault!",
                "With a war cry that freezes blood, {attacker} charges with {weapon} aimed at vital organs!",
                "The crowd falls silent in awe as {attacker} performs a legendary technique with their {weapon}!",
                "{attacker} strikes with such speed that their {weapon} appears as mere blur to untrained eyes!",
                "Ancient warriors would weep at the perfection of {attacker}'s form as they strike with their {weapon}!",
                "The master-crafted {weapon} sings in {attacker}'s hands, hungry for victory!",
                "{attacker} creates a diversion with a handful of sand before attacking with their {weapon}!",
                "The distinctive battle stance of the Northern Tribes makes {attacker}'s {weapon} strike unpredictable!",
                "With precision born of countless arena battles, {attacker}'s {weapon} seeks the kill with surgical intent!"
            ],
            "defenses": [
                "{defender} skillfully parries with their {weapon}, showing years of training!",
                "{defender} narrowly escapes death, rolling away from the attack in a display of agility!",
                "{defender} calls upon their training, deflecting the attack with their {weapon}!",
                "{defender} stands resolute against the onslaught, blocking with expert precision!",
                "{defender} counters with the swiftness of a seasoned gladiator!",
                "Like water, {defender} flows around the attack, the crowd gasping at such grace!",
                "{defender}'s armor absorbs the blow, a testament to their preparation for battle!",
                "The attack meets {defender}'s {weapon} with a resonant clash of metal!",
                "With a champion's resolve, {defender} refuses to yield, deflecting the strike!",
                "{defender} turns defense into opportunity, positioning for a counter-attack!",
                "Using the sacred defensive stance of the Temple Warriors, {defender} remains untouched!",
                "{defender} twists their body in the 'Serpent's Evasion,' the attack missing by a hair's breadth!",
                "The crowd cheers as {defender} performs the perfect counter-stance taught in the Immortal Academies!",
                "With the legendary 'Steel Wind' defense, {defender} turns aside what should have been a killing blow!",
                "{defender}'s eyes never leave their opponent as they calmly redirect the lethal attack!",
                "Battle-hardened reflexes save {defender} as they instinctively avoid certain death!",
                "The echo of steel on steel rings through the arena as {defender} performs a masterful parry!",
                "Drawing on reserves of willpower, {defender} withstands an attack that would fell lesser fighters!",
                "The ancestral techniques of the Shield Maidens guide {defender}'s perfect defensive movement!",
                "In a display of supreme control, {defender} allows the attack to miss by the width of a blade!",
                "{defender} channels the spirit of {god}, their form becoming almost ethereal as the attack passes through empty space!",
                "Spectators from the Warriors' Guild nod in approval at {defender}'s flawless defensive technique!",
                "Not a single wasted movement as {defender} negates their opponent's attack with practiced efficiency!",
                "The sands shift beneath {defender}'s feet as they pivot away from death's embrace!",
                "Through sheer force of will, {defender} continues fighting despite a blow that would cripple others!",
                "With the poise of a true arena veteran, {defender} makes survival look effortless!",
                "The attack finds only air as {defender} employs the famous 'Ghost Step' technique!",
                "A lifetime of battle instinct allows {defender} to anticipate and counter the deadly strike!",
                "The protective blessings of {god} manifest as {defender} escapes what should have been certain doom!",
                "The legendary 'Wall of Blades' defense makes {defender} momentarily untouchable!"
            ],
            "advantages": [
                "The {weapon1} gives {p1} a clear advantage against {p2}'s {weapon2}! The crowd recognizes this tactical edge!",
                "{p1}'s mastery of the {weapon1} proves devastating against {p2}'s defenses!",
                "A gladiator who knows their weapons! {p1}'s {weapon1} is ideally suited against {p2}'s {weapon2}!",
                "The trainers nod in approval as {p1}'s choice of {weapon1} outmaneuvers {p2}'s {weapon2}!",
                "The blessing of {god} empowers {p1}'s {weapon1}, overwhelming {p2}'s {weapon2}!",
                "Years in the fighting pits have taught {p1} how to exploit the weaknesses of {p2}'s {weapon2} type!",
                "Arena veterans recognize {p1}'s tactical brilliance in wielding a {weapon1} against {p2}'s {weapon2}!",
                "The legendary weapon matchup favors {p1}'s {weapon1} - a fact well-known to students of war!",
                "The ancient scrolls of combat clearly state: a {weapon1} will triumph over a {weapon2} in skilled hands!",
                "The distinctive fighting style of {p1}'s {weapon1} creates openings in {p2}'s {weapon2} defense!",
                "The superior reach of {p1}'s {weapon1} gives them a deadly advantage over {p2}'s {weapon2}!",
                "Fablelands combat lore is clear - the {weapon1} naturally counters the {weapon2} when wielded with skill!",
                "The unique balance of {p1}'s {weapon1} allows attacks that bypass the defensive strengths of {p2}'s {weapon2}!",
                "Combat scholars in the audience explain to novices why {p1}'s {weapon1} has the tactical edge here!",
                "The weight distribution of {p1}'s {weapon1} overcomes the defensive capabilities of {p2}'s {weapon2}!",
                "Historical battles have proven time and again: a skilled {weapon1} wielder defeats a {weapon2} user!"
            ],
            "special_moves": [
                "{attacker} performs the legendary '{move}' technique with their {weapon}! The crowd goes wild!",
                "By the gods! {attacker} unleashes a forbidden technique taught only to champions!",
                "{attacker} channels ancient power through their {weapon}, a technique blessed by {god}!",
                "The arena trembles as {attacker} executes their signature move, '{move}'!",
                "{attacker}'s {weapon} glows with mystical energy for a devastating strike!",
                "A move straight from the scrolls of ancient arena champions! {attacker} stuns all with '{move}'!",
                "The crowd chants '{attacker}! {attacker}!' as they perform a technique not seen in generations!",
                "Masters of the arena would weep to see {attacker}'s perfect execution of the '{move}' stance!",
                "The very air seems to shimmer as {attacker} channels the forbidden '{move}' technique!",
                "Blood and sand swirl in unnatural patterns as {attacker} performs a move thought lost to time!",
                "The mystical energies of Fablelands react to {attacker}'s perfect execution of the '{move}'!",
                "Veteran gladiators gasp as {attacker} performs the '{move}', a technique costing years of life to master!",
                "With movements too fast for untrained eyes to follow, {attacker} unleashes the devastating '{move}'!",
                "The spirits of fallen champions seem to guide {attacker}'s {weapon} as they perform the sacred '{move}'!",
                "Not seen since the Age of Heroes, {attacker}'s '{move}' technique leaves spectators breathless!",
                "Reality itself seems to bend as {attacker}'s {weapon} traces the patterns of the legendary '{move}'!"
            ],
            "godly_interventions": [
                "The sky brightens as Astraea, Goddess of Light, favors {player} with her blessing!",
                "Shadows writhe at {player}'s feet! Sepulchure, God of Darkness, grants his cruel power!",
                "Reality itself warps around {player} as Drakath, God of Chaos, intervenes capriciously!",
                "A beam of pure light empowers {player}'s {weapon}, Astraea's divine favor made manifest!",
                "The crowd falls silent as Sepulchure's dark energy courses through {player}'s veins!",
                "Drakath's chaotic will sends unpredictable power surging through {player}'s {weapon}!",
                "Astraea's radiance blinds {player}'s opponent, creating an opening!",
                "Sepulchure's deathly chill emanates from {player}, weakening all who stand nearby!",
                "The very rules of combat seem to bend around {player} as Drakath's chaos manifests!",
                "Astraea's holy light forms protective wings around {player}, deflecting a lethal blow!",
                "The blood spilled on the arena sand bubbles and writhes at Sepulchure's dark command, aiding {player}!",
                "Drakath's laughter echoes as probability itself shifts in {player}'s favor!",
                "Golden tears fall from the statue of Astraea, landing on {player}'s wounds and healing them instantly!",
                "Sepulchure's shadow elongates, becoming a second weapon in {player}'s arsenal!",
                "The laws of physics briefly suspend as Drakath allows {player} to defy gravity!",
                "Astraea's blessing makes {player}'s movements fluid and perfect, like a celestial dance!",
                "Sepulchure grants {player} the ability to see their opponent's next move, painted in shadows!",
                "Drakath's chaos transforms {player}'s minor wound into unexpected strength!",
                "The very air around {player} shimmers with Astraea's divine protection!",
                "Sepulchure's darkness devours the light around {player}, making their strikes impossible to predict!",
                "Drakath's influence causes {player}'s weapon to briefly transform into something impossible!"
            ],
            "comebacks": [
                "{player} refuses to yield, finding new strength as the crowd begins to chant their name!",
                "Just when defeat seemed certain, {player} draws on reserves of will known only to true gladiators!",
                "{player} surprises everyone with a second wind, a testament to their fighting spirit!",
                "The tide of battle shifts as {player} rallies with the determination of a champion!",
                "Blood-soaked but unbowed, {player} shows why they have survived countless arena battles!",
                "The mark of a true gladiator! {player} turns imminent defeat into renewed opportunity!",
                "{player} remembers their trainer's words: 'The battle isn't over until you stop breathing!'",
                "With a prayer to {god}, {player} finds the strength to continue this brutal contest!",
                "Drawing on the ancient warrior spirit of their ancestors, {player} refuses to fall!",
                "As if touched by the hand of {god} themselves, {player} rises from certain defeat!",
                "The crowd's energy seems to flow into {player}, renewing their fighting spirit!",
                "With blood streaming from their wounds, {player} stands tall, embodying the warrior's creed!",
                "{player} wipes blood from their eyes, their gaze now burning with unquenchable determination!",
                "Against all odds, {player} finds reserves of strength that shock even veteran arena masters!",
                "The legendary 'Heart of the Gladiator' manifests as {player} transforms near-defeat into new power!",
                "With a roar that silences the crowd, {player} surges back from the brink of defeat!"
            ],
            "arena_events": [
                "The crowd throws {item} into the arena, which {player} quickly grabs!",
                "A section of the arena wall collapses, forcing both fighters to adapt!",
                "The midday sun beats down mercilessly, testing the endurance of both gladiators!",
                "The emperor signals for the release of {hazard} into the arena! The crowd roars with excitement!",
                "Arena slaves hurriedly clear fallen debris as the battle rages on!",
                "A powerful gust of wind sweeps sand across the arena, momentarily blinding the combatants!",
                "The crowd's favorite gladiator receives a thunderous ovation, renewing their spirit!",
                "The arena master signals a change in rules! The fighters must now {new_condition}!",
                "Hidden mechanisms activate, raising sections of the arena floor into dangerous platforms!",
                "Ancient runes carved into the arena floor glow with power, strengthening those who stand upon them!",
                "The sacred battle drums of Fablelands begin a rhythm that quickens the blood of all warriors!",
                "A rare eclipse darkens the arena, traditionalists claim this is an omen from the gods!",
                "The Emperor's exotic beasts rattle their cages at the scent of blood, distracting fighters!",
                "Servants scatter fresh sand over blood-soaked areas, the red stains spreading like omens!",
                "Ancestral spirits of fallen champions materialize briefly, watching the worthy successors to their legacy!",
                "The mystical barriers containing the fight flare with power as particularly violent techniques are used!"
            ],
            "finishers": [
                "With a final decisive strike worthy of legend, {winner} secures victory! The crowd erupts!",
                "Glory and gold to {winner}! Their name will be etched in the annals of arena history today!",
                "{winner} stands triumphant over {loser}, the arena sands stained with evidence of their struggle!",
                "The emperor gives the thumbs-up! {winner} is victorious and {loser} lives to fight another day!",
                "A display of martial prowess not seen in years! {winner} claims rightful victory!",
                "Let it be known throughout the empire that on this day, {winner} conquered the challenge of {loser}!",
                "The heralds will sing of this victory! {winner} has proven worthy of {god}'s favor today!",
                "{winner}'s technique, courage, and strength have prevailed! Glory to the victor!",
                "In a final exchange of blows that will be remembered for generations, {winner} emerges triumphant!",
                "The crowds of Fablelands will speak of this day when {winner} achieved immortality in the arena!",
                "With skill that would make the ancient champions proud, {winner} claims victory over {loser}!",
                "The Scribes of Battle record another glorious victory for {winner} in the annals of Fablelands!",
                "By strength, skill, and the favor of {god}, {winner} stands where many have fallen!",
                "The arena has made its judgment - {winner} is worthy to continue the path of the warrior!",
                "Let trumpets sound and banners fly! {winner} has earned glory in the eyes of all Fablelands!",
                "The sands drink deeply of spilled blood as {winner} claims mastery over {loser}!"
            ],
            "two_handed_comments": [
                "The massive {weapon} in {player}'s hands requires incredible strength to wield effectively!",
                "Few can withstand the crushing power of {player}'s two-handed {weapon}!",
                "{player}'s training with the mighty {weapon} is evident in every devastating swing!",
                "The crowd gasps as {player} demonstrates surprising agility with their massive {weapon}!",
                "The reach advantage of {player}'s {weapon} keeps their opponent at bay!",
                "The ground trembles with each impact of {player}'s mighty {weapon}!",
                "Only the strongest warriors of Fablelands can master such a formidable {weapon}!",
                "The distinctive fighting style of the Mountain Clans is evident in {player}'s {weapon} technique!",
                "Each swing of that massive {weapon} carries enough force to shatter bone and steel alike!",
                "The distinctive whistling sound of {player}'s {weapon} cutting through air strikes fear in opponents!",
                "That {weapon} requires years of conditioning just to lift, let alone wield with such deadly grace!",
                "The weight distribution of {player}'s {weapon} allows for devastating momentum in each strike!"
            ],
            "shield_comments": [
                "{player}'s shield becomes a weapon itself, used both for protection and striking!",
                "The shield of {player} has been dented by many foes, yet still provides stalwart protection!",
                "Like a fortress wall, {player}'s shield technique is impenetrable!",
                "The defensive mastery of {player} turns their opponent's strength against them!",
                "A shield in the hands of {player} is as deadly as any blade in lesser hands!",
                "The distinctive embossing on {player}'s shield marks them as a disciple of the Bulwark Brotherhood!",
                "The ancient techniques of the Shield Maidens guide {player}'s perfect defensive stance!",
                "That shield bears the marks of countless battles, each dent a story of survival!",
                "The reinforced rim of {player}'s shield can crush windpipes as effectively as any blade!",
                "The way {player} positions their shield shows training in the Ironwall Technique!",
                "Few appreciate the lethal potential of a shield until they face someone like {player}!",
                "The balance between offense and defense in {player}'s shield work is a marvel to witness!"
            ],
            "dual_wield_comments": [
                "{player} wields a weapon in each hand with deadly precision!",
                "The crowd marvels at {player}'s mastery of dual-wielding!",
                "Few can control two weapons as skillfully as {player}!",
                "A flurry of strikes from {player}'s twin weapons leaves spectators breathless!",
                "The dual-wielding style of {player} has claimed many victims in these sands!",
                "{player} demonstrates why two weapons can be superior to one in skilled hands!",
                "The legendary 'Twin Serpents' fighting style is evident in {player}'s dual weapon mastery!",
                "Each of {player}'s weapons moves independently, as if guided by separate minds!",
                "Only the most coordinated warriors of Fablelands can achieve such dual weapon harmony!",
                "The ambidextrous talent required to fight as {player} does is exceedingly rare!",
                "The distinctive fighting style of the Twinblade Monastery is unmistakable in {player}'s form!",
                "Twice the weapons means twice the danger when in the hands of a master like {player}!"
            ],
            "knife_attacks": [
                "{attacker} slashes with lightning speed, their knife a silver blur aimed at {defender}'s throat!",
                "{attacker} performs the infamous 'Death by Thousand Cuts' technique, their knife flickering between vital points!",
                "{attacker}'s knife dances between their fingers before darting toward {defender}'s exposed flank!",
                "With surgical precision, {attacker} targets the gaps in {defender}'s armor with their razor-sharp knife!",
                "{attacker} feints low then brings their knife up in a vicious arc toward {defender}'s face!",
                "The crowd gasps as {attacker} performs the legendary 'Serpent's Fang' knife technique!",
                "{attacker} hurls their knife with deadly accuracy, then draws another from a hidden sheath!",
                "Using the 'Crimson Crescent' style, {attacker} whirls their knife in horrifying patterns!",
                "{attacker} rolls beneath {defender}'s guard, knife positioned to open arteries with surgical precision!",
                "With a flourish that would make the Shadowguild assassins proud, {attacker} slashes with their knife!",
                "The knife in {attacker}'s hand seems to vanish, only to reappear aimed at {defender}'s kidneys!",
                "{attacker} employs the forbidden 'Red Smile' technique, targeting {defender}'s throat with their blade!"
            ],
            "knife_defenses": [
                "{defender} parries the knife attack with their own blade, the clash of metal echoing through the arena!",
                "With acrobatic grace, {defender} arches backward as the knife passes over their exposed throat!",
                "{defender} catches {attacker}'s wrist, forcing the knife away with practiced expertise!",
                "The crowd roars as {defender} counters the knife attack with the legendary 'Scorpion's Tail' defense!",
                "{defender} uses their bracer to deflect the knife, sparks flying from the contact!",
                "Using the 'Shadow Step' technique, {defender} seems to melt away from the path of the deadly knife!",
                "Years of training in the back alleys of Shadowport serve {defender} well as they evade the knife strike!",
                "{defender} sacrifices their shoulder pad to the knife, preventing a more lethal wound!"
            ],
            "dagger_attacks": [
                "{attacker} lunges with their dagger, aiming for the gap between {defender}'s ribs!",
                "With a flourish taught in the Assassin's Guild, {attacker} slashes their dagger in a deadly arc!",
                "{attacker} feints with their off-hand before driving their poisoned dagger toward {defender}'s vitals!",
                "The dagger in {attacker}'s hand leaves a trail of dark energy as they execute the 'Soul Severer' technique!",
                "{attacker} throws their dagger with deadly precision, already drawing another as the first flies!",
                "Using the brutal 'Gut Ripper' method, {attacker} sweeps their dagger in a disemboweling motion!",
                "{attacker}'s dagger glints in the arena light as they target {defender}'s exposed tendons!",
                "With the speed of a striking viper, {attacker} thrusts their dagger at {defender}'s throat!",
                "{attacker} spins their dagger skillfully before launching into the infamous 'Dance of Blades' attack pattern!",
                "The crowd falls silent as {attacker} performs the legendary 'Nightshade' dagger technique!",
                "Employing the ruthless 'Heartseeker' stance, {attacker} aims their dagger with lethal intent!",
                "{attacker} slides into the 'Shadow Dancer' stance, their dagger a whisper of death in their hand!"
            ],
            "dagger_defenses": [
                "{defender} deflects the dagger with their bracers, the enchanted metal ringing from the impact!",
                "With a counter-move taught by the Royal Guard, {defender} redirects the dagger thrust!",
                "{defender} catches {attacker}'s wrist mid-strike, forcing the dagger away from their vital organs!",
                "The 'Serpent's Coil' defense serves {defender} well as they twist away from the deadly dagger!",
                "{defender} sacrifices their cloak to the dagger, the fabric wrapping around the blade!",
                "Years of training in the Shadowmere pits allows {defender} to anticipate and evade the dagger's path!",
                "{defender} creates distance with a backward roll, the dagger finding only air!",
                "Using the 'Iron Skin' technique, {defender} tenses their muscles to resist the dagger's bite!"
            ],
            "sword_attacks": [
                "{attacker} brings their sword down in a mighty overhead cleave that could split {defender} from crown to groin!",
                "With precision taught by Blademaster Kain, {attacker} thrusts their sword at {defender}'s heart!",
                "{attacker} whirls their sword in the ancient 'Cyclone of Steel' pattern, forcing {defender} to give ground!",
                "The sword in {attacker}'s hands whistles through the air as they execute a perfect 'Valkyrie's Strike'!",
                "{attacker} feints high then brings their sword in a devastating low sweep aimed at {defender}'s legs!",
                "Using the 'Sundering Blade' technique, {attacker} channels their strength into a single mighty sword stroke!",
                "{attacker}'s sword becomes a blur of lethal steel as they launch into the 'Thousand Blades' attack routine!",
                "With a two-handed grip, {attacker} drives their sword forward in the unstoppable 'Boar's Rush' technique!",
                "The crowd roars as {attacker}'s sword traces glowing patterns in the air, a sign of perfect form!",
                "Channeling the ancient warriors of the Vale, {attacker} performs a sword maneuver not seen in generations!",
                "{attacker} slides into the 'Blade Dancer' stance before unleashing a flurry of sword strikes!",
                "The legendary 'Dragon's Tooth' technique makes {attacker}'s sword seem to multiply as they attack!",
                "Employing the brutal 'Crimson Arc' style, {attacker}'s sword aims to separate {defender}'s head from their shoulders!",
                "{attacker} uses their sword to perform the deadly 'Imperial Cross' technique, slashing from two angles simultaneously!"
            ],
            "sword_defenses": [
                "{defender} raises their sword in the 'Bulwark' stance, catching {attacker}'s blade with a shower of sparks!",
                "With elegance taught in the Highgarden fencing schools, {defender} deflects the sword thrust!",
                "{defender}'s blade meets {attacker}'s in the perfect 'Mirrored Sky' parry, locking the weapons momentarily!",
                "Using the 'Wind Through Reeds' philosophy, {defender}'s sword redirects the attacking blade's momentum!",
                "{defender} employs the defensive 'Ironwall' sword technique, creating an impenetrable barrier of steel!",
                "The ancient 'Seven Stars' defense allows {defender} to counter each attack with minimal movement!",
                "{defender}'s blade seems to be everywhere at once as they execute the 'Peacock's Tail' defensive pattern!",
                "With a technique passed down from the Knights of Valoria, {defender} turns aside the deadly sword strike!",
                "The crowd cheers as {defender} performs the perfect 'Knight's Honor' parry against the sword attack!"
            ],
            "hammer_attacks": [
                "{attacker} swings their massive hammer in a bone-crushing arc aimed at {defender}'s rib cage!",
                "The ground trembles as {attacker} brings their hammer down in the devastating 'Earth Splitter' attack!",
                "{attacker} spins to add momentum to their hammer strike, capable of pulverizing armor and bone alike!",
                "With the unstoppable 'Avalanche' technique, {attacker} launches a series of brutal hammer blows!",
                "{attacker}'s hammer whistles through the air, aimed at {defender}'s knee to cripple them permanently!",
                "Using the dreaded 'Skull Cracker' stance, {attacker} targets {defender}'s helmet with their hammer!",
                "{attacker} feints with the hammer head before reversing to strike with the reinforced pommel!",
                "The crowd winces as {attacker} unleashes the 'Ribcage Reducer' hammer technique!",
                "{attacker}'s hammer glows with runic power as they channel the 'Mountain's Wrath' attack!",
                "With frightening speed for such a heavy weapon, {attacker}'s hammer seeks to pulverize {defender}'s collarbone!",
                "The infamous 'Forge Master's Fury' makes {attacker}'s hammer strikes rain down like thunderbolts!",
                "Employing techniques from the Ironheart tribe, {attacker}'s hammer becomes an extension of their rage!"
            ],
            "hammer_defenses": [
                "{defender} sidesteps the hammer with a nimbleness that belies their armor's weight!",
                "Rather than blocking the mighty hammer, {defender} redirects its momentum with a glancing deflection!",
                "{defender} rolls beneath the hammer swing, feeling the wind of its passage ruffle their hair!",
                "Using the 'Bend Like Reed' philosophy, {defender} allows their body to flow away from the hammer's path!",
                "{defender} catches the hammer shaft with their armored gauntlet, dispersing its force!",
                "The crowd gasps as {defender} performs the nearly impossible 'Stone Meets Water' defense against the hammer!",
                "{defender} times their movement perfectly, letting the hammer pass within a hair's breadth!",
                "With a technique taught by the Mountain Monks, {defender} uses {attacker}'s hammer momentum against them!"
            ],
            "bow_attacks": [
                "{attacker} draws their bow with practiced grace, loosing an arrow aimed at {defender}'s throat!",
                "With inhuman speed, {attacker} fires three arrows in rapid succession, leaving {defender} little room to dodge!",
                "{attacker} channels the 'Eagle's Sight' technique, their arrow seeking {defender}'s heart with uncanny precision!",
                "The crowd falls silent as {attacker} performs the legendary 'Piercing Heaven' bow draw, their arrow a blur!",
                "{attacker} fires a low shot aimed to cripple {defender}'s mobility by piercing their thigh!",
                "Using the 'Horizon's Reach' stance, {attacker} arcs their arrow to descend upon {defender} from above!",
                "{attacker}'s bow sings the song of death as they unleash the 'Storm of Shafts' technique!",
                "With deadly calm, {attacker} aims for the gap in {defender}'s armor where neck meets shoulder!",
                "The infamous 'Heartpiercer' shot leaves {attacker}'s bow with enough force to penetrate plate armor!",
                "{attacker} dips their arrow in poison before firing the dreaded 'Viper's Kiss' shot!",
                "Employing the brutal 'Joint Seeker' technique, {attacker}'s arrow targets {defender}'s knee!",
                "The arrow leaves {attacker}'s bow with a whisper, the deadly 'Silent End' technique in action!"
            ],
            "bow_defenses": [
                "{defender} catches the arrow mid-flight, a display of reflexes that draws gasps from the crowd!",
                "With their shield raised at the perfect angle, {defender} deflects the arrow harmlessly aside!",
                "{defender} twists with serpentine grace, the arrow passing through the space they occupied a heartbeat before!",
                "Using a technique perfected against the Sylvan Archers, {defender} anticipates and evades the arrow's path!",
                "{defender}'s armor deflects the arrow, though the impact surely leaves a bruise beneath!",
                "The crowd cheers as {defender} performs the miraculous 'Wind Dancer' evasion against the arrow!",
                "{defender} drops and rolls, hearing the deadly whisper of the arrow passing overhead!",
                "With perfect timing, {defender} swats the arrow from the air with their weapon!"
            ],
            "scythe_attacks": [
                "{attacker} sweeps their curved scythe in a wide arc that threatens to disembowel {defender} in a single stroke!",
                "The wicked curve of {attacker}'s scythe seeks to hook behind {defender}'s defenses and pull them into its lethal edge!",
                "{attacker} spins their scythe in the dreaded 'Harvest of Souls' pattern, each revolution promising death!",
                "With the precision of a reaper at work, {attacker}'s scythe targets the vulnerable joint of {defender}'s knee!",
                "{attacker} feints with the scythe's handle before reversing into the devastating 'Last Heartbeat' technique!",
                "Using the horrifying 'Red Crescent' style, {attacker}'s scythe traces crimson patterns in the air!",
                "{attacker}'s scythe glows with unholy light as they channel the 'Touch of the Beyond' attack!",
                "The crowd watches in terrified awe as {attacker} performs the legendary 'Death's Caress' scythe technique!",
                "With a technique banned in seven kingdoms, {attacker}'s scythe aims to separate {defender}'s soul from their body!",
                "{attacker} uses the scythe's reach advantage in the deadly 'Horizon Cut' that few can evade!",
                "Employing the 'Moonfall' stance, {attacker}'s scythe descends from above with unstoppable force!",
                "The ancient 'Whisper of Inevitability' makes {attacker}'s scythe almost invisible as it cuts toward {defender}!"
            ],
            "scythe_defenses": [
                "{defender} steps inside the scythe's deadly arc, nullifying its cutting advantage!",
                "With perfect timing, {defender} catches the scythe's shaft before its blade can complete its lethal path!",
                "{defender} leaps over the low scythe sweep in a display of acrobatic prowess!",
                "Using the 'Dance with Death' technique, {defender} predicts and evades the scythe's curved path!",
                "{defender}'s armor deflects the scythe blade at an angle, preventing it from finding purchase!",
                "The crowd gasps as {defender} performs the nearly impossible 'Thread the Needle' evasion between the scythe's strikes!",
                "{defender} drops to the ground, allowing the scythe to pass harmlessly overhead!",
                "With a counter developed by the Sunguard, {defender} turns the scythe's momentum against {attacker}!"
            ],
            "wand_attacks": [
                "{attacker} channels arcane energy through their wand, releasing a bolt of destructive force at {defender}!",
                "With a complex gesture, {attacker}'s wand creates phantom serpents that strike at {defender}'s exposed flesh!",
                "{attacker} traces glowing sigils in the air with their wand, culminating in the dreaded 'Mindfire' spell!",
                "The crowd shields their eyes as {attacker} performs the blinding 'Sunburst' spell with their wand!",
                "{attacker}'s wand hums with power before unleashing the flesh-withering 'Decay Touch' enchantment!",
                "Using the forbidden 'Soul Siphon' technique, {attacker}'s wand draws ghostly tendrils toward {defender}!",
                "{attacker} points their wand at the ground beneath {defender}, summoning the 'Quicksand Trap' with a whispered word!",
                "With deadly precision, {attacker}'s wand shoots forth the feared 'Threadcutter' spell that severs muscle and sinew!",
                "The ancient 'Seven Stars of Pain' makes {attacker}'s wand fire multiple homing projectiles at {defender}!",
                "{attacker}'s wand glows with elemental fury as they channel the 'Primal Cascade' attack!",
                "Employing techniques from the Arcane Collegium, {attacker}'s wand becomes a conduit for pure destructive magic!",
                "The dreaded 'Mind Spike' spell leaves {attacker}'s wand aimed directly at {defender}'s consciousness!"
            ],
            "wand_defenses": [
                "{defender} raises a magical barrier with their own arcane knowledge, dispersing the spell harmlessly!",
                "With a counter-sigil traced hastily in the air, {defender} reflects the magical attack back toward its source!",
                "{defender} activates a protective amulet, absorbing the spell's energy in a flash of light!",
                "Using the 'Spell Eater' stance taught by the Mage Hunters, {defender} nullifies the arcane attack!",
                "{defender}'s enchanted armor glows as it resists the magical assault!",
                "The crowd cheers as {defender} performs the legendary 'Mystic Mirror' defense against the spell!",
                "{defender} grounds the spell's energy by touching their weapon to the arena floor!",
                "With a technique developed in the War of Whispers, {defender} dissipates the magical energy!"
            ],
            "shield_attacks": [
                "{attacker} smashes forward with their shield's edge, aiming to crush {defender}'s windpipe!",
                "With the devastating 'Avalanche Press' technique, {attacker} charges with their shield as a battering ram!",
                "{attacker} feints with their weapon before spinning to deliver a skull-cracking shield bash!",
                "The reinforced rim of {attacker}'s shield becomes a deadly weapon as they employ the 'Circle of Pain' technique!",
                "{attacker}'s shield smashes downward in the brutal 'Judgment From Above' attack!",
                "Using the 'Tower's Fall' stance, {attacker} puts all their weight behind their shield to overwhelm {defender}!",
                "{attacker} performs the legendary 'Turtle's Revenge' shield combination that has broken many warriors!",
                "With frightening speed, {attacker} lashes out with their shield in a hook that could dislocate {defender}'s jaw!",
                "The infamous 'Ironwall Assault' makes {attacker}'s shield both impenetrable defense and unstoppable offense!",
                "{attacker}'s shield edge aims for {defender}'s throat in the dreaded 'Mercy Cut' technique!",
                "Employing the forgotten 'Battering Tide' method, {attacker}'s shield becomes a blur of concentrated force!",
                "The crowd roars as {attacker}'s shield glows with runic power in the 'Ancestral Bulwark' attack!"
            ],
            "shield_defenses": [
                "{defender} hides behind their own shield, creating an impenetrable wall against the attack!",
                "With perfect angling, {defender}'s shield deflects the blow that would have shattered lesser defenses!",
                "{defender} braces with their legs in the 'Mountain Stance,' their shield absorbing the massive impact!",
                "Using the 'Tortoise Shell' technique, {defender} covers vital areas with overlapping shield protection!",
                "{defender}'s enchanted shield glows as it absorbs and nullifies the attack's energy!",
                "The crowd cheers as {defender} performs the perfect 'Bulwark of the Ages' defense!",
                "{defender} angles their shield to redirect the force of the blow into the ground!",
                "With a technique from the Shield Masters of Valoria, {defender} turns defense into attack opportunity!",
                "The legendary 'Sentinel's Watch' stance allows {defender} to remain unmoved by the powerful attack!"
            ],
            "mace_attacks": [
                "{attacker} swings their heavy mace in a bone-crushing arc aimed at {defender}'s skull!",
                "With the brutal 'Skullcracker' technique, {attacker} brings their mace down with enough force to split a helmet!",
                "{attacker}'s mace whistles through the air, its flanged head designed to punch through armor with ease!",
                "The crowd winces as {attacker} employs the infamous 'Joint Breaker' mace technique targeting {defender}'s knee!",
                "{attacker} feints high then brings their mace in a vicious upswing that could shatter {defender}'s jaw!",
                "Using the 'Tombmaker' stance, {attacker}'s mace becomes a blur of concentrated killing force!",
                "{attacker} channels holy power through their mace, performing the 'Light's Judgment' attack!",
                "With a two-handed grip, {attacker} puts terrifying power behind their mace in the 'Coffin Nail' technique!",
                "The ancient 'Hammer of Righteousness' makes {attacker}'s mace glow with divine power as they strike!",
                "{attacker}'s mace targets the weak points in {defender}'s armor with uncanny precision!",
                "Employing the crushing 'Mountain's Fist' style, {attacker}'s mace aims to cave in {defender}'s chest!",
                "The dreaded 'Bell Ringer' technique guides {attacker}'s mace toward {defender}'s temple!"
            ],
            "mace_defenses": [
                "{defender} redirects the mace's crushing momentum with a glancing deflection!",
                "With a sidestep worthy of a dancer, {defender} allows the heavy mace to swing past harmlessly!",
                "{defender} catches the mace shaft with their weapon, halting its deadly arc before impact!",
                "Using the 'Flow Like Water' philosophy, {defender} moves with the mace's energy rather than opposing it!",
                "{defender}'s armor disperses the impact of the mace across its reinforced plates!",
                "The crowd gasps as {defender} performs the nearly impossible 'Thread the Needle' timing against the mace!",
                "{defender} ducks beneath the mace swing, feeling the wind of its passage through their hair!",
                "With a counter-technique developed in the Ironhold Citadel, {defender} turns the mace's weight against {attacker}!"
            ],
            "axe_attacks": [
                "{attacker} swings their axe in a vicious arc that could cleave {defender} from shoulder to sternum!",
                "With the brutal 'Executioner's Call' technique, {attacker}'s axe descends with unstoppable force!",
                "{attacker} feints low then brings their axe up in a disemboweling stroke that could spill {defender}'s entrails!",
                "The crowd roars as {attacker} performs the savage 'Berserker's Fury' axe combination!",
                "{attacker}'s axe whistles through the air, its razor edge seeking to separate {defender}'s head from their shoulders!",
                "Using the 'Woodsman's Revenge' stance, {attacker} channels raw power into their axe swing!",
                "{attacker} hooks {defender} with the back spike of their axe, attempting to tear them off balance!",
                "With frightening speed, {attacker}'s axe traces the 'Blood Eagle' pattern in the air!",
                "The infamous 'Mountain Cleaver' technique makes {attacker}'s axe strike with enough force to split stone!",
                "{attacker}'s axe glows with ancestral runes as they channel the 'Forefathers' Fury' attack!",
                "Employing the savage 'Red Harvest' method, {attacker}'s axe becomes an extension of their bloodlust!",
                "The brutal 'Limb Taker' guides {attacker}'s axe toward {defender}'s exposed extremities!"
            ],
            "axe_defenses": [
                "{defender} catches the axe head on their reinforced bracer, sparks flying from the impact!",
                "With perfect timing, {defender} steps inside the axe's arc where its cutting edge cannot reach!",
                "{defender} deflects the heavy axe head with their weapon, the clang of metal echoing through the arena!",
                "Using the 'Bend Don't Break' philosophy, {defender} rolls with the axe's momentum!",
                "{defender}'s armor turns the axe blade at an angle, preventing it from biting deeply!",
                "The crowd cheers as {defender} performs the legendary 'Viper's Retreat' against the axe stroke!",
                "{defender} sacrifices their cloak to the axe blade, the fabric wrapping around the weapon!",
                "With a counter developed by the Imperial Guard, {defender} uses {attacker}'s axe momentum against them!"
            ],
            "spear_attacks": [
                "{attacker} thrusts their spear with deadly precision, aiming for {defender}'s throat above their breastplate!",
                "With the unstoppable 'Piercing Thorn' technique, {attacker}'s spear seeks the gap in {defender}'s armor!",
                "{attacker} feints high then drops their spear point toward {defender}'s exposed thigh!",
                "The crowd gasps as {attacker} performs the legendary 'Serpent's Fang' spear thrust!",
                "{attacker}'s spear blurs in the complex 'Dance of the Heron' pattern, attacking from multiple angles!",
                "Using the devastating 'Heart Seeker' stance, {attacker} puts their full weight behind their spear thrust!",
                "{attacker} spins their spear in a defensive wheel before launching a surprise thrust at {defender}'s midsection!",
                "With the reach advantage of their weapon, {attacker}'s spear keeps {defender} at bay while probing for weakness!",
                "The infamous 'Dragon's Tongue' makes {attacker}'s spear flicker with unnatural speed toward its target!",
                "{attacker}'s spear glints with deadly purpose as they employ the feared 'Gill Splitter' technique!",
                "Employing the precise 'Thread the Needle' method, {attacker}'s spear aims for the eye slit in {defender}'s helm!",
                "The methodical 'Fortress Breaker' stance guides {attacker}'s spear toward the weakest point in {defender}'s defense!"
            ],
            "spear_defenses": [
                "{defender} deflects the spear point with a circular parry, moving the deadly tip just inches from their vitals!",
                "With a sidestep worthy of a bullfighter, {defender} allows the spear thrust to pass harmlessly by!",
                "{defender} traps the spear shaft against their body, preventing {attacker} from withdrawing for another strike!",
                "Using the 'Swallow Takes Flight' technique, {defender} leaps over the low spear thrust!",
                "{defender}'s armor deflects the spear point, though the impact surely leaves a bruise beneath!",
                "The crowd roars as {defender} performs the difficult 'Leaf on the Wind' evasion against the spear!",
                "{defender} slaps the spear shaft aside with their open palm, displaying contempt for the attack!",
                "With a counter developed against the Spear Maidens of the East, {defender} turns the thrust against its originator!",
                "The legendary 'River Flows Around Stone' stance allows {defender} to make the spear miss by the smallest margin!"
            ],
            "emperor_signals": [
                "The Emperor rises slowly from his gilded throne, the arena falling silent...",
                "All eyes turn to the Imperial Box as the Emperor considers the fallen gladiator's fate...",
                "The crowd chants for mercy or death as the Emperor weighs the performance of the defeated...",
                "Drums roll ominously as the Emperor prepares to render his judgment on the fallen warrior...",
                "The Emperor confers with his advisors, considering the entertainment value of the combat...",
                "Gold changes hands in the royal box as nobles place last bets on the Emperor's decision...",
                "The fallen gladiator looks up with desperate hope as the Emperor stands to signal their fate...",
                "Priestesses of Astraea burn incense, hoping to influence the Emperor toward mercy...",
                "The sand grows dark with blood as the Emperor contemplates his verdict...",
                "The Emperor's face remains impassive as he considers whether the defeated has earned life..."
            ],
            "emperor_mercy": [
                "Thumbs up! The Emperor grants mercy! {loser} will live to fight another day!",
                "The Emperor raises his thumb! {loser}'s courage has earned them the right to continue their journey!",
                "Mercy is granted! The Emperor acknowledges the skill {loser} displayed despite their defeat!",
                "The crowd roars with approval as the Emperor signals that {loser} shall be spared!",
                "Thumbs up! The Emperor nods with respect at {loser}'s performance today!",
                "Life is the Emperor's gift to {loser} today! Medical slaves rush forward to tend their wounds!",
                "The Emperor smiles and raises his thumb! {loser} bows in gratitude for this second chance!",
                "Mercy! The Emperor decrees that {loser} showed too much potential to perish today!",
                "With a raised thumb, the Emperor spares {loser}, acknowledging their contribution to the day's entertainment!",
                "The Emperor signals life! {loser} clasps their hands in thanks for the Imperial mercy!"
            ],
            "emperor_death": [
                "Thumbs down! The Emperor condemns {loser} to death! {winner} must fulfill the Emperor's will!",
                "The arena falls silent as the Emperor's thumb points downward. {loser}'s journey ends today!",
                "Death is decreed! The Emperor has judged {loser} unworthy of continued life!",
                "The crowd's bloodlust is sated as the Emperor signals for {loser}'s execution!",
                "Thumbs down! {winner} now bears the sacred duty of sending {loser} to the afterlife!",
                "The ultimate price must be paid! The Emperor's downturned thumb seals {loser}'s fate!",
                "No mercy today! The Emperor signals that {loser}'s blood must soak the sands!",
                "Judgment is rendered! By Imperial decree, {loser} must not leave the arena alive!",
                "With a downturned thumb, the Emperor condemns {loser} to join the ranks of fallen gladiators!",
                "The Emperor signals death! {loser} closes their eyes, preparing to meet their ancestors!"
            ],
            "finishing_moves": {
                "knife": [
                    "{winner} grabs {loser} by the hair, drawing their knife across the exposed throat in a spray of crimson!",
                    "With surgical precision, {winner}'s knife finds the gap between {loser}'s ribs, piercing their heart!",
                    "{winner} drives their knife into {loser}'s eye socket, ending their life in an instant!",
                    "The crowd falls silent as {winner} performs the dreaded 'Red Smile,' their knife opening {loser}'s throat ear to ear!",
                    "Using the assassin's 'Mercy Stroke,' {winner} slides their knife between {loser}'s vertebrae at the base of the skull!",
                    "{winner} throws {loser} to the ground and plunges their knife repeatedly into their exposed back!",
                    "With the 'Thousand Cuts' technique, {winner}'s knife inflicts numerous small wounds until {loser} succumbs to blood loss!",
                    "{winner} drives their knife up under {loser}'s jaw, the blade penetrating into their brain!"
                ],
                "dagger": [
                    "{winner} forces {loser} to their knees before plunging their dagger into the base of their skull!",
                    "With a flourish, {winner} spins their dagger before driving it into {loser}'s heart with ceremonial precision!",
                    "{winner} slits {loser}'s hamstrings with their dagger, then delivers a final thrust to the throat as they fall!",
                    "The crowd roars as {winner} performs the 'Crimson Butterfly,' their dagger tracing lethal patterns across {loser}'s body!",
                    "Using the forbidden 'Soul Release,' {winner}'s dagger finds the exact spot to separate {loser} from their mortal coil!",
                    "{winner} drives their poisoned dagger into {loser}'s thigh, stepping back to watch as the toxin takes effect!",
                    "With merciless efficiency, {winner} slips their dagger between {loser}'s ribs and into their lung!",
                    "{winner} forces {loser}'s head back and drives their dagger up through the soft tissue beneath the chin!"
                ],
                "sword": [
                    "{winner} raises their sword high and brings it down in a perfect executioner's stroke, cleaving through {loser}'s neck!",
                    "With honor, {winner} allows {loser} to kneel before delivering a clean decapitation with their sword!",
                    "{winner} impales {loser} through the chest with their sword, twisting the blade to ensure a quick end!",
                    "The crowd chants as {winner} performs the 'Sundering Strike,' their sword splitting {loser} from collar to sternum!",
                    "Using the ancient 'Mercy of Steel,' {winner}'s sword removes {loser}'s head with a single fluid stroke!",
                    "{winner} drives their sword through {loser}'s mouth and out the back of their skull!",
                    "With the traditional 'Warrior's Release,' {winner} allows {loser} to fall on their outstretched sword!",
                    "{winner} slashes {loser} across the abdomen with their sword, releasing a cascade of viscera onto the sand!"
                ],
                "hammer": [
                    "{winner} swings their hammer in a devastating arc that caves in the side of {loser}'s skull!",
                    "With brutal efficiency, {winner} brings their hammer down on {loser}'s sternum, pulverizing heart and lungs!",
                    "{winner} sweeps {loser}'s legs with the hammer's shaft, then smashes their skull as they hit the ground!",
                    "The crowd winces as {winner} performs the 'Bonecrusher,' their hammer reducing {loser}'s rib cage to splinters!",
                    "Using the feared 'Final Rest,' {winner}'s hammer crushes {loser}'s spine where it meets the skull!",
                    "{winner} delivers a hammer blow to {loser}'s knee, crippling them before a final strike to the head!",
                    "With merciless strength, {winner} brings their hammer down repeatedly until {loser} no longer moves!",
                    "{winner} drives the spiked end of their hammer through {loser}'s eye socket and into their brain!"
                ],
                "bow": [
                    "{winner} nocks a final arrow, taking careful aim before sending it through {loser}'s eye!",
                    "With deadly precision, {winner}'s arrow pierces {loser}'s throat, silencing them forever!",
                    "{winner} fires three arrows in rapid succession, forming a perfect triangle in {loser}'s chest!",
                    "The crowd gasps as {winner} performs the 'Heart Seeker,' their arrow finding {loser}'s heart despite the armor!",
                    "Using the legendary 'Death from Afar,' {winner}'s arrow splits {loser}'s skull between the eyes!",
                    "{winner} fires a barbed arrow into {loser}'s stomach, ensuring a slow and painful end!",
                    "With ceremonial calm, {winner} sends their final arrow through {loser}'s open mouth and into their brain stem!",
                    "{winner} shoots {loser} through both knees, bringing them down before a mercy shot to the heart!"
                ],
                "scythe": [
                    "{winner} sweeps their scythe in a wide arc that separates {loser}'s head from their shoulders!",
                    "With theatrical flair, {winner} hooks {loser} with their scythe before disemboweling them with a single pull!",
                    "{winner} trips {loser} with the scythe's shaft before bringing the curved blade down through their chest!",
                    "The crowd falls silent as {winner} performs the 'Reaper's Harvest,' their scythe opening {loser} from groin to throat!",
                    "Using the dreaded 'Soul Collector,' {winner}'s scythe traces a glowing pattern in the air before cleaving through {loser}!",
                    "{winner} sweeps {loser}'s legs with their scythe's blade, severing tendons before a final stroke!",
                    "With ritual precision, {winner} places their scythe blade against {loser}'s throat before pulling it through!",
                    "{winner} spins their scythe overhead before bringing it down to split {loser}'s skull to the teeth!"
                ],
                "wand": [
                    "{winner} points their wand at {loser}, unleashing a spell that causes them to wither and age until only dust remains!",
                    "With arcane words, {winner}'s wand releases a bolt of energy that leaves a smoking hole in {loser}'s chest!",
                    "{winner} traces a complex sigil with their wand before {loser}'s blood boils within their veins!",
                    "The crowd shields their eyes as {winner} performs the 'Soul Flayer,' their wand extracting {loser}'s essence!",
                    "Using the forbidden 'Final Word,' {winner}'s wand turns {loser} to stone where they stand!",
                    "{winner} taps {loser} lightly with their wand, causing them to collapse as their heart simply stops!",
                    "With eldritch precision, {winner}'s wand unleashes a spell that unravels {loser} from existence!",
                    "{winner} points their wand at the ground beneath {loser}, opening a pit of flames that consumes them!"
                ],
                "shield": [
                    "{winner} smashes their shield's edge into {loser}'s throat, crushing their windpipe!",
                    "With brutal efficiency, {winner} brings their shield down on {loser}'s head repeatedly until movement ceases!",
                    "{winner} bashes {loser} off balance with their shield before driving its reinforced edge into their temple!",
                    "The crowd roars as {winner} performs the 'Ironwall Execution,' their shield crushing {loser}'s skull against the arena wall!",
                    "Using the dreaded 'Final Bastion,' {winner}'s shield becomes an instrument of death as it caves in {loser}'s chest!",
                    "{winner} hooks {loser}'s ankle with their shield, bringing them down before a fatal blow to the face!",
                    "With calculated force, {winner} drives the bottom edge of their shield up under {loser}'s chin, snapping their neck!",
                    "{winner} traps {loser}'s head between their shield and the ground, applying pressure until bones give way!"
                ],
                "mace": [
                    "{winner} brings their mace down upon {loser}'s head, the flanged weapon cracking their skull like an egg!",
                    "With ceremonial precision, {winner} delivers a perfect blow to {loser}'s temple with their mace!",
                    "{winner} sweeps {loser}'s legs then brings their mace down on their exposed chest, crushing organs beneath!",
                    "The crowd winces as {winner} performs the 'Judgment,' their mace reducing {loser}'s head to an unrecognizable mass!",
                    "Using the ancient 'Bell Ringer,' {winner}'s mace strikes with a sound that signals {loser}'s passage to the beyond!",
                    "{winner} shatters {loser}'s spine with their mace, leaving them paralyzed before a final blow to the skull!",
                    "With righteous fury, {winner}'s mace pulverizes {loser}'s chest cavity in a single mighty strike!",
                    "{winner} hooks {loser} with their mace's flanges, tearing flesh and bone in a display of brutal efficiency!"
                ],
                "axe": [
                    "{winner} brings their axe down upon {loser}'s head, cleaving through skull and brain in a single stroke!",
                    "With butcher's precision, {winner} severs {loser}'s head with a powerful swing of their axe!",
                    "{winner} buries their axe in {loser}'s chest, the blade finding their heart with unerring accuracy!",
                    "The crowd cheers as {winner} performs the 'Executioner's Right,' their axe separating {loser}'s head from shoulders!",
                    "Using the feared 'Woodsman's Harvest,' {winner}'s axe hews through {loser}'s neck like a fallen tree!",
                    "{winner} severs {loser}'s arm with their axe before delivering a final blow to the exposed neck!",
                    "With terrible strength, {winner} splits {loser} from crown to sternum with their heavy axe!",
                    "{winner} sweeps their axe low, hamstringing {loser} before a finishing blow parts their head from their body!"
                ],
                "spear": [
                    "{winner} drives their spear through {loser}'s chest, pinning them to the arena floor in a spray of blood!",
                    "With practiced efficiency, {winner} thrusts their spear through {loser}'s throat, severing their spine!",
                    "{winner} feints before driving their spear up under {loser}'s jaw and into their brain!",
                    "The crowd falls silent as {winner} performs the 'Impaler's Art,' their spear penetrating {loser} completely!",
                    "Using the ancient 'Pinning Strike,' {winner}'s spear finds {loser}'s heart with unerring accuracy!",
                    "{winner} sweeps {loser}'s legs with their spear shaft before impaling them through the stomach!",
                    "With perfect aim, {winner}'s spear finds the eye slit in {loser}'s helmet, ending their life instantly!",
                    "{winner} plants their spear in the sand before forcing {loser} to fall upon its point in the traditional death of honor!"
                ],
                "unknown": [
                    "{winner} ends {loser}'s life with brutal efficiency!",
                    "With merciless precision, {winner} delivers the final blow to {loser}!",
                    "{winner} claims victory as {loser}'s blood soaks into the arena sand!",
                    "The crowd roars as {winner} performs the killing stroke upon {loser}!",
                    "Using techniques perfected in countless battles, {winner} dispatches {loser} permanently!",
                    "{winner} ensures {loser} will never rise again to challenge another!",
                    "With deadly accuracy, {winner} targets {loser}'s vital points for an instant kill!",
                    "{winner} sends {loser} to the afterlife with a display of superior combat skill!"
                ]
            },
            "fablelands_references": [
                "The ancient wards of Valoria's Grand Arena flare to life, recognizing true warriors in {p1} and {p2}!",
                "From the mist-shrouded forests of Gloomhaven to the peaks of the Skyspear Mountains, word will spread of this battle!",
                "The Soothsayers of Mystral Bay predicted this clash between {p1} and {p2} in the stars a fortnight ago!",
                "The sacred fighting grounds of Bloodsand, oldest arena in all Fablelands, welcomes worthy combatants today!",
                "The spirits of fallen champions from the Age of Heroes look down from Warrior's Heaven upon this battle!",
                "By ancient tradition dating back to Emperor Valorian the Mighty, first ruler of Fablelands, this combat is sanctified!",
                "The mystic energy of the Leyline Nexus beneath the arena strengthens both {p1} and {p2} for glorious combat!",
                "Representatives from the Five Kingdoms of Fablelands watch with interest to scout potential champions!",
                "The Oracle of Whisperwind has blessed this arena with her presence, eager to witness the fates of {p1} and {p2}!",
                "As dictated in the Scrolls of Kharabad, these warriors salute the Emperor of Fablelands before their blood is shed!",
                "The legendary Beast Masters of the Southern Wilds have supplied today's arena hazards from their exotic collection!",
                "Runesmiths from the Forge Districts of Hammerhall inspect the warriors' weapons before combat commences!",
                "The sacred flame from the Temple of the Undefeated Burns brightly today, blessing this match with divine purpose!",
                "Veteran gladiators from the notorious Fighting Pits of Blackscar watch with professional interest!",
                "The mysterious Blue Tower mages have cast clarity spells over the arena, ensuring spectators miss no detail of combat!",
                "By decree of the Archduke of Westmarch, this battle shall be recorded in the Annals of Significant Combat!",
                "The dreaded Crimson Sisterhood has placed substantial bets on today's outcome, their assassins watching closely!",
                "Merchants from the Spice Road have brought exotic refreshments for nobles watching this highly anticipated match!",
                "As the twin moons of Fablelands align overhead, the ancient power of the arena intensifies for all who fight here!",
                "The Chronographers of Pendulum Keep time this match, for it may enter their records of legendary duels!",
                "Warriors of the fabled Iron Legion observe from reserved seats, evaluating potential recruits for their elite ranks!",
                "The Guild of Blades has sent representatives to study the fighting techniques displayed today!",
                "By ancient custom, the waters of Lake Silverblood have been sprinkled at the arena's four corners for good fortune!",
                "The Grandmaster of the Onyx Tower watches from the shadows, seeking promising disciples among today's fighters!",
                "Tribal shamans from the Razorback Steppes have blessed the weapons of both combatants with ancestral spirits!",
                "The notorious Laughing Jackals, arena champions from the Drylands of Khet, study the battle techniques on display!",
                "Healers from the Sacred Springs of Aeolus stand ready to attend wounds deemed non-fatal by the Emperor!",
                "The enchanted banners of Fablelands' nine provinces flutter in anticipation of glorious combat!",
                "Ancient war drums from the extinct Thunder Clans beat out the sacred rhythm that begins all honorable combat!",
                "The mystical soul-fires around the arena burn with the color of heightened emotions as the warriors prepare!"
            ],
            "crowd_reactions": [
                "The crowd surges against the barrier walls, bloodlust rising as the combat intensifies!",
                "Spectators throw colored flowers into the arena, showing their favor for the warrior wearing matching colors!",
                "The noble houses chant their champion's name, their voices unified in rhythmic support!",
                "A hush falls over the arena as even the most jaded spectators witness a display of exceptional skill!",
                "The crowd roars with such fervor that small stones fall from the ancient arena ceiling!",
                "Veteran gladiators in the audience nod with approval, recognizing the perfect execution of a difficult technique!",
                "The Fablelands betting masters scurry through the stands, adjusting odds as the fight's momentum shifts!",
                "Children on parents' shoulders wave miniature replicas of their favorite gladiator's weapons!",
                "The crowd stomps their feet in unison, creating a thunderous backdrop to the clash of steel below!",
                "Nobles fan themselves frantically, overcome by the intensity and brutality of the display!",
                "A wave of gasps sweeps through the audience as a particularly vicious blow lands with terrible effect!",
                "The Emperor's personal guards maintain their stoic vigilance despite the crowd's wild emotions!",
                "Arena veterans explain complex techniques to wide-eyed newcomers as the battle unfolds!",
                "The crowd falls utterly silent, holding their collective breath during a crucial moment of combat!",
                "Masked members of the mysterious Crimson Order observe from their private box, their interest piqued!",
                "Spectators from warring nations set aside their differences, united in appreciation of martial excellence!",
                "The crowd chants ancient battle hymns that echo the glory days of Fablelands' warrior past!",
                "Wealthy merchants toss gold coins into the arena to show their appreciation for particularly fine moves!",
                "Even the hardened arena slaves pause in their grim duties to witness an exchange of legendary quality!",
                "The crowd parts respectfully as the High Priestess of Astraea moves to the railing for a better view!",
                "Battle scholars furiously scribble notes, documenting techniques to teach the next generation!",
                "The arena's magical amplification crystals pulse with energy, feeding off the crowd's wild emotions!",
                "Spectators from the distant Frost Marches ululate in their traditional appreciation of spilled blood!",
                "The crowd reflexively leans away from the spray of blood that reaches the first row of seats!",
                "Children of noble houses receive their first taste of sanctioned violence, eyes wide with fascination!",
                "The notorious Pit Vipers, an infamous spectator gang, bang their weapons against the barrier in approval!",
                "A collective wince ripples through the audience as a particularly brutal injury is inflicted!",
                "Arena healers prepare their equipment as the combat reaches potentially fatal intensity!",
                "The famed Bardsinger of Lyria composes spontaneous verse about the unfolding combat!",
                "Spectators from enemy nations eye each other with newfound respect as their champions display equal valor!"
            ],
            "brutal_injuries": [
                "{victim}'s armor gives way, the blade sliding between ribs to puncture a lung! They cough a spray of crimson!",
                "The weapon finds {victim}'s shoulder joint, grinding against bone and severing tendons in a single vicious strike!",
                "A perfect blow catches {victim} in the face, shattering cheekbone and sending teeth scattering across the sand!",
                "{victim} howls in agony as their knee is destroyed, the joint bent at an impossible angle never intended by nature!",
                "The crowd winces collectively as {victim}'s forearm breaks with an audible crack, bone fragments protruding from flesh!",
                "Blood cascades from {victim}'s scalp, running into their eyes and painting their face in a horrific crimson mask!",
                "The brutal attack leaves {victim}'s ear hanging by a thread of tissue, their balance visibly affected!",
                "{victim} stumbles back as their nose explodes in a fountain of blood, cartilage completely destroyed!",
                "The weapon finds the gap between armor plates, leaving a wound in {victim}'s side that pulses with each heartbeat!",
                "A devastating blow to {victim}'s throat crushes their windpipe, leaving them gasping desperately for air!",
                "{victim}'s shield arm goes limp as tendons are severed at the wrist, fingers no longer responding to commands!",
                "The weapon tears through {victim}'s thigh, leaving a wound so deep that white bone is visible within!",
                "A perfect strike catches {victim} in the temple, their eyes rolling back as consciousness momentarily flees!",
                "{victim}'s armor dents inward from the powerful blow, ribs audibly cracking beneath the protective layer!",
                "The attack leaves {victim} with a wound from hip to rib, intestines threatening to spill through their desperate fingers!",
                "A precision strike finds {victim}'s eye, leaving it a ruined, weeping mass that will never see again!",
                "{victim} reels as their jaw dislocates from a powerful uppercut, leaving it hanging at an unnatural angle!",
                "The weapon finds the join in {victim}'s armor at the armpit, sinking deep into vulnerable flesh beneath!",
                "A sweeping blow takes {victim} behind the knees, hamstring tendons severing with a sound like wet rope snapping!",
                "{victim}'s helm is knocked free, revealing a deep furrow in their scalp that immediately flows with crimson!",
                "The crushing blow leaves {victim}'s collarbone shattered, their shoulder noticeably lower on the affected side!",
                "A precise strike pierces {victim}'s cheek, the weapon point briefly visible inside their open mouth!",
                "{victim} howls as their fingers are crushed, weapon falling from suddenly useless hands!",
                "The attack tears through {victim}'s calf muscle, leaving it hanging in tatters that will never heal properly!",
                "A savage blow to {victim}'s sternum leaves them struggling for breath, internal damage evident in their movements!",
                "The weapon finds {victim}'s inner thigh, blood pumping alarmingly fast from the femoral artery!",
                "{victim}'s attempt to block fails as the strike breaks their forearm, leaving the limb bent at a sickening angle!",
                "A powerful blow to {victim}'s kidneys leaves them retching, dark blood spilling from their mouth!",
                "The weapon glances off {victim}'s helm but tears their ear clean off in its passage!",
                "A devastating low blow leaves {victim} pale and vomiting, the crowd wincing in sympathetic pain!"
            ],
            "sword_duelist_comments": [
                "Two sword masters face each other! The ancient 'Way of the Blade' dictates this will be a combat of precision!",
                "Sword against sword! The classic duel that has decided the fate of kingdoms throughout Fablelands history!",
                "The Master Swordsmen of Highgarden would approve of the form displayed by these blade wielders!",
                "Steel rings against steel as these sword duelists honor the traditions of the Valorian Blade Schools!",
                "The crowd falls respectfully silent, recognizing the rare privilege of witnessing two sword masters at work!",
                "Every child in Fablelands who has swung a wooden sword dreams of mastering the blade as these warriors have!",
                "The legendary Sword Saints of the Eastern Provinces would find worthy successors in these combatants!",
                "When sword meets sword, the Scrolls of Battle say it is not strength but heart that determines the victor!"
            ],
            "axe_berserker_comments": [
                "The axe-wielder enters the Bloodrage stance, a technique forbidden in all arenas except Fablelands!",
                "Spectators from the Northern Clans ululate their traditional axe-warrior chants!",
                "The savage techniques of the Axe Tribes are on full display in this gladiator's brutal style!",
                "The distinct notches on the axe blade mark previous victims - a tradition of the Blackwood Berserkers!",
                "Axe warriors are known to enter a trance-like state where pain means nothing and blood is everything!",
                "The crowd chants 'CLEAVE! CLEAVE!' encouraging the primal savagery that axe-wielders are famous for!",
                "Each swing of the axe leaves a crimson arc in the air, the signature of a true Bloodreaver!",
                "The Berserker's Guild representatives watch with keen interest - this axe-wielder shows promise!"
            ],
            "mage_wand_comments": [
                "The wand-wielder traces ancient sigils in the air, arcane energy crackling at their command!",
                "Arena regulations require all battle-mages to wear the dampening bands that prevent arena-destroying spells!",
                "The Arcane Collegium rarely allows their members to participate in arena combat - this mage is a rare sight!",
                "Spectators shield their eyes as mystic energy flares from the tip of the battlemage's wand!",
                "The distinct blue flame of controlled arcane power dances along the wand's length!",
                "The crowd falls silent in respect and fear - magic users in Fablelands are both revered and dreaded!",
                "Protective wards around the arena glow in response to the magical energies being channeled!",
                "The distinct aroma of ozone and arcane components fills the air as the mage prepares their arts!"
            ],
            "dual_wielder_special": [
                "Dual weapons flash like lightning in the hands of this master of the Twin Fang fighting style!",
                "The crowd chants 'Left-Right-Death!' - the traditional call for dual-wielding combatants!",
                "Few can master fighting with weapons in both hands - this gladiator has clearly studied with the Ambidextrous Order!",
                "The paired weapons move in perfect harmony, displaying the legendary 'Twinned Soul' technique!",
                "In the ancient tongue of warriors, this fighting style translates to 'Death from Many Angles'!",
                "Spectators from the Twinblade Mountains perform their traditional dual-weapon salute!",
                "Arena physicians prepare their tools - dual-wielding fights typically result in twice the wounds!",
                "The Imperial Fencing Master nods with approval - controlling two weapons requires exceptional skill!"
            ],
            "massive_weapon_comments": [
                "The arena floor trembles with each impact of that massive weapon! Even grazing blows can shatter bone!",
                "Wielding such a tremendous armament requires strength bred through generations of warrior bloodlines!",
                "The Giantslayer Clans of Fablelands traditionally forge their weapons to enormous scale like this one!",
                "Spectators instinctively flinch when that behemoth of a weapon is raised for a strike!",
                "Traditional battle wisdom says: 'When the great weapon falls, do not be beneath it!'",
                "The distinctive fighting style originates from the Mountain Folk, who forge their children's spirits in steel!",
                "Arena slaves reinforce the barriers - weapons of this scale have been known to cleave through standard defenses!",
                "The crowd's collective breath catches with each massive swing - the raw destruction potential is awe-inspiring!"
            ],
            "ranged_weapon_master": [
                "The bow-wielder's fingers bear the distinctive calluses of the Thousand Arrow Brotherhood!",
                "Arena regulations require all arrow tips to be regulation width - still lethal, but retrievable by the healers!",
                "The Eastern Steppes produce the finest archers in Fablelands, and this one's stance is unmistakable!",
                "Spectators shield their eyes to better track the incredible speed of those arrows!",
                "The unique draw technique identifies this archer as a student of the legendary Hawkeye Monastery!",
                "The crowd maintains a respectful distance from the archer's firing line - stray shots in Fablelands arenas are rare but legendary!",
                "The distinct feathering pattern on those arrows marks them as crafted by the secretive Fletcher's Guild!",
                "Professional warriors in the audience nod with respect - mastering ranged combat in arena settings requires exceptional skill!"
            ]
        }
        
        # Special moves by weapon type
        self.special_moves = {
            "knife": ["Thousand Cuts", "Vital Strike", "Shadow Slice", "Crimson Talon", "Viper's Strike", "Death's Whisper", "Dancing Blade", "Arterial Slash", "Kidney Puncture", "Soul Piercer"],
            "dagger": ["Backstab", "Venomous Strike", "Kidney Slash", "Assassin's Kiss", "Throat Ripper", "Gut Wrench", "Heartseeker", "Silent End", "Shadow Dance", "Blood Collector"],
            "sword": ["Whirlwind Slash", "Piercing Thrust", "Blade Dancer's Fury", "Sundering Strike", "Valiant Charge", "Templar's Justice", "Heaven's Arc", "Dragon's Fang", "Knight's Vengeance", "Paladin's Oath"],
            "hammer": ["Skull Crusher", "Earthquake Smash", "Stunning Blow", "Ribcage Smasher", "Mountain's Wrath", "Anvil Strike", "Bone Breaker", "Thunder Fall", "Stone Render", "Executioner's Toll"],
            "bow": ["Rain of Arrows", "Piercing Shot", "Eagle Eye Strike", "Heaven's Volley", "Serpent Arrow", "Death from Afar", "Sundering Shaft", "Wind's Judgment", "Skyfall", "Heart Seeker"],
            "scythe": ["Soul Harvest", "Reaper's Sweep", "Death's Embrace", "Blood Moon Rising", "Grim Collection", "Final Threshold", "Bone Harvester", "Crimson Tide", "Life Thief", "Soul Severance"],
            "wand": ["Arcane Blast", "Mystic Barrage", "Eldritch Bolt", "Soulfire Eruption", "Mind Shatter", "Chaos Cascade", "Frostbite Surge", "Astral Detonation", "Mana Rupture", "Dimensional Slash"],
            "shield": ["Shield Bash", "Phalanx Defense", "Reflective Barrier", "Aegis Retribution", "Bulwark Charge", "Tower's Revenge", "Shieldbreaker", "Wall of Pain", "Bastion's Fall", "Unbreakable Will"],
            "mace": ["Holy Smite", "Bone Breaker", "Righteous Fury", "Judgment's Fall", "Skull Splitter", "Divine Wrath", "Crusader's Verdict", "Purifier's Strike", "Consecrated Blow", "Saint's Hammer"],
            "axe": ["Cleave", "Berserker Rage", "Splitting Maul", "Reaver's Cut", "Blood Eagle", "Savage Dismemberment", "Limb Taker", "Headhunter", "Gore Harvest", "Bloodthirst Rampage"],
            "spear": ["Impaling Thrust", "Javelin Throw", "Phalanx Charge", "Heartpiercer", "Serpent's Fang", "Dragon's Tail", "Piercing Heaven", "Horizon Strike", "Sundering Shaft", "Reaper's Reach"]
        }
        
        # Arena hazards and items for events
        self.arena_hazards = [
            "hungry lions", "venomous snakes", "swinging blade traps", "hidden pit spikes",
            "fire jets", "rabid wolves", "iron golems", "trained attack eagles",
            "the legendary Manticore", "a pack of hyenas", "mechanical blade scorpions",
            "flesh-eating scarabs", "poisonous gas vents", "animated statues",
            "the dreaded twin tigers of Kharabad", "spiked walls that slowly close in",
            "flooding waters filled with carnivorous fish", "a rain of burning oil",
            "the Emperor's prized wyvern", "enchanted weapons that fly of their own accord",
            "sand elementals", "a chariot driven by skeletal horses", "a ravenous chimera",
            "the notorious Blood Apes of the Southern Jungles"
        ]
        
        self.arena_items = [
            "a small shield", "a poisoned dagger", "an enchanted amulet", "a healing potion",
            "a handful of caltrops", "a net", "a section of chain", "throwing knives",
            "a spiked gauntlet", "a flask of burning oil", "a war horn that disorients opponents",
            "an ancestral charm that grants temporary strength", "a vial of basilisk blood",
            "a talisman that slows bleeding", "enchanted dust that blinds when thrown",
            "a ceremonial blade from the Temple of Astraea", "a whip lined with razor edges",
            "a grappling hook", "a vial of berserker's rage potion", "weighted bolas",
            "a smoke bomb", "a shield boss that can be used as a weapon", "a handful of flash powder",
            "a magically preserved heart that grants second wind when consumed"
        ]
        
        self.arena_conditions = [
            "fight standing on pedestals", "avoid the center pit", "contend with released beasts",
            "continue while the arena floods", "fight in complete darkness", "use only one arm",
            "fight back-to-back against new opponents", "switch to provided weapons",
            "battle with your legs chained together", "wear blindfolds and fight by sound alone",
            "continue as the arena floor rotates", "battle while poisonous gas slowly fills the area",
            "prove your worth against arena champions", "survive the Emperor's champion for one minute",
            "battle with weighted armor", "fight with weapons that gradually heat to burning temperatures",
            "compete to collect golden coins scattered in the hazardous areas", "show mercy on command",
            "battle on narrow bridges over deep pits", "win the crowd's favor through spectacular techniques",
            "use only weapons picked up from the arena floor", "battle while standing in ever-rising water",
            "fight with weapons too heavy for normal use", "prove themselves against captured war beasts"
        ]
        
        # Weapon type characteristics
        self.weapon_types = {
            "knife": {
                "strong_against": ["dagger", "wand"], 
                "weak_against": ["sword", "spear"],
                "handed": 1
            },
            "dagger": {
                "strong_against": ["wand", "knife"], 
                "weak_against": ["shield", "sword"],
                "handed": 1
            },
            "sword": {
                "strong_against": ["knife", "dagger"], 
                "weak_against": ["axe", "hammer"],
                "handed": 1
            },
            "hammer": {
                "strong_against": ["sword", "shield"], 
                "weak_against": ["spear", "knife"],
                "handed": 1
            },
            "bow": {
                "strong_against": ["sword", "spear"], 
                "weak_against": ["shield", "hammer"],
                "handed": 2
            },
            "scythe": {
                "strong_against": ["spear", "wand"], 
                "weak_against": ["bow", "mace"],
                "handed": 2
            },
            "wand": {
                "strong_against": ["mace", "axe"], 
                "weak_against": ["knife", "dagger"],
                "handed": 1
            },
            "shield": {
                "strong_against": ["dagger", "bow"], 
                "weak_against": ["mace", "hammer"],
                "handed": 1
            },
            "mace": {
                "strong_against": ["shield", "scythe"], 
                "weak_against": ["wand", "axe"],
                "handed": 2
            },
            "axe": {
                "strong_against": ["sword", "mace"], 
                "weak_against": ["spear", "wand"],
                "handed": 1
            },
            "spear": {
                "strong_against": ["axe", "hammer"], 
                "weak_against": ["scythe", "knife"],
                "handed": 1
            },
            "unknown": {
                "strong_against": [], 
                "weak_against": [],
                "handed": 1
            }
        }
        
        # Special events that can happen during battles
        self.special_events = [
            {
                "name": "audience_favor",
                "description": "The crowd shows favor to {player}, throwing a small token of support!",
                "bonus": 2
            },
            {
                "name": "weapon_strain",
                "description": "{player}'s {weapon} shows signs of strain under the brutal combat!",
                "penalty": -2
            },
            {
                "name": "critical_hit",
                "description": "{player} finds a gap in their opponent's defense for a devastating strike!",
                "bonus": 3
            },
            {
                "name": "arena_trap",
                "description": "{player} triggers a hidden arena trap! The crowd roars with excitement!",
                "penalty": -2
            },
            {
                "name": "battle_fury",
                "description": "A battle fury overcomes {player}, their attacks becoming more ferocious!",
                "bonus": 2
            },
            {
                "name": "footing_lost",
                "description": "The blood-soaked sand betrays {player}'s footing at a crucial moment!",
                "penalty": -1
            },
            {
                "name": "training_memory",
                "description": "{player} recalls a crucial lesson from their gladiator training!",
                "bonus": 2
            },
            {
                "name": "gladiator_technique",
                "description": "{player} executes a perfect arena technique with their {weapon}!",
                "bonus": 2
            },
            {
                "name": "equipment_failure",
                "description": "A piece of {player}'s armor comes loose at a critical moment!",
                "penalty": -2
            },
            {
                "name": "crowd_distraction",
                "description": "A sudden roar from the crowd momentarily distracts {player}!",
                "penalty": -1
            },
            {
                "name": "second_weapon",
                "description": "{player} draws a hidden secondary weapon, surprising their opponent!",
                "bonus": 2
            },
            {
                "name": "ancestral_memory",
                "description": "The spirits of fallen Fablelands warriors guide {player}'s hand for a moment!",
                "bonus": 3
            },
            {
                "name": "arena_favor",
                "description": "The ancient magic of the arena itself seems to favor {player}!",
                "bonus": 2
            },
            {
                "name": "blood_frenzy",
                "description": "The sight and smell of blood drives {player} into a terrifying frenzy!",
                "bonus": 3
            },
            {
                "name": "weapon_blessing",
                "description": "The runes on {player}'s {weapon} flare with ancestral power!",
                "bonus": 2
            },
            {
                "name": "muscle_cramp",
                "description": "{player}'s muscles seize painfully, their movements momentarily impaired!",
                "penalty": -2
            },
            {
                "name": "blinding_sand",
                "description": "Kicked-up sand blinds {player}, leaving them vulnerable!",
                "penalty": -2
            },
            {
                "name": "sun_glare",
                "description": "The merciless Fablelands sun reflects off metal, blinding {player}!",
                "penalty": -1
            },
            {
                "name": "blood_in_eyes",
                "description": "Blood from a scalp wound runs into {player}'s eyes, obscuring their vision!",
                "penalty": -2
            },
            {
                "name": "unexpected_recovery",
                "description": "Drawing on reserves of strength, {player} shakes off their fatigue!",
                "bonus": 2
            }
        ]

<<<<<<< HEAD
    async def manage_battle_message(self, ctx, battle_id, new_content, event_counter=0, force_new=False):
        """Create a new message or edit existing one based on event count and content length"""
        # Get battle context
        if battle_id not in self.battle_contexts:
            self.battle_contexts[battle_id] = {
                "battle_messages": [],
                "current_battle_message": None,
                "current_content": "",
                "message_counter": 0
            }

        battle_ctx = self.battle_contexts[battle_id]

        # Check if we need to create a new message
        if (force_new or
                not battle_ctx["current_battle_message"] or
                battle_ctx["message_counter"] >= 3 or
                len((battle_ctx["current_content"] + "\n\n" + new_content) if battle_ctx[
                    "current_content"] else new_content) > 1800):

            # Create a new message
            battle_ctx["current_content"] = new_content
            battle_ctx["current_battle_message"] = await ctx.send(f"{new_content}")
            battle_ctx["battle_messages"].append(battle_ctx["current_battle_message"])
            battle_ctx["message_counter"] = 1
        else:
            # Update existing message
            battle_ctx["current_content"] += f"\n\n{new_content}"
            await battle_ctx["current_battle_message"].edit(content=battle_ctx["current_content"])
            battle_ctx["message_counter"] += 1

        return battle_ctx["current_battle_message"]

=======
    async def manage_battle_message(self, ctx, new_content, event_counter=0, force_new=False):
        """Create a new message or edit existing one based on event count and content length"""
        # Check if we need to store this as a property
        if not hasattr(self, 'battle_messages'):
            self.battle_messages = []
            self.current_battle_message = None
            self.current_content = ""
            self.message_counter = 0
            
        # Check if we need to create a new message
        if (force_new or 
            self.message_counter >= 5 or 
            not self.current_battle_message or 
            len(self.current_content + "\n\n" + new_content) > 1950):
            
            # Create a new message
            self.current_content = new_content
            self.current_battle_message = await ctx.send(f"{new_content}")
            self.battle_messages.append(self.current_battle_message)
            self.message_counter = 1
        else:
            # Update existing message
            self.current_content += f"\n\n{new_content}"
            await self.current_battle_message.edit(content=self.current_content)
            self.message_counter += 1
            
        return self.current_battle_message
        
    
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
    async def get_weapon_info(self, ctx, user_id) -> Dict:
        """Get the weapon information of a user based on their equipped items."""
        try:
            async with self.bot.pool.acquire() as conn:
                # Get all equipped items for this user (should return 0-2 rows)
                items = await conn.fetch(
                    "SELECT ai.type, ai.name, p.god FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                    " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1",
                    user_id
                )
<<<<<<< HEAD

=======
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                result = {
                    "type": "unknown",
                    "name": "bare hands",
                    "handed": 1,  # Default: 1-handed
                    "god": None,  # Default: godless
                    "second_type": None,
                    "second_name": None,
                    "style": "unarmed"
                }
<<<<<<< HEAD

                if not items:
                    # No equipped items
                    return result

                # Check if any of the equipped items is a shield
                shield_item = None
                weapon_item = None

=======
                
                if not items:
                    # No equipped items
                    return result
                
                # Check if any of the equipped items is a shield
                shield_item = None
                weapon_item = None
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                for item in items:
                    item_type = item["type"].lower() if item["type"] else "unknown"
                    if item_type == "shield":
                        shield_item = item
                    else:
                        weapon_item = item
<<<<<<< HEAD

                # Set god from profile
                if items:
                    result["god"] = items[0].get("god")

=======
                
                # Set god from profile
                if items:
                    result["god"] = items[0].get("god")
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                # Prioritize weapon as primary if available
                if weapon_item:
                    result["type"] = weapon_item["type"].lower() if weapon_item["type"] else "unknown"
                    result["name"] = weapon_item["name"]
<<<<<<< HEAD

                    if result["type"] in self.weapon_types:
                        result["handed"] = self.weapon_types[result["type"]]["handed"]

=======
                    
                    if result["type"] in self.weapon_types:
                        result["handed"] = self.weapon_types[result["type"]]["handed"]
                    
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                    # If there's also a shield
                    if shield_item:
                        result["second_type"] = "shield"
                        result["second_name"] = shield_item["name"]
                        result["style"] = "shield"
                    else:
                        result["style"] = "two_handed" if result["handed"] == 2 else "single"
<<<<<<< HEAD

=======
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                # If only a shield is equipped (unusual but possible)
                elif shield_item:
                    result["type"] = "shield"
                    result["name"] = shield_item["name"]
                    result["style"] = "shield"
<<<<<<< HEAD

=======
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                return result
        except Exception as e:
            await ctx.send(f"Error getting weapon info: {e}")
            traceback.print_exc()
            return {
                "type": "unknown",
                "name": "bare hands",
                "handed": 1,
                "god": None,
                "second_type": None,
                "second_name": None,
                "style": "unarmed"
            }

    async def get_weapon_advantage(self, ctx, weapon1: str, weapon2: str) -> int:
        """Determine if one weapon has advantage over the other."""
        try:
            if weapon1 == "unknown" or weapon2 == "unknown":
                return 0
<<<<<<< HEAD

=======
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            if weapon2 in self.weapon_types.get(weapon1, {}).get("strong_against", []):
                return 1  # weapon1 has advantage
            elif weapon2 in self.weapon_types.get(weapon1, {}).get("weak_against", []):
                return -1  # weapon1 has disadvantage
            else:
                return 0  # neutral
        except Exception as e:
            # Log the error for debugging
            await ctx.send(f"Error getting weapon advantage: {e}")
            traceback.print_exc()
            # Return default values in case of error
            return 0

<<<<<<< HEAD
    async def manage_phase_message(self, ctx, battle_id, phase_name, new_content=None, edit=False, force_new=False):
        """Manages messages by battle phase."""
        # Get battle context
        if battle_id not in self.battle_contexts:
            self.battle_contexts[battle_id] = {
                "battle_messages": [],
                "current_battle_message": None,
                "current_content": "",
                "message_counter": 0,
                "phase_messages": {},
                "phase_contents": {}
            }

        battle_ctx = self.battle_contexts[battle_id]

        # Initialize phase messages dict if not exists in this battle context
        if "phase_messages" not in battle_ctx:
            battle_ctx["phase_messages"] = {}
            battle_ctx["phase_contents"] = {}

        # Create phase header
        header = f"⚔️ == {phase_name} == ⚔️"

        # If we need to create a new phase message
        if force_new or phase_name not in battle_ctx["phase_messages"]:
=======
    async def manage_battle_message(self, ctx, new_content, event_counter=0, force_new=False):
        """Create a new message or edit existing one based on event count and content length"""
        # Check if we need to create a new message
        if (force_new or 
            not self.current_battle_message or 
            self.message_counter >= 3 or  # Reduced from 5 to 3 for more frequent new messages
            len(self.current_content + "\n\n" + new_content) > 1800):  # Reduced limit for safety
            
            # Create a new message
            self.current_content = new_content
            self.current_battle_message = await ctx.send(f"{new_content}")
            self.battle_messages.append(self.current_battle_message)
            self.message_counter = 1
        else:
            # Update existing message
            self.current_content += f"\n\n{new_content}"
            await self.current_battle_message.edit(content=self.current_content)
            self.message_counter += 1
            
        return self.current_battle_message


    async def manage_phase_message(self, ctx, phase_name, new_content=None, edit=False, force_new=False):
        """
        Manages messages by battle phase.
        
        Parameters:
        - phase_name: The name of the battle phase (e.g., "PREPARATION PHASE")
        - new_content: Content to add to the phase message
        - edit: Whether to edit the existing phase message or create a new one
        - force_new: Force creation of a new message even if the phase exists
        
        Returns:
        - The phase message object
        """
        # Initialize phase messages dict if not exists
        if not hasattr(self, 'phase_messages'):
            self.phase_messages = {}
            self.phase_contents = {}
        
        # Create phase header
        header = f"⚔️ == {phase_name} == ⚔️"
        
        # If we need to create a new phase message
        if force_new or phase_name not in self.phase_messages:
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            if new_content:
                content = f"{header}\n{new_content}"
            else:
                content = header
<<<<<<< HEAD

            # Create new message for this phase
            battle_ctx["phase_messages"][phase_name] = await ctx.send(content)
            battle_ctx["phase_contents"][phase_name] = content

        # If we're editing an existing phase message
        elif edit and new_content:
            # Update content for this phase
            if phase_name not in battle_ctx["phase_contents"]:
                battle_ctx["phase_contents"][phase_name] = header

            battle_ctx["phase_contents"][phase_name] += f"\n{new_content}"

            # Edit the existing message
            await battle_ctx["phase_messages"][phase_name].edit(content=battle_ctx["phase_contents"][phase_name])

        return battle_ctx["phase_messages"][phase_name]
=======
                
            # Create new message for this phase
            self.phase_messages[phase_name] = await ctx.send(content)
            self.phase_contents[phase_name] = content
            
        # If we're editing an existing phase message
        elif edit and new_content:
            # Update content for this phase
            if phase_name not in self.phase_contents:
                self.phase_contents[phase_name] = header
                
            self.phase_contents[phase_name] += f"\n{new_content}"
            
            # Edit the existing message
            await self.phase_messages[phase_name].edit(content=self.phase_contents[phase_name])
        
        return self.phase_messages[phase_name]
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e

    @has_char()
    @user_cooldown(90)
    @discord.ext.commands.command(brief=_("Battle another player in the arena"))
    @locale_doc
    async def battle(self, ctx, money: IntGreaterThan(-1) = 0, enemy: discord.Member = None):
        _(
            """`[money]` - Amount to bet, defaults to 0
            `[enemy]` - The player to battle, defaults to anyone willing to join

            Challenge another player to a gladiatorial battle in the arena.
            Bet money on your victory, and the winner takes all!
<<<<<<< HEAD

            Weapons have strengths and weaknesses against other types.
            Two-handed weapons (bow, scythe, mace) have their own advantages.

            The gods (Astraea, Sepulchure, or Drakath) may intervene in battle.

            The victorious gladiator earns glory, gold, and a PvP win on their profile.
            (This command has a cooldown of 90 seconds.)"""
        )

        # Create a unique battle ID
        battle_id = f"{ctx.author.id}-{ctx.channel.id}-{int(time.time())}"

        # Initialize battle context for this battle
        self.battle_contexts[battle_id] = {
            "battle_messages": [],
            "current_battle_message": None,
            "current_content": "",
            "message_counter": 0,
            "phase_messages": {},
            "phase_contents": {}
        }

=======
            
            Weapons have strengths and weaknesses against other types.
            Two-handed weapons (bow, scythe, mace) have their own advantages.
            
            The gods (Astraea, Sepulchure, or Drakath) may intervene in battle.
            
            The victorious gladiator earns glory, gold, and a PvP win on their profile.
            (This command has a cooldown of 90 seconds.)"""
        )
        
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        # Initialize variables for potential refund in case of error
        challenger_id = ctx.author.id
        enemy_id = None
        money_deducted = False
        enemy_joined = False
<<<<<<< HEAD

=======
        
        # Reset phase messages for this session
        if hasattr(self, 'phase_messages'):
            self.phase_messages = {}
            self.phase_contents = {}
        else:
            self.phase_messages = {}
            self.phase_contents = {}
        
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        # Initialize battle tracking variables
        victory_points = [0, 0]  # Track actual points that determine winner
        last_event_winner = None  # Track who won the last event
        consecutive_wins = [0, 0]  # Track consecutive wins for momentum
<<<<<<< HEAD

        try:
            if enemy == ctx.author:
                # Clean up battle context
                if battle_id in self.battle_contexts:
                    del self.battle_contexts[battle_id]
                return await ctx.send(_("You can't battle yourself in the arena."))

            if ctx.character_data["money"] < money:
                # Clean up battle context
                if battle_id in self.battle_contexts:
                    del self.battle_contexts[battle_id]
=======
        
        try:
            if enemy == ctx.author:
                return await ctx.send(_("You can't battle yourself in the arena."))
            if ctx.character_data["money"] < money:
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                return await ctx.send(_("You don't have enough gold for this battle."))

            # Deduct the bet amount from challenger
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )
            money_deducted = True

            # Create battle invitation message
            if not enemy:
                if money > 0:
                    text = _("⚔️ {author} steps up to the arena gates seeking glory! The prize: **${money}**.").format(
                        author=ctx.author.mention, money=money
                    )
                else:
                    text = _("⚔️ {author} steps up to the arena gates seeking glory and honor!").format(
                        author=ctx.author.mention
                    )
            else:
                if money > 0:
                    text = _(
                        "⚔️ {author} calls out {enemy} before the arena master! The stakes: **${money}**."
                    ).format(author=ctx.author.mention, enemy=enemy.mention, money=money)
                else:
                    text = _(
                        "⚔️ {author} calls out {enemy} before the arena master!"
                    ).format(author=ctx.author.mention, enemy=enemy.mention)

            # Check if joining player has enough money
            async def check(user: discord.User) -> bool:
                try:
                    return await has_money(self.bot, user.id, money)
                except Exception as e:
                    await ctx.send(f"Error checking player funds: {str(e)}")
                    return False

            # Create SingleJoinView for the battle invitation
            future = asyncio.Future()
            view = SingleJoinView(
                future,
                Button(
                    style=ButtonStyle.danger,
                    label=_("Accept the challenge!"),
                    emoji="\U00002694",
                ),
                allowed=enemy,
                prohibited=ctx.author,
                timeout=60,
                check=check,
                check_fail_message=_("You don't have enough gold to accept this challenge."),
            )

            invitation_message = await ctx.send(text, view=view)

            try:
                enemy_ = await future
                enemy_id = enemy_.id
                enemy_joined = True
            except asyncio.TimeoutError:
                # No one accepted the challenge, refund the money
                await self.bot.reset_cooldown(ctx)
                if money_deducted:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    money_deducted = False
<<<<<<< HEAD
                # Clean up battle context
                if battle_id in self.battle_contexts:
                    del self.battle_contexts[battle_id]
=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                return await ctx.send(
                    _("The crowd boos as no one accepts {author}'s challenge!").format(
                        author=ctx.author.mention
                    )
                )

            # Deduct money from the accepting player
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, enemy_.id
            )

            # Get players' weapon information
            p1_weapon_info = await self.get_weapon_info(ctx, ctx.author.id)
            p2_weapon_info = await self.get_weapon_info(ctx, enemy_.id)
<<<<<<< HEAD

=======
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Choose gods if not already set
            gods = ["Astraea", "Sepulchure", "Drakath", None]
            p1_god = p1_weapon_info.get("god") or random.choice(gods)
            p2_god = p2_weapon_info.get("god") or random.choice(gods)
<<<<<<< HEAD

            # Format god names for display
            p1_god_display = p1_god if p1_god else "no patron deity"
            p2_god_display = p2_god if p2_god else "no patron deity"

            # Determine weapon advantage
            advantage = await self.get_weapon_advantage(ctx, p1_weapon_info["type"], p2_weapon_info["type"])

            # Get base stats and apply weapon advantage - CONVERT TO FLOAT HERE
            p1_stats_tuple = await self.bot.get_damage_armor_for(ctx.author)
            p2_stats_tuple = await self.bot.get_damage_armor_for(enemy_)

            # Convert Decimal to float to avoid type errors
            p1_stats = float(p1_stats_tuple[0]) + float(p1_stats_tuple[1])
            p2_stats = float(p2_stats_tuple[0]) + float(p2_stats_tuple[1])

=======
            
            # Format god names for display
            p1_god_display = p1_god if p1_god else "no patron deity"
            p2_god_display = p2_god if p2_god else "no patron deity"
            
            # Determine weapon advantage
            advantage = await self.get_weapon_advantage(ctx, p1_weapon_info["type"], p2_weapon_info["type"])
            
            # Get base stats and apply weapon advantage - CONVERT TO FLOAT HERE
            p1_stats_tuple = await self.bot.get_damage_armor_for(ctx.author)
            p2_stats_tuple = await self.bot.get_damage_armor_for(enemy_)
            
            # Convert Decimal to float to avoid type errors
            p1_stats = float(p1_stats_tuple[0]) + float(p1_stats_tuple[1])
            p2_stats = float(p2_stats_tuple[0]) + float(p2_stats_tuple[1])
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Apply 2-handed weapon bonus
            if p1_weapon_info["handed"] == 2:
                p1_stats += 1.0  # 2-handed bonus
            if p2_weapon_info["handed"] == 2:
                p2_stats += 1.0  # 2-handed bonus
<<<<<<< HEAD

=======
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Apply weapon advantage - Add victory points for advantage (IMPORTANT FOR NARRATIVE)
            if advantage == 1:
                p1_stats += 2.0
                victory_points[0] += 2  # Player 1 gets initial advantage points
            elif advantage == -1:
                p2_stats += 2.0
                victory_points[1] += 2  # Player 2 gets initial advantage points
<<<<<<< HEAD

            # Battle intro - introduce the gladiators
            intro = random.choice(self.commentaries["intros"]).format(
                p1=ctx.author.display_name,
=======
            
            # Battle intro - introduce the gladiators
            intro = random.choice(self.commentaries["intros"]).format(
                p1=ctx.author.display_name, 
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                p2=enemy_.display_name,
                w1=p1_weapon_info["name"],
                w2=p2_weapon_info["name"]
            )
<<<<<<< HEAD

=======
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Create battle embed
            battle_embed = discord.Embed(
                title="⚔️ ARENA BATTLE ⚔️",
                description=intro,
                color=0xe74c3c
            )
<<<<<<< HEAD

=======
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Add god affiliations if available
            p1_display = f"{ctx.author.display_name}"
            if p1_god:
                p1_display += f" ({p1_god_display})"
<<<<<<< HEAD

            p2_display = f"{enemy_.display_name}"
            if p2_god:
                p2_display += f" ({p2_god_display})"

            battle_embed.add_field(
                name=p1_display,
                value=f"Wielding: {p1_weapon_info['name']}" + (
                    f" & {p1_weapon_info['second_name']}" if p1_weapon_info['second_name'] else ""),
                inline=True
            )

            battle_embed.add_field(
                name=p2_display,
                value=f"Wielding: {p2_weapon_info['name']}" + (
                    f" & {p2_weapon_info['second_name']}" if p2_weapon_info['second_name'] else ""),
                inline=True
            )

            # Send the battle embed
            await ctx.send(embed=battle_embed)
            await asyncio.sleep(3)  # Wait 3 seconds before starting

=======
                
            p2_display = f"{enemy_.display_name}"
            if p2_god:
                p2_display += f" ({p2_god_display})"
            
            battle_embed.add_field(
                name=p1_display, 
                value=f"Wielding: {p1_weapon_info['name']}" + (f" & {p1_weapon_info['second_name']}" if p1_weapon_info['second_name'] else ""), 
                inline=True
            )
            
            battle_embed.add_field(
                name=p2_display, 
                value=f"Wielding: {p2_weapon_info['name']}" + (f" & {p2_weapon_info['second_name']}" if p2_weapon_info['second_name'] else ""), 
                inline=True
            )
            
            # Send the battle embed
            await ctx.send(embed=battle_embed)
            await asyncio.sleep(3)  # Wait 3 seconds before starting
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Pre-defined options for commentaries
            announcer_lines = [
                f"The crowds roar as the massive iron gates of the arena begin to open...",
                f"The beating of war drums fills the air as the gladiators prepare to enter the arena!",
                f"Thousands of spectators from across Fablelands fill the stands, eager for blood and glory!",
                f"The Emperor's box is draped with golden banners as nobles take their seats for the spectacle!",
                f"Vendors hawk their wares through the crowd as the arena floor is raked smooth for battle!",
                f"Betting masters hurry to collect final wagers before the competitors make their entrance!",
                f"The ancient arena stones seem to pulse with the energy of countless battles fought before!",
                f"Priests of Astraea bless the sands while acolytes of Sepulchure whisper dark omens at the gates!",
                f"The Arena Master raises his staff, commanding silence before the grand introduction!",
            ]
            
            p1_entrance_options = [
                f"{ctx.author.display_name} strides confidently into the arena, weapons glinting in the sunlight!",
                f"The crowd erupts as {ctx.author.display_name} enters, arms raised to acknowledge their fans!",
                f"{ctx.author.display_name} enters silently, eyes fixed on their opponent with cold determination!",
                f"With a battle cry that silences the crowd, {ctx.author.display_name} leaps into the arena!",
                f"Sand swirls around {ctx.author.display_name}'s boots as they step onto the hallowed fighting grounds!",
                f"{ctx.author.display_name} performs the traditional warrior's salute to the Emperor before turning to face battle!",
                f"The arena gates close with a thunderous boom behind {ctx.author.display_name} - there is no turning back now!",
                f"Flowers rain down from adoring fans as {ctx.author.display_name}, champion of many battles, enters the ring!",
                f"{ctx.author.display_name} kneels briefly to kiss the arena sand, honoring those who have fallen before!",
                f"With practiced showmanship, {ctx.author.display_name} draws their {p1_weapon_info['name']}, exciting the bloodthirsty crowd!"
            ]
            
            p2_entrance_options = [
                f"{enemy_.display_name} strides confidently into the arena, weapons glinting in the sunlight!",
                f"The crowd erupts as {enemy_.display_name} enters, arms raised to acknowledge their fans!",
                f"{enemy_.display_name} enters silently, eyes fixed on their opponent with cold determination!",
                f"With a battle cry that silences the crowd, {enemy_.display_name} leaps into the arena!",
                f"Sand swirls around {enemy_.display_name}'s boots as they step onto the hallowed fighting grounds!",
                f"{enemy_.display_name} performs the traditional warrior's salute to the Emperor before turning to face battle!",
                f"The arena gates close with a thunderous boom behind {enemy_.display_name} - there is no turning back now!",
                f"Flowers rain down from adoring fans as {enemy_.display_name}, champion of many battles, enters the ring!",
                f"{enemy_.display_name} kneels briefly to kiss the arena sand, honoring those who have fallen before!",
                f"With practiced showmanship, {enemy_.display_name} draws their {p2_weapon_info['name']}, exciting the bloodthirsty crowd!"
            ]
            
            announcer_intros = [
                f"Citizens of Fablelands! Today we witness a clash between {ctx.author.display_name} and {enemy_.display_name}! May the worthy prevail!",
                f"By decree of the Emperor, let it be known that {ctx.author.display_name} and {enemy_.display_name} shall battle for glory this day!",
                f"Two warriors enter! One shall leave victorious! {ctx.author.display_name} versus {enemy_.display_name}!",
                f"The sacred combat between {ctx.author.display_name} and {enemy_.display_name} shall commence! Prepare yourselves for blood and glory!",
                f"The gods watch with interest as {ctx.author.display_name} and {enemy_.display_name} prepare to test their fate!",
                f"Let the names of {ctx.author.display_name} and {enemy_.display_name} be recorded in the annals of the arena! Let combat begin!"
            ]
            
            commencement_options = [
                "A horn blasts, signaling the start of combat! The crowd roars as the fighters leap into action!",
                "The Arena Master drops his ceremonial scarf! The battle is joined with explosive fury!",
                "A thunderous gong reverberates through the arena! The warriors clash in a fury of steel and skill!",
                "\"FIGHT!\" The command echoes across the sands, and the gladiators explode into violent motion!",
                "The ritual drum reaches its crescendo, and as one, the fighters surge forward into battle!",
                "A flock of white doves is released overhead as the signal to begin this deadly dance!",
                "The Emperor's hand falls, and two destinies collide in a shower of sparks and battle cries!",
                "The sacred flame is extinguished, plunging the arena into shadow as the warriors engage!"
            ]
            
            # ========== PREPARATION PHASE ==========
            # Create a separate message for the preparation phase
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id, "PREPARATION PHASE")
=======
            await self.manage_phase_message(ctx, "PREPARATION PHASE")
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(2)  # Pause after section header
            
            # Create pre-battle atmosphere with arena announcements
            atmosphere = random.choice(announcer_lines)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id, "PREPARATION PHASE", f"🏟️ **Arena Atmosphere:** {atmosphere}", edit=True)
=======
            await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🏟️ **Arena Atmosphere:** {atmosphere}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Send entrance messages
            p1_entrance = random.choice(p1_entrance_options)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id, "PREPARATION PHASE", f"🥇 **Challenger:** {p1_entrance}", edit=True)
            await asyncio.sleep(4)
            
            p2_entrance = random.choice(p2_entrance_options)
            await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🥈 **Opponent:** {p2_entrance}", edit=True)
=======
            await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🥇 **Challenger:** {p1_entrance}", edit=True)
            await asyncio.sleep(4)
            
            p2_entrance = random.choice(p2_entrance_options)
            await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🥈 **Opponent:** {p2_entrance}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Announcer introduces the fighters formally
            formal_intro = random.choice(announcer_intros)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"📣 **Arena Master:** {formal_intro}", edit=True)
=======
            await self.manage_phase_message(ctx, "PREPARATION PHASE", f"📣 **Arena Master:** {formal_intro}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Add a Fablelands reference
            fablelands_ref = random.choice(self.commentaries["fablelands_references"]).format(
                p1=ctx.author.display_name,
                p2=enemy_.display_name
            )
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🌍 **Fablelands Lore:** {fablelands_ref}", edit=True)
=======
            await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🌍 **Fablelands Lore:** {fablelands_ref}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Show weapon style commentary for each player
            if p1_weapon_info["handed"] == 2:
                style_comment = random.choice(self.commentaries["two_handed_comments"]).format(
                    player=ctx.author.display_name,
                    weapon=p1_weapon_info["type"]
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🗡️ **Weapon Style:** {style_comment}", edit=True)
=======
                await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🗡️ **Weapon Style:** {style_comment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            elif p1_weapon_info["style"] == "shield":
                style_comment = random.choice(self.commentaries["shield_comments"]).format(
                    player=ctx.author.display_name
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🛡️ **Shield Style:** {style_comment}", edit=True)
=======
                await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🛡️ **Shield Style:** {style_comment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            if p2_weapon_info["handed"] == 2:
                style_comment = random.choice(self.commentaries["two_handed_comments"]).format(
                    player=enemy_.display_name,
                    weapon=p2_weapon_info["type"]
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🗡️ **Weapon Style:** {style_comment}", edit=True)
=======
                await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🗡️ **Weapon Style:** {style_comment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            elif p2_weapon_info["style"] == "shield":
                style_comment = random.choice(self.commentaries["shield_comments"]).format(
                    player=enemy_.display_name
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"🛡️ **Shield Style:** {style_comment}", edit=True)
=======
                await self.manage_phase_message(ctx, "PREPARATION PHASE", f"🛡️ **Shield Style:** {style_comment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Show weapon advantage if there is one
            if advantage != 0:
                if advantage == 1:
                    advantage_text = random.choice(self.commentaries["advantages"]).format(
                        p1=ctx.author.display_name, 
                        p2=enemy_.display_name,
                        weapon1=p1_weapon_info["name"],
                        weapon2=p2_weapon_info["name"],
                        god=p1_god_display
                    )
<<<<<<< HEAD
                    await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"⚡ **Tactical Advantage:** {advantage_text}", edit=True)
=======
                    await self.manage_phase_message(ctx, "PREPARATION PHASE", f"⚡ **Tactical Advantage:** {advantage_text}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                else:
                    advantage_text = random.choice(self.commentaries["advantages"]).format(
                        p1=enemy_.display_name, 
                        p2=ctx.author.display_name,
                        weapon1=p2_weapon_info["name"],
                        weapon2=p1_weapon_info["name"],
                        god=p2_god_display
                    )
<<<<<<< HEAD
                    await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"⚡ **Tactical Advantage:** {advantage_text}", edit=True)
=======
                    await self.manage_phase_message(ctx, "PREPARATION PHASE", f"⚡ **Tactical Advantage:** {advantage_text}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                await asyncio.sleep(4)

            # Check if there's a significant difference in base stats
            # Get the base stats including 2-handed bonuses but before weapon advantages
            p1_base_stats = float(p1_stats_tuple[0]) + float(p1_stats_tuple[1])
            p2_base_stats = float(p2_stats_tuple[0]) + float(p2_stats_tuple[1])

            # Apply 2-handed weapon bonus to base stats for comparison
            if p1_weapon_info["handed"] == 2:
                p1_base_stats += 1.0  # 2-handed bonus
            if p2_weapon_info["handed"] == 2:
                p2_base_stats += 1.0  # 2-handed bonus

            # Use a 20% threshold for "significant" stat difference
            stat_dominance_threshold = 0.2  # 20% difference

            # Avoid division by zero
            p1_base_safe = max(p1_base_stats, 0.1)
            p2_base_safe = max(p2_base_stats, 0.1)

            stat_difference = abs(p1_base_safe - p2_base_safe)
            stat_difference_percentage = stat_difference / min(p1_base_safe, p2_base_safe)

            if stat_difference_percentage >= stat_dominance_threshold:
                dominant_player = ctx.author if p1_base_stats > p2_base_stats else enemy_
                underdog_player = enemy_ if p1_base_stats > p2_base_stats else ctx.author
                
                # Determine if weapon advantage helps or hurts the base stats advantage
                weapon_helps_dominant = False
                if (dominant_player == ctx.author and advantage == 1) or (dominant_player == enemy_ and advantage == -1):
                    weapon_helps_dominant = True
                
                weapon_helps_underdog = False
                if (underdog_player == ctx.author and advantage == 1) or (underdog_player == enemy_ and advantage == -1):
                    weapon_helps_underdog = True
                
                # Different message depending on how weapon advantage plays in
                if weapon_helps_dominant:
                    dominance_messages = [
                        f"The crowd murmurs as {dominant_player.display_name} enters the arena - both superior combat skills AND a favorable weapon matchup make them the clear favorite!",
                        f"Betting masters frantically adjust their odds in {dominant_player.display_name}'s favor - their greater prowess combined with tactical weapon advantage spells doom for {underdog_player.display_name}!",
                        f"A double advantage! {dominant_player.display_name}'s superior combat record is further enhanced by their ideal weapon choice against {underdog_player.display_name}!",
                        f"The Arena Master shakes his head at the mismatch - {dominant_player.display_name} outclasses {underdog_player.display_name} in both skill and weapon strategy!"
                    ]
                elif weapon_helps_underdog:
                    dominance_messages = [
                        f"While {dominant_player.display_name}'s combat prowess clearly outmatches {underdog_player.display_name}, the underdog's weapon choice might help even the odds!",
                        f"Betting masters note that despite {dominant_player.display_name}'s superior skills, {underdog_player.display_name}'s tactical weapon advantage gives them a fighting chance!",
                        f"{dominant_player.display_name} brings greater experience and strength to the arena, though {underdog_player.display_name}'s weapon selection shows strategic thinking!",
                        f"The Arena Master observes that while {dominant_player.display_name} is clearly the more accomplished gladiator, {underdog_player.display_name}'s favorable weapon matchup could prove crucial!"
                    ]
                else:
                    dominance_messages = [
                        f"The crowd murmurs as {dominant_player.display_name} enters the arena - their reputation and combat prowess clearly outmatching {underdog_player.display_name}!",
                        f"Betting masters adjust their odds heavily in favor of {dominant_player.display_name}, recognizing their superior training and equipment!",
                        f"Veterans in the crowd whisper that {underdog_player.display_name} faces an uphill battle against the superior skills of {dominant_player.display_name}!",
                        f"The Arena Master raises an eyebrow at the matchup - {dominant_player.display_name}'s combat record clearly overshadows {underdog_player.display_name}'s!"
                    ]
                
                underdog_courage_messages = [
                    f"Yet {underdog_player.display_name} shows no fear, stepping forward with the courage that defines a true gladiator!",
                    f"Despite the odds, determination blazes in {underdog_player.display_name}'s eyes - perhaps enough to turn the tide of fate!",
                    f"The crowd admires {underdog_player.display_name}'s bravery in facing such a formidable opponent!",
                    f"As the saying goes in Fablelands: 'The fiercest wolves were once underestimated pups.' Will {underdog_player.display_name} prove this true today?",
                    f"History is written by those who defy expectations - will {underdog_player.display_name} author a new chapter of arena legend today?"
                ]
                
                dominance_message = random.choice(dominance_messages)
                courage_message = random.choice(underdog_courage_messages)
                
                # Add to preparation phase
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "PREPARATION PHASE", f"⚔️ **Battle Odds:** {dominance_message} {courage_message}", edit=True)
=======
                await self.manage_phase_message(ctx, "PREPARATION PHASE", f"⚔️ **Battle Odds:** {dominance_message} {courage_message}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                await asyncio.sleep(4)

            
            # Battle commencement signal
            commencement = random.choice(commencement_options)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"⚔️ **Battle Begins:** {commencement}", edit=True)
=======
            await self.manage_phase_message(ctx, "BATTLE BEGINS", f"⚔️ **Battle Begins:** {commencement}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)
            
            # Battle events
            event_count = random.randint(5, 8)
            players = [ctx.author, enemy_]
            player_info = [p1_weapon_info, p2_weapon_info]
            player_stats = [p1_stats, p2_stats]
            player_gods = [p1_god, p2_god]
            
            # Special tracking to ensure narrative balance
            special_move_used = [False, False]
            comeback_narrated = [False, False]
            divine_intervention = [False, False]
            
            # Track events for grouping
            event_counter = 0
            need_blank_line = False  # Flag to determine if we need a blank line before next event
            
            for i in range(event_count):
                # Every 3 events, add a blank line for better readability
                if event_counter >= 3:
                    need_blank_line = True
                    event_counter = 0
                
                # Add blank line if needed
                if need_blank_line:
<<<<<<< HEAD
                    await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", " ", edit=True)
=======
                    await self.manage_phase_message(ctx, "BATTLE BEGINS", " ", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                    need_blank_line = False
                
                # Determine which player is featured in this event
                # Important change: favor player with higher stats less often (give underdog more narrative focus)
                if i < 2:
                    # First events should include both players taking turns
                    player_idx = i % 2
                elif i == event_count - 1:
                    # Last event should favor the underdog if they're not too far behind
                    if abs(victory_points[0] - victory_points[1]) <= 5:
                        player_idx = 0 if victory_points[0] < victory_points[1] else 1
                    else:
                        # Otherwise, favor the player who's winning
                        player_idx = 0 if victory_points[0] > victory_points[1] else 1
                else:
                    # Middle events - give underdog more chances
                    # If there's a big point difference, give the underdog 70% of events
                    if abs(victory_points[0] - victory_points[1]) > 5:
                        underdog_idx = 0 if victory_points[0] < victory_points[1] else 1
                        player_idx = underdog_idx if random.random() < 0.7 else 1 - underdog_idx
                    else:
                        # Otherwise somewhat random but slightly favor underdog
                        underdog_idx = 0 if player_stats[0] < player_stats[1] else 1
                        player_idx = underdog_idx if random.random() < 0.55 else 1 - underdog_idx
                
                player = players[player_idx]
                opponent_idx = 1 - player_idx
                opponent = players[opponent_idx]
                
                try:
                    # Determine event type with weighted probabilities
                    event_type = random.choices(
                        ["attack", "special_event", "special_move", "arena_event", "divine_intervention"],
                        weights=[0.4, 0.25, 0.15, 0.15, 0.05],
                        k=1
                    )[0]
                    
                    # Skip divine intervention if character is godless or already had one
                    if event_type == "divine_intervention" and (
                        not player_gods[player_idx] or divine_intervention[player_idx]
                    ):
                        event_type = "attack"
                    
                    # Skip special move if already used
                    if event_type == "special_move" and special_move_used[player_idx]:
                        event_type = "attack"
                    
                    # If underdog is way behind, give them more chance for special move/divine intervention
                    if victory_points[player_idx] < victory_points[opponent_idx] - 8 and random.random() < 0.6:
                        if player_gods[player_idx] and not divine_intervention[player_idx]:
                            event_type = "divine_intervention"
                        elif not special_move_used[player_idx]:
                            event_type = "special_move"
                    
                    # Handle different event types
                    if event_type == "attack":
                        # Get weapon-specific attack commentary if available
                        weapon_type = player_info[player_idx]["type"]
                        attack_key = f"{weapon_type}_attacks"
                        
                        if attack_key in self.commentaries:
                            attack = random.choice(self.commentaries[attack_key]).format(
                                attacker=player.display_name,
                                defender=opponent.display_name,
                                weapon=player_info[player_idx]["name"]
                            )
                        else:
                            # Fall back to generic attacks
                            attack = random.choice(self.commentaries["attacks"]).format(
                                attacker=player.display_name,
                                weapon=player_info[player_idx]["name"]
                            )
                        
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"⚔️ **Attack:** {attack}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"⚔️ **Attack:** {attack}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        await asyncio.sleep(3)  # Wait before showing the result
                        
                        # Determine attack success (60% chance base, modified by stat difference)
                        stat_diff = player_stats[player_idx] - player_stats[opponent_idx]
                        success_chance = 0.6 + (stat_diff * 0.05)  # Each point difference is 5% advantage
                        
                        # Important change: If player is behind in victory points, increase chance of success
                        if victory_points[player_idx] < victory_points[opponent_idx]:
                            # The more behind they are, the higher the boost (up to +0.15)
                            point_diff = victory_points[opponent_idx] - victory_points[player_idx]
                            comeback_boost = min(point_diff * 0.03, 0.15)
                            success_chance += comeback_boost
                        
                        success = random.random() < min(max(success_chance, 0.3), 0.9)  # Bound between 30% and 90%
                        
                        if success:
                            # Attack succeeds - possibly add a brutal injury description
                            damage_points = random.randint(2, 4)  # Important change: Bigger impact for hits
                            
                            # Add victory points for successful hit
                            victory_points[player_idx] += damage_points
                            player_stats[opponent_idx] -= float(damage_points)
                            
                            # Update consecutive wins tracker
                            last_event_winner = player_idx
                            consecutive_wins[player_idx] += 1
                            consecutive_wins[opponent_idx] = 0
                            
                            # Chance for a brutal injury description
                            if random.random() < 0.3:  # 30% chance for brutal injury
                                injury = random.choice(self.commentaries["brutal_injuries"]).format(
                                    victim=opponent.display_name
                                )
<<<<<<< HEAD
                                await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🩸 **Brutal Injury:** {injury}", edit=True)
                            else:
                                await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"💥 **Hit:** The strike lands true! {opponent.display_name} staggers back!", edit=True)
=======
                                await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🩸 **Brutal Injury:** {injury}", edit=True)
                            else:
                                await self.manage_phase_message(ctx, "BATTLE BEGINS", f"💥 **Hit:** The strike lands true! {opponent.display_name} staggers back!", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        else:
                            # Attack is defended - use weapon-specific defense
                            defender_weapon = player_info[opponent_idx]["type"]
                            defense_key = f"{defender_weapon}_defenses"
                            
                            # Add small victory point for successful defense
                            victory_points[opponent_idx] += 1
                            
                            if defense_key in self.commentaries:
                                defense = random.choice(self.commentaries[defense_key]).format(
                                    defender=opponent.display_name,
                                    attacker=player.display_name,
                                    weapon=player_info[opponent_idx]["name"]
                                )
                            else:
                                # Fall back to generic defenses
                                defense = random.choice(self.commentaries["defenses"]).format(
                                    defender=opponent.display_name,
                                    weapon=player_info[opponent_idx]["name"]
                                )
<<<<<<< HEAD
                            await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🛡️ **Defense:** {defense}", edit=True)
=======
                            await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🛡️ **Defense:** {defense}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                    
                    elif event_type == "special_event":
                        # Random special event
                        event = random.choice(self.special_events)
                        
                        # Format the event description
                        event_text = event["description"].format(
                            player=player.display_name,
                            weapon=player_info[player_idx]["name"]
                        )
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🌟 **Special Event:** {event_text}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🌟 **Special Event:** {event_text}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                        # Apply event effect to stats and victory points
                        if "bonus" in event:
                            event_bonus = float(event["bonus"])
                            player_stats[player_idx] += event_bonus
                            victory_points[player_idx] += int(event_bonus * 1.5)
                            
                            # Update consecutive wins tracker for positive event
                            last_event_winner = player_idx
                            consecutive_wins[player_idx] += 1
                            consecutive_wins[opponent_idx] = 0
                        elif "penalty" in event:
                            event_penalty = float(event["penalty"])
                            player_stats[player_idx] += event_penalty  # Should be negative
                            victory_points[opponent_idx] += int(abs(event_penalty))
                            
                            # Update consecutive wins tracker for negative event
                            last_event_winner = opponent_idx
                            consecutive_wins[opponent_idx] += 1
                            consecutive_wins[player_idx] = 0
                        
                        # Check if comeback narrative would be appropriate
                        if victory_points[player_idx] < victory_points[opponent_idx] - 6 and not comeback_narrated[player_idx]:
                            comeback = random.choice(self.commentaries["comebacks"]).format(
                                player=player.display_name,
                                god=player_gods[player_idx] or "the gods"
                            )
                            await asyncio.sleep(3)  # Wait before showing comeback
<<<<<<< HEAD
                            await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"💪 **Comeback:** {comeback}", edit=True)
=======
                            await self.manage_phase_message(ctx, "BATTLE BEGINS", f"💪 **Comeback:** {comeback}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                            
                            # Big boost for comeback
                            comeback_bonus = random.randint(4, 6)
                            victory_points[player_idx] += comeback_bonus
                            player_stats[player_idx] += float(comeback_bonus / 2)
                            
                            comeback_narrated[player_idx] = True
                            event_counter += 1
                    
                    elif event_type == "special_move":
                        # Special weapon move
                        weapon_type = player_info[player_idx]["type"]
                        
                        # Get appropriate special moves for this weapon type
                        moves = self.special_moves.get(weapon_type, ["Desperate Attack", "Warrior's Gambit", "Battle Tactic"])
                        
                        # Format special move
                        move_name = random.choice(moves)
                        special_move = random.choice(self.commentaries["special_moves"]).format(
                            attacker=player.display_name,
                            weapon=player_info[player_idx]["name"],
                            move=move_name,
                            god=player_gods[player_idx] or "the gods"
                        )
                        
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"✨ **Special Move:** {special_move}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"✨ **Special Move:** {special_move}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                        # Special moves have big impact
                        damage_points = random.randint(4, 6)  # Important change: Bigger impact
                        victory_points[player_idx] += damage_points
                        player_stats[opponent_idx] -= float(damage_points / 2)
                        special_move_used[player_idx] = True
                        
                        # Update consecutive wins tracker
                        last_event_winner = player_idx
                        consecutive_wins[player_idx] += 1
                        consecutive_wins[opponent_idx] = 0
                        
                        await asyncio.sleep(3)  # Wait before showing effect
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"💥 **Effect:** A devastating technique! {opponent.display_name} suffers greatly!", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"💥 **Effect:** A devastating technique! {opponent.display_name} suffers greatly!", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                    
                    elif event_type == "arena_event":
                        # Random arena event that affects both fighters
                        event_text = random.choice(self.commentaries["arena_events"]).format(
                            player=player.display_name,
                            item=random.choice(self.arena_items),
                            hazard=random.choice(self.arena_hazards),
                            new_condition=random.choice(self.arena_conditions)
                        )
                        
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🏟️ **Arena Event:** {event_text}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🏟️ **Arena Event:** {event_text}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                        # Event affects both fighters but usually benefits one more
                        # Determine who benefits more
                        if random.random() < 0.7:  # Usually benefits triggered player
                            benefit_player = player_idx
                            suffer_player = opponent_idx
                        else:  # Sometimes benefits opponent
                            benefit_player = opponent_idx
                            suffer_player = player_idx
                        
                        # Apply benefits and penalties
                        benefit = random.randint(2, 4)
                        penalty = random.randint(1, 2)
                        
                        victory_points[benefit_player] += benefit
                        victory_points[suffer_player] -= penalty
                        
                        player_stats[benefit_player] += float(benefit / 2)
                        player_stats[suffer_player] -= float(penalty / 2)
                        
                        # Update consecutive wins tracker
                        last_event_winner = benefit_player
                        consecutive_wins[benefit_player] += 1
                        consecutive_wins[suffer_player] = 0
                    
                    elif event_type == "divine_intervention":
                        # Divine intervention based on character's god
                        god = player_gods[player_idx]
                        
                        intervention = random.choice(self.commentaries["godly_interventions"]).format(
                            player=player.display_name,
                            weapon=player_info[player_idx]["name"]
                        )
                        
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🔮 **Divine Intervention:** {intervention}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🔮 **Divine Intervention:** {intervention}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                        # Powerful bonus from the gods - major impact on victory points
                        god_bonus = random.randint(6, 8)
                        victory_points[player_idx] += god_bonus
                        player_stats[player_idx] += float(god_bonus / 2)
                        divine_intervention[player_idx] = True
                        
                        # Update consecutive wins tracker
                        last_event_winner = player_idx
                        consecutive_wins[player_idx] += 1
                        consecutive_wins[opponent_idx] = 0
                    
                    # Add crowd reactions occasionally 
                    if random.random() < 0.3:  # 30% chance after each event
                        await asyncio.sleep(2)  # Wait before showing crowd reaction
                        crowd_reaction = random.choice(self.commentaries["crowd_reactions"])
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"👥 **Crowd:** {crowd_reaction}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"👥 **Crowd:** {crowd_reaction}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                    # Show momentum updates strategically
                    if ((i == event_count // 2) or  # Middle of battle
                        (consecutive_wins[0] >= 3 or consecutive_wins[1] >= 3) or  # Someone is on a streak
                        (abs(victory_points[0] - victory_points[1]) > 10)):  # Big point difference
                        
                        # Reset consecutive wins after reporting
                        if consecutive_wins[0] >= 3 or consecutive_wins[1] >= 3:
                            streak_player = 0 if consecutive_wins[0] >= 3 else 1
                            streak_msg = f"{players[streak_player].display_name} is on a devastating streak, landing blow after blow!"
<<<<<<< HEAD
                            await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"🔥 **Battle Streak:** {streak_msg}", edit=True)
=======
                            await self.manage_phase_message(ctx, "BATTLE BEGINS", f"🔥 **Battle Streak:** {streak_msg}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                            consecutive_wins = [0, 0]
                            event_counter += 1
                        
                        # Ensure victory points don't go negative
                        victory_points = [max(0, points) for points in victory_points]
                        
                        # Create momentum message based on current points
                        if abs(victory_points[0] - victory_points[1]) <= 4:
                            momentum = f"The battle remains closely matched as {ctx.author.display_name} and {enemy_.display_name} exchange blows!"
                        elif victory_points[0] > victory_points[1]:
                            lead = "slight" if victory_points[0] - victory_points[1] < 8 else "strong"
                            momentum = f"{ctx.author.display_name} has gained a {lead} advantage in the battle!"
                        else:
                            lead = "slight" if victory_points[1] - victory_points[0] < 8 else "strong"
                            momentum = f"{enemy_.display_name} has gained a {lead} advantage in the battle!"
                        
                        await asyncio.sleep(2)
<<<<<<< HEAD
                        await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", f"⚖️ **Battle Momentum:** {momentum}", edit=True)
=======
                        await self.manage_phase_message(ctx, "BATTLE BEGINS", f"⚖️ **Battle Momentum:** {momentum}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                        event_counter += 1
                        
                except Exception as event_error:
                    # If an individual event fails, log it but continue with the battle
                    print(f"Error in event {i+1}: {event_error}")
<<<<<<< HEAD
                    await self.manage_phase_message(ctx, battle_id,  "BATTLE BEGINS", "👥 **Crowd:** The crowd's roar drowns out a moment of the battle...", edit=True)
=======
                    await self.manage_phase_message(ctx, "BATTLE BEGINS", "👥 **Crowd:** The crowd's roar drowns out a moment of the battle...", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                    event_counter += 1
                
                # Wait between events - longer pause for better readability
                await asyncio.sleep(4)
            
            # Ensure victory points don't go negative
            victory_points = [max(0, points) for points in victory_points]
            
            # Determine winner based on accumulated victory points
            if victory_points[0] == victory_points[1]:
                # In case of a tie, look at remaining stats
                if player_stats[0] >= player_stats[1]:
                    winner_idx = 0
                else:
                    winner_idx = 1
            else:
                winner_idx = 0 if victory_points[0] > victory_points[1] else 1
            
            winner = players[winner_idx]
            loser = players[1 - winner_idx]
            winner_weapon = player_info[winner_idx]
            loser_weapon = player_info[1 - winner_idx]
            
            # Determine if this is a comeback victory
            is_comeback = (winner_idx == 0 and advantage < 0) or (winner_idx == 1 and advantage > 0)
            
            # ========== DECISIVE MOMENT ==========
            # Create a separate message for the decisive moment
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "DECISIVE MOMENT")
=======
            await self.manage_phase_message(ctx, "DECISIVE MOMENT")
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(3)  # Longer pause before climax
            
            # Final decisive moment - customize based on how the battle went
            decisive_moments = []
            
            if is_comeback:
                decisive_moments = [
                    f"Against all odds, {winner.display_name} turns the tide with a brilliant counterattack!",
                    f"In a stunning reversal of fortune, {winner.display_name} overcomes {loser.display_name}'s early advantage!",
                    f"The crowd gasps as {winner.display_name} executes a desperate gambit that turns certain defeat into victory!",
                    f"Proving that battles are not won by advantages alone, {winner.display_name} claws back from the brink!",
                    f"With the endurance of a true champion, {winner.display_name} weathers the storm and seizes the perfect moment to strike!"
                ]
            elif victory_points[winner_idx] - victory_points[1-winner_idx] > 12:  # Dominant victory
                decisive_moments = [
                    f"{winner.display_name}'s dominance is complete as they deliver the finishing blow to a battered {loser.display_name}!",
                    f"The outcome was never in doubt as {winner.display_name} methodically dismantles {loser.display_name}'s defenses!",
                    f"With relentless skill, {winner.display_name} brings this one-sided contest to its inevitable conclusion!",
                    f"The difference in skill is laid bare as {winner.display_name} ends {loser.display_name}'s suffering with a final strike!",
                    f"Having controlled the entire battle, {winner.display_name} finishes with a flourish that brings the crowd to its feet!"
                ]
            else:  # Close victory
                decisive_moments = [
                    f"In a breathtaking exchange, {winner.display_name} finds the perfect opening!",
                    f"The crowd gasps as {winner.display_name} executes a masterful feint followed by a decisive strike!",
                    f"With perfect timing, {winner.display_name} counters {loser.display_name}'s attack and turns the tide!",
                    f"A momentary lapse in {loser.display_name}'s defense gives {winner.display_name} the opportunity they sought!",
                    f"Years of training culminate in this perfect moment as {winner.display_name} seizes victory!"
                ]
            
            decisive_moment = random.choice(decisive_moments)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "DECISIVE MOMENT", f"⚡ **Decisive Moment:** {decisive_moment}", edit=True)
=======
            await self.manage_phase_message(ctx, "DECISIVE MOMENT", f"⚡ **Decisive Moment:** {decisive_moment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)  # Longer pause after decisive moment
            
            # Final commentary - customize based on battle narrative
            if is_comeback:
                finishers = [
                    f"Glory and gold to {winner.display_name}! Their comeback will be celebrated in taverns across Fablelands!",
                    f"Let it be known throughout the empire that on this day, {winner.display_name} snatched victory from the jaws of defeat!",
                    f"Against all odds, {winner.display_name} has proven that skill and determination can overcome any advantage!",
                    f"The crowd chants the name of {winner.display_name}, honoring their resilience in the face of adversity!",
                    f"Victory belongs to {winner.display_name}! Their name will be etched in the annals of arena history today!"
                ]
            elif victory_points[winner_idx] - victory_points[1-winner_idx] > 12:  # Dominant victory
                finishers = [
                    f"A masterclass in combat! {winner.display_name}'s victory over {loser.display_name} was never in doubt!",
                    f"Glory and gold to {winner.display_name}, whose dominance in the arena today was absolute!",
                    f"The spectators will long remember the day {winner.display_name} made battling look effortless against {loser.display_name}!",
                    f"Let the historians record that {winner.display_name} utterly outclassed {loser.display_name} on the sands of Fablelands!",
                    f"A victory for the ages! {winner.display_name} has shown why they are feared throughout the fighting pits!"
                ]
            else:  # Close victory
                finishers = [
                    f"In a contest of equals, {winner.display_name} emerges victorious through skill and determination!",
                    f"Glory and gold to {winner.display_name}! Their name will be etched in the annals of arena history today!",
                    f"Let it be known throughout the empire that on this day, {winner.display_name} conquered the challenge of {loser.display_name}!",
                    f"Victory belongs to {winner.display_name} after a battle that had the crowds on the edge of their seats!",
                    f"The crowd roars their approval as {winner.display_name} stands triumphant in a battle for the ages!"
                ]
            
            finisher = random.choice(finishers)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "DECISIVE MOMENT", f"🏆 **Victory:** {finisher}", edit=True)
=======
            await self.manage_phase_message(ctx, "DECISIVE MOMENT", f"🏆 **Victory:** {finisher}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)  # Longer pause after victory
            
            # ========== EMPEROR'S JUDGMENT ==========
            # [Emperor's judgment section remains largely unchanged]
            # Create a separate message for the emperor's judgment
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT")
=======
            await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT")
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(3)  # Longer pause before judgment
            
            # Crowd anticipation
            anticipation_messages = [
                f"The crowd falls silent as all eyes turn to the Emperor's box...",
                f"A hush descends upon the arena as the Emperor considers the fate of the fallen...",
                f"The defeated {loser.display_name} kneels, head bowed, awaiting the Emperor's judgment...",
                f"Victory achieved, {winner.display_name} stands over {loser.display_name}, awaiting the final verdict...",
                f"Drums beat a slow rhythm as the Emperor deliberates the worth of the combat...",
                f"The arena master raises his staff, commanding absolute silence for the Imperial decree...",
                f"Blood-soaked sand darkens beneath {loser.display_name} as they await the Emperor's decision..."
            ]
            anticipation = random.choice(anticipation_messages)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"👑 **Emperor's Decision:** {anticipation}", edit=True)
=======
            await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"👑 **Emperor's Decision:** {anticipation}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)  # Longer pause before verdict
            
            # Emperor's verdict
            judgment = random.choice(self.commentaries["emperor_signals"])
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}", edit=True)
=======
            await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(5)  # Extended dramatic pause
            
            # Make mercy more likely for close battles, less likely for dominant victories
            mercy_chance = 0.5
            if is_comeback:
                mercy_chance = 0.7  # More mercy for exciting comebacks
            elif victory_points[winner_idx] - victory_points[1-winner_idx] > 12:
                mercy_chance = 0.3  # Less mercy for dominant victories
                
            if random.random() < mercy_chance:  # Mercy
                mercy = random.choice(self.commentaries["emperor_mercy"]).format(
                    loser=loser.display_name
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}\n\n**JUDGMENT:** {mercy}", edit=True)
=======
                await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}\n\n**JUDGMENT:** {mercy}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                
                # Add mercy reaction
                mercy_reactions = [
                    f"{loser.display_name} bows deeply, acknowledging the Emperor's mercy and {winner.display_name}'s superiority.",
                    f"Medical attendants rush to {loser.display_name}'s side, tending to wounds that will become honorable scars.",
                    f"The crowd cheers the Emperor's wisdom as {loser.display_name} lives to fight another day.",
                    f"{winner.display_name} helps {loser.display_name} to their feet in a display of warrior's respect.",
                    f"A relieved {loser.display_name} makes the traditional gesture of gratitude toward the Emperor's box."
                ]
                mercy_reaction = random.choice(mercy_reactions)
                await asyncio.sleep(4)
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"🤝 **Mercy:** {mercy_reaction}", edit=True)
=======
                await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"🤝 **Mercy:** {mercy_reaction}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            else:  # Death
                death = random.choice(self.commentaries["emperor_death"]).format(
                    winner=winner.display_name,
                    loser=loser.display_name
                )
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}\n\n**JUDGMENT:** {death}", edit=True)
=======
                await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"👑 **Emperor:** {judgment}\n\n**JUDGMENT:** {death}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                
                # Add execution details
                weapon_type = player_info[winner_idx]["type"]
                if weapon_type not in self.commentaries["finishing_moves"]:
                    weapon_type = "unknown"
                    
                finishing_move = random.choice(self.commentaries["finishing_moves"][weapon_type]).format(
                    winner=winner.display_name,
                    loser=loser.display_name
                )
                await asyncio.sleep(4)
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"☠️ **Execution:** {finishing_move}", edit=True)
=======
                await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"☠️ **Execution:** {finishing_move}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                
                # Add death aftermath
                death_aftermath = [
                    f"Arena slaves hurry forward with hooks to drag away the fallen as fresh sand is scattered over blood-soaked ground.",
                    f"The crowd's bloodlust sated, they cheer {winner.display_name}'s name as attendants prepare the arena for the next combat.",
                    f"Another soul joins the countless warriors who have fallen upon the sacred sands of Fablelands.",
                    f"{winner.display_name} raises their bloodied {player_info[winner_idx]['name']} high, accepting the adulation of the spectators.",
                    f"The priests of Astraea intone the final rites as {loser.display_name}'s journey in the arena comes to its end."
                ]
                aftermath = random.choice(death_aftermath)
                await asyncio.sleep(4)
<<<<<<< HEAD
                await self.manage_phase_message(ctx, battle_id,  "EMPEROR'S JUDGMENT", f"⚰️ **Aftermath:** {aftermath}", edit=True)
            
            # ========== BATTLE CONCLUSION ==========
            # Create a separate message for battle conclusion
            await self.manage_phase_message(ctx, battle_id,  "BATTLE CONCLUSION")
=======
                await self.manage_phase_message(ctx, "EMPEROR'S JUDGMENT", f"⚰️ **Aftermath:** {aftermath}", edit=True)
            
            # ========== BATTLE CONCLUSION ==========
            # Create a separate message for battle conclusion
            await self.manage_phase_message(ctx, "BATTLE CONCLUSION")
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(3)  # Pause after section header
            
            # Victor celebration
            victor_celebrations = [
                f"{winner.display_name} raises their arms in triumph as the crowd chants their name!",
                f"Garlands of victory are bestowed upon {winner.display_name} by the arena attendants!",
                f"The victorious {winner.display_name} performs the traditional champion's salute to all corners of the arena!",
                f"Glory and honor belong to {winner.display_name} this day as their legend grows in the Fablelands!",
                f"{winner.display_name} stands tall amid the roaring approval of thousands, bathed in the golden light of victory!"
            ]
            celebration = random.choice(victor_celebrations)
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "BATTLE CONCLUSION", f"🏆 **Victory Celebration:** {celebration}", edit=True)
=======
            await self.manage_phase_message(ctx, "BATTLE CONCLUSION", f"🏆 **Victory Celebration:** {celebration}", edit=True)
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            await asyncio.sleep(4)  # Final pause before results
            
            # Final result message
            if money > 0:
                result = _(f"**Arena Master:** The battle is decided! {winner.mention} defeats {loser.mention} in glorious combat! {money * 2} gold has been awarded to the victor!")
            else:
                result = _(f"**Arena Master:** The battle is decided! {winner.mention} defeats {loser.mention} in glorious combat! The victor claims honor and glory this day!")
            
<<<<<<< HEAD
            await self.manage_phase_message(ctx, battle_id,  "BATTLE CONCLUSION", result, edit=True)

            # Update database with winner info
=======
            await self.manage_phase_message(ctx, "BATTLE CONCLUSION", result, edit=True)
            
            # Update database
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "pvpwins"="pvpwins"+1, "money"="money"+$1 WHERE "user"=$2;',
                    money * 2,
                    winner.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=loser.id,
                    to=winner.id,
                    subject="Arena Battle",
                    data={"Gold": money},
                    conn=conn,
                )
<<<<<<< HEAD

            # Clean up battle context when done
            if battle_id in self.battle_contexts:
                del self.battle_contexts[battle_id]

=======
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
        except Exception as e:
            # Handle any exceptions that occur during battle
            import traceback
            error_traceback = traceback.format_exc()
            error_message = f"An error occurred during the battle:\n```{str(e)}```"
<<<<<<< HEAD

            await ctx.send(error_message)

=======
            
            await ctx.send(error_message)
            
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
            # Refund money to both players if battle failed
            try:
                if money_deducted:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        challenger_id,
                    )
<<<<<<< HEAD

=======
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                if enemy_joined and enemy_id:
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        enemy_id,
                    )
<<<<<<< HEAD

                await ctx.send(_("Gold has been refunded to both gladiators due to arena malfunction."))

=======
                
                await ctx.send(_("Gold has been refunded to both gladiators due to arena malfunction."))
                
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
                # Reset cooldown so player can try again
                await self.bot.reset_cooldown(ctx)
            except Exception as refund_error:
                await ctx.send(f"Error during refund process: {str(refund_error)}")

<<<<<<< HEAD
            # Clean up battle context even in case of error
            if battle_id in self.battle_contexts:
                del self.battle_contexts[battle_id]


=======
>>>>>>> 377581b229c4fa257ab84dcbe98be88cf6bd930e
async def setup(bot):
    await bot.add_cog(SimpleBattle(bot))