-- Lunar New Year Event Database Migration
-- Run these SQL commands to add the necessary columns for the Lunar New Year event

-- Main currency column for Lunar Lanterns
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lunar_lanterns INTEGER DEFAULT 0;

-- Shop inventory columns (how many of each item each user can buy)
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnyuncommon INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnyrare INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnymagic INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnylegendary INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnyfortune INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnydivine INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnyclass INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnybg INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnytoken INTEGER DEFAULT 0;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnybag INTEGER DEFAULT 0;

-- Lunar New Year bags (items that can be opened)
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lunar_bags INTEGER DEFAULT 0;

-- Flags for special items
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lnybg1 BOOLEAN DEFAULT FALSE;
ALTER TABLE profile ADD COLUMN IF NOT EXISTS lunarclass BOOLEAN DEFAULT FALSE;

-- Note: You may want to set initial shop quantities for all users
-- Example: UPDATE profile SET lnyuncommon = 10, lnyrare = 5, lnymagic = 3, lnylegendary = 2, lnyfortune = 1, lnydivine = 1, lnyclass = 1, lnybg = 1, lnytoken = 5, lnybag = 10;
