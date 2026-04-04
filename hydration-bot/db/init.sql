-- Hydration Bot Database Schema
-- Initializes the users table for storing reminder preferences.

CREATE TABLE IF NOT EXISTS users (
    user_id         BIGINT PRIMARY KEY,
    username        TEXT,
    interval_minutes INT NOT NULL DEFAULT 60,
    reminder_active BOOLEAN NOT NULL DEFAULT FALSE,
    last_reminder_time TIMESTAMP WITH TIME ZONE
);

-- Index for quickly querying active reminders on bot restart
CREATE INDEX IF NOT EXISTS idx_users_active_reminders
    ON users (reminder_active)
    WHERE reminder_active = TRUE;
