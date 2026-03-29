#!/usr/bin/env python3
"""
watchdog-health-parser.py — Consolidated health metrics parser

Replaces 80+ individual Python subprocess calls in watchdog-gather.sh with
a single invocation. Parses JSON outputs from health checks and extracts
metrics needed for TICK logging.

Input: JSON file paths or inline JSON
Output: Shell-compatible variable assignments

Usage:
    python3 watchdog-health-parser.py --trend-prediction ticks.jsonl
    python3 watchdog-health-parser.py --anomaly-detection ticks.jsonl --error-count 42
    python3 watchdog-health-parser.py --circuit-state circuit-output.json
"""

import sys
import json
import argparse
from pathlib import Path


def parse_trend_prediction(json_input):
    """Parse trend prediction output."""
    try:
        if isinstance(json_input, str) and json_input.startswith('{'):
            d = json.loads(json_input)
        else:
            with open(json_input) as f:
                d = json.load(f)

        direction = d.get('trend_direction', 'unknown')

        # Check for approaching thresholds
        approaching = ""
        hits = d.get('predicted_threshold_hits', {})
        for level, info in hits.items():
            if info.get('minutes_until', 999) < 30:
                approaching = f"{level}:{info['minutes_until']}:{info['threshold']}"
                break

        return f"ERR_DIRECTION={direction}\nAPPROACHING_THRESHOLD={approaching}"
    except Exception as e:
        return f"ERR_DIRECTION=unknown\nAPPROACHING_THRESHOLD="


def parse_anomaly_detection(json_input, error_count):
    """Parse anomaly detection output."""
    try:
        if isinstance(json_input, str) and json_input.startswith('{'):
            d = json.loads(json_input)
        else:
            with open(json_input) as f:
                d = json.load(f)

        severity = d.get('severity', 'NORMAL')
        z_score = d.get('z_score', 0)
        deviation = d.get('deviation_from_mean', 0)

        return f"ANOMALY_SEVERITY={severity}\nANOMALY_ZSCORE={z_score}\nANOMALY_DEV={deviation}"
    except Exception as e:
        return f"ANOMALY_SEVERITY=NORMAL\nANOMALY_ZSCORE=0\nANOMALY_DEV=0"


def parse_circuit_state(json_input):
    """Parse circuit breaker state."""
    try:
        if isinstance(json_input, str) and json_input.startswith('{'):
            d = json.loads(json_input)
        else:
            with open(json_input) as f:
                d = json.load(f)

        recovered = len(d.get('recovered', []))
        still_open = len(d.get('still_open', []))

        return f"CIRCUIT_RECOVERED={recovered}\nCIRCUIT_STILL_OPEN={still_open}"
    except Exception as e:
        return f"CIRCUIT_RECOVERED=0\nCIRCUIT_STILL_OPEN=0"


def parse_credentials(alert_file, flags_file):
    """Parse credential health from alert and flags files."""
    try:
        # Parse alerts
        alert_count = 0
        if Path(alert_file).exists():
            with open(alert_file) as f:
                d = json.load(f)
                alert_count = len(d.get('alerts', []))

        # Parse flags
        valid = invalid = 0
        if Path(flags_file).exists():
            with open(flags_file) as f:
                d = json.load(f)
                agents = d.get('agents', {})
                for flags in agents.values():
                    if flags.get('flagged'):
                        invalid += 1
                    else:
                        valid += 1

        # Determine fleet health
        total = valid + invalid
        if total == 0:
            fleet_health = 'unknown'
        elif invalid == 0:
            fleet_health = 'healthy'
        elif invalid > total / 2:
            fleet_health = 'crisis'
        else:
            fleet_health = 'degraded'

        return f"CRED_ALERT_COUNT={alert_count}\nCRED_HEALTH_FLEET={fleet_health}\nCRED_HEALTH_VALID={valid}\nCRED_HEALTH_INVALID={invalid}"
    except Exception as e:
        return f"CRED_ALERT_COUNT=0\nCRED_HEALTH_FLEET=unknown\nCRED_HEALTH_VALID=0\nCRED_HEALTH_INVALID=0"


def batch_parse(json_files):
    """
    Parse multiple JSON files in a single invocation.

    Input format: JSON array of objects with 'type' and 'path' keys
    Example: [{"type": "trend", "path": "/tmp/trend.json"}, {"type": "anomaly", "path": "/tmp/anomaly.json"}]
    """
    try:
        results = {}
        for item in json_files:
            type_ = item['type']
            path = item.get('path', '')
            inline = item.get('inline', '')

            if type_ == 'trend':
                result = parse_trend_prediction(inline or path)
            elif type_ == 'anomaly':
                error_count = item.get('error_count', 0)
                result = parse_anomaly_detection(inline or path, error_count)
            elif type_ == 'circuit':
                result = parse_circuit_state(inline or path)
            elif type_ == 'credentials':
                alert_file = item.get('alert_file', '')
                flags_file = item.get('flags_file', '')
                result = parse_credentials(alert_file, flags_file)
            else:
                continue

            # Parse result into dict
            for line in result.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    results[key] = value

        return results
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser(description='Parse watchdog health metrics')
    parser.add_argument('--mode', choices=['single', 'batch'], default='single',
                        help='Parsing mode: single metric or batch')
    parser.add_argument('--type', choices=['trend', 'anomaly', 'circuit', 'credentials'],
                        help='Type of metric to parse')
    parser.add_argument('--input', help='Input JSON string or file path')
    parser.add_argument('--error-count', type=int, default=0,
                        help='Error count for anomaly detection')
    parser.add_argument('--alert-file', help='Credential alerts file path')
    parser.add_argument('--flags-file', help='Credential flags file path')
    parser.add_argument('--batch-input', help='Batch input JSON array')

    args = parser.parse_args()

    if args.mode == 'batch':
        if not args.batch_input:
            print("ERROR: --batch-input required for batch mode", file=sys.stderr)
            sys.exit(1)

        json_files = json.loads(args.batch_input)
        results = batch_parse(json_files)

        # Output as shell variable assignments
        for key, value in results.items():
            print(f"{key}='{value}'")
    else:
        # Single metric mode
        if args.type == 'trend':
            result = parse_trend_prediction(args.input)
        elif args.type == 'anomaly':
            result = parse_anomaly_detection(args.input, args.error_count)
        elif args.type == 'circuit':
            result = parse_circuit_state(args.input)
        elif args.type == 'credentials':
            result = parse_credentials(args.alert_file, args.flags_file)
        else:
            print("ERROR: --type required for single mode", file=sys.stderr)
            sys.exit(1)

        print(result)


if __name__ == '__main__':
    main()
