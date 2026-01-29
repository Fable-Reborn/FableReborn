# Lunar New Year Event - Changelog

## Version 1.0.0 - Initial Release

### Added

#### Core Event System
- **New Event Cog**: Created `lunar_new_year` cog (`cogs/lunar_new_year/__init__.py`)
  - Event-themed around Lunar New Year celebrations
  - Toggleable via configuration and GM commands
  - Disabled by default until explicitly enabled

#### Event Currency System
- **Lunar Lanterns Currency**: New event currency earned by completing adventures
  - Database column: `lunar_lanterns` in `profile` table
  - Automatically awarded upon adventure completion
  - Scales based on adventure level (1.5x multiplier)
  - **Scaling Formula**:
    - Base: `adventure_level * 7.5`
    - Random bonus: `0 to min(adventure_level * 1.5, 150)`
    - Minimum reward: 4 lanterns
    - Example rewards:
      - Level 1: ~7-9 lanterns
      - Level 10: ~75-90 lanterns
      - Level 50: ~375-450 lanterns
      - Level 100: ~750-900 lanterns

#### Shop System
- **Lunar New Year Shop**: Complete shop implementation with 8 purchasable items
  - Command: `$lunar` or `$lunarshop`
  - Shop items:
    1. Uncommon Crate - 30 Lanterns
    2. Rare Crate - 60 Lanterns
    3. Magic Crate - 250 Lanterns
  - 4. Legendary Crate - 1300 Lanterns
    5. Fortune Crate - 1750 Lanterns
    6. Divine Crate - 2900 Lanterns
    7. Weapon Type Token - 200 Lanterns
    8. 3 Lunar New Year Bags - 200 Lanterns
  - Database columns: `lnyuncommon`, `lnyrare`, `lnymagic`, `lnylegendary`, `lnyfortune`, `lnydivine`, `lnyweapon`, `lnybag`
  - Per-user inventory tracking

#### Commands
- **User Commands**:
  - `$lunar` / `$lunarshop` - Opens the Lunar New Year shop
  - `$lunar buy <item_id> [quantity]` - Purchase items from shop (item IDs 1-8)
  - `$lunar bal` / `$lunar balance` - Check Lunar Lantern balance
  - `$openlunar` / `$lunaropenbag` / `$lunaropen` - Open Lunar New Year bags
  - `$lunarbagcount` / `$lnybagcount` - Check bag inventory count

- **Game Master Commands**:
  - `$lnyenable [true/false]` - Enable/disable the event (GM only)

#### Lunar New Year Bags
- **Bag System**: Openable bags that award random items
  - Database column: `lnybag` for tracking inventory
  - Awards random crates and items when opened
  - Can be purchased from shop (3 bags per purchase)

#### Event Integration
- **Adventure Completion Listener**: `on_adventure_completion` event handler
  - Listens for completed adventures
  - Awards Lunar Lanterns based on adventure level
  - Sends notification message to players
  - Handles errors gracefully without breaking adventure flow

#### Database Schema
- **New Columns Added** (via `DATABASE_MIGRATION.sql`):
  - `lunar_lanterns` (BIGINT) - Event currency
  - `lnyuncommon` (BIGINT) - Uncommon crate inventory
  - `lnyrare` (BIGINT) - Rare crate inventory
  - `lnymagic` (BIGINT) - Magic crate inventory
  - `lnylegendary` (BIGINT) - Legendary crate inventory
  - `lnyfortune` (BIGINT) - Fortune crate inventory
  - `lnydivine` (BIGINT) - Divine crate inventory
  - `lnyweapon` (BIGINT) - Weapon token inventory
  - `lnybag` (BIGINT) - Lunar New Year bag inventory

### Changed

#### Configuration
- **config.toml**: Added `"cogs.lunar_new_year"` to `initial_extensions` list (commented by default)

#### Command Aliases
- **Resolved Conflicts**: Fixed `CommandRegistrationError` by updating command aliases
  - `lunarnewyear` group: Changed from `["lny", "lunar"]` to `["lunar", "lunarshop"]`
  - `openlunar` command: Changed from `["lnybag", "lunarbag"]` to `["lunaropenbag", "lunaropen"]`
  - `lunarbags` command: Renamed to `lunarbagcount` with alias `["lnybagcount"]`

