# Prompt: Build Silent Auctions and Raffles for FableReborn

You are working in the FableReborn Discord bot (discord.py 2.4.0, asyncpg/Postgres, Redis, prefix commands). It runs as **several cluster processes** (see `launcher.py`, `shards_per_cluster`). Every cluster loads every cog, but a guild's channels and interactions exist on only one cluster.

Add **two new GM-run systems** next to the existing auction: a **silent (blind) auction** and a **raffle**. Leave the existing `$gmauction` / `$bid` alone. They must keep working exactly as they do now.

Correctness matters more than speed. Real gold moves through these systems, so there must be no way to duplicate, lose or overdraw money, double-draw, or leak a hidden bid. Read all of this before writing code.

---

## 0. Read these first

- `cogs/game_master/__init__.py`
  - `__init__` around lines 222-252: config ids `auction_channel_id` and `auction_ping_role_id` come from `bot.config.ids.game_master`.
  - The existing auction, lines ~3884-4070 (`gmauction`, `run_auction`, `end_auction`, `bid`). This is **the anti-pattern to avoid**:
    - all state is in memory, so a restart loses the auction and any escrowed gold;
    - the balance check comes from stale `ctx.character_data`, and the update has no row lock or transaction;
    - `end_auction` is defined twice;
    - the command awaits a 12-hour task.
  - `cog_load` around line 7288: the `CREATE TABLE IF NOT EXISTS` pattern used in this repo.
- `cogs/raid/__init__.py` ~1754-1800: a bid flow that uses `conn.transaction()`.
- `cogs/guild/__init__.py` ~62-120 and ~320-340: a persistent button `View` (`timeout=None`, stable `custom_id`), ephemeral replies, and re-attaching views after a restart with `bot.add_view(view, message_id=...)`.
- `classes/bot.py:1671` `log_transaction`. It asserts `subject` is in a fixed list and reads `ctx.command.qualified_name`. **Button and modal interactions have no `ctx`.** Read the whole function. Then either add an interaction-safe path (e.g. an optional `command_name` and `ctx=None` handling), or write a thin adapter. Add `"raffle"` to the subject list if you log raffle purchases under it. Also check whether anything else, such as a DB enum or a reader of these logs, depends on that list.
- `utils/checks.py` `is_gm`, `has_char`.
- `utils/random.py`: secrets-backed `shuffle`, `randint`, `choice`.
- `utils/birthday.py` `parse_birthday_duration`: parses `24h`, `1d12h`, `90m`. Reuse it or move it to a shared util; don't write a third parser.
- `utils/boot_cogs.py` and `config.toml` `initial_extensions`: how a new cog gets loaded.
- `tests/`: pytest style; `tests/test_boot_cogs.py` checks that cogs load.

## 1. Where the code goes

`cogs/game_master/__init__.py` is already 7000+ lines. Create a **new cog package**, `cogs/gm_events/`, laid out like this:

- `__init__.py`: the Cog, its commands and its loops.
- `models.py` or `logic.py`: pure functions with no Discord or DB code. These are winner selection, tie-breaking, the raffle shuffle and draw, and seed and commitment hashing, so they can be unit-tested.
- `views.py`: DynamicItem buttons and modals.

Register the cog so it boots. Add it to `EXTRA_COGS` in `utils/boot_cogs.py`, or to `config.toml`, whichever matches how similar cogs are added. Read the comments there.

- Wrap every user-facing string in `_()` from `utils.i18n`. Use `@locale_doc` on commands, as the existing auction does.
- Reuse `auction_channel_id` and `auction_ping_role_id` by default. Also accept optional new keys `silent_auction_channel_id`, `raffle_channel_id` and `raffle_ping_role_id` in `ids.game_master`, falling back to the auction ones. Fail with a clear message if neither is set.

## 2. Database (create in `cog_load`, idempotent)

