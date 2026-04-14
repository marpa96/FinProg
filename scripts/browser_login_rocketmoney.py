"""Browser-backed Rocket Money login helper.

Raw HTTP login is fragile with Auth0/Akamai. This script uses a real browser
profile, lets Rocket Money run its normal auth flow, and writes the resulting
GraphQL cookie header back to .env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.local_env import load_env_file, update_env_file


DEFAULT_PROFILE_DIR = Path("data/private/rocketmoney_browser_profile")
DEFAULT_COOKIE_OUTPUT = Path("data/private/rocketmoney_browser_cookie.txt")
DEFAULT_LOGIN_URL = "https://app.rocketmoney.com/"
GRAPHQL_ORIGIN = "https://client-api.rocketmoney.com"


def cookie_header_from_playwright_cookies(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies if cookie.get("name") and cookie.get("value"))


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required for browser login. Install it with:\n"
            "python -m pip install playwright\n"
            "python -m playwright install chromium"
        ) from exc
    return sync_playwright


def fill_if_present(page, selector: str, value: str) -> None:
    locator = page.locator(selector)
    if locator.count() > 0:
        locator.first.fill(value)


def click_first_present(page, selectors: list[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            locator.first.click()
            return True
    return False


def maybe_autofill_login(page) -> None:
    username = os.environ.get("ROCKETMONEY_USERNAME")
    password = os.environ.get("ROCKETMONEY_PASSWORD")
    if not username or not password:
        return

    fill_if_present(page, 'input[name="username"]', username)
    fill_if_present(page, 'input[name="email"]', username)
    fill_if_present(page, 'input[type="email"]', username)
    fill_if_present(page, 'input[name="password"]', password)
    fill_if_present(page, 'input[type="password"]', password)
    click_first_present(
        page,
        [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
        ],
    )


def refresh_cookie_with_browser(
    env_path: Path,
    profile_dir: Path,
    output_path: Path,
    login_url: str,
    timeout_seconds: int,
    headless: bool,
) -> str:
    sync_playwright = require_playwright()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        maybe_autofill_login(page)

        print("Browser login opened. Complete any MFA/CAPTCHA/login prompts if they appear.")
        print("Waiting for an authenticated Rocket Money session...")
        page.wait_for_url("**app.rocketmoney.com/**", timeout=timeout_seconds * 1000)
        page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000)

        cookies = context.cookies([GRAPHQL_ORIGIN, "https://app.rocketmoney.com"])
        cookie_header = cookie_header_from_playwright_cookies(cookies)
        if not cookie_header:
            context.close()
            raise RuntimeError("No Rocket Money cookies were available after browser login.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(cookie_header + "\n", encoding="utf-8")
        update_env_file(env_path, {"ROCKETMONEY_COOKIE": cookie_header})
        context.close()
        return cookie_header


def main() -> int:
    env_path = ROOT / ".env"
    load_env_file(env_path)

    parser = argparse.ArgumentParser(description="Refresh Rocket Money cookies using a real browser session.")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_COOKIE_OUTPUT)
    parser.add_argument("--login-url", default=os.environ.get("ROCKETMONEY_LOGIN_START_URL") or DEFAULT_LOGIN_URL)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Not recommended for first login.")
    args = parser.parse_args()

    cookie_header = refresh_cookie_with_browser(
        env_path=env_path,
        profile_dir=args.profile_dir,
        output_path=args.output,
        login_url=args.login_url,
        timeout_seconds=args.timeout,
        headless=args.headless,
    )
    print(f"Wrote browser cookie header with {len(cookie_header.split(';'))} cookie(s) to {args.output}")
    print("Updated ROCKETMONEY_COOKIE in .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
