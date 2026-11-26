# Prompt: GM Auction Builder (interactive panel for all 3 auction types)

You are working in the FableReborn Discord bot (discord.py 2.4.0, asyncpg/Postgres, prefix commands, several cluster processes).

**This is phase 2.** Phase 1 (`SONNET_PROMPT_silent_auction_raffle.md`, in this same folder) adds silent auctions and raffles in a new cog `cogs/gm_events/`. Read that file first. Then check that phase 1 really exists in the code: the cog, the `silent_auctions` and `raffles` tables, and the DynamicItem buttons. **If phase 1 is missing, stop and say so; don't build it half-way inside this task.**

Build a **GM-only interactive builder** where a Game Master:

1. picks one of the three auction types: **Classic Auction** (the existing `$gmauction`/`$bid`), **Silent Auction**, or **Raffle**;
2. fills in that type's details;
3. **types their own announcement message**;
4. sees a live preview of exactly what will be posted;
5. presses Post. The announcement then goes to the auction channel with the GM's message, the auction details, and an auto-written **"How to take part"** section for that type. The event then starts.

The existing text commands (`$gmauction`, `$gmsilent start`, `$gmraffle start`) must keep working. The builder is another way in, not a replacement.

---

## 0. Read these first

- `cogs/monstermanager/editor.py`: an existing GM editor in this repo. Copy its style:
  - a `discord.ui.View` that owns the state;
  - Modals with `TextInput`s;
  - `interaction_check` that locks the view to its owner (around line 781);
  - `on_timeout` that disables the panel (around line 792);
  - a confirmation sub-view (`DeleteMonsterConfirmation`).
- `cogs/game_master/__init__.py` ~3921-4070: the classic auction (`gmauction`, `run_auction`, `end_auction`, `bid`).
  - `gmauction` **awaits the whole auction task**, so the command never returns.
  - The posted text says bidding ends "12 hours" after the last bid (`timeout=43200`), but the docstring says 30 minutes. **The code is right; use 12 hours** in the how-to text.
- The phase 1 code in `cogs/gm_events/`: its start functions, duration/amount parsers and config lookups. Reuse them and don't duplicate them.
- `utils/i18n.py` (`_`, `locale_doc`) and `utils/checks.py` (`is_gm`).

## 1. One start function per type (refactor first)

The builder and the text commands must use **the same code path**, so there is only one place for bugs.

- **Classic auction.** In `cogs/game_master/__init__.py`, pull the body of `gmauction` out into
  `async def start_classic_auction(self, *, gm, channel, role, item, announcement: str | None, ping: bool) -> discord.Message`. It must:
  - do the same "auction already running" check;
  - set up the same state;
  - send the announcement (section 3);
  - start `run_auction` with `asyncio.create_task(...)` **without awaiting it**. Keep a reference on `self` and add a done-callback that logs exceptions and calls `cleanup_auction()`.

  `gmauction` then calls it and returns at once. Don't change `bid`, the refund logic or the 12h timer; that is outside this task. If you notice bugs there, list them in your summary and don't fix them.
- **Silent auction / raffle.** Make sure phase 1 exposes `start_silent_auction(*, gm, channel, role, item, min_bid, duration, announcement, ping)` and `start_raffle(*, gm, channel, role, prize, ticket_price, max_per_user, duration_or_none, announcement, ping)`, and that the text commands call them.
- **Store the announcement.** Add `announcement TEXT` to `silent_auctions` and `raffles` with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `cog_load`. Any later edit of the posted message must rebuild it from the stored row. Edits include the raffle's debounced ticket-count updates, removing buttons at close, and cancel notices. **Otherwise the GM's text disappears the first time the embed is edited.** This is the easiest bug to ship here; test it.

## 2. The builder panel

**Command:** `$gmauctionbuilder` (aliases `$gmab`, `$auctionbuilder`), `@is_gm()`, with `@locale_doc`. Check that the names and aliases don't collide with any other command: grep every cog for `name=` and `aliases=`.

Running it posts **one panel message** in the channel where the GM ran it. Tell GMs in the help text to use a staff channel. The panel is locked to that GM: `interaction_check` refuses anyone else with an ephemeral "This builder belongs to {gm}".

- Use a normal message, not an ephemeral one. Ephemeral messages can only be edited for 15 minutes through the interaction token; after that you get `Unknown Webhook` errors.
- One open builder per GM: opening a new one disables the old one.
- The View has a 15-minute timeout. `on_timeout` edits the panel to "Builder expired — run `$gmab` again" with every component disabled. Wrap that edit in try/except `discord.NotFound`/`HTTPException`.
- Drafts live only in memory (a dataclass on the View). If the bot restarts, the draft is lost; say so in the help text.

