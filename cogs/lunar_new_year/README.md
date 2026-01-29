# Lunar New Year Event Cog

A seasonal event cog for the Fable RPG Discord bot, themed around Lunar New Year celebrations.

## Features

- **Event Currency**: Players earn "Lunar Lanterns" by completing adventures
- **Shop System**: Spend lanterns on crates, backgrounds, classes, and special items
- **Lunar New Year Bags**: Openable bags that contain themed items
- **Enable/Disable**: Game Masters can toggle the event on/off using `$lnyenable`

## Commands

### User Commands

- `$lunar` or `$lunarshop` - Opens the Lunar New Year shop
- `$lunar buy <item_id>` - Purchase an item from the shop (item IDs 1-8)
- `$lunar bal` or `$lunar balance` - Check your Lunar Lantern balance
- `$openlunar` or `$lnybag` - Open a Lunar New Year bag
- `$lunarbagcount` or `$lnybagcount` - Check how many Lunar New Year bags you have

### Game Master Commands

- `$lnyenable [true/false]` - Enable or disable the Lunar New Year event

## Shop Items

1. Uncommon Crate - 30 Lanterns
2. Rare Crate - 60 Lanterns
3. Magic Crate - 250 Lanterns
4. Legendary Crate - 1300 Lanterns
5. Fortune Crate - 1750 Lanterns
6. Divine Crate - 2900 Lanterns
7. Weapon Type Token - 200 Lanterns
8. 3 Lunar New Year Bags - 200 Lanterns

## Currency Earning

Players earn Lunar Lanterns automatically when completing adventures. The amount earned is based on the adventure difficulty:
- Formula: `int(adventure_number ** 1.2 * random.randint(1, 8))`
- Higher level adventures award more lanterns

## Setup

1. **Database Migration**: Run the SQL commands in `DATABASE_MIGRATION.sql` to add the required columns

   **How to Run SQL Commands in pgAdmin4:**
   
   **Method 1: Query Tool (Recommended)**
   1. Open pgAdmin4 and connect to your PostgreSQL server
   2. Navigate to your database: Expand Servers → your server → Databases → **Fable** (or your database name)
   3. Right-click the **Fable** database → Select **Query Tool** (or click the Query Tool icon)
   4. Click the **Open File** icon (folder icon) or press `Ctrl+O`
   5. Navigate to: `/home/fableadmin/FableRPG-FINAL/FableRPG-FINAL/Fable/cogs/lunar_new_year/DATABASE_MIGRATION.sql`
   6. Select the file and click **Open** - the SQL commands will load in the query editor
   7. Review the SQL (it contains `ALTER TABLE` statements to add columns)
   8. Click the **Execute** button (play icon) or press `F5` to run the migration
   9. Verify the columns were added: Expand Databases → Fable → Schemas → public → Tables → **profile** → Columns
      - You should see new columns like `lunar_lanterns`, `lnyuncommon`, `lnyrare`, etc.

   **Method 2: Copy-Paste**
   1. Open `DATABASE_MIGRATION.sql` in a text editor
   2. Copy all the SQL commands
   3. In pgAdmin4, open Query Tool on the Fable database
   4. Paste the SQL into the query editor
   5. Click **Execute** or press `F5`

   **Note:** The migration uses `IF NOT EXISTS`, so it's safe to run multiple times if needed.

2. **Enable the Cog**: Uncomment `"cogs.lunar_new_year"` in `config.toml`:
   ```toml
   initial_extensions = [
       # ... other cogs ...
       "cogs.lunar_new_year",
   ]
   ```

3. **Set Shop Quantities**: Update the shop inventory columns for users (see SQL file comments)

4. **Restart the Bot**: The cog will load automatically

## Disabling the Event

To disable the event without removing the cog:
- Use `$lnyenable false` (Game Master only)
- Or comment out the cog in `config.toml` and restart

## Customization

- **Currency Name**: Currently "Lunar Lanterns" - can be changed in the code
- **Shop Items**: Modify the items list in the `lunarnewyear` command
- **Currency Formula**: Adjust the calculation in `on_adventure_completion`
- **Background Images**: Update thumbnail URLs in the shop embed

## Notes

- The event is disabled by default (`self.enabled = True` in code, but you can set it to `False`)
- All database operations use `COALESCE` to handle missing columns gracefully
- The adventure completion listener only triggers for adventures level 15+
- Shop quantities are per-user (each user has their own inventory)