```sql
CREATE TABLE IF NOT EXISTS silent_auctions (
    id            BIGSERIAL PRIMARY KEY,
    item          TEXT NOT NULL,
    min_bid       BIGINT NOT NULL CHECK (min_bid >= 1),
    created_by    BIGINT NOT NULL,
    channel_id    BIGINT NOT NULL,
    message_id    BIGINT,
    status        TEXT NOT NULL DEFAULT 'open',   -- open | closing | closed | cancelled
    starts_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ends_at       TIMESTAMPTZ NOT NULL,
    winner_id     BIGINT,
    winning_bid   BIGINT,
    closed_at     TIMESTAMPTZ
);
-- only one live silent auction at a time
CREATE UNIQUE INDEX IF NOT EXISTS silent_auctions_one_live
    ON silent_auctions ((true)) WHERE status IN ('open', 'closing');

CREATE TABLE IF NOT EXISTS silent_auction_bids (
    auction_id    BIGINT NOT NULL REFERENCES silent_auctions(id),
    user_id       BIGINT NOT NULL,
    amount        BIGINT NOT NULL CHECK (amount > 0),
    amount_set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- when the current amount was reached (tie-break)
    refunded      BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (auction_id, user_id)
);

CREATE TABLE IF NOT EXISTS raffles (
    id              BIGSERIAL PRIMARY KEY,
    prize           TEXT NOT NULL,
    ticket_price    BIGINT NOT NULL CHECK (ticket_price >= 1),
    max_per_user    INTEGER,                 -- NULL = no cap
    created_by      BIGINT NOT NULL,
    channel_id      BIGINT NOT NULL,
    message_id      BIGINT,
    status          TEXT NOT NULL DEFAULT 'open',  -- open | drawing | drawn | cancelled
    ends_at         TIMESTAMPTZ,                   -- NULL = ends only by GM command
    seed_secret     TEXT NOT NULL,                 -- hex, revealed only after the draw
    seed_commitment TEXT NOT NULL,                 -- sha256(seed_secret), published at start
    ticket_digest   TEXT,
    winning_ticket  INTEGER,
    winner_id       BIGINT,
    drawn_at        TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS raffles_one_live
    ON raffles ((true)) WHERE status IN ('open', 'drawing');

CREATE TABLE IF NOT EXISTS raffle_purchases (
    id          BIGSERIAL PRIMARY KEY,
    raffle_id   BIGINT NOT NULL REFERENCES raffles(id),
    user_id     BIGINT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    paid        BIGINT NOT NULL,
    refunded    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS raffle_purchases_by_raffle ON raffle_purchases (raffle_id, id);
```

The DB is the **only source of truth**. Don't keep auction or raffle state in memory beyond caches you can throw away.

## 3. Money rules (both systems)

- Every gold movement happens in one `async with conn.transaction():` block. Debit with a guarded update and check that it changed a row:
  `UPDATE profile SET money = money - $1 WHERE "user" = $2 AND money >= $1` must return `UPDATE 1`. Otherwise reply "not enough gold" and roll back. Never check a balance in Python and then subtract.
- Inside the same transaction, lock the parent row first (`SELECT ... FROM silent_auctions WHERE id=$1 FOR UPDATE`) and re-check `status = 'open' AND ends_at > NOW()`. A bid or purchase that races the closer then either commits before the close or is rejected. It never lands after the close.
- Lock order is always **parent auction/raffle row → bid/purchase row → profile row**, to avoid deadlocks.
- Refunds use a `refunded` flag on each row, set in the same transaction as the credit, so a crash mid-refund resumes without paying anyone twice.
- Log every debit and credit with `log_transaction` (see section 0), inside the transaction (`conn=conn`).
- The player must have a character (a `profile` row). Check this in the handler; the `has_char` decorator doesn't apply to buttons.

## 4. Silent auction

**GM commands** (`@is_gm()`), as a group, e.g. `$gmsilent`:

- `$gmsilent start <duration> <min_bid> <item...>`
  - Validate the duration: at least 5m, at most 14d. Validate `min_bid >= 1`.
  - Insert the row. If the unique index fails (`UniqueViolationError`), say an auction is already live.
  - Post an embed in the auction channel: item, minimum bid, end time as `<t:unix:F>` and `<t:unix:R>`, and the rules ("bids are sealed; only you see your bid; you may raise but not lower or withdraw; the highest bid wins, ties go to whoever reached that amount first; your bid is held from your balance and refunded if you lose").
  - Ping the role with `allowed_mentions=discord.AllowedMentions(roles=True)`, then save `message_id`.
  - Return immediately. Never await the auction's lifetime inside the command.
- `$gmsilent end`: close now and announce.
- `$gmsilent cancel [reason]`: refund every bid and announce that the auction was cancelled.
- `$gmsilent status`: tell the GM the time left and the **number of bidders only**. No amounts or names, because GMs may also bid. This is a deliberate rule.

**Player flow** (buttons on the auction message, implemented as `discord.ui.DynamicItem` with custom_ids like `sa:bid:<auction_id>` and `sa:mine:<auction_id>`, registered once with `bot.add_dynamic_items(...)` in `cog_load` so they survive restarts):

