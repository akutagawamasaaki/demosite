import contextlib
import socket
import subprocess
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]


def get_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


class LoginStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = get_free_port()
        cls.server = subprocess.Popen(
            ["python3", "-m", "http.server", str(cls.port), "--bind", "127.0.0.1"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=10)

    def test_login_state_persists_across_pages(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(3000)
            page.goto(f"http://127.0.0.1:{self.port}/index.html", wait_until="domcontentloaded")

            initial_page_view = page.evaluate(
                "() => window.adobeDataLayer.find((entry) => entry.event === 'demo.pageView')"
            )
            self.assertEqual(initial_page_view["_acssandboxgdctwo"]["account"]["status"], "logged_out")
            self.assertNotIn("displayName", initial_page_view["_acssandboxgdctwo"]["account"])
            initial_account_event = self.wait_for_edge_event(page, "demo.accountStateView", page_name="home")
            self.assertEqual(initial_account_event["important"]["accountStatus"], "logged_out")
            self.assertIsNone(initial_account_event["important"]["accountDisplayName"])

            page.get_by_role("button", name="Log in").click()
            page.get_by_label("Email").fill("   ")
            page.get_by_role("button", name="Submit").click()
            self.assertTrue(page.get_by_text("Enter an email address.").is_visible())

            page.get_by_label("Email").fill("invalid")
            page.get_by_role("button", name="Submit").click()
            self.assertTrue(page.get_by_text("Enter a valid email address.").is_visible())

            page.get_by_label("Email").fill("taro.yamada@example.com")
            page.get_by_role("button", name="Submit").click()

            self.assertTrue(page.get_by_text("Hello, taro.yamada@example.com").is_visible())
            login_event = page.evaluate("() => window.adobeDataLayer[window.adobeDataLayer.length - 1]")
            self.assertEqual(login_event["event"], "login_success")
            self.assertEqual(login_event["_acssandboxgdctwo"]["account"]["status"], "logged_in")
            self.assertEqual(login_event["_acssandboxgdctwo"]["account"]["displayName"], "taro.yamada@example.com")
            login_edge_event = self.wait_for_edge_event(page, "demo.loginSuccess", page_name="home")
            self.assertEqual(login_edge_event["important"]["accountStatus"], "logged_in")
            self.assertEqual(login_edge_event["important"]["accountDisplayName"], "taro.yamada@example.com")
            self.assertIn("Email: taro.yamada@example.com", login_edge_event["important"]["identityMap"])

            page.goto(f"http://127.0.0.1:{self.port}/product-a.html", wait_until="domcontentloaded")
            self.assertTrue(page.get_by_text("Hello, taro.yamada@example.com").is_visible())
            logged_in_page_view = page.evaluate(
                "() => window.adobeDataLayer.find((entry) => entry.event === 'demo.pageView')"
            )
            self.assertEqual(logged_in_page_view["_acssandboxgdctwo"]["account"]["status"], "logged_in")
            self.assertEqual(logged_in_page_view["_acssandboxgdctwo"]["account"]["displayName"], "taro.yamada@example.com")
            logged_in_account_event = self.wait_for_edge_event(page, "demo.accountStateView", page_name="product-a")
            self.assertEqual(logged_in_account_event["important"]["accountStatus"], "logged_in")
            self.assertEqual(logged_in_account_event["important"]["accountDisplayName"], "taro.yamada@example.com")
            self.assertIn("Email: taro.yamada@example.com", logged_in_account_event["important"]["identityMap"])

            page.reload(wait_until="domcontentloaded")
            self.assertTrue(page.get_by_text("Hello, taro.yamada@example.com").is_visible())

            page.get_by_role("button", name="Log out").click()
            logout_event = page.evaluate("() => window.adobeDataLayer[window.adobeDataLayer.length - 1]")
            self.assertEqual(logout_event["event"], "logout")
            self.assertEqual(logout_event["_acssandboxgdctwo"]["account"]["status"], "logged_out")
            self.assertNotIn("displayName", logout_event["_acssandboxgdctwo"]["account"])
            logout_edge_event = self.wait_for_edge_event(page, "demo.logout", page_name="product-a")
            self.assertEqual(logout_edge_event["important"]["accountStatus"], "logged_out")
            self.assertIsNone(logout_edge_event["important"]["accountDisplayName"])
            self.assertIn("Email: taro.yamada@example.com", logout_edge_event["important"]["identityMap"])
            self.assertTrue(page.get_by_role("button", name="Log in").is_visible())

            browser.close()

    def test_home_dev_tools_row_is_above_hero_and_compact(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.set_default_timeout(3000)
            page.goto(f"http://127.0.0.1:{self.port}/index.html", wait_until="domcontentloaded")

            layout = page.evaluate(
                """() => {
                    const hero = document.querySelector('.hero');
                    const toolsHeading = Array.from(document.querySelectorAll('h2')).find((node) => node.textContent.trim() === 'Dev Tools');
                    const toolLinks = Array.from(document.querySelectorAll('.tool-link'));
                    return {
                      heroTop: hero.getBoundingClientRect().top,
                      toolsTop: toolsHeading.getBoundingClientRect().top,
                      toolWidths: toolLinks.map((node) => Math.round(node.getBoundingClientRect().width)),
                      toolTops: toolLinks.map((node) => Math.round(node.getBoundingClientRect().top))
                    };
                }"""
            )

            self.assertLess(layout["toolsTop"], layout["heroTop"])
            self.assertTrue(all(width < 140 for width in layout["toolWidths"]))
            self.assertEqual(len(set(layout["toolTops"])), 1)

            browser.close()

    def test_dev_tools_row_appears_above_hero_on_all_pages(self):
        pages = [
            "index.html",
            "product-a.html",
            "product-b.html",
            "product-c.html",
            "order1.html",
            "order2.html",
        ]

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.set_default_timeout(3000)

            for page_path in pages:
                page.goto(f"http://127.0.0.1:{self.port}/{page_path}", wait_until="domcontentloaded")
                layout = page.evaluate(
                    """() => {
                        const hero = document.querySelector('.hero');
                        const toolsHeading = Array.from(document.querySelectorAll('h2')).find((node) => node.textContent.trim() === 'Dev Tools');
                        const toolLinks = Array.from(document.querySelectorAll('.tool-link')).map((node) => node.textContent.trim());
                        return {
                          hasTools: Boolean(toolsHeading),
                          heroTop: hero ? hero.getBoundingClientRect().top : null,
                          toolsTop: toolsHeading ? toolsHeading.getBoundingClientRect().top : null,
                          toolLinks
                        };
                    }"""
                )

                self.assertTrue(layout["hasTools"], page_path)
                self.assertLess(layout["toolsTop"], layout["heroTop"], page_path)
                self.assertIn("Connection", layout["toolLinks"], page_path)
                self.assertIn("AT", layout["toolLinks"], page_path)
                self.assertEqual(len(layout["toolLinks"]), 8, page_path)

            browser.close()

    def wait_for_edge_event(self, page, event_type, page_name=None):
        deadline = time.time() + 8
        while time.time() < deadline:
            entries = page.evaluate("() => JSON.parse(window.localStorage.getItem('adobeEdgeDebugHistory') || '[]')")
            for entry in entries:
                important = entry.get("important", {})
                if important.get("eventType") != event_type:
                    continue
                if page_name is not None and important.get("pageName") != page_name:
                    continue
                return entry
            page.wait_for_timeout(250)

        self.fail(f"Adobe Edge event not found: {event_type}")


if __name__ == "__main__":
    unittest.main()
