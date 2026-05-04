-- Migration: Add trigger to update calls.updated_at when analysis is saved
-- Purpose: Enable real-time dashboard updates via SSE polling
-- Date: 2026-05-04

-- Trigger fires on INSERT OR UPDATE to analyses table
CREATE TRIGGER IF NOT EXISTS trg_analyses_update_call_timestamp
AFTER INSERT ON analyses
FOR EACH ROW
BEGIN
    UPDATE calls
    SET updated_at = CURRENT_TIMESTAMP
    WHERE call_id = NEW.call_id;
END;

-- Also handle UPDATE case (re-enrichment)
CREATE TRIGGER IF NOT EXISTS trg_analyses_update_call_timestamp_upd
AFTER UPDATE ON analyses
FOR EACH ROW
BEGIN
    UPDATE calls
    SET updated_at = CURRENT_TIMESTAMP
    WHERE call_id = NEW.call_id;
END;
