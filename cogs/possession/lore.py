"""Vessels, underlings and narration for the GM Possession event.

Every line the Possessor (the GM) receives is spoken by that vessel's
underling. Templates use str.format fields; missing fields render blank.
Shared fields: {round} {max_rounds} {weakest} {strongest} {rite} {goal}
{dread} {vessel_pct} {living} {target} {fallen}.
"""

import random
import string


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render(template, **fields):
    return string.Formatter().vformat(template, (), _Blank(fields))


def line(pool, **fields):
    return render(random.choice(pool), **fields)


VESSELS = {
    "sepulchure": {
        "god": "Sepulchure",
        "name": "the Doomknight's Husk",
        "voice": "The Husk",
        "emoji": "💀",
        "color": 0x5B0E0E,
        "arrival": (
            "The torches gutter out one by one. Something in black plate stands "
            "where no one stood a heartbeat ago, a Doomknight long dead with "
            "its visor empty. Then the helm *turns*. It is watching you, and something "
            "behind it is **thinking**.\n\n"
            "*Sepulchure has lent this husk to a will not its own. Stand against it.*"
        ),
        "abilities": {
            "smite": ("Doomblade", "🗡️", "The Husk raises its black blade and brings it down on {target}."),
            "execute": ("Headsman's Verdict", "⚰️", "The Husk seizes {target} by the throat and passes sentence."),
            "sweep": ("Shadow Cleave", "🌑", "A crescent of shadow tears across the line."),
            "siphon": ("Soul Tithe", "🩸", "Chains of red light hook into {target}. The Husk drinks."),
            "dominate": ("Black Chains of Will", "⛓️", "Invisible chains snap tight around {target}'s wrists."),
            "ward": ("Obsidian Carapace", "🛡️", "Volcanic glass creeps over the armor. Blows skitter off it."),
            "cataclysm": ("The Final Night", "🌘", "The sky goes out. For one breath there is only the dark, and it is hungry."),
        },
        "cataclysm_variance": None,
        "omen": "The torches die. The stars above the Husk go out one by one. **The Final Night is gathering.**",
        "interrupted": "The Husk staggers mid-invocation. The gathered dark bleeds away into nothing.",
        "phases": {
            2: "Cracks race across the black plate, and red light leaks from within. **The Husk's armor is broken.**",
            3: "The Husk tears off its own helm. There is no face beneath, only hunger. **It fights with everything it has left.**",
        },
        "endings": {
            "slain": "The Husk buckles. Black smoke pours from the joints of its armor, and whatever wore it screams as it is torn loose. The plate falls empty to the floor.",
            "exorcised": "The Severance closes like a fist. The Husk's visor flares white, and the will inside is *expelled*, flung back into Sepulchure's dark to answer for its failure.",
            "wiped": "The last raider falls. The Husk stands alone among the bodies and slowly, deliberately, sheathes its blade. Sepulchure is pleased.",
            "withdrawn": "Dawn breaks over the field. The Husk turns its empty visor to the sun, bows mockingly, and walks into the shadows. It will be back.",
        },
        "underling": {
            "name": "Grimvale",
            "title": "Keeper of the Black Ledger",
            "master": "my liege",
            "greeting": [
                "*A thin, ink-stained creature bows so low its nose touches the floor.*\n\n"
                "My liege. I am **Grimvale**, and I keep the Ledger of Debts. Sepulchure has lent you his "
                "Doomknight's Husk. Wear it well.\n\n"
                "Anything you **write to me here** I will speak aloud through the Husk's throat. The mortals "
                "will hear *you*. Each turn I will bring you their names and their weaknesses. Choose, and the "
                "Husk obeys.\n\n*The mortals are gathering now. Patience, my liege. Patience.*",
            ],
            "prompt": [
                "Turn {round}, my liege. {weakest} is bleeding badly. The Ledger says they are *overdue*.",
                "The mortals huddle together. {strongest} strikes hardest. Shall we make an example of them?",
                "My liege, the Husk holds at {vessel_pct}%. {living} mortals still draw breath. Whose name shall I cross out?",
                "*Grimvale licks his quill.* Turn {round} of {max_rounds}. I await your ruling.",
            ],
            "rite_warning": [
                "My liege! The Severance chant stands at **{rite}/{goal}**. If they finish, you are *cast out*. Silence the singers!",
                "They are chanting, my liege. {rite} of {goal}. I have seen the Ledger's end before, and it is not kind to the evicted.",
            ],
            "vessel_low": [
                "The Husk is cracking, my liege. {vessel_pct}% remains. Perhaps a Tithe would steady it?",
            ],
            "dread_full": [
                "The dark is full to bursting, my liege. **The Final Night** is yours to call.",
            ],
            "kill": [
                "*Grimvale strikes through a name with obvious delight.* {fallen}: paid in full.",
                "Another debt settled. {fallen} will not trouble us again.",
            ],
            "improvise_public": [
                "*A thin, ink-stained voice echoes from inside the helm:* \"The master is… occupied. I shall choose.\"",
                "*Something small and nervous whispers from the visor:* \"Er. My liege said… *this* one. Yes.\"",
            ],
            "improvise_private": "You were silent, my liege, so I chose for you. I do hope I chose well.",
            "charging": "The dark is gathering, my liege. It falls at the end of this turn, unless they break it first.",
            "victory": "*Grimvale closes the Ledger with trembling reverence.* Magnificent, my liege. Every debt collected.",
            "defeat": "*Grimvale is scrubbing your name from the Ledger before you have fully faded.* It was an honor, my liege. Mostly.",
        },
    },
    "drakath": {
        "god": "Drakath",
        "name": "the Laughing Colossus",
        "voice": "The Colossus",
        "emoji": "🌀",
        "color": 0x7A1FA2,
        "arrival": (
            "The ground hiccups. Stones fall *upward*. From a crack in the world "
            "climbs a titan stitched together from mismatched shards: marble, "
            "bone, a church bell, a door. Its face is a spinning mask of chaos-crystal, "
            "and it is **laughing** in a voice that isn't its own.\n\n"
            "*Drakath has handed his toy to a new player. Stand against it.*"
        ),
        "abilities": {
            "smite": ("Fracture Bolt", "⚡", "A jagged bolt of wrong-colored lightning finds {target}."),
            "execute": ("Last Laugh", "🃏", "The Colossus picks {target} up like a toy, and giggles."),
            "sweep": ("Riot of Shards", "🔮", "The Colossus shakes itself like a wet dog. Shards everywhere."),
            "siphon": ("Entropic Feast", "🌪️", "The air around {target} unravels, and the Colossus slurps the loose threads."),
            "dominate": ("Puppet Strings", "🪆", "Glittering strings drop from nowhere and loop around {target}'s limbs."),
            "ward": ("Kaleidoscope Mirror", "🪞", "The Colossus fractures into a hundred reflections. Which one is real?"),
            "cataclysm": ("The Great Unmaking", "🎲", "Drakath rolls the dice of the world. Nobody knows what the numbers mean."),
        },
        "cataclysm_variance": (0.3, 2.5),
        "omen": "Every die in the world starts rolling at once. **The Great Unmaking is gathering.**",
        "interrupted": "The dice clatter to the floor, every face blank. The Colossus pouts.",
        "phases": {
            2: "Chunks of marble and bell-bronze rain from the Colossus. **Its shell is broken.**",
            3: "The Colossus's mask spins so fast it screams. **It has stopped playing.**",
        },
                "endings": {
            "slain": "The Colossus shatters into ten thousand pieces, each one still giggling. The giggling fades. The pieces are just rocks now. Probably.",
            "exorcised": "The Severance snaps shut, and the mind inside the Colossus is spat out like a cherry pit. The shards fall down in a heap, bored.",
            "wiped": "Silence. Then the Colossus claps its mismatched hands, delighted. *Again,* it says. *Again, again, AGAIN.*",
            "withdrawn": "The Colossus loses interest mid-swing, wanders off, and folds itself into a crack in the sky. Drakath's attention has moved on.",
        },
        "underling": {
            "name": "Pip",
            "title": "the Unraveled Imp",
            "master": "boss",
            "greeting": [
                "*A small purple imp with three mismatched eyes pops out of your inkwell.*\n\n"
                "BOSS! Hi boss! I'm **Pip**! Drakath said I get to help you drive the big shiny Colossus!!\n\n"
                "Anything you **type to me here**, I'll shout through its big crystal face, so the "
                "mortals hear YOU. Each turn I'll tell you who's squishy. You pick the smashing, and I pull the levers!\n\n"
                "*Pip vibrates with anticipation.* They're gathering, boss. Tee-hee.",
            ],
            "prompt": [
                "Turn {round}, boss!! {weakest} looks REAL squishy. Can we? Can we??",
                "Ooh, ooh, {strongest} keeps hitting us. That's rude, boss. Let's be rude back.",
                "Colossus is at {vessel_pct}%! {living} little mortals left. Eeny, meeny, miny…",
                "Turn {round} of {max_rounds}, boss! Pick a lever, any lever!",
            ],
            "rite_warning": [
                "BOSS. BOSS. They're doing the boring chant! **{rite}/{goal}!** If they finish we get kicked out!!",
                "The Severance is at {rite} of {goal}, boss, and I do NOT like that song.",
            ],
            "vessel_low": [
                "Uh, boss? Bits are falling off. Like, important bits. We're at {vessel_pct}%.",
            ],
            "dread_full": [
                "Boss, the dice are GLOWING. **The Great Unmaking** is ready! Nobody knows what happens! Isn't that GREAT?",
            ],
            "kill": [
                "*Pip does a cartwheel.* {fallen} got UNMADE! Points for us!",
                "Byeeee, {fallen}! *Pip waves with all four hands.*",
            ],
            "improvise_public": [
                "*A tiny voice squeaks from somewhere inside the Colossus:* \"Boss isn't answering so I'M DRIVING!\"",
                "*The Colossus's face spins and briefly shows a purple imp grinning:* \"Pip's turn!\"",
            ],
            "improvise_private": "You were quiet so I pulled a random lever!! Was that the good one? It felt like the good one.",
            "charging": "The dice are ROLLING, boss!! End of this turn: BOOM. Unless they stop it. Don't let them stop it.",
            "victory": "*Pip is sobbing with joy.* Best. Boss. EVER. Can we do it again tomorrow?",
            "defeat": "*Pip pats your hand consolingly as you fade.* It's okay boss. Drakath says losing is just winning in a funny hat.",
        },
    },
    "elysia": {
        "god": "Elysia",
        "name": "the Hollow Seraph",
        "voice": "The Seraph",
        "emoji": "🕊️",
        "color": 0xD4C9A8,
        "arrival": (
            "A chord of choir-song, perfect and cold. Down through the clouds "
            "descends one of Elysia's own seraphim, six wings wide, crowned in light. "
            "The faithful kneel at first. Then they see its eyes: two hollow sockets "
            "with *something else* looking out through them.\n\n"
            "*A blessed thing has been hollowed out and worn like a mask. Stand against it.*"
        ),
        "abilities": {
            "smite": ("Hollow Radiance", "✴️", "A lance of cold, colorless light pierces {target}."),
            "execute": ("Last Rites", "🪦", "The Seraph kneels beside {target} and begins the last rites."),
            "sweep": ("Wings of Ash", "🪶", "Six wings beat once. Every feather is a blade of cinder."),
            "siphon": ("Mercy Inverted", "💧", "The Seraph lays a gentle hand on {target}, and takes rather than gives."),
            "dominate": ("Sermon of Obedience", "📿", "The Seraph speaks {target}'s true name, and {target} kneels."),
            "ward": ("Veil of Tears", "🌫️", "A shroud of weeping mist folds around the Seraph."),
            "cataclysm": ("Judgment Without Grace", "⚖️", "The Seraph lifts its hands and passes sentence on *everyone*."),
        },
        "cataclysm_variance": None,
        "omen": "The choir falls silent. Six wings rise to blot out the sun. **Judgment Without Grace is gathering.**",
        "interrupted": "The Seraph's raised hands falter. The sentence goes unspoken.",
        "phases": {
            2: "Feathers of light peel away, showing ash beneath. **The Seraph's halo is shattered.**",
            3: "The Seraph screams a hymn in a voice that is not Elysia's. **The mask is slipping.**",
        },
        "endings": {
            "slain": "The Seraph's wings fold. The light drains from its crown, and for one moment its eyes are its own again. *Thank you,* it whispers, and becomes dust.",
            "exorcised": "The Severance rings out like a bell. The foreign will is burned out of the Seraph, and it rises, whole and weeping, back toward Elysia's light.",
            "wiped": "The Seraph hovers over the fallen, humming a hymn no church has ever sung. Somewhere, Elysia is weeping.",
            "withdrawn": "The Seraph ascends slowly into the clouds. The choir-song fades, but the hollow eyes stay open. It will find another flock.",
        },
        "underling": {
            "name": "Sister Maren",
            "title": "the Unanswered",
            "master": "Holy One",
            "greeting": [
                "*A gaunt acolyte in a torn white habit kneels before you, eyes shining.*\n\n"
                "Holy One. I am **Sister Maren**. I prayed to Elysia for forty years and she never "
                "answered me. *You* answered.\n\n"
                "Whatever you **speak to me here**, I will sing through the Seraph's mouth, and the faithless will "
                "hear your voice as scripture. Each turn I will name the sinners. You pass judgment.\n\n"
                "*She folds her hands.* They are gathering, Holy One. Let them come.",
            ],
            "prompt": [
                "Turn {round}, Holy One. {weakest} is weak in body and in faith. Shall they be judged?",
                "{strongest} raises steel against a seraph. Such pride, Holy One. Such *sin*.",
                "The Seraph holds at {vessel_pct}%. {living} sinners remain. Speak, and I will make it so.",
                "Turn {round} of {max_rounds}. I kneel and await your word, Holy One.",
            ],
            "rite_warning": [
                "Holy One, they are chanting the Severance. **{rite}/{goal}**. They would cast you out of your temple!",
                "{rite} of {goal}, Holy One. Their heresy grows louder.",
            ],
            "vessel_low": [
                "The Seraph's light is failing, Holy One. {vessel_pct}%. Take what you need from them.",
            ],
            "dread_full": [
                "The scales are heavy, Holy One. **Judgment Without Grace** awaits only your word.",
            ],
            "kill": [
                "*Maren traces a sign in the air.* {fallen} has been judged. May they find the mercy we did not.",
                "{fallen} is gone, Holy One. I will not pray for them.",
            ],
            "improvise_public": [
                "*A thin, fervent voice sings from within the Seraph:* \"The Holy One is silent, so I shall interpret!\"",
                "*The Seraph's lips move, but the voice is a zealous acolyte's:* \"By the will of the Holy One!\"",
            ],
            "improvise_private": "You did not speak, Holy One, so I spoke for you. Forgive me if I erred.",
            "charging": "The sentence is being written, Holy One. It falls at the end of this turn, unless they silence it.",
            "victory": "*Maren weeps with joy.* I knew it. I *knew* someone was listening.",
            "defeat": "*Maren clutches your fading sleeve.* Don't go. Please. Not you too.",
        },
    },
}

