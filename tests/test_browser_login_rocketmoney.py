import unittest

from scripts.browser_login_rocketmoney import cookie_header_from_playwright_cookies


class BrowserLoginRocketMoneyTests(unittest.TestCase):
    def test_cookie_header_from_playwright_cookies(self) -> None:
        cookies = [
            {"name": "a", "value": "one"},
            {"name": "b", "value": "two"},
            {"name": "", "value": "ignored"},
        ]

        self.assertEqual(cookie_header_from_playwright_cookies(cookies), "a=one; b=two")


if __name__ == "__main__":
    unittest.main()
