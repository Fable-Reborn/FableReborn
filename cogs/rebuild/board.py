"""Pictures of the Draslin rebuild: the live board and the "finished" card. Pure PIL, run in a thread.

The town is drawn from the game's own map: assets/draslin_rebuild/base.png (the ruins) with each project's
reached stage laid over it, in the order the game lays them (tools/build-rebuild-board-assets.py makes both).
"""
from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import rules

FONTS = rules.ASSETS.parent / "profile_themes" / "fonts"
TEXT, MUTED, INK, GOLD = (240, 234, 224), (152, 148, 162), (10, 10, 15), (236, 190, 92)
PANEL, LINE, GREEN, BLUE = (22, 21, 30), (52, 50, 64), (120, 200, 120), (96, 178, 255)
MATERIAL_COLOURS = {"timber": (176, 124, 72), "stone": (170, 170, 180), "iron": (120, 140, 170),
                    "glass": (130, 210, 220), "cloth": (200, 110, 140)}
FOOTER = "$gather   ·   $rebuild vote   ·   $rebuild donate   ·   $rebuild me"


@lru_cache(maxsize=None)
def _font(name: str, size: int):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default(size)


def display(size): return _font("Cinzel.ttf", size)
def bold(size): return _font("Lato-Bold.ttf", size)
def regular(size): return _font("Lato-Regular.ttf", size)
def mix(a, b, t): return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


@lru_cache(maxsize=1)
def _data():
    data = rules.load_projects()
    data["by_id"] = {p["id"]: p for p in data["projects"]}
    return data


@lru_cache(maxsize=1)
def _base():
    return Image.open(rules.ASSETS / "base.png").convert("RGBA")


@lru_cache(maxsize=64)
def _patch(pid: str, at: int):
    return Image.open(rules.ASSETS / "patches" / f"{pid}_{at:03d}.png").convert("RGBA")


def name_of(pid: str | None) -> str:
    return _data()["by_id"].get(pid, {}).get("name", pid or "")


def town_image(progress: dict[str, int]) -> Image.Image:
    """The whole town with every project at the stage its progress has reached."""
    img = _base().copy()
    for project in _data()["projects"]:
        at = max((s for s in project["stages"] if s <= progress.get(project["id"], 0)), default=0)
        if at:
            img.alpha_composite(_patch(project["id"], at), tuple(project["pixels"][:2]))
    return img


def _backdrop(w, h):
    glow = Image.new("RGB", (w, h), INK)
    g = ImageDraw.Draw(glow)
    g.ellipse((w - 700, -400, w + 300, 500), fill=mix(INK, GOLD, 0.16))
    g.ellipse((-300, h - 300, 500, h + 300), fill=mix(INK, BLUE, 0.10))
    return glow.filter(ImageFilter.GaussianBlur(160)).convert("RGBA")