- **Place / Raise Bid** opens a modal with one amount field. Send the modal as the immediate interaction response, with no DB work before `send_modal`.
  - In `on_submit`, call `interaction.response.defer(ephemeral=True, thinking=True)` first, then do the DB work, then reply with `interaction.followup.send(..., ephemeral=True)`.
  - Parse the amount strictly. Accept `1000`, `1,000`, `1k`/`1.5m` if you add that. Reject negatives, zero, non-numbers and anything above a sane cap such as 10^15.
  - Rules:
    - The first bid must be `>= min_bid`.
    - A raise must be `> current own bid`.
    - Debit only the **difference** (new − old).
    - Update `amount` and set `amount_set_at = NOW()`.
  - Ephemeral confirmation: "🔒 Your sealed bid on **{item}** is now **${amount:,}**. Only you can see this." Nothing about other bids, rank, or whether they are leading.
- **View My Bid** sends an ephemeral reply with the player's current bid, or "you haven't bid".
- **No public message ever reveals a bid, a bidder, or a bid count while the auction is open.** Don't edit the embed on bids; editing it only on a bid would leak activity timing.
- Don't add a text `$bid` variant for silent auctions. A message in a channel is public, and that defeats the point.

**Closing** (one function, `finalize_silent_auction(auction_id)`, safe to call many times and from any cluster):

1. Claim the auction atomically:
   `UPDATE silent_auctions SET status='closing' WHERE id=$1 AND status='open' RETURNING *`.
   If no row comes back, also allow resuming a row already in `'closing'`, which means a crash mid-close. Use a Redis lock (`SET key NX EX 120`) or `pg_try_advisory_lock(id)` so two clusters don't resume at the same time.
2. Pick the winner from the DB: `ORDER BY amount DESC, amount_set_at ASC, user_id ASC LIMIT 1`. Put this ordering in a pure function too and unit-test it.
3. In one transaction:
   - refund every non-winner bid where `refunded = FALSE`, setting `refunded = TRUE`;
   - keep the winner's gold, which is the payment;
   - set `status='closed'`, `winner_id`, `winning_bid` and `closed_at`.
4. After commit, announce in the channel: "🔨 Silent auction for **{item}** has closed. Winner: {mention} with **${amount:,}**. All other bids have been refunded." If nobody bid, say so.
   - Remove the buttons with a message edit to `view=None`, or have the DynamicItem reject non-open auctions.
   - Optionally DM each loser "your bid of $X was refunded". Ignore `Forbidden`.
   - The prize is given manually by a GM, as with the existing auction. Say so in the announcement and log it to `config.game.gm_log_channel`.

**Timers / clusters:**

- Run a `discord.ext.tasks.loop(seconds=30)` in the cog. Each tick, select `silent_auctions WHERE status IN ('open','closing') AND ends_at <= NOW()` and call `finalize_silent_auction`.
- **Only act if `self.bot.get_channel(row.channel_id)` is not None on this cluster.** This keeps each auction on the one cluster that owns the guild. The atomic claim is the second safety net.
- Start the loop in `cog_load` and cancel it in `cog_unload`. Wrap the body in try/except and log the error, so one bad row can't kill the loop.
- A bot restart therefore loses nothing: overdue auctions close on the first tick, and open ones keep their buttons through DynamicItem.
- **No anti-sniping extension.** Bids are sealed, so a last-second bid gives no information advantage. The end time is fixed and shown up front.

## 5. Raffle

**GM commands** (`@is_gm()`), as a group, e.g. `$gmraffle`:

- `$gmraffle start <duration|manual> <ticket_price> [max_per_user] <prize...>`
  - `manual` means no timer; it ends only by `$gmraffle draw`.
  - Generate `seed_secret = secrets.token_hex(32)` and `seed_commitment = sha256(seed_secret)`.
  - Post the embed: prize, ticket price, max per user, end time (or "ends when a GM draws"), **"Fairness commitment: `{seed_commitment}`"**, and a Buy Tickets button. Ping the role.
- `$gmraffle draw`: draw now.
- `$gmraffle cancel [reason]`: refund all purchases.
- `$gmraffle status`: entrants, total tickets, total gold collected.

**Player flow** (DynamicItems `rf:buy:<id>` and `rf:mine:<id>`):

- **Buy Tickets** opens a modal with a quantity field. Validate that `1 <= qty <= 1000` per purchase and that the per-user cap holds against the **DB sum inside the locked transaction**, not a cached count.
  - Debit `qty * ticket_price` with the guarded update and insert a `raffle_purchases` row.
  - Ephemeral reply: "🎟️ You bought N tickets (you now hold M) for **{prize}**."
  - Also add a `$raffle buy <qty>` text command, since raffle entries don't need to be secret. It should use the same core function.