**Panel layout:**

- An embed that shows the current draft and a **preview**, plus components:
  - **Row 0: a type Select.**
    - 🔨 Classic Auction: "Open bids, highest wins, ends 12h after the last bid."
    - 🔒 Silent Auction: "Sealed bids, fixed end time."
    - 🎟️ Raffle: "Buy tickets, a random ticket wins."

    Switching type keeps the shared fields (item/prize name, announcement, ping toggle) and clears the type-only fields, with a short note saying so.
  - **Row 1 buttons:**
    - **✏️ Details** opens the modal for the chosen type.
    - **📝 Announcement** opens the announcement modal.
    - **🔔 Ping: On/Off** toggles the role ping (default On; the label shows the current state).
  - **Row 2 buttons:**
    - **👁️ Preview** posts the exact final message ephemerally to the GM. This shows them how it will look to players, embeds included.
    - **📣 Post** is disabled until the draft is valid.
    - **✖ Cancel** closes the builder.

**Details modals.** Max 5 `TextInput`s each. **Pre-fill every field with `default=` the current draft value** so that reopening the modal doesn't wipe what was typed.

| Type | Fields |
|---|---|
| Classic | Item (required, ≤200 chars) |
| Silent | Item (required, ≤200 chars); Minimum bid (required, e.g. `1000`, `1,000`, `1k`); Duration (required, e.g. `24h`, `1d12h`; 5m-14d) |
| Raffle | Prize (required, ≤200 chars); Ticket price (required); Max tickets per player (optional, blank = no cap, 1-1000); Duration (`24h` etc. **or** `manual` = ends only when a GM draws) |

**Announcement modal:**

- Title (optional, ≤100 chars; default e.g. "🔒 Silent Auction: {item}").
- Message (paragraph, optional, ≤1500 chars, placeholder text "Tell players about the item, why it's special, any extra rules…"). Blank means a short default line for the type.

**Validation.**

- Validate in `on_submit` with phase 1's parsers. Show errors **in the panel embed**, e.g. a "⚠️ Fix before posting:" list, and also in an ephemeral reply. Don't silently drop bad values; keep the GM's raw text in the draft so they can correct it.
- Each `on_submit` must answer within 3 seconds. Update the draft, then call `interaction.response.edit_message(...)` on the panel, or `defer()` and then edit the panel message by reference.

**Live status line.** Each time the panel renders, show whether a classic auction, silent auction or raffle is already live; this checks memory or the DB. If the chosen type already has a live event, disable Post and say why.

## 3. What gets posted (one renderer, pure function)

Write `build_announcement(kind, draft_or_row, *, prefix, role, ends_at, extra) -> (content: str | None, embeds: list[discord.Embed])` as a **pure function** in `cogs/gm_events/announce.py`. The text commands, the builder Preview, the builder Post, and every later re-render from a DB row all use it. Because the preview and the real post come from the same function, they can't drift apart.

**Layout:**

- `content`: the role mention, only if ping is on. Nothing else.
- **Embed 1: the announcement.**
  - Title: the GM's title.
  - Description: the GM's message.
  - Fields with the details:
    - Item/Prize.
    - Minimum bid or ticket price.
    - Max per player.
    - Ends: `<t:unix:F>` and `<t:unix:R>`, or "When a GM draws", or "12 hours after the last bid" for Classic.
    - For raffles, the fairness commitment code.
  - Footer: "Hosted by {gm display name}".
  - Colour by type.
- **Embed 2: "How to take part".** Auto-written per type and **not editable by the GM**, so the rules players see always match what the code does. Keep each under ~900 chars. Use the real `prefix` (`ctx.clean_prefix`) and real numbers:
  - **Classic:**
    - "Type `{prefix}bid <amount>` in any channel."
    - "Your bid must be higher than the current top bid, and you can't outbid yourself."
    - "Your gold is taken when you bid and refunded automatically if someone outbids you."
    - "The auction ends **12 hours after the last bid**; the highest bidder then wins."
  - **Silent:**
    - "Press **🔒 Place / Raise Bid** below and enter an amount (minimum **${min_bid:,}**)."
    - "Only you can see your bid; nobody can see who is winning."
    - "You can raise your bid any time, but you can't lower or withdraw it. Only the difference is taken."
    - "Press **View My Bid** to check it."
    - "Ends {relative time}. Highest bid wins; if two bids are equal, whoever reached that amount first wins."
    - "Everyone else is refunded automatically."
  - **Raffle:**
    - "Press **🎟️ Buy Tickets** below, or type `{prefix}raffle buy <amount>`."
    - "Each ticket costs **${price:,}** (max **{cap}** per player)."
    - "More tickets means better odds."
    - "When the raffle ends ({relative time / when a GM draws}), all tickets are shuffled and one is drawn at random."
    - "The fairness code above lets anyone check the draw afterwards."
    - "Ticket gold isn't refunded unless the raffle is cancelled."

  Check every number and rule in these texts against the actual phase 1 code. If phase 1 differs (e.g. different limits, or the pot goes to the winner), the text must follow the code. Don't invent rules.