ABILITY_RULES = {
    "smite": "heavy hit on one raider, breaks their chant",
    "sweep": "hits a third of the raid at random",
    "siphon": "hit one raider and heal from it, breaks their chant",
    "dominate": "turn one raider's action against the raid",
    "ward": "halve the damage you take this turn",
    "execute": "kill a raider under 25% HP unless they're guarded",
    "cataclysm": "hits everyone after a one-turn warning",
}

PLAYER_ACTION_FLAVOR = {
    "strike": ("Strike", "⚔️", "You ready your weapon."),
    "guard": ("Guard", "🛡️", "You brace to protect {target}."),
    "mend": ("Mend", "✨", "You prepare to tend {target}."),
    "rite": ("Rite", "🕯️", "You join the Severance chant."),
    "signature": ("Signature", "💫", "You gather yourself for **{target}**."),
}

SPIRIT_FLAVOR = {
    "haunt": ("Haunt", "👻", "Drain 5 Dread from the vessel.", "You coil around the vessel, feeding on its dread."),
    "echo": ("Echo", "🔔", "Chant from beyond. Every 2 echoes add 1 to the Severance.",
             "Your voice joins the circle from the other side."),
    "foresee": ("Foresee", "👁️", "Glimpse the vessel's choice this turn, once its master decides.", ""),
}