- **My Tickets** sends an ephemeral reply with the player's ticket count.
- The public embed may show the total tickets and entrants. Edit it at most once every ~15s, debounced, so it isn't rate-limited. It is fine if that number lags.

**Drawing** (`draw_raffle(raffle_id)`, idempotent, same claim pattern as above: `status open → drawing`, resume `drawing` under a lock):

1. Load all non-refunded purchases `ORDER BY id`. Expand them into a ticket list: one entry per ticket, each holding `user_id`, numbered 1..N in purchase order.
2. Compute `ticket_digest = sha256(canonical string of "ticket_no:user_id" joined by ",")`.
3. Compute `seed = sha256(seed_secret + ":" + ticket_digest)`. Shuffle the ticket list with Fisher-Yates driven by `random.Random(int.from_bytes(seed, "big"))`; stdlib `Random.shuffle` is Fisher-Yates. Then pick `winner = shuffled[rng.randrange(len(shuffled))]` from the same RNG.
   - Why: the user requires the tickets to be shuffled before the pick.
   - The seed is committed before any ticket is sold.
   - The ticket digest stops anyone precomputing a result without knowing every final purchase.
   - Publishing `seed_secret` afterwards lets anyone re-run the draw and verify it.
   - Put this in a pure function `draw_winner(seed_secret, tickets) -> (winning_ticket_no, user_id, ticket_digest)` and unit-test that it is deterministic and that every ticket can win. Also test the distribution roughly, e.g. a 1-ticket vs 3-ticket player over many seeds gives ~25%/75%.
4. In one transaction, set `status='drawn'`, `winner_id`, `winning_ticket`, `ticket_digest` and `drawn_at`. Ticket gold is a **gold sink** and is not refunded; the GM hands out the prize manually.
5. Announce: the winner mention, winning ticket #, total tickets and entrants, plus "Verification: seed `{seed_secret}` (sha256 = commitment above), ticket digest `{digest}`". Remove the buttons and log to the GM log channel.
6. If there are zero tickets, the raffle ends with no winner. With one entrant, that entrant wins; still run the draw.
7. Don't automatically re-draw if the winner has left or deleted their character. The win stands, and a GM handles it manually. (Don't add a reroll command unless told to.)

Timers and clusters work exactly like the silent auction: the same 30s loop, the same "only if this cluster sees the channel" check, and an atomic claim. Raffles with `ends_at IS NULL` are skipped by the loop.

## 6. Things that commonly go wrong (check each one)

- [ ] An interaction not answered within 3s. Send the modal or `defer` first, then do the work.
- [ ] Double-clicks or two modals submitted at once. The row lock plus the guarded debit make this safe; test that two concurrent raises can't overdraw.
- [ ] A bid or purchase arriving while the close runs. Handled by `FOR UPDATE` on the parent row plus the `ends_at > NOW()` re-check.
- [ ] Two clusters, or the loop and the GM `end` command, finalising together. Handled by the atomic status claim; only the claimer announces.
- [ ] A crash mid-close. Handled by the `closing`/`drawing` resume path and the per-row `refunded` flags.
- [ ] A restart while live. Handled by DynamicItems and the loop.
- [ ] Integer overflow or bigint limits. Cap the input amounts.
- [ ] Hidden info leaking: through public messages, embed edits, `status` output, error messages (e.g. "bid must exceed $X" is fine only if X is the player's **own** bid), or logs posted in public channels.
- [ ] `log_transaction` crashing on interactions (no `ctx`).
- [ ] Mentions: the role ping only on start. Use `AllowedMentions.none()` elsewhere, except a user mention for the winner.
- [ ] Existing `$gmauction`/`$bid` unchanged. New command names must not collide; check with `grep` for `name=`/aliases across cogs.

## 7. Tests (add under `tests/`, pytest, no live Discord or DB needed)

- Silent auction winner ordering: highest amount, then the earliest `amount_set_at` on a tie, then no bids → None.
- The raffle draw is deterministic for the same inputs, changes when one ticket changes, verifies against the commitment, and has the right rough distribution.
- Duration and amount parsing edge cases.
- The cog boots (follow `tests/test_boot_cogs.py`).

Run the full test suite and report the results honestly. If you can't run something against a real DB, say exactly what you couldn't verify.

## 8. Done means

- Both systems work as specified and survive a restart mid-event without losing or duplicating gold.
- New tests pass, and existing tests still pass.
- There is a short summary of the commands, config keys and tables added, plus anything you chose to differ from this spec and why.
