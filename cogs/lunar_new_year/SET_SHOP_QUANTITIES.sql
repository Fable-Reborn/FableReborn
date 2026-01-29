-- Lunar New Year Shop - Set Initial Quantities
-- Run these SQL commands to set how many of each item users can buy

-- ============================================
-- OPTION 1: Set quantities for ALL users
-- ============================================
-- This will give every user the same amount of each item they can purchase

UPDATE profile 
SET 
    lnyuncommon = 10,      -- Uncommon Crates
    lnyrare = 5,           -- Rare Crates
    lnymagic = 3,          -- Magic Crates
    lnylegendary = 2,      -- Legendary Crates
    lnyfortune = 1,        -- Fortune Crates
    lnydivine = 1,         -- Divine Crates
    lnytoken = 5,          -- Weapon Type Tokens
    lnybag = 10;           -- Lunar New Year Bags (3 per purchase, so 10 = 30 bags total)

-- ============================================
-- OPTION 2: Set quantities for SPECIFIC users
-- ============================================
-- Replace USER_ID_HERE with the actual Discord user ID (as a number)

UPDATE profile 
SET 
    lnyuncommon = 10,
    lnyrare = 5,
    lnymagic = 3,
    lnylegendary = 2,
    lnyfortune = 1,
    lnydivine = 1,
    lnytoken = 5,
    lnybag = 10
WHERE "user" = USER_ID_HERE;

-- Example for multiple specific users:
UPDATE profile 
SET 
    lnyuncommon = 10,
    lnyrare = 5,
    lnymagic = 3,
    lnylegendary = 2,
    lnyfortune = 1,
    lnydivine = 1,
    lnytoken = 5,
    lnybag = 10
WHERE "user" IN (123456789, 987654321, 555555555);  -- Replace with actual user IDs

-- ============================================
-- OPTION 3: Add quantities to existing values
-- ============================================
-- This adds to what users already have (useful for restocking)

UPDATE profile 
SET 
    lnyuncommon = COALESCE(lnyuncommon, 0) + 10,
    lnyrare = COALESCE(lnyrare, 0) + 5,
    lnymagic = COALESCE(lnymagic, 0) + 3,
    lnylegendary = COALESCE(lnylegendary, 0) + 2,
    lnyfortune = COALESCE(lnyfortune, 0) + 1,
    lnydivine = COALESCE(lnydivine, 0) + 1,
    lnytoken = COALESCE(lnytoken, 0) + 5,
    lnybag = COALESCE(lnybag, 0) + 10;

-- ============================================
-- OPTION 4: Set different quantities based on conditions
-- ============================================
-- Example: Give more items to users above a certain level

UPDATE profile 
SET 
    lnyuncommon = 20,
    lnyrare = 10,
    lnymagic = 5,
    lnylegendary = 3,
    lnyfortune = 2,
    lnydivine = 2,
    lnytoken = 10,
    lnybag = 20
WHERE xp >= 1000000;  -- Users with XP >= 1,000,000 (adjust threshold as needed)

-- ============================================
-- CHECK CURRENT QUANTITIES
-- ============================================
-- View quantities for a specific user
SELECT 
    "user",
    lnyuncommon,
    lnyrare,
    lnymagic,
    lnylegendary,
    lnyfortune,
    lnydivine,
    lnytoken,
    lnybag
FROM profile 
WHERE "user" = USER_ID_HERE;  -- Replace with actual user ID

-- View quantities for all users (first 20)
SELECT 
    "user",
    lnyuncommon,
    lnyrare,
    lnymagic,
    lnylegendary,
    lnyfortune,
    lnydivine,
    lnytoken,
    lnybag
FROM profile 
ORDER BY "user"
LIMIT 20;

-- ============================================
-- RESET ALL QUANTITIES TO ZERO
-- ============================================
-- Use this if you want to reset everything (be careful!)

-- UPDATE profile 
-- SET 
--     lnyuncommon = 0,
--     lnyrare = 0,
--     lnymagic = 0,
--     lnylegendary = 0,
--     lnyfortune = 0,
--     lnydivine = 0,
--     lnytoken = 0,
--     lnybag = 0;
