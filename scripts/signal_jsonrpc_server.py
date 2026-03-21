#!/usr/bin/env python3
"""
Signal JSON-RPC HTTP Server — Event-driven message processing.

Uses signal-cli jsonRpc with --receive-mode on-connection so messages
are pushed immediately (no polling). A background thread reads incoming
messages from signal-cli stdout and dispatches them to handlers.

The HTTP API is preserved for outbound calls (send, listGroups, etc.)
and health checks.

Usage:
    python3 signal_jsonrpc_server.py [--port 8080] [--account +15165643945]
"""

import argparse
import json
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import os
import signal
import time
import traceback
from collections import deque
from datetime import datetime

SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
DEFAULT_PORT = int(os.getenv("SIGNAL_HTTP_PORT", "8080"))
# Group allowlist: comma-separated group IDs. Empty = accept all groups.
_RAW_ALLOWLIST = os.getenv("SIGNAL_GROUP_ALLOWLIST", "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=")
GROUP_ALLOWLIST = set(g.strip() for g in _RAW_ALLOWLIST.split(",") if g.strip())
LOG_FILE = os.path.expanduser("~/.openclaw/logs/signal_jsonrpc_server.log")

# Known group members
GROUP_MEMBERS = {
    "+19194133445": "Danny",
    "+16624580725": "Liz",
}

# Recent messages ring buffer (for /api/v1/recent endpoint)
_recent_messages = deque(maxlen=50)
_stats = {"received": 0, "processed": 0, "errors": 0, "started_at": None}

# Exposed for direct access by signal_message_handler (avoids HTTP self-deadlock)
_active_rpc_client = None


def log(message: str, level: str = "INFO"):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.now().isoformat()
    line = f"[{ts}] [{level}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line.strip(), file=sys.stderr if level == "ERROR" else sys.stdout)


# ============================================================================
# Signal-cli RPC Client (event-driven)
# ============================================================================

