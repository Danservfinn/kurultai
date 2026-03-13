#!/usr/bin/env python3
"""Test script to verify cron model fix"""
import json

def main():
    expected = "qwen3.5:9b"

    # Check if the model names are correct
    with open("/Users/kublai/.openclaw/cron/jobs.json") as f:
        data = json.load(f)

    # Find heartbeat-watchdog
    heartbeat = next((j for j in data["jobs"] if j.get("name") == "heartbeat-watchdog"), None)
    # Find tock-gather
    tock = next((j for j in data["jobs"] if j.get("name") == "tock-gather"), None)

    print("Cron jobs file is valid JSON")

    # Verify model names
    heartbeat_model = heartbeat.get("payload", {}).get("model", "") if heartbeat else ""
    tock_model = tock.get("payload", {}).get("model", "") if tock else ""

    if heartbeat_model == expected:
        print(f"heartbeat-watchdog model: {heartbeat_model} - OK")
    else:
        print(f"heartbeat-watchdog model: {heartbeat_model} - WRONG (expected: {expected})")

    if tock_model == expected:
        print(f"tock-gather model: {tock_model} - OK")
    else:
        print(f"tock-gather model: {tock_model} - WRONG (expected: {expected})")

    if heartbeat_model == expected and tock_model == expected:
        print("\nFix verified successfully!")
        return 0
    else:
        print("\nOne or both models still incorrect!")
        return 1

if __name__ == "__main__":
    main()
