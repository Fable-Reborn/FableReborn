# Possession art: brief and wiring guide

This is the single brief for the GM Possession event's artwork. It covers what
to generate, where to save each file, how the bot already uses the files, and
how to check the result.

**If you are an AI working on this:**
- **Steps 1 and 2** are the job. Generate the 12 images and save them under
  the exact names below.
- **Step 3** explains the wiring, which is already done in code. Don't
  rewrite it unless something in Step 4 fails.
- **Step 4** is how to check the result.

---

## Step 1: Generate the images

There are 12 images in total:
- **The three vessels** each get three faces: `sinister`, `anger` and `laugh`.
- **Each vessel's underling** (the minion who talks to the GM) gets one portrait.

### Output rules (apply to every image)

- Square, **1024 × 1024**, saved as PNG. WEBP or JPG also work.
- Bust or head-and-shoulders shot, **face in the upper-middle** of the frame.
  The bot crops to a square and scales down to 236 px on the turn card and
  256 px for chat portraits. Anything at the very edges or bottom may be lost.
- Dark, simple background. The images sit on a dark Discord embed and a dark card.
- **No text, lettering, watermark, frame or border** in the image.
- The subject must read clearly at thumbnail size (about 80 px in Discord).

### Keeping each vessel consistent across its three faces

1. Generate the **sinister** face first.
2. Generate **anger** and **laugh** from the sinister image: use it as the
   reference or image prompt, or run a variation with the same seed. Change
   only the expression and effects.
3. Keep the same framing, camera angle, lighting direction, palette and costume
   in all three faces.

### Style block (append to every prompt)

```text
dark fantasy character portrait, bust shot, square 1:1, face in upper-middle of frame, painterly digital illustration, dramatic rim lighting, dark smoky background, high detail, no text, no watermark, no border
```

### Vessel 1: Sepulchure's Doomknight's Husk (folder `sepulchure`)

Palette: black and deep crimson.

**sinister**
```text
An empty suit of black Doomknight plate armor with a horned great-helm, visor slits glowing faint blood-red with nothing inside, tattered black cape, thin cracks in the armor leaking red light, black and deep crimson palette. The helm is tilted slightly, the red slits narrowed, a black blade held close to the face.
```

**anger**
```text
Same character and framing as the reference: the empty black Doomknight armor with the horned great-helm. The visor is blazing bright red, the cracks in the armor flare with red light, black smoke pours from the joints, and it lunges toward the viewer.
```

**laugh**
```text
Same character and framing as the reference: the empty black Doomknight armor with the horned great-helm. The helm is thrown back mockingly, red light pulses through every crack like laughter, and shadows swirl around it.
```

### Vessel 2: Drakath's Laughing Colossus (folder `drakath`)

Palette: violet and magenta.

**sinister**
```text
A titan stitched together from mismatched shards of marble, bone, a bronze church bell and an old wooden door, its face a spinning mask of glowing purple chaos crystal, violet and magenta palette, floating dice and stone fragments. The crystal mask forms a thin crooked grin, one eye glinting.
```

**anger**
```text
Same character and framing as the reference: the stitched-together shard titan with the purple chaos-crystal mask. The mask has fractured into jagged red-violet shards, pieces fly outward, and cracks of light split its face.
```

**laugh**
```text
Same character and framing as the reference: the stitched-together shard titan with the purple chaos-crystal mask. The mask has split into a huge manic grin, and crystal fragments and dice orbit wildly around its head.
```

### Vessel 3: Elysia's Hollow Seraph (folder `elysia`)

Palette: ivory and pale gold.

**sinister**
```text
A six-winged seraph crowned in cold light, ivory and pale gold palette, serene porcelain face with two hollow eye sockets where pinpoint lights of something foreign stare out, feathers edged in ash. A calm faint smile, hands folded in prayer, hollow eyes locked on the viewer.
```

**anger**
```text
Same character and framing as the reference: the six-winged ivory seraph with hollow eye sockets. The wings are flared wide, the halo is cracked, the mouth is open in a silent scream, harsh white light blazes, and ash feathers scatter.
```

**laugh**
```text
Same character and framing as the reference: the six-winged ivory seraph with hollow eye sockets. The head is tilted, with an eerie wide serene smile, and tears of light stream from the hollow eyes.
```

### The underlings (one image each)

**Grimvale, Keeper of the Black Ledger** (`sepulchure/underling.png`)
```text
A thin, stooped, ink-stained goblin-like clerk with long fingers, cracked spectacles and an obsequious grin, clutching a quill over a huge black ledger, candlelight, dusty scriptorium.
```

**Pip, the Unraveled Imp** (`drakath/underling.png`)
```text
A small mischievous purple imp with three mismatched eyes and four hands, wide toothy grin, bursting out of an inkwell, sparkles of chaotic purple magic, playful and unhinged.
```

**Sister Maren, the Unanswered** (`elysia/underling.png`)
```text
A gaunt acolyte in a torn white habit, hollow cheeks, eyes shining with fervent devotion, hands clasped around prayer beads, flickering candles, cold cathedral light.
```

---

## Step 2: Save the files

Save into this folder (`assets/possession/`) using exactly these names. The
folder names are the vessel keys used by `$possess`.

```
assets/possession/
  sepulchure/   sinister.png   anger.png   laugh.png   underling.png
  drakath/      sinister.png   anger.png   laugh.png   underling.png
  elysia/       sinister.png   anger.png   laugh.png   underling.png
```

