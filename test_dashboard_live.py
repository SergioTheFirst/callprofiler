#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify dashboard live updates.
Simulates call processing by updating call status and checking if dashboard detects changes.
"""

import sqlite3
import time
from datetime import datetime

DB_PATH = "C:/calls/data/db/callprofiler.db"
USER_ID = "serhio"


def get_latest_timestamp(conn):
    """Get latest updated_at timestamp."""
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(ts) AS latest FROM (
            SELECT MAX(updated_at) AS ts FROM calls WHERE user_id = ?
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM entities WHERE user_id = ?
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM entity_metrics WHERE user_id = ?
        )
    """, (USER_ID, USER_ID, USER_ID))
    row = cur.fetchone()
    return row[0] if row else None


def get_pending_call(conn):
    """Find a call with status='pending' or 'transcribed'."""
    cur = conn.cursor()
    cur.execute("""
        SELECT call_id, status, source_filename
        FROM calls
        WHERE user_id = ? AND status IN ('pending', 'transcribed')
        ORDER BY created_at DESC
        LIMIT 1
    """, (USER_ID,))
    row = cur.fetchone()
    return {"call_id": row[0], "status": row[1], "filename": row[2]} if row else None


def update_call_status(conn, call_id, new_status):
    """Update call status (simulates pipeline processing)."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE calls
        SET status = ?, updated_at = datetime('now')
        WHERE call_id = ?
    """, (new_status, call_id))
    conn.commit()
    print(f"[+] Updated call {call_id} to status='{new_status}'")


def main():
    print("=" * 60)
    print("Dashboard Live Update Test")
    print("=" * 60)
    print()

    conn = sqlite3.connect(DB_PATH)

    # Step 1: Get initial timestamp
    initial_ts = get_latest_timestamp(conn)
    print(f"1. Initial timestamp: {initial_ts}")
    print()

    # Step 2: Find a call to update
    call = get_pending_call(conn)
    if not call:
        print("[!] No pending/transcribed calls found. Creating a test call...")
        import hashlib
        test_md5 = hashlib.md5(f"test_dashboard_{datetime.now().isoformat()}".encode()).hexdigest()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO calls (user_id, source_filename, source_md5, direction, status, created_at, updated_at)
            VALUES (?, 'test_dashboard_live.wav', ?, 'incoming', 'pending', datetime('now'), datetime('now'))
        """, (USER_ID, test_md5))
        conn.commit()
        call_id = cur.lastrowid
        call = {"call_id": call_id, "status": "pending", "filename": "test_dashboard_live.wav"}
        print(f"[+] Created test call: {call_id}")

    print(f"2. Found call to update:")
    print(f"   - call_id: {call['call_id']}")
    print(f"   - status: {call['status']}")
    print(f"   - filename: {call['filename']}")
    print()

    # Step 3: Simulate pipeline stages
    stages = [
        ("transcribed", 2),
        ("analyzed", 3),
    ]

    for new_status, delay in stages:
        if call['status'] == new_status:
            continue

        print(f"3. Simulating pipeline stage: {call['status']} -> {new_status}")
        print(f"   Waiting {delay} seconds...")
        time.sleep(delay)

        update_call_status(conn, call['call_id'], new_status)
        call['status'] = new_status

        # Check if timestamp changed
        new_ts = get_latest_timestamp(conn)
        print(f"   New timestamp: {new_ts}")

        if new_ts != initial_ts:
            print(f"   [+] Timestamp changed! Dashboard should detect this.")
        else:
            print(f"   [-] Timestamp unchanged. Dashboard won't detect this.")

        initial_ts = new_ts
        print()

    print("=" * 60)
    print("Test complete!")
    print()
    print("Expected dashboard behavior:")
    print("  1. 'Live Events' panel should show:")
    print("     - Transcription complete")
    print("     - Analysis complete")
    print("  2. 'History' should refresh automatically")
    print("  3. Stats should update (total calls, avg risk)")
    print()
    print("To verify:")
    print("  1. Open http://127.0.0.1:8765 in browser")
    print("  2. Run this script: python test_dashboard_live.py")
    print("  3. Watch the dashboard update in real-time")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
