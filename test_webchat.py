#!/usr/bin/env python3
"""Test webchat WebSocket connection and verify the fix."""
from __future__ import annotations

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
            console_logs.append(f"[{msg.type}] {msg.text}")
            print(f"[Console {msg.type}] {msg.text[:200]}")

        page.on("console", handle_console)

        # Capture WebSocket traffic
        ws_messages = []
        def handle_websocket(ws):
            print(f"[WebSocket] URL: {ws.url}")
            ws_messages.append(f"WebSocket created: {ws.url}")

            def handle_receive(msg):
                print(f"[WebSocket Receive] {msg[:200] if len(msg) > 200 else msg}")
                ws_messages.append(f"Receive: {msg[:100]}")

            def handle_send(msg):
                print(f"[WebSocket Send] {msg[:200] if len(msg) > 200 else msg}")
                ws_messages.append(f"Send: {msg[:100]}")

            ws.on("framereceived", handle_receive)
            ws.on("framesent", handle_send)
            ws.on("close", lambda: print(f"[WebSocket] Closed"))
            ws.on("error", lambda err: print(f"[WebSocket] Error: {err}"))

        page.on("websocket", handle_websocket)

        # Navigate to webchat with hard reload (clear cache)
        url = "https://moltbot-railway-template-production-c0a3.up.railway.app/webchat"
        print(f"Navigating to: {url}")

        # Clear cache first by using a new context or clearing storage
        context.clear_cookies()

        # Navigate and wait for network idle
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait a bit more for WebSocket to attempt connection
        page.wait_for_timeout(5000)

        # Take screenshot
        screenshot_path = "/tmp/webchat_test.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved to: {screenshot_path}")

        # Get page content
        content = page.content()

        # Check for specific elements
        status_text = ""
        try:
            status_element = page.locator('text=/Disconnected|Connected|Offline|Online/i').first
            if status_element:
                status_text = status_element.text_content()
                print(f"Status indicator found: {status_text}")
        except:
            pass

        # Check the gateway URL input field
        gateway_url = ""
        try:
            # Look for input that might contain the gateway URL
            inputs = page.locator('input').all()
            for inp in inputs:
                val = inp.input_value()
                if 'ws://' in val or 'wss://' in val:
                    gateway_url = val
                    print(f"Gateway URL input found: {gateway_url}")
                    break
        except Exception as e:
            print(f"Error finding gateway URL: {e}")

        # Close browser
        browser.close()

        # Report findings
        print("\n" + "="*60)
        print("WEBCHAT TEST RESULTS")
        print("="*60)

        if gateway_url:
            print(f"Gateway URL in UI: {gateway_url}")
            if "moltbot-railway-template-production" in gateway_url:
                print("✅ Gateway URL correctly shows Railway URL")
            else:
                print("❌ Gateway URL does not show Railway URL")
        else:
            print("⚠️  Could not find gateway URL input")

        if status_text:
            print(f"Status: {status_text}")
            if "connected" in status_text.lower() or "online" in status_text.lower():
                print("✅ Webchat shows connected/online status")
            elif "disconnected" in status_text.lower() or "offline" in status_text.lower():
                print("❌ Webchat shows disconnected/offline status")

        # Check console logs for WebSocket errors
        ws_errors = [log for log in console_logs if "websocket" in log.lower() or "ws" in log.lower()]
        if ws_errors:
            print(f"\nWebSocket-related console logs ({len(ws_errors)} found):")
            for log in ws_errors[:10]:
                print(f"  {log}")
        else:
            print("\nNo WebSocket errors in console logs")

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)

        success = True
        if gateway_url and "moltbot-railway-template-production" in gateway_url:
            print("✅ WebSocket URL is correctly configured")
        else:
            print("❌ WebSocket URL may not be correctly configured")
            success = False

        if ws_errors and any("error" in log.lower() for log in ws_errors):
            print("❌ WebSocket connection errors detected")
            success = False
        else:
            print("✅ No WebSocket errors detected")

        return success

if __name__ == "__main__":
    success = test_webchat()
    sys.exit(0 if success else 1)
