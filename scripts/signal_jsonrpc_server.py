#!/usr/bin/env python3
"""
Signal JSON-RPC HTTP Server

Wrapper for signal-cli jsonRpc command that provides an HTTP interface.
This replaces the deprecated daemon --http mode.

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

SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
DEFAULT_PORT = int(os.getenv("SIGNAL_HTTP_PORT", "8080"))


class SignalRpcClient:
    """Client for signal-cli jsonRpc subprocess."""

    def __init__(self, account: str):
        self.account = account
        self.process = None
        self.start_rpc()

    def start_rpc(self):
        """Start the signal-cli jsonRpc subprocess."""
        # Use full path for launchd compatibility
        signal_cli = os.path.expanduser("/opt/homebrew/bin/signal-cli")
        if not os.path.exists(signal_cli):
            # Fallback to PATH
            signal_cli = "signal-cli"

        # Use manual receive mode so receive RPC calls work
        cmd = [
            signal_cli,
            "-a", self.account,
            "jsonRpc",
            "--receive-mode", "manual"
        ]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0  # Line buffered
        )

        # Start stderr reader thread
        threading.Thread(target=self._read_stderr, daemon=True).start()

        # Wait for process to be ready
        time.sleep(2)

    def _read_stderr(self):
        """Read stderr from signal-cli process."""
        for line in self.process.stderr:
            line = line.strip()
            if line:
                print(f"[signal-cli stderr] {line}", file=sys.stderr)

    def call(self, method: str, params: dict = None) -> dict:
        """Make a JSON-RPC call to signal-cli."""
        if self.process.poll() is not None:
            # Process died, restart it
            print("[signal-cli] Process died, restarting...", file=sys.stderr)
            self.start_rpc()

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }

        request_line = json.dumps(request) + "\n"

        try:
            # Send request
            self.process.stdin.write(request_line)
            self.process.stdin.flush()

            # Read response
            response_line = self.process.stdout.readline()

            if not response_line:
                return {"error": "No response from signal-cli"}

            response = json.loads(response_line.strip())

            if "error" in response:
                return {"error": response["error"]}

            return response.get("result", {})

        except Exception as e:
            return {"error": str(e)}

    def close(self):
        """Close the signal-cli process."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)


class JsonRpcHandler(BaseHTTPRequestHandler):
    """HTTP handler that proxies requests to signal-cli jsonRpc."""

    rpc_client: SignalRpcClient = None

    def _set_headers(self, status_code=200, content_type="application/json"):
        """Set response headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        elif self.path == "/":
            self._set_headers()
            self.wfile.write(json.dumps({
                "service": "signal-jsonrpc",
                "account": SIGNAL_ACCOUNT
            }).encode())
        else:
            self._set_headers(404)
            self.wfile.write(b"Not found")

    def do_POST(self):
        """Handle POST requests - JSON-RPC API."""
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

                result = self.rpc_client.call(method, params)

                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "result": result
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
        """Suppress default logging."""
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server."""
    daemon_threads = True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Signal JSON-RPC HTTP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="HTTP port (default: 8080)")
    parser.add_argument("--account", type=str, default=SIGNAL_ACCOUNT,
                        help="Signal account")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="HTTP host (default: 127.0.0.1)")
    args = parser.parse_args()

    print(f"[signal-jsonrpc] Starting server on {args.host}:{args.port}")
    print(f"[signal-jsonrpc] Using account: {args.account}")

    # Create RPC client
    rpc_client = SignalRpcClient(args.account)
    JsonRpcHandler.rpc_client = rpc_client

    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"[signal-jsonrpc] Shutting down...")
        rpc_client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start HTTP server
    server = ThreadedHTTPServer((args.host, args.port), JsonRpcHandler)

    print(f"[signal-jsonrpc] Server ready at http://{args.host}:{args.port}")
    print(f"[signal-jsonrpc] JSON-RPC endpoint: http://{args.host}:{args.port}/api/v1/rpc")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        rpc_client.close()


if __name__ == "__main__":
    main()
