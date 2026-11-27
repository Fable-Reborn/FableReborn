"""Renders a sample get-well card with made-up wishes, to see the design.

    python scripts/render_getwell_card_sample.py [count] [recipient name]

Writes assets/getwell/sample_card.png (and sample_card_2.png... when the count needs more pages).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.getwell.card import render_cards  # noqa: E402

SAMPLES = [
    ("Thornwick", "Get well soon! You make this place feel like home. Take all the time you need, we'll keep your seat warm."),
    ("MoonlitMira", "Sending you the biggest hug 🤗 Rest up, drink water and let everyone else carry the raids for a while."),
    ("Grumblefoot", "Still owe you for that revive in the Ice Dragon fight. Consider this wish partial payment. Feel better!"),
    ("Saffron of the Vale", "I joined for the game and stayed because of people like you. Thank you for every late-night laugh, every patient answer, and every time you remembered my pet's name. Be gentle with yourself and come back when you're ready."),
    ("xX_Dragonbane_Xx", "get well soon legend ⭐"),
    ("Pip", "May your crates be divine and your blankets be warm."),
    ("Elowen Ashgrove", "Wishing you soft pillows, good food and zero bug reports. You deserve all of it and more."),
    ("Brannoch", "The whole guild argued about who got to write this. Nobody won, so here's all of us: feel better soon."),
    ("tinyfrogzard", "get well soon!!! ♥ you once stayed up helping me fix my build until 3am and i never forgot it"),
    ("Captain Vex", "To the heart of this server: fair winds, calm seas and a speedy return to the helm."),
    ("Odalys", "¡Que te mejores pronto! Todo mi cariño desde aquí."),
    ("Rook", "Take your time. You're the reason I log in on bad days, so I'm sending some of that back."),
    ("Wrenna Starfall", "If kindness were XP you would have hit max level years ago. Rest well, you absolute gem."),
    ("Old Man Hemlock", "Back in my day we had no get-well events. Glad the first one is for you. Mend quickly!"),
    ("Juniper", "🌸 I hope someone brings you soup and nobody pings you before noon."),
    ("Kestrel", "You once told me that every big adventure starts with showing up. Thanks for showing up for all of us, every single day. Now it's our turn to show up for you."),
    ("Sir Reginald Fluffington III", "My pets and I wish you the speediest of recoveries. The slime insisted on signing too."),
    ("ashfall", "feel better soon!! ☀"),
    ("Liora", "To the person who makes Fable feel like a story worth being part of: this is just a slow chapter. The next one is better."),
    ("Dunmore the Unready", "I rolled a nat 1 on writing something clever, so: get well soon, you're wonderful, please come back."),
    ("Nyx", "Here's to you, and to every day getting a little brighter."),
    ("Barnaby Quill", "I raise a Phoenix Pepper Elixir in your honour (I will not be drinking it, they are expensive)."),
    ("Sorrel", "Thank you for being patient with every silly question I ever asked. There were a lot. Rest up!"),
    ("Ember", "You are sunshine with a sword. Heal up ♥"),
    ("Hollis", "Wishing you rest, loot and laughter, in whichever order you like."),
    ("The Lantern Keeper", "We'll keep a light on for you. Come back whenever you're ready."),
    ("Fenwick", "get well soon from me and the entire alliance!! we love you!!"),
    ("Isolde", "I don't say it enough: this community is gentler and funnier because you're in it. I hope this gives a little of that back to you."),
    ("Mags", "Rest, eat something good, come back and tell us everything."),
    ("Quentin Ashdown", "To many more raids and many more of your terrible puns. Get well soon, friend."),
]


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    recipient = " ".join(sys.argv[2:]) or "Sam"
    wishes = [dict(name=name, message=message) for name, message in (SAMPLES * (count // len(SAMPLES) + 1))[:count]]
    out = ROOT / "assets" / "getwell"
    out.mkdir(parents=True, exist_ok=True)
    for i, (data, filename) in enumerate(render_cards(recipient, wishes), start=1):
        path = out / ("sample_card" + ("" if i == 1 else f"_{i}") + Path(filename).suffix)
        path.write_bytes(data)
        print(path, f"{len(data) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
