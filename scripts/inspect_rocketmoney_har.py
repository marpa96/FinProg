from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_har(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_graphql_requests(har: dict[str, Any]) -> list[dict[str, Any]]:
    entries = har.get("log", {}).get("entries", [])
    matches: list[dict[str, Any]] = []
    for entry in entries:
        request = entry.get("request", {})
        if "client-api.rocketmoney.com/graphql" not in request.get("url", ""):
            continue
        post_text = request.get("postData", {}).get("text")
        if not post_text:
            continue
        try:
            payload = json.loads(post_text)
        except json.JSONDecodeError:
            continue
        matches.append(
            {
                "status": entry.get("response", {}).get("status"),
                "payload": payload,
            }
        )
    return matches


def summarize_operations(requests: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in requests:
        name = item["payload"].get("operationName") or "<none>"
        counts[name] = counts.get(name, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Rocket Money HAR files for GraphQL operation names and persisted query hashes.",
    )
    parser.add_argument("har_path", type=Path, help="Path to a browser-exported HAR file.")
    parser.add_argument(
        "--operation",
        default="TransactionsPageTransactionTable",
        help="Specific GraphQL operation to print in detail.",
    )
    args = parser.parse_args()

    har = load_har(args.har_path)
    graphql_requests = iter_graphql_requests(har)
    counts = summarize_operations(graphql_requests)

    print(f"HAR: {args.har_path}")
    print(f"GraphQL requests: {len(graphql_requests)}")
    print("Operations:")
    for name in sorted(counts):
        print(f"  {name}: {counts[name]}")

    detailed = [item for item in graphql_requests if item["payload"].get("operationName") == args.operation]
    if not detailed:
        print(f"\nNo requests found for operation: {args.operation}")
        return 0

    print(f"\nDetailed requests for {args.operation}:")
    for index, item in enumerate(detailed, start=1):
        payload = item["payload"]
        query = payload.get("extensions", {}).get("persistedQuery", {})
        print(f"\n[{index}] status={item['status']}")
        print(f"  hash={query.get('sha256Hash')}")
        print("  variables=")
        print(json.dumps(payload.get("variables", {}), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
