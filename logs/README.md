# Gear balance logs

Player gear actions write to the `equipment_events` table on the live database.

At the end of a balance window, a GM runs:

```
$gear balance
$gear balance 14
```

That writes `logs/gear_balance_review.md` on the bot host and also attaches the file in Discord.

Next review pass: drop that markdown into Cursor chat (or copy it into this folder) and ask for a balance read against the intended craft, forge, and crate rates.