# name, emoji, rule, result narration ({actor} {target} {amount})
SIGNATURE_LORE = {
    "rampage": ("Rampage", "🪓", "Strike for 2.5× damage.",
                "{actor} goes berserk and carves **{amount}** out of the vessel!"),
    "bulwark": ("Bulwark", "🏰", "The whole raid takes half damage this turn.",
                "{actor} plants their shield, and the whole raid shelters behind it."),
    "pilfer": ("Pilfer", "🗝️", "Steal up to 40 Dread. Breaks a gathering Cataclysm.",
               "{actor} slips a hand into the vessel's shadow and steals **{amount}** Dread!"),
    "arcane_surge": ("Arcane Surge", "🔮", "1.5× damage that ignores armor and wards.",
                     "{actor} unleashes raw arcana for **{amount}**, straight through every defense!"),
    "paragons_will": ("Paragon's Will", "🌟", "Strike, mend the most wounded and chant, all at once.",
                      "{actor} does it all at once: strikes for **{amount}**, mends, and joins the chant."),
    "resurrection": ("Resurrection", "🔆", "Raise a fallen ally at 40% health.",
                     "{actor} calls {target} back from beyond the veil!"),
    "hunters_mark": ("Hunter's Mark", "🏹", "Every strike deals +30% this turn and next.",
                     "{actor} marks the vessel's weak point. Every blade knows where to land."),
    "sunder": ("Sunder", "⚓", "1.5× strike, and the vessel takes +10% damage for the rest of the fight.",
               "{actor} tears a rent in the vessel for **{amount}**. It will not close."),
    "unbroken_circle": ("Unbroken Circle", "🪬", "+2 Severance, and no blow can shatter the circle this turn.",
                        "{actor} seals the circle in blood. The Severance surges and holds!"),
    "harvest": ("Harvest", "🌒", "Strike harder for every fallen raider (up to 3×).",
                "{actor} gathers the grief of the fallen into one swing: **{amount}**!"),
    "ballad": ("Rallying Ballad", "🎻", "Heal every living raider for 15% of their health.",
               "{actor} strikes up a ballad. The raid recovers **{amount}** health in all."),
    "pack_hunt": ("Pack Hunt", "🐺", "2× strike that ignores wards.",
                  "{actor} and their pack tear in together for **{amount}**!"),
    "gift": ("Gift of Cheer", "🎁", "Fully heal one ally.",
             "{actor} hands {target} a gift, restoring **{amount}** health!"),
    "last_stand": ("Last Stand", "✊", "Strike for 2× damage.",
                   "{actor} throws everything into one blow: **{amount}**!"),
}