- **Names:** lowercase, exactly as shown. `.webp`, `.jpg` or `.jpeg` may
  replace `.png`; the bot tries `.png` → `.webp` → `.jpg` → `.jpeg`, so keep
  only one file per name to avoid confusion.
- **Size:** keep each file under about 2 MB. They are resized when used, so
  bigger files only slow the first load.
- **Partial sets are fine.** Every file is optional, and the bot works while
  art is still missing (see the fallbacks in Step 3).

---

## Step 3: How the images are wired (already done)

No code changes are needed to use the images. The bot looks up files by the
paths above, so dropping them in is enough once the bot restarts or the cog
reloads.

### Where each image appears

| File | Where it appears | Code |
|---|---|---|
| `<vessel>/sinister.png` | Vessel box on the turn card (default face); chat portrait when the GM's message has no tag or `<sinister>` | `card.portrait_path`, `PossessionSession.vessel_mood`, `speech_embed` |
| `<vessel>/anger.png` | Turn card in Phase III; chat portrait for `<anger>` | same |
| `<vessel>/laugh.png` | Turn card while a Cataclysm is gathering; chat portrait for `<laugh>` | same |
| `<vessel>/underling.png` | Thumbnail on the GM's welcome DM; small icon on each turn's GM prompt; icon on the channel message when the underling picks a move for a silent GM | `card.underling_path`, `underling_embed` |
| `assets/classes/ClassesNew/<Class>.webp` (existing) | Raider avatars on the turn card, cropped to the head | `card.class_art_path`, `_head` |

### The speaking flow

1. **The GM types in their DM with the bot**, optionally starting with a tag:
   `<anger> You dare?`, `<laugh> Tee-hee.`, `<sinister> Soon.`
2. **`speech_emotion()` reads the tag** in `cogs/possession/__init__.py`.
   - Tags aren't case-sensitive.
   - Aliases: `<angry>` and `<rage>` give anger, `<smirk>` and `<calm>` give
     sinister, `<laughing>` and `<lol>` give laugh.
   - An unknown tag is left in the text, and the face defaults to sinister.
3. **`speech_embed()` posts the line** in the event channel as an embed with
   the vessel's name, the text and the matching portrait as a thumbnail. The
   file is attached as `speaker.png`.

### Fallbacks when art is missing

- **A missing `anger` or `laugh`** uses `sinister` instead.
- **A missing `sinister`:**
  - the turn card draws a coloured box with the vessel's initial;
  - chat messages post without a portrait.
- **A missing `underling`:** the embeds post without it.
- **A card render failure:** the turn falls back to the plain embed version,
  and the error goes to the bot log.

### Caching

Portraits are cached in memory after the first use (`card._square`,
`card._head` and `card.portrait_png`). After adding or replacing art, restart
the bot or reload the cog.

### Adding another emotion later

1. Save the image as `<vessel>/<emotion>.png`.
2. Add the tag to `EMOTION_ALIASES` in `cogs/possession/__init__.py`, for
   example `"sad": "sad"`.
3. Mention the new tag in the greeting field in the `possess` command so GMs
   know about it.

---

## Step 4: Check the result

Run this from the repo root. It lists which art is found, then renders a test
card for each vessel to `possession_test_<vessel>.jpg`.

```python
import sys, random
sys.path.insert(0, ".")
from cogs.possession import card

for vessel in ("sepulchure", "drakath", "elysia"):
    for emotion in ("sinister", "anger", "laugh"):
        path = card.portrait_path(vessel, emotion)
        print(f"{vessel:<11} {emotion:<9} {path.name if path else 'MISSING (placeholder)'}")
    under = card.underling_path(vessel)
    print(f"{vessel:<11} underling {under.name if under else 'MISSING (no portrait)'}")
    data = {
        "accent": (90, 20, 30), "turn": 3, "max_turns": 15, "rite": 4, "rite_goal": 16,
        "dread": 60, "dread_max": 100, "bonus": 0.1, "warning": None,
        "vessel": {"name": vessel.title(), "hp": 14000, "max_hp": 21000, "phase": "II",
                   "portrait": card.portrait_path(vessel)},
        "raiders": [
            {"name": name, "hp": random.randint(1000, 5000), "max_hp": 5000, "alive": True,
             "portrait": card.class_art_path(cls), "signature": "Rampage", "signature_ready": True}
            for name, cls in (("Lunar", "Warrior"), ("Mara", "Paladin"), ("Ossian", "Ritualist"))
        ],
    }
    open(f"possession_test_{vessel}.jpg", "wb").write(card.render_turn_card(data).getvalue())
```

Delete the `possession_test_*.jpg` files afterwards.

### Checklist

- [x] All 12 files exist with the exact names, and the script prints no `MISSING`.
- [x] On each test card, the vessel's face is centred and not cut off at the
      top. If it is, add headroom to the image and regenerate or re-crop.
- [x] The three faces of each vessel look like the same character.
- [x] No image contains text, a watermark or a border.
- [ ] Live check: after restarting the bot, start `$possess` in a test channel,
      join with test accounts, and from the GM's DM send `<anger> test`,
      `<laugh> test` and `test`. Each should post with the matching portrait.

Local verification completed on 2026-10-01: all 12 PNGs are 1024 × 1024 and
under 2 MiB (approximately 2 MB). All nine vessel/emotion combinations render;
speech thumbnails, both underling attachment layouts, and phase mood selection
pass local checks. The three sample cards were visually inspected and removed.
Live Discord verification remains pending. Prompts used with the built-in
image generator are recorded in `generation-prompts.json`.
