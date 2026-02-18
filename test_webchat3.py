#!/usr/bin/env python3
"""Test webchat WebSocket connection with correct localStorage URL."""

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
        page.goto(url)

        # Set correct gateway URL in localStorage
        correct_url = "wss://moltbot-railway-template-production-c0a3.up.railway.app/ws"
        page.evaluate(f"""() => {{
            const settings = JSON.parse(localStorage.getItem('openclaw.control.settings.v1') || '{{}}');
            settings.gatewayUrl = '{correct_url}';
            localStorage.setItem('openclaw.control.settings.v1', JSON.stringify(settings));
            console.log('Set gatewayUrl to: ' + settings.gatewayUrl);
        }}""")
        print(f"Set correct gateway URL in localStorage: {correct_url}")

        # Reload to apply new settings
        page.reload(wait_until="networkidle")
        print("Page reloaded with correct settings")

        # Wait for WebSocket to attempt connection
        page.wait_for_timeout(5000)

        # Take screenshot
        screenshot_path = "/tmp/webchat_test3.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved to: {screenshot_path}")

        # Check localStorage
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

        # Close browser
        browser.close()

        # Report findings
        print("\n" + "="*60)
        print("WEBCHAT TEST RESULTS")
        print("="*60)

        print(f"\nWebSocket URLs attempted: {ws_urls}")

        all_have_ws = all('/ws' in url for url in ws_urls) if ws_urls else False

        if ws_urls:
            for ws_url in ws_urls:
                if '/ws' in ws_url:
                    print(f"  ✅ {ws_url} - has /ws path")
                else:
                    print(f"  ❌ {ws_url} - missing /ws path!")

        if status_text:
            print(f"\nStatus: {status_text}")
            if "connected" in status_text.lower() or "online" in status_text.lower():
                print("✅ Webchat shows connected status")
            elif "disconnected" in status_text.lower() or "offline" in status_text.lower():
                print("❌ Webchat shows disconnected status")

        # Check console logs for success
        success_logs = [log for log in console_logs if "hello" in log.lower() or "connected" in log.lower()]
        error_logs = [log for log in console_logs if "error" in log.lower() and "websocket" in log.lower()]

        if error_logs:
            print(f"\n❌ WebSocket errors found: {len(error_logs)}")
            for log in error_logs[:3]:
                print(f"  {log[:200]}")

        if all_have_ws and not error_logs:
            print("\n✅ SUCCESS: WebSocket URLs are correct and no errors!")
            return True
        else:
            print("\n❌ FAILURE: WebSocket URLs incorrect or errors present")
            return False

if __name__ == "__main__":
    success = test_webchat()
    sys.exit(0 if success else 1)
