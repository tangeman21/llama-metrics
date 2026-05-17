#!/usr/bin/env python3
"""llama-snapshot.py — write a time-series snapshot to SQLite.
Called by the power sampler every 5 minutes.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time

DB_PATH = os.path.expanduser("~/.hermes/llama-snapshots.db")
TOKENS_FILE = os.path.expanduser("~/.hermes/llama-tokens.json")
ENERGY_FILE = os.path.expanduser("~/.hermes/llama-energy.json")
LLAMA_URL = "http://localhost:8018/metrics"


def init_db(conn):
    """Create the snapshots table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            epoch REAL NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            predicted_tokens INTEGER NOT NULL,
            cumulative INTEGER NOT NULL,
            total_power_w REAL NOT NULL,
            amd_w REAL NOT NULL,
            nvidia_w REAL NOT NULL,
            cum_wh REAL NOT NULL,
            prompt_tps REAL,
            output_tps REAL,
            ctx_max INTEGER,
            requests INTEGER
        )
    """)
    # Index for time-range queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_epoch ON snapshots(epoch)")
    # Auto-vacuum to keep DB small
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.commit()


def fetch_llama_metrics():
    """Read live metrics from llama-server /metrics endpoint."""
    try:
        resp = subprocess.run(
            ["curl", "-s", "--max-time", "3", LLAMA_URL],
            capture_output=True, text=True, timeout=5
        )
        result = {}
        for line in resp.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0]
                val = parts[1]
                if key == "llamacpp:prompt_tokens_total":
                    result["prompt_tokens"] = int(float(val))
                elif key == "llamacpp:tokens_predicted_total":
                    result["predicted_tokens"] = int(float(val))
                elif key == "llamacpp:prompt_tokens_seconds":
                    result["prompt_tps"] = float(val)
                elif key == "llamacpp:predicted_tokens_seconds":
                    result["output_tps"] = float(val)
                elif key == "llamacpp:n_tokens_max":
                    result["ctx_max"] = int(float(val))
                elif key == "llamacpp:requests_processing":
                    result["requests"] = int(float(val))
        return result
    except Exception:
        return {}


def read_json_field(path, key, default=0):
    """Read a field from a JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get(key, default)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def cleanup_old(conn, keep_days=7):
    """Delete snapshots older than keep_days."""
    cutoff = time.time() - (keep_days * 86400)
    conn.execute("DELETE FROM snapshots WHERE epoch < ?", (cutoff,))
    deleted = conn.total_changes
    conn.execute("PRAGMA incremental_vacuum")
    conn.commit()
    return deleted


def main():
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    # Token metrics from llama-server
    live = fetch_llama_metrics()
    prompt_tokens = live.get("prompt_tokens", 0)
    predicted_tokens = live.get("predicted_tokens", 0)
    prompt_tps = live.get("prompt_tps")
    output_tps = live.get("output_tps")
    ctx_max = live.get("ctx_max")
    requests = live.get("requests")

    # Cumulative from state file
    cumulative = int(read_json_field(TOKENS_FILE, "cumulative", 0))

    # Power from energy state file
    amd_w = read_json_field(ENERGY_FILE, "last_amd_watts", 0)
    nvidia_w = read_json_field(ENERGY_FILE, "last_nvidia_watts", 0)
    total_power_w = amd_w + nvidia_w
    cum_wh = read_json_field(ENERGY_FILE, "cumulative_wh", 0)

    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    conn.execute(
        """INSERT INTO snapshots
           (ts, epoch, prompt_tokens, predicted_tokens, cumulative,
            total_power_w, amd_w, nvidia_w, cum_wh,
            prompt_tps, output_tps, ctx_max, requests)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, now, prompt_tokens, predicted_tokens, cumulative,
         total_power_w, amd_w, nvidia_w, cum_wh,
         prompt_tps, output_tps, ctx_max, requests)
    )

    # Cleanup old data (once per day — check via file mtime)
    CLEANUP_MARKER = DB_PATH + ".cleanup"
    try:
        last_cleanup = os.path.getmtime(CLEANUP_MARKER)
    except OSError:
        last_cleanup = 0
    if now - last_cleanup > 86400:  # 24 hours
        deleted = cleanup_old(conn, keep_days=7)
        if deleted > 0:
            print(f"Cleaned {deleted} old snapshots", file=sys.stderr)
        with open(CLEANUP_MARKER, "w") as f:
            f.write(str(now))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
