#!/usr/bin/env python3
"""Test webchat WebSocket connection with device identity."""

from playwright.sync_api import sync_playwright
import sys

def test_webchat():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )
        page = context.new_page()

        # Capture console logs
        console_logs = []
        def handle_console(msg):
            log_text = f"[{msg.type}] {msg.text}"
            console_logs.append(log_text)
            print(log_text[:300])

        page.on("console", handle_console)

        # Capture WebSocket traffic
        ws_events = []
        def handle_websocket(ws):
            print(f"[WebSocket Created] URL: {ws.url}")
            ws_events.append({"type": "created", "url": ws.url})

            def handle_receive(msg):
                print(f"[WebSocket Receive] {msg[:200]}")
                ws_events.append({"type": "receive", "data": msg[:100]})

            def handle_send(msg):
                print(f"[WebSocket Send] {msg[:200]}")
                ws_events.append({"type": "send", "data": msg[:100]})

            ws.on("framereceived", handle_receive)
            ws.on("framesent", handle_send)
            ws.on("close", lambda: print(f"[WebSocket Closed]"))
            ws.on("error", lambda err: print(f"[WebSocket Error] {err}"))

        page.on("websocket", handle_websocket)

        # Navigate to webchat
        url = "https://moltbot-railway-template-production-c0a3.up.railway.app/webchat"
        print(f"Navigating to: {url}")
        page.goto(url)

        # Set correct gateway URL in localStorage and clear any old device identity
        correct_url = "wss://moltbot-railway-template-production-c0a3.up.railway.app/ws"
        page.evaluate(f"""() => {{
            // Clear device identity to force regeneration
            localStorage.removeItem('openclaw-device-identity-v1');

            // Set correct gateway URL
            const settings = JSON.parse(localStorage.getItem('openclaw.control.settings.v1') || '{{}}');
            settings.gatewayUrl = '{correct_url}';
            localStorage.setItem('openclaw.control.settings.v1', JSON.stringify(settings));
            console.log('Cleared device identity and set gatewayUrl to: ' + settings.gatewayUrl);
        }}""")
        print(f"Cleared device identity and set correct gateway URL")

        # Reload to apply new settings
        page.reload(wait_until="networkidle")
        print("Page reloaded with fresh settings")

        # Wait for WebSocket to attempt connection
        page.wait_for_timeout(8000)

        # Check localStorage for device identity
        local_storage = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        print(f"\nlocalStorage contents:")
        for key, value in local_storage.items():
            print(f"  {key}: {value[:200]}...")

        # Take screenshot
        screenshot_path = "/tmp/webchat_test_identity.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nScreenshot saved to: {screenshot_path}")

        # Close browser
        browser.close()

        # Report findings
        print("\n" + "="*60)
        print("WEBCHAT TEST RESULTS")
        print("="*60)

        # Check for WebSocket events
        ws_errors = [e for e in ws_events if e.get("type") == "receive" and "error" in e.get("data", "").lower()]
        ws_closes = [e for e in ws_events if e.get("type") == "created"]

        print(f"\nWebSocket connections attempted: {len(ws_closes)}")
        for event in ws_events[:10]:
            if event["type"] == "created":
                print(f"  - {event['url']}")

        # Check for error messages in console
        errors = [log for log in console_logs if "error" in log.lower()]
        if errors:
            print(f"\nErrors found ({len(errors)}):")
            for log in errors[:5]:
                print(f"  {log[:200]}")

        # Check for success indicators
        hello_msgs = [log for log in console_logs if "hello" in log.lower()]
        if hello_msgs:
            print(f"\n✅ Hello messages found: {len(hello_msgs)}")

        return True

if __name__ == "__main__":
    success = test_webchat()
    sys.exit(0 if success else 1)