- Silent and Raffle posts carry their phase 1 DynamicItem buttons. Classic has none.

**Safety:**

- **Sanitise mentions.** Send with `allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if ping else False)`. A GM typing `@everyone` or `<@&id>` in their message then pings nobody else.
- **Enforce limits:**
  - embed description ≤ 4096 (your cap is 1500);
  - field value ≤ 1024;
  - total of all embeds ≤ 6000;
  - title ≤ 256.

  Truncate defensively and test with maximum-length input.
- Wrap all user text in `_()` only for the fixed strings, never for GM-typed text.

## 4. Posting flow

1. The GM presses **📣 Post**. Re-validate the draft. Show an ephemeral **confirmation view**: "Post this **Silent Auction** to #channel and ping @Role? [✅ Post] [↩ Back]". This view is owner-locked and has a 60s timeout.
2. On ✅:
   - Immediately disable the panel's buttons, using a per-builder `asyncio.Lock` and a `posting` flag, so a double-click can't post twice.
   - Call the type's start function from section 1.
   - The DB unique index (phase 1) and the classic `top_auction` check are the final guard against two live events. Catch "already live" and show it nicely.
3. On success:
   - Edit the panel to "✅ Posted: [jump link]" with all components removed.
   - Log to `config.game.gm_log_channel`: who posted, the type and the details.
4. On failure (missing channel or role, permissions, already live, Discord error):
   - Re-enable the panel with the error shown.
   - Never leave a half-started event. For Silent/Raffle: if the DB row was inserted but the message failed to send, mark the row `cancelled` in the same start function, before re-raising.

Resolve the channel and role the same way the existing commands do (the config ids, plus phase 1's optional per-type keys). If the builder is opened in a server where the role or channel isn't visible, say so in the panel and disable Post.

## 5. Things that commonly go wrong (check each one)

- [ ] The GM's announcement is lost when the posted embed is re-rendered or edited later.
- [ ] The preview doesn't match the real post (fixed by the single renderer).
- [ ] Modal fields reset on reopening (`default=` missing).
- [ ] A second GM, or a player, pressing panel buttons.
- [ ] A double-posted event from a double-click.
- [ ] Expired panels throwing errors on `on_timeout`.
- [ ] Mentions leaking from GM text.
- [ ] Embed limits exceeded with long input.
- [ ] The classic `$gmauction` blocking or behaving differently after the refactor. It should post (now with a How-to embed), start, and return.
- [ ] The how-to text disagreeing with the code (the classic 12h, the silent raise-only rule, the raffle caps).
- [ ] Interaction "This interaction failed": every callback must respond or defer within 3s.

## 6. Tests (`tests/`, pytest, no live Discord or DB)

- `build_announcement` for each type:
  - the right fields;
  - the right how-to text with the real prefix and numbers;
  - ping on/off changes only `content`;
  - `@everyone` in GM text survives as text, and the allowed-mentions settings are right (test the helper that builds them);
  - max-length input stays within Discord limits;
  - a blank announcement gives the default line.
- Draft validation: missing or invalid fields per type; switching type keeps shared fields and clears type-only ones.
- Re-rendering from a stored row keeps the GM's announcement.
- The cog still boots (`tests/test_boot_cogs.py`).

Run the whole suite and report the real results. Say clearly what you couldn't verify without a live bot, especially the actual Discord rendering and the modal and button flow. Give the GM a short manual test checklist for it.

## 7. Done means

- `$gmab` opens a working builder for all three types, and posting starts the event with the GM's message plus a correct "How to take part" section.
- The old text commands still work and now post the same format.
- Tests pass. Your summary lists:
  - the commands added;
  - the refactors made, especially to `gmauction`;
  - the columns added;
  - any bugs you noticed in the classic auction but left alone.
