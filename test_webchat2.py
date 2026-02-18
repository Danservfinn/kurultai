#!/usr/bin/env python3
"""Test webchat WebSocket connection with localStorage clearing."""

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
        ws_urls = []
        def handle_websocket(ws):
            print(f"[WebSocket Created] URL: {ws.url}")
            ws_urls.append(ws.url)

            ws.on("close", lambda: print(f"[WebSocket Closed]"))
            ws.on("error", lambda err: print(f"[WebSocket Error] {err}"))

        page.on("websocket", handle_websocket)

        # Navigate to webchat
        url = "https://moltbot-railway-template-production-c0a3.up.railway.app/webchat"
        print(f"Navigating to: {url}")

        # Clear all storage first
        page.goto(url)
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        print("Cleared localStorage and sessionStorage")

        # Reload to get fresh state
        page.reload(wait_until="networkidle")
        print("Page reloaded after clearing storage")

        # Wait for WebSocket to attempt connection
        page.wait_for_timeout(5000)

        # Take screenshot
        screenshot_path = "/tmp/webchat_test2.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved to: {screenshot_path}")

        # Check localStorage for any saved gateway URL
        local_storage = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        print(f"\nlocalStorage contents: {local_storage}")

        # Check for status
        status_text = ""
        try:
            status_element = page.locator('text=/Disconnected|Connected|Offline|Online/i').first
            if status_element:
                status_text = status_element.text_content()
                print(f"\nStatus indicator: {status_text}")
        except:
            pass

        # Check for any inputs that might contain the gateway URL
        try:
            inputs = page.locator('input').all()
            for inp in inputs:
                placeholder = inp.get_attribute('placeholder') or ''
                value = inp.input_value() or ''
                if 'ws' in placeholder.lower() or 'ws' in value.lower() or 'gateway' in placeholder.lower():
                    print(f"\nGateway input found - placeholder: '{placeholder}', value: '{value}'")
        except Exception as e:
            print(f"Error finding inputs: {e}")

        # Close browser
        browser.close()

        # Report findings
        print("\n" + "="*60)
        print("WEBCHAT TEST RESULTS")
        print("="*60)

        print(f"\nWebSocket URLs attempted: {ws_urls}")

        if ws_urls:
            for ws_url in ws_urls:
                if '/ws' in ws_url:
                    print(f"  ✅ {ws_url} - has /ws path")
                else:
                    print(f"  ❌ {ws_url} - missing /ws path!")

        if status_text:
            print(f"\nStatus: {status_text}")

        # Check console logs for errors
        ws_errors = [log for log in console_logs if "websocket" in log.lower()]
        if ws_errors:
            print(f"\nWebSocket console errors ({len(ws_errors)}):")
            for log in ws_errors[:5]:
                print(f"  {log[:200]}")

        return len(ws_errors) == 0

if __name__ == "__main__":
    success = test_webchat()
    sys.exit(0 if success else 1)
