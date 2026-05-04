#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to simulate full call processing with LLM analysis.
This creates realistic dashboard events including risk scores and summaries.
"""

import sqlite3
import time
import json
import hashlib
from datetime import datetime

DB_PATH = "C:/calls/data/db/callprofiler.db"
USER_ID = "serhio"


def create_test_call(conn):
    """Create a new test call."""
    test_md5 = hashlib.md5(f"test_analysis_{datetime.now().isoformat()}".encode()).hexdigest()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO calls (user_id, source_filename, source_md5, direction, status,
                          call_datetime, duration_sec, created_at, updated_at)
        VALUES (?, ?, ?, 'incoming', 'pending', datetime('now'), 120, datetime('now'), datetime('now'))
    """, (USER_ID, 'test_analysis.wav', test_md5))
    conn.commit()
    call_id = cur.lastrowid
    print(f"[+] Created test call: {call_id}")
    return call_id


def add_transcript(conn, call_id):
    """Add test transcript."""
    cur = conn.cursor()
    segments = [
        ("OWNER", "Hello, this is a test call for dashboard verification.", 0, 3000),
        ("OTHER", "Yes, I understand. Let's discuss the project timeline.", 3000, 7000),
        ("OWNER", "We need to deliver by next Friday. Can you commit to that?", 7000, 11000),
        ("OTHER", "I'll do my best, but I need to check with the team first.", 11000, 15000),
    ]

    for speaker, text, start_ms, end_ms in segments:
        cur.execute("""
            INSERT INTO transcripts (call_id, speaker, text, start_ms, end_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (call_id, speaker, text, start_ms, end_ms))

    conn.commit()
    print(f"[+] Added transcript segments")


def add_analysis(conn, call_id):
    """Add test LLM analysis."""
    cur = conn.cursor()

    analysis_data = {
        "call_type": "business",
        "priority": 75,
        "risk_score": 45,
        "summary": "Discussion about project timeline. Commitment requested but not confirmed.",
        "hook": "Deadline commitment unclear",
        "key_topics": ["project timeline", "team coordination", "deadline"],
        "promises": [
            {
                "who": "OTHER",
                "what": "Check with team about Friday deadline",
                "when": "soon",
                "confidence": 0.8
            }
        ],
        "flags": ["vague_commitment"],
        "action_items": ["Follow up on deadline confirmation"],
        "entities": [
            {"name": "Test Contact", "type": "PERSON", "mention": "discussed project"}
        ],
        "relations": [],
        "structured_facts": [
            {
                "fact_type": "promise",
                "entity_name": "Test Contact",
                "quote": "I'll do my best",
                "confidence": 0.7,
                "polarity": 0.3,
                "intensity": 0.6
            }
        ]
    }

    cur.execute("""
        INSERT INTO analyses (call_id, call_type, priority, risk_score, summary, hook,
                             key_topics, raw_response, prompt_version, schema_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'analyze_v001', 'v2', datetime('now'))
    """, (
        call_id,
        analysis_data["call_type"],
        analysis_data["priority"],
        analysis_data["risk_score"],
        analysis_data["summary"],
        analysis_data["hook"],
        json.dumps(analysis_data["key_topics"]),
        json.dumps(analysis_data)
    ))

    conn.commit()
    print(f"[+] Added LLM analysis (risk_score={analysis_data['risk_score']})")


def update_call_status(conn, call_id, status):
    """Update call status."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE calls SET status = ?, updated_at = datetime('now')
        WHERE call_id = ?
    """, (status, call_id))
    conn.commit()
    print(f"[+] Updated call {call_id} to status='{status}'")


def main():
    print("=" * 60)
    print("Dashboard Live Update Test - With LLM Analysis")
    print("=" * 60)
    print()
    print("This script simulates a full call processing pipeline:")
    print("  1. Create new call (pending)")
    print("  2. Add transcript (transcribed)")
    print("  3. Add LLM analysis (analyzed)")
    print()
    print("Dashboard should show:")
    print("  - Live event: Call created")
    print("  - Live event: Transcription complete")
    print("  - Live event: Analysis complete (with risk score)")
    print("  - Updated history with new call")
    print("  - Updated stats")
    print()
    print("Starting in 3 seconds...")
    time.sleep(3)
    print()

    conn = sqlite3.connect(DB_PATH)

    # Stage 1: Create call
    print("Stage 1: Creating new call...")
    call_id = create_test_call(conn)
    time.sleep(2)

    # Stage 2: Add transcript
    print("\nStage 2: Adding transcript...")
    add_transcript(conn, call_id)
    update_call_status(conn, call_id, "transcribed")
    time.sleep(3)

    # Stage 3: Add analysis
    print("\nStage 3: Adding LLM analysis...")
    add_analysis(conn, call_id)
    update_call_status(conn, call_id, "analyzed")
    time.sleep(2)

    print("\n" + "=" * 60)
    print("Test complete!")
    print()
    print("Check your dashboard at http://127.0.0.1:8765")
    print("You should see:")
    print("  - 3 new events in 'Live Events' panel")
    print("  - New call in 'History' with risk_score=45")
    print("  - Updated total_calls counter")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