def _bar(d, x, y, w, h, frac, colour, back=LINE):
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=back)
    if frac > 0:
        d.rounded_rectangle((x, y, x + max(h, round(w * min(1, frac))), y + h), radius=h // 2, fill=colour)


def _check(d, x, y, s, colour):
    d.line([(x - s * .45, y), (x - s * .1, y + s * .35), (x + s * .5, y - s * .4)], fill=colour, width=max(3, s // 5))


def _tag(d, x, y, label, fill, text_colour=INK, icon=None, size=17):
    font = bold(size)
    w = round(d.textlength(label, font=font)) + (52 if icon else 28)
    d.rounded_rectangle((x - w // 2, y - 16, x + w // 2, y + 16), radius=16, fill=fill, outline=INK, width=2)
    d.text((x + (12 if icon else 0), y), label, font=font, fill=text_colour, anchor="mm")
    if icon == "check":
        _check(d, x - w // 2 + 20, y, 16, text_colour)


def _clip(d, text, font, width):
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _wrap(d, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and d.textlength(trial, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def _png(img) -> io.BytesIO:
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def _who(row) -> str:
    return (row.get("name") or "").strip() or f"Builder {str(row['discord_id'])[-4:]}"


# ---- the live board ------------------------------------------------------------------------------------
def render_board(snap: dict) -> io.BytesIO:
    data = _data()
    W, H = 1600, 1030
    img = _backdrop(W, H)
    d = ImageDraw.Draw(img, "RGBA")
    done = sum(1 for p in snap["projects"] if p["status"] == "done")
    d.text((40, 30), "DRASLIN IS WHOLE AGAIN" if snap["finished"] else "REBUILDING DRASLIN", font=display(44), fill=TEXT)
    d.line((40, 92, 1020, 92), fill=GOLD, width=3)
    d.line((1020, 92, 1080, 74), fill=GOLD, width=3)
    opened, active = snap.get("opened", True), snap.get("active", True)
    when = f"Day {snap['day']}" if opened and snap.get("day") else "Opens soon"
    if opened and not active and not snap["finished"]:
        when += "  ·  paused"
    d.text((1560, 38), f"{when}  ·  {done} of {len(snap['projects'])} projects done", font=bold(20),
           fill=GOLD if not opened or not active else MUTED, anchor="ra")
    d.text((1560, 66), f"{snap['builders_week']} builder{'s' * (snap['builders_week'] != 1)} this week",
           font=regular(18), fill=MUTED, anchor="ra")

    progress = {p["id"]: p["progress"] for p in snap["projects"]}
    town = town_image(progress).convert("RGB")
    MX, MY, MW = 40, 118, 980
    scale = MW / town.width
    MH = round(town.height * scale)
    town = town.resize((MW, MH), Image.LANCZOS)
    def box(pid):
        x0, y0, x1, y1 = data["by_id"][pid]["pixels"]
        return tuple(round(v * scale) for v in (x0, y0, x1, y1))
    current = snap["current"]
    focus = box(current["id"]) if current and current["id"] in data["by_id"] else None
    # Light up the project being built, unless it covers most of the town (the walls, the streets).
    small = focus and (focus[2] - focus[0]) * (focus[3] - focus[1]) < 0.3 * MW * MH
    if small:
        dim = ImageEnhance.Brightness(ImageEnhance.Color(town).enhance(0.6)).enhance(0.55)
        dim.paste(town.crop(focus), focus[:2])
        town = dim
    img.paste(town, (MX, MY))
    d.rounded_rectangle((MX - 3, MY - 3, MX + MW + 3, MY + MH + 3), radius=6, outline=LINE, width=3)
    tag = None  # the "now building" tag goes on top of everything else; markers keep out of its way
    if focus:
        fx0, fy0, fx1, fy1 = focus[0] + MX, focus[1] + MY, focus[2] + MX, focus[3] + MY
        if small:
            for i in range(3):
                d.rectangle((fx0 - i * 3, fy0 - i * 3, fx1 + i * 3, fy1 + i * 3), outline=GOLD + (220 - i * 70,), width=2)
            tag = ((fx0 + fx1) // 2, max(MY + 20, fy0 - 26),
                   f"NOW BUILDING  {current['progress']}%" if opened else "FIRST UP")
        else:
            tag = (MX + MW // 2, MY + 28, f"NOW BUILDING: {name_of(current['id']).upper()}  {current['progress']}%")
    tag_box = None
    if tag:
        half = (d.textlength(tag[2], font=bold(17)) + 28) / 2
        tag_box = (tag[0] - half - 22, tag[1] - 38, tag[0] + half + 22, tag[1] + 38)
    for p in snap["projects"]:
        if p["status"] == "done" and p["id"] in data["by_id"]:
            b = box(p["id"])
            if (b[2] - b[0]) * (b[3] - b[1]) < 0.3 * MW * MH:
                _tag(d, MX + (b[0] + b[2]) // 2, MY + (b[1] + b[3]) // 2, name_of(p["id"]), GREEN, icon="check", size=15)
    for n, entry in enumerate(snap["ballot"], 1):
        if entry["id"] not in data["by_id"]:
            continue
        b = box(entry["id"])
        cx, cy = MX + (b[0] + b[2]) // 2, MY + (b[1] + b[3]) // 2
        if tag_box and tag_box[0] < cx < tag_box[2] and tag_box[1] < cy < tag_box[3]:
            cy = tag_box[3] + 6
        d.ellipse((cx - 20, cy - 20, cx + 20, cy + 20), fill=(30, 30, 44, 235), outline=TEXT, width=2)
        d.text((cx, cy), str(n), font=bold(22), fill=TEXT, anchor="mm")
    if tag:
        _tag(d, tag[0], tag[1], tag[2], GOLD)

    PX, PW = 1060, 500
    d.rounded_rectangle((PX - 16, 112, PX + PW + 4, MY + MH + 3), radius=14, fill=PANEL + (235,), outline=LINE, width=2)
    y = 132
    if current:
        project = data["by_id"].get(current["id"], {"name": current["id"], "called": current["id"], "steps": {}, "lines": {}})
        stage = rules.stage_of(current["progress"])
        d.text((PX, y), "NOW BUILDING" if opened else "FIRST UP, WHEN THE REBUILD OPENS", font=bold(18), fill=GOLD)
        size = next((n for n in range(46, 21, -2) if d.textlength(project["name"], font=display(n)) <= PW - 120), 22)
        d.text((PX, y + 24 + (46 - size) // 2), _clip(d, project["name"], display(size), PW - 120), font=display(size),
               fill=TEXT)
        d.text((PX + PW - 12, y + 40), f"{current['progress']}%", font=display(40), fill=GOLD, anchor="ra")
        y += 92
        _bar(d, PX, y, PW - 12, 18, current["progress"] / 100, GOLD)
        for i, label in enumerate(("Rubble", "Foundations", "Walls", "Finished")):
            sx = PX + round((PW - 12) * (i + 1) / 4)
            d.line((sx - 1, y - 4, sx - 1, y + 22), fill=PANEL, width=3)
            d.text((PX + round((PW - 12) * (i + .5) / 4), y + 30), label, font=bold(15),
                   fill=TEXT if (i + 1) * 25 <= current["progress"] else MUTED, anchor="ma")
        y += 62
        step = project.get("steps", {}).get(str(stage)) or rules.STEPS.get(stage, "")
        d.text((PX, y), _clip(d, f"Next: {step} ({min(100, stage + 25)}%)", regular(17), PW - 12), font=regular(17), fill=MUTED)
        y += 46
        d.line((PX, y, PX + PW - 12, y), fill=LINE, width=2)
        y += 16
        d.text((PX, y), "MATERIALS DELIVERED", font=bold(18), fill=GOLD)
        y += 34
        for need in snap["needs"][:5]:
            c = MATERIAL_COLOURS.get(need["material"], MUTED)
            d.rounded_rectangle((PX, y + 2, PX + 20, y + 22), radius=5, fill=c)
            d.text((PX + 32, y + 12), rules.MATERIAL_NAMES.get(need["material"], need["material"]), font=bold(19),
                   fill=TEXT, anchor="lm")
            full = need["delivered"] >= need["needed"]
            d.text((PX + PW - 12, y + 12), f"{need['delivered']:,} / {need['needed']:,}", font=regular(18),
                   fill=TEXT if full else MUTED, anchor="rm")
            _bar(d, PX + 130, y + 6, PW - 260, 12, need["delivered"] / need["needed"], c)
            y += 38
    else:
        d.text((PX, y), "EVERY PROJECT IS FINISHED", font=bold(18), fill=GOLD)
        for line in _wrap(d, "The streets are paved, the doors are open and the people are home. "
                             "Thank you, builders.", regular(20), PW - 12):
            y += 30
            d.text((PX, y), line, font=regular(20), fill=TEXT)
        y += 50

    if snap["ballot"]:
        y += 10
        d.line((PX, y, PX + PW - 12, y), fill=LINE, width=2)
        y += 16
        d.text((PX, y), "WHAT'S NEXT?  VOTE", font=bold(18), fill=GOLD)
        if current:
            note = ("closes when this build is done" if active else
                    "opens with the rebuild" if not opened else "paused")
            d.text((PX + PW - 12, y + 2), note, font=regular(15), fill=MUTED if active else GOLD, anchor="ra")
        y += 34
        total = sum(e["votes"] for e in snap["ballot"]) or 1
        lead = max(e["votes"] for e in snap["ballot"])
        for n, entry in enumerate(snap["ballot"], 1):
            d.ellipse((PX, y, PX + 26, y + 26), fill=(30, 30, 44), outline=TEXT, width=2)
            d.text((PX + 13, y + 13), str(n), font=bold(15), fill=TEXT, anchor="mm")
            d.text((PX + 40, y + 13), _clip(d, name_of(entry["id"]), bold(19), 180), font=bold(19), fill=TEXT, anchor="lm")
            leading = entry["votes"] == lead and lead > 0
            _bar(d, PX + 230, y + 7, PW - 330, 12, entry["votes"] / total, BLUE if leading else mix(BLUE, LINE, .45))
            d.text((PX + PW - 12, y + 13), str(entry["votes"]), font=bold(18), fill=TEXT, anchor="rm")
            perk = rules.PERKS.get(entry["id"])
            if perk:   # what voting for it gets everyone
                d.text((PX + 40, y + 30), _clip(d, f"Perk: {perk.short}", regular(15), PW - 60), font=regular(15),
                       fill=mix(GOLD, MUTED, .35))
                y += 18
            y += 38

    y += 10
    d.line((PX, y, PX + PW - 12, y), fill=LINE, width=2)
    y += 16
    d.text((PX, y), "TOP BUILDERS THIS WEEK", font=bold(18), fill=GOLD)
    y += 34
    if not snap["top"]:
        d.text((PX, y), "Nobody yet. Be the first: $gather", font=regular(18), fill=MUTED)
    medal = (GOLD, (200, 200, 210), (205, 140, 90))
    for rank, row in enumerate(snap["top"], 1):
        if y > MY + MH - 30:
            break
        d.text((PX, y), str(rank), font=display(22), fill=medal[rank - 1] if rank <= 3 else MUTED)
        d.text((PX + 36, y + 2), _clip(d, _who(row), bold(19), 180), font=bold(19), fill=TEXT)
        where = " + ".join(s.capitalize() if s != "tiamat" else "Tiamat" for s in sorted(row["sources"]))
        d.text((PX + 230, y + 4), where, font=regular(15), fill=MUTED)
        d.text((PX + PW - 12, y + 2), f"{row['amount']:,}", font=bold(19), fill=TEXT, anchor="ra")
        y += 32

    d.text((40, 996), FOOTER, font=bold(18), fill=MUTED, anchor="lm")
    d.text((1560, 996), "Restored Draslin, The Tiamat Sacrament", font=regular(15), fill=mix(MUTED, INK, .3), anchor="rm")
    return _png(img)


# ---- a project is finished --------------------------------------------------------------------------------
def render_finished(pid: str, progress_after: dict[str, int], stats: dict) -> io.BytesIO:
    data = _data()
    project = data["by_id"][pid]
    W, H = 1600, 900
    img = _backdrop(W, H)
    d = ImageDraw.Draw(img, "RGBA")
    tile = data["tile"]
    x0, y0, x1, y1 = project["pixels"]
    pad = tile * 2
    crop = (max(0, x0 - pad), max(0, y0 - pad), min(data["size"][0], x1 + pad), min(data["size"][1], y1 + pad))
    before_progress = dict(progress_after, **{pid: 0})
    after = town_image(progress_after).crop(crop)
    before = ImageEnhance.Color(town_image(before_progress).crop(crop).convert("RGB")).enhance(0.7)
    BW, BH = 440, 560
    factor = min(BW / after.width, BH / after.height)
    # Whole-number enlargements keep the pixel art sharp; shrinking (the big projects) is smoothed.
    resample = Image.NEAREST if factor >= 1 else Image.LANCZOS
    factor = max(1, int(factor)) if factor >= 1 else factor
    size = (round(after.width * factor), round(after.height * factor))
    for x, pic, label in ((60, before, "BEFORE"), (560, after.convert("RGB"), "AFTER")):
        pic = pic.resize(size, resample)
        px, py = x + (BW - size[0]) // 2, 150 + (BH - size[1]) // 2
        img.paste(pic, (px, py))
        d.rounded_rectangle((px - 3, py - 3, px + size[0] + 3, py + size[1] + 3), radius=6,
                            outline=GOLD if label == "AFTER" else LINE, width=3)
        _tag(d, x + BW // 2, py + size[1] + 30, label, GOLD if label == "AFTER" else LINE, INK if label == "AFTER" else TEXT)
    d.polygon([(530 - 14, 410), (530 + 14, 431), (530 - 14, 452)], fill=GOLD)
    title = f"{project['name'].upper()} {'ARE' if project['name'].endswith('s') else 'IS'} FINISHED"
    size = next((n for n in range(48, 29, -2) if d.textlength(title, font=display(n)) <= 1000), 30)
    d.text((60, 46 + (48 - size) // 2), _clip(d, title, display(size), 1000), font=display(size), fill=TEXT)
    d.line((60, 112, 1000, 112), fill=GOLD, width=3)
    d.line((1000, 112, 1060, 94), fill=GOLD, width=3)

    RX, RW = 1060, 480
    y = 160
    d.text((RX, y), "ROLAN", font=bold(18), fill=GOLD)
    y += 30
    for line in _wrap(d, f"“{project['finish']}”", regular(24), RW)[:4]:
        d.text((RX, y), line, font=regular(24), fill=TEXT)
        y += 34
    if project.get("resident"):
        y += 22
        d.text((RX, y), f"{project['resident']['name'].upper()}, HOME AGAIN", font=bold(18), fill=GOLD)
        y += 30
        for line in _wrap(d, f"“{project['resident']['line']}”", regular(21), RW)[:3]:
            d.text((RX, y), line, font=regular(21), fill=MUTED)
            y += 30
    y += 26
    d.line((RX, y, RX + RW, y), fill=LINE, width=2)
    y += 20
    took = stats.get("took")
    days = f"{max(1, round(took.total_seconds() / 86400))} day{'s' * (round(took.total_seconds() / 86400) > 1)}" if took else "-"
    for big, small in ((f"{stats['builders']:,}", "builders"), (f"{stats['materials']:,}", "materials"), (days, "to build")):
        d.text((RX, y), big, font=display(32), fill=TEXT)
        d.text((RX + 170, y + 12), small, font=bold(18), fill=MUTED)
        y += 46
    if stats["helpers"]:
        y += 10
        d.text((RX, y), "MOST HELP", font=bold(18), fill=GOLD)
        y += 28
        d.text((RX, y), _clip(d, "  ·  ".join(_who(h) for h in stats["helpers"]), bold(20), RW), font=bold(20), fill=TEXT)
        y += 44
    if stats.get("next_id"):
        d.rounded_rectangle((RX - 4, y, RX + RW, y + 74), radius=12, fill=PANEL, outline=BLUE, width=2)
        d.text((RX + 16, y + 12), _clip(d, f"NEXT UP: {name_of(stats['next_id']).upper()}", bold(18), RW - 30),
               font=bold(18), fill=BLUE)
        votes = stats.get("votes") or []
        d.text((RX + 16, y + 42), f"won the vote {' – '.join(map(str, votes))}" if votes else "next in line",
               font=regular(18), fill=MUTED)
    perk = rules.PERKS.get(pid)
    if perk:
        d.rounded_rectangle((56, 772, 1004, 836), radius=12, fill=PANEL, outline=GOLD, width=2)
        d.text((76, 784), _clip(d, f"NEW PERK FOR EVERY BUILDER: {perk.name.upper()}", bold(18), 900), font=bold(18),
               fill=GOLD)
        d.text((76, 810), _clip(d, perk.text, regular(17), 910), font=regular(17), fill=TEXT)
    d.text((60, 870), "Walk in: Restored Draslin, The Tiamat Sacrament", font=bold(18), fill=MUTED, anchor="lm")
    return _png(img)
