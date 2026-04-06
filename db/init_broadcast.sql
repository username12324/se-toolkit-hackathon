-- Event Broadcast Reminder System — Database Schema
-- Extends the existing LMS schema with broadcast and participant tables.

-- Participants: aliases for event attendees, mapped to Telegram chat IDs
CREATE TABLE IF NOT EXISTS participants (
    alias VARCHAR(100) PRIMARY KEY,
    telegram_chat_id BIGINT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Broadcast schedules: define what message to send, how often, and when
CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    message TEXT NOT NULL,
    interval_minutes INT NOT NULL,          -- e.g., 60 for every hour
    start_time TIME NOT NULL,               -- e.g., '09:00'
    end_time TIME NOT NULL,                 -- e.g., '19:00'
    is_active BOOLEAN DEFAULT TRUE,
    last_sent_at TIMESTAMP DEFAULT NULL,    -- tracks when last batch was sent
    created_at TIMESTAMP DEFAULT NOW()
);

-- Target aliases for each broadcast (many-to-many join table)
CREATE TABLE IF NOT EXISTS broadcast_targets (
    broadcast_id INT REFERENCES broadcasts(id) ON DELETE CASCADE,
    participant_alias VARCHAR(100) REFERENCES participants(alias) ON DELETE CASCADE,
    PRIMARY KEY (broadcast_id, participant_alias)
);

-- Delivery log: records every attempted broadcast message
CREATE TABLE IF NOT EXISTS delivery_log (
    id SERIAL PRIMARY KEY,
    broadcast_id INT REFERENCES broadcasts(id),
    participant_alias VARCHAR(100),
    sent_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) CHECK (status IN ('sent', 'failed'))
);

-- Personal water reminder state (retains original hydration bot functionality)
CREATE TABLE IF NOT EXISTS water_reminders (
    telegram_chat_id BIGINT PRIMARY KEY,
    interval_minutes INT NOT NULL DEFAULT 60,
    is_active BOOLEAN DEFAULT FALSE,
    last_sent_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_broadcasts_is_active ON broadcasts(is_active);
CREATE INDEX IF NOT EXISTS idx_broadcast_targets_broadcast ON broadcast_targets(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_broadcast ON delivery_log(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_sent_at ON delivery_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_water_reminders_active ON water_reminders(is_active);

-- Helpful views
CREATE OR REPLACE VIEW v_broadcast_schedule AS
SELECT
    b.id,
    b.message,
    b.interval_minutes,
    b.start_time,
    b.end_time,
    b.is_active,
    b.last_sent_at,
    b.created_at,
    ARRAY_AGG(t.participant_alias) AS targets
FROM broadcasts b
LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
GROUP BY b.id;
