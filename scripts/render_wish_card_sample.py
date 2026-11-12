"""Renders a sample birthday wish card with made-up wishes, to see the design.

    python scripts/render_wish_card_sample.py [count] [recipient name]

Writes assets/wish/sample_card.png (and sample_card_2.png... when the count needs more pages).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.wish.card import render_cards  # noqa: E402

SAMPLES = [
    ("Thornwick", "Happy birthday!! You make this place feel like home. Here's to another year of you carrying us through raids we had no business winning."),
    ("MoonlitMira", "Happiest of birthdays 🎂 I hope today is as kind to you as you are to every new player who wanders in lost."),
    ("Grumblefoot", "HBD! Still owe you for that revive in the Ice Dragon fight. Consider this wish partial payment."),
    ("Saffron of the Vale", "I joined for the game and stayed because of people like you. Thank you for every late-night laugh, every patient answer, and every time you remembered my pet's name. Have the best day."),
    ("xX_Dragonbane_Xx", "happy birthday legend ⭐"),
    ("Pip", "May your crates be divine and your cake be enormous."),
    ("Elowen Ashgrove", "Wishing you a day full of soft blankets, good food and zero bug reports. You deserve all of it and more."),
    ("Brannoch", "Another year older and still the best of us. Happy birthday from the whole guild, we argued about who got to write this."),
    ("tinyfrogzard", "happy birthday!!! ♥ you once stayed up helping me fix my build until 3am and i never forgot it"),
    ("Captain Vex", "To the heart of this server: fair winds, full sails and a birthday worth singing about."),
    ("Odalys", "Feliz cumpleaños! Que este año te traiga todo lo que sueñas."),
    ("Rook", "Happy birthday. You're the reason I log in on bad days."),
    ("Wrenna Starfall", "If kindness were XP you would have hit max level years ago. Have a wonderful birthday, you absolute gem."),
    ("Old Man Hemlock", "Back in my day we had no birthday events. Glad the first one is for you. Many happy returns!"),
    ("Juniper", "🎉 Happy birthday! I hope someone makes you breakfast and nobody pings you before noon."),
    ("Kestrel", "You once told me that every big adventure starts with showing up. Thanks for showing up for all of us, every single day. Happy birthday."),
    ("Sir Reginald Fluffington III", "My pets and I wish you the grandest of birthdays. The slime insisted on signing too."),
    ("ashfall", "hbd!! hope it's a good one ☀"),
    ("Liora", "Happy birthday to the person who makes Fable feel like a story worth being part of. May your year be full of plot twists, only the good kind."),
    ("Dunmore the Unready", "I rolled a nat 1 on writing something clever, so: happy birthday, you're wonderful, please never leave."),
    ("Nyx", "Here's to you, and to a year as bright as you make everyone else's."),
    ("Barnaby Quill", "Many happy returns of the day! I raise a Phoenix Pepper Elixir in your honour (I will not be drinking it, they are expensive)."),
    ("Sorrel", "Happy birthday! Thank you for being patient with every silly question I ever asked. There were a lot."),
    ("Ember", "You are sunshine with a sword. Happy birthday ♥"),
    ("Hollis", "Wishing you cake, rest, loot and laughter, in whichever order you like."),
    ("The Lantern Keeper", "One lantern for every good thing you've done here would light the whole sky. Happy birthday."),
    ("Fenwick", "happy birthday from me and the entire alliance!! we love you!!"),
    ("Isolde", "I don't say it enough: this community is gentler and funnier because you're in it. I hope today gives a little of that back to you."),
    ("Mags", "Happy birthday! Go touch grass, eat cake, come back and tell us everything."),
    ("Quentin Ashdown", "To many more years, many more raids and many more of your terrible puns. Happy birthday, friend."),
]


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    recipient = " ".join(sys.argv[2:]) or "Manic"
    wishes = [dict(name=name, message=message) for name, message in (SAMPLES * (count // len(SAMPLES) + 1))[:count]]
    out = ROOT / "assets" / "wish"
    out.mkdir(parents=True, exist_ok=True)
    for i, (data, filename) in enumerate(render_cards(recipient, wishes), start=1):
        path = out / ("sample_card" + ("" if i == 1 else f"_{i}") + Path(filename).suffix)
        path.write_bytes(data)
        print(path, f"{len(data) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