class SignalRpcClient:
    """Client for signal-cli jsonRpc subprocess in on-connection mode.

    In on-connection mode, signal-cli pushes incoming messages as
    JSON-RPC notifications (no id field) on stdout. Outbound RPC calls
    (send, listGroups) use the normal request/response pattern with an id.
    """

    def __init__(self, account: str, on_message=None):
        self.account = account
        self.process = None
        self.on_message = on_message  # callback(envelope_dict)
        self._lock = threading.Lock()
        self._pending = {}  # id -> threading.Event + result
        self._next_id = 1
        self.start_rpc()

    def start_rpc(self):
        """Start signal-cli in on-connection receive mode."""
        signal_cli = "/opt/homebrew/bin/signal-cli"
        if not os.path.exists(signal_cli):
            signal_cli = "signal-cli"

        cmd = [
            signal_cli,
            "-a", self.account,
            "jsonRpc",
            "--receive-mode", "on-connection",
        ]

        log(f"Starting signal-cli: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line buffered
        )

        # Background thread: read stdout for both pushed messages and RPC responses
        threading.Thread(target=self._read_stdout, daemon=True, name="signal-stdout").start()
        threading.Thread(target=self._read_stderr, daemon=True, name="signal-stderr").start()

        time.sleep(2)
        log("signal-cli started (on-connection mode)")

    def _read_stdout(self):
        """Read all lines from signal-cli stdout.

        Lines with 'id' are RPC responses to our calls.
        Lines without 'id' (method='receive') are pushed incoming messages.
        Auto-restarts signal-cli if stdout closes unexpectedly.
        """
        while True:
            try:
                for line in self.process.stdout:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        log(f"Non-JSON from signal-cli: {line[:200]}", "WARNING")
                        continue

                    msg_id = data.get("id")

                    if msg_id is not None:
                        with self._lock:
                            if msg_id in self._pending:
                                entry = self._pending[msg_id]
                                entry["result"] = data
                                entry["event"].set()
                    else:
                        self._handle_pushed_message(data)

                log("signal-cli stdout closed — restarting in 5s...", "WARNING")
            except Exception as e:
                log(f"stdout reader error: {e} — restarting in 5s...", "ERROR")

            # Auto-restart signal-cli after crash
            time.sleep(5)
            try:
                self.start_rpc()
                log("signal-cli restarted successfully")
            except Exception as e:
                log(f"signal-cli restart failed: {e} — retrying in 30s...", "ERROR")
                time.sleep(30)

    def _handle_pushed_message(self, data: dict):
        """Handle a pushed message from signal-cli."""
        _stats["received"] += 1

        # Extract the envelope
        method = data.get("method", "")
        params = data.get("params", {})

        if method != "receive":
            return

        envelope = params.get("envelope", params)
        if not envelope:
            return

        # Store in recent buffer
        _recent_messages.append({
            "timestamp": datetime.now().isoformat(),
            "envelope": envelope,
        })

        # Dispatch to handler
        if self.on_message:
            try:
                self.on_message(envelope)
                _stats["processed"] += 1
            except Exception as e:
                _stats["errors"] += 1
                log(f"Message handler error: {e}\n{traceback.format_exc()}", "ERROR")

    def _read_stderr(self):
        for line in self.process.stderr:
            line = line.strip()
            if line:
                log(f"[signal-cli] {line}", "DEBUG")

    def call(self, method: str, params: dict = None) -> dict:
        """Make a synchronous RPC call to signal-cli (for outbound operations)."""
        if self.process.poll() is not None:
            log("signal-cli died, restarting...", "WARNING")
            self.start_rpc()

        with self._lock:
            call_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            self._pending[call_id] = {"event": event, "result": None}

        request = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": method,
            "params": params or {},
        }

        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()

            # Wait for response (timeout 30s)
            if not event.wait(timeout=30):
                with self._lock:
                    self._pending.pop(call_id, None)
                return {"error": "RPC call timed out"}

            with self._lock:
                entry = self._pending.pop(call_id, {})
                result = entry.get("result", {})

            if "error" in result:
                return {"error": result["error"]}
            return result.get("result", {})

        except Exception as e:
            with self._lock:
                self._pending.pop(call_id, None)
            return {"error": str(e)}

    def close(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


# ============================================================================
# Message Handler — processes incoming Signal messages
# ============================================================================

def handle_incoming_message(envelope: dict):
    """Process an incoming Signal message envelope.

    This is called in real-time as messages arrive (no polling delay).
    """
    sender = envelope.get("source") or envelope.get("sourceNumber", "")
    if not sender:
        s = envelope.get("sender", {})
        sender = s.get("number", "") if isinstance(s, dict) else ""

    data_message = envelope.get("dataMessage", {})
    if not data_message:
        return

    message_text = data_message.get("message", "")
    group_info = data_message.get("groupInfo", {})
    group_id = group_info.get("groupId", "")

    # Skip messages from non-allowlisted groups
    if group_id and GROUP_ALLOWLIST and group_id not in GROUP_ALLOWLIST:
        return

    if not message_text:
        return

    sender_name = GROUP_MEMBERS.get(sender, sender)
    is_dm = not group_id  # Empty group_id = direct message

    log(f"Message from {sender_name} ({'DM' if is_dm else 'group'}): {message_text[:80]}")

    # Build the raw_msg dict expected by the processing pipeline
    raw_msg = {
        "message": message_text,
        "sender": sender,
        "sender_name": sender_name,
        "group_id": group_id if group_id else None,  # None = DM
        "is_dm": is_dm,
        "timestamp": datetime.now(),
        "message_id": envelope.get("timestamp"),
    }

    # Dispatch to processing pipeline in a separate thread
    # (prevents blocking the stdout reader while LLM generates a response)
    def _process():
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from signal_message_handler import process_message
            process_message(raw_msg)
        except Exception as e:
            log(f"Processing pipeline error: {e}\n{traceback.format_exc()}", "ERROR")

    threading.Thread(target=_process, daemon=True, name=f"msg-{sender[:8]}").start()


# ============================================================================
# HTTP API (outbound calls + health)
# ============================================================================

class JsonRpcHandler(BaseHTTPRequestHandler):
    rpc_client: SignalRpcClient = None

    def _set_headers(self, status_code=200, content_type="application/json"):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._set_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "mode": "event-driven",
                "stats": _stats,
            }).encode())
        elif self.path == "/api/v1/recent":
            self._set_headers()
            self.wfile.write(json.dumps({
                "messages": list(_recent_messages),
                "count": len(_recent_messages),
            }).encode())
        elif self.path == "/":
            self._set_headers()
            self.wfile.write(json.dumps({
                "service": "signal-jsonrpc",
                "mode": "event-driven (on-connection)",
                "account": SIGNAL_ACCOUNT,
                "stats": _stats,
            }).encode())
        else:
            self._set_headers(404)
            self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path.startswith("/api/v1/rpc"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                request = json.loads(body.decode("utf-8"))

                method = request.get("method")
                params = request.get("params", {})

                if not method:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Missing method"}).encode())
                    return

                # For 'receive' calls in event-driven mode, return recent messages
                if method == "receive":
                    self._set_headers()
                    self.wfile.write(json.dumps({
                        "jsonrpc": "2.0",
                        "id": request.get("id", 1),
                        "result": list(_recent_messages),
                    }).encode())
                    return

                result = self.rpc_client.call(method, params)

                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "result": result,
                }

                self._set_headers()
                self.wfile.write(json.dumps(response).encode())

            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Signal JSON-RPC Server (event-driven)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--account", type=str, default=SIGNAL_ACCOUNT)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    _stats["started_at"] = datetime.now().isoformat()

    log(f"Starting event-driven server on {args.host}:{args.port}")
    log(f"Account: {args.account}")

    # Create RPC client with message handler
    rpc_client = SignalRpcClient(args.account, on_message=handle_incoming_message)
    JsonRpcHandler.rpc_client = rpc_client

    # Expose RPC client for direct access by signal_message_handler
    # (avoids HTTP self-deadlock when handler needs to send responses)
    global _active_rpc_client
    _active_rpc_client = rpc_client

    def signal_handler(signum, frame):
        log("Shutting down...")
        rpc_client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server = ThreadedHTTPServer((args.host, args.port), JsonRpcHandler)
    log(f"Server ready — messages will be processed instantly on arrival")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        rpc_client.close()


if __name__ == "__main__":
    main()
