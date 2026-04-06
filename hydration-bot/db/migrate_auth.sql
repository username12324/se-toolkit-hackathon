-- Migration: add multi-user authentication support
-- Run this once before starting the web app with auth

-- App users table (separate from the bot's water-reminder users)
CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add owner_id columns to scope data per user
ALTER TABLE broadcasts
    ADD COLUMN IF NOT EXISTS owner_id INT REFERENCES app_users(id) ON DELETE CASCADE;

ALTER TABLE participants
    ADD COLUMN IF NOT EXISTS owner_id INT REFERENCES app_users(id) ON DELETE CASCADE;

ALTER TABLE broadcast_targets
    ADD COLUMN IF NOT EXISTS owner_id INT REFERENCES app_users(id) ON DELETE SET NULL;

ALTER TABLE delivery_log
    ADD COLUMN IF NOT EXISTS owner_id INT REFERENCES app_users(id) ON DELETE SET NULL;

-- Indexes for ownership queries
CREATE INDEX IF NOT EXISTS idx_broadcasts_owner ON broadcasts(owner_id);
CREATE INDEX IF NOT EXISTS idx_participants_owner ON participants(owner_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_owner ON delivery_log(owner_id);
