"""Extract Rocket Money transactions to a private JSON file.

Set ROCKETMONEY_COOKIE to the browser cookie header value from the captured
request. Optional environment variables:

- ROCKETMONEY_TRUEBILL_WEB_CLIENT_VERSION
- ROCKETMONEY_USER_AGENT
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractors.rocketmoney_graphql import RocketMoneyGraphqlExtractor
from scripts.local_env import load_env_file
from scripts.refresh_rocketmoney_cookie import refresh_cookie


DEFAULT_OUTPUT = Path("data/private/rocketmoney_transactions.json")


def parse_header(value: str) -> tuple[str, str]:
    name, separator, header_value = value.partition(":")
    if not separator or not name.strip():
        raise argparse.ArgumentTypeError("headers must look like 'Header-Name: value'")
    return name.strip(), header_value.strip()


def build_headers(extra_headers: list[tuple[str, str]], refresh_if_missing: bool) -> dict[str, str]:
    cookie = os.environ.get("ROCKETMONEY_COOKIE")
    if not cookie and refresh_if_missing:
        refresh_cookie(Path("data/private/rocketmoney_refreshed_cookies.txt"), ROOT / ".env")
        cookie = os.environ.get("ROCKETMONEY_COOKIE")

    if not cookie:
        raise SystemExit(
            "ROCKETMONEY_COOKIE is required. Fill it in .env, or fill ROCKETMONEY_USERNAME and "
            "ROCKETMONEY_PASSWORD so the script can refresh it."
        )

    headers = {
        "cookie": cookie,
        "user-agent": os.environ.get(
            "ROCKETMONEY_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        ),
    }

    client_version = os.environ.get("ROCKETMONEY_TRUEBILL_WEB_CLIENT_VERSION")
    if client_version:
        headers["x-truebill-web-client-version"] = client_version

    headers.update(dict(extra_headers))
    return headers


def should_refresh_after_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    auth_markers = [
        "http 401",
        "http 403",
        "unauthorized",
        "forbidden",
        "session",
        "expired",
        "login",
        "not authenticated",
    ]
    return any(marker in message for marker in auth_markers)


def run_extraction(args: argparse.Namespace) -> Any:
    headers = build_headers(args.header, refresh_if_missing=not args.no_refresh)
    extractor = RocketMoneyGraphqlExtractor(
        headers=headers,
        page_size=args.page_size,
        start_cursor=args.start_cursor,
        max_pages=args.max_pages,
    )
    return extractor.extract()


def payload_to_jsonable(payload: Any) -> dict[str, Any]:
    extracted = asdict(payload)
    extracted["format"] = "finprog.raw_extraction.v1"
    return extracted


def main() -> int:
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Extract all Rocket Money transactions into JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--start-cursor", default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--no-refresh", action="store_true", help="Do not refresh cookies when missing or expired.")
    parser.add_argument(
        "--header",
        action="append",
        type=parse_header,
        default=[],
        help="Extra request header, for example 'x-analytics-session: 1776128147754'.",
    )
    args = parser.parse_args()

    if args.page_size <= 0:
        raise SystemExit("--page-size must be greater than zero")
    if args.max_pages is not None and args.max_pages <= 0:
        raise SystemExit("--max-pages must be greater than zero")

    try:
        extracted = run_extraction(args)
    except Exception as exc:
        if args.no_refresh or not should_refresh_after_failure(exc):
            raise
        print("Rocket Money session looks stale; refreshing cookies from .env credentials and retrying once.")
        refresh_cookie(Path("data/private/rocketmoney_refreshed_cookies.txt"), ROOT / ".env")
        extracted = run_extraction(args)

    output = payload_to_jsonable(extracted)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    metadata = extracted.metadata
    print(
        f"Wrote {metadata['transactionCount']} transactions across {metadata['pageCount']} pages "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
