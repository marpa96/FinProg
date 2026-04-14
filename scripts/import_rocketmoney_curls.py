"""Import useful Rocket Money/Auth0 values from browser-copied cURL commands.

Paste cURLs into a private ignored file, then run this script to update .env.
The script stores secrets only in .env and prints key names, not values.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib import parse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.local_env import update_env_file


DEFAULT_INPUT = Path("data/private/rocketmoney_login_curls.txt")
DEFAULT_ENV = ROOT / ".env"


def normalize_windows_curl(text: str) -> str:
    text = text.replace("^\r\n", " ").replace("^\n", " ")
    replacements = {
        '^"': '"',
        "^&": "&",
        "^%": "%",
        "^?": "?",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def extract_quoted_after(text: str, marker: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(marker)}\s+\"([^\"]*)\"", re.IGNORECASE)
    return pattern.findall(text)


def extract_first_url(text: str) -> str | None:
    match = re.search(r"curl(?:\.exe)?\s+\"([^\"]+)\"", text, re.IGNORECASE)
    return match.group(1) if match else None


def parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in extract_quoted_after(text, "-H"):
        name, separator, value = header.partition(":")
        if separator and name.strip():
            headers[name.strip().lower()] = value.strip()
    return headers


def parse_data_raw(text: str) -> dict[str, str]:
    values = extract_quoted_after(text, "--data-raw")
    if not values:
        return {}
    parsed = parse.parse_qs(values[-1], keep_blank_values=True)
    return {key: parsed_values[-1] for key, parsed_values in parsed.items() if parsed_values}


def split_curl_blocks(text: str) -> list[str]:
    normalized = normalize_windows_curl(text)
    parts = re.split(r"(?=curl(?:\.exe)?\s+\")", normalized, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def collect_updates(curl_text: str) -> dict[str, str]:
    updates: dict[str, str] = {}

    for block in split_curl_blocks(curl_text):
        url = extract_first_url(block)
        headers = parse_headers(block)
        data = parse_data_raw(block)

        user_agent = headers.get("user-agent")
        if user_agent:
            updates["ROCKETMONEY_USER_AGENT"] = user_agent

        if url and "auth.rocketaccount.com/u/login" in url:
            updates["ROCKETMONEY_AUTH_LOGIN_URL"] = url
            state = data.get("state") or parse.parse_qs(parse.urlparse(url).query).get("state", [""])[0]
            if state:
                updates["ROCKETMONEY_AUTH_STATE"] = state
            if headers.get("cookie"):
                updates["ROCKETMONEY_AUTH_COOKIE"] = headers["cookie"]
            if data.get("ulp-anonymous-id"):
                updates["ROCKETMONEY_ULP_ANONYMOUS_ID"] = data["ulp-anonymous-id"]
            if data.get("acul-sdk"):
                updates["ROCKETMONEY_ACUL_SDK"] = data["acul-sdk"]
            if data.get("username"):
                updates["ROCKETMONEY_USERNAME"] = data["username"]
            if data.get("password"):
                updates["ROCKETMONEY_PASSWORD"] = data["password"]

        if url and "client-api.rocketmoney.com/graphql" in url:
            if headers.get("cookie"):
                updates["ROCKETMONEY_COOKIE"] = headers["cookie"]
            if headers.get("x-truebill-web-client-version"):
                updates["ROCKETMONEY_TRUEBILL_WEB_CLIENT_VERSION"] = headers["x-truebill-web-client-version"]
            if headers.get("x-analytics-session"):
                updates["ROCKETMONEY_ANALYTICS_SESSION"] = headers["x-analytics-session"]

    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Rocket Money cURL capture values into .env.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    updates = collect_updates(args.input.read_text(encoding="utf-8"))
    if not updates:
        raise SystemExit("No supported Rocket Money/Auth0 values found in cURL capture.")

    update_env_file(args.env, updates)
    print(f"Updated {len(updates)} .env value(s):")
    for key in sorted(updates):
        print(f"- {key}")
    if "ROCKETMONEY_COOKIE" not in updates:
        print("No GraphQL cookie was found. Paste a client-api.rocketmoney.com/graphql cURL to enable direct extraction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