#### Adventure Level Scaling
- **Reward Scaling**: Implemented adventure-level-based scaling for lantern rewards
  - Initially used simple fixed formula: `int(num ** 1.2 * random.randint(1, 8))`
  - **Updated to 1.5x multiplier** for better rewards:
    - Base formula: `adventure_level * 7.5`
    - Bonus scaling: `min(adventure_level * 1.5, 150)`
    - Minimum: 4 lanterns per adventure

### Fixed

#### Message Display Issues
- **Lantern Notification Message**: Fixed issue where players weren't seeing lantern rewards
  - Moved message sending outside main try block to ensure it always runs
  - Improved error handling for context access
  - Added fallback methods for message delivery (`ctx.send()` → `ctx.channel.send()`)
  - Enhanced exception handling to prevent silent failures

#### Adventure Number Extraction
- **Robust Adventure Level Detection**: Improved method for getting adventure level from context
  - Primary: `ctx.adventure_data` tuple (adventure_number, time, done)
  - Fallback 1: `ctx.character_data.get("adventure")`
  - Fallback 2: Calculate from player level using `xptolevel()`
  - Default: Level 1 if all methods fail
  - Added comprehensive error handling for each method

### Documentation

#### Created Files
- **README.md**: Complete documentation for the Lunar New Year event
  - Features overview
  - Command reference
  - Shop items list
  - Setup instructions
  - pgAdmin4 SQL execution guide
  - Customization notes

- **DATABASE_MIGRATION.sql**: SQL migration script
  - `ALTER TABLE` statements with `IF NOT EXISTS` checks
  - Safe for multiple executions
  - Column definitions for all event-related data

- **SET_SHOP_QUANTITIES.sql**: Example SQL for setting shop inventory
  - Sample `UPDATE` queries for all users
  - Example for specific user updates
  - Verification `SELECT` queries

- **ANNOUNCEMENT.md**: Discord announcement template
  - Formatted message with all user commands
  - Shop items list
  - Event-themed introduction text

- **CHANGELOG.md**: This file - comprehensive change log

### Removed

#### Shop Items
- **Seasonal Class and Background**: Removed from shop (Items 7-8 in original design)
  - Removed `lnyclass` column requirement
  - Removed `lnybg` column requirement
  - Shop reduced from 10 items to 8 items
  - Renumbered remaining items accordingly

### Technical Details

#### Error Handling
- All database operations use `COALESCE` for null-safe arithmetic
- Adventure completion listener includes comprehensive exception handling
- Message sending failures are logged but don't break adventure flow
- Event can be disabled without removing the cog

#### Code Quality
- Follows existing codebase patterns (modeled after Halloween event)
- Uses existing utility functions (`utils.random`, `user_cooldown`)
- Integrates with existing event system (`self.bot.dispatch`, `@commands.Cog.listener`)
- Maintains consistency with other event cogs

#### Internationalization
- All user-facing messages use `_()` translation wrapper
- Follows existing i18n patterns

### Known Issues / Notes

- Event is disabled by default - must be enabled via `$lnyenable` or configuration
- Database migration must be run before enabling the event
- Shop quantities start at 0 for all users - use `SET_SHOP_QUANTITIES.sql` to populate
- Message sending relies on context availability - may fail in rare edge cases
- Adventure level detection may default to player level if adventure data unavailable

---

## Version 1.0.1 - Bug Fixes (Current)

### Fixed
- **Lantern Notification Message**: Fixed message not appearing after adventure completion
  - Restructured message sending to occur outside main try block
  - Improved context access with multiple fallback methods
  - Enhanced exception handling for message delivery

- **Adventure Level Extraction**: Improved robustness of adventure number detection
  - Added type checking for `ctx.adventure_data`
  - Multiple fallback methods with proper error handling
  - Prevents exceptions from breaking lantern calculation

---

*Last Updated: 2026*
