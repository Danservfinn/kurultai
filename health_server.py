#!/usr/bin/env python3
"""Simple health check server for agent configuration container."""

import http.server
import socketserver
import json
from datetime import datetime

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                'status': 'healthy',
                'service': 'openclaw-agent-config',
                'timestamp': datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logs

if __name__ == '__main__':
    PORT = 18789
    with socketserver.TCPServer(('', PORT), HealthHandler) as httpd:
        print(f'Agent configuration container running on port {PORT}')
        print('Health check available at /health')
        httpd.serve_forever()
