"""Rocket Money GraphQL transaction extraction.

This module intentionally does not store credentials. Pass request headers at
runtime from a private source such as environment variables or an ignored local
wrapper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib import error, request

from extractors.base import ExtractedPayload


ROCKET_MONEY_GRAPHQL_URL = "https://client-api.rocketmoney.com/graphql"
TRANSACTIONS_OPERATION_NAME = "TransactionsPageTransactionTable"
TRANSACTIONS_PERSISTED_QUERY_HASH = "c949db03d63e87919c3ec8a5b096efde3d0fa811935717ee7ab8fff71a30359f"
PageTransport = Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


@dataclass
class RocketMoneyGraphqlExtractor:
    """Page through Rocket Money's transaction connection."""

    headers: dict[str, str]
    page_size: int = 200
    endpoint: str = ROCKET_MONEY_GRAPHQL_URL
    source_type: str = "rocketmoney_graphql_transactions"
    variables: dict[str, Any | None] = field(default_factory=dict)
    start_cursor: str | None = None
    max_pages: int | None = None
    transport: PageTransport | None = None

    def build_payload(self, cursor: str | None) -> dict[str, Any]:
        variables = {
            "query": None,
            "order": "reverse:date",
            "accountIds": [],
            "transactionCategoryIds": [],
            "gteDate": None,
            "ltDate": None,
            "cursor": cursor,
            "pageSize": self.page_size,
            "metaCategory": None,
        }
        variables.update(self.variables)
        variables["cursor"] = cursor
        variables["pageSize"] = self.page_size

        return {
            "operationName": TRANSACTIONS_OPERATION_NAME,
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": TRANSACTIONS_PERSISTED_QUERY_HASH,
                },
            },
        }

    def fetch_page(self, cursor: str | None) -> dict[str, Any]:
        payload = self.build_payload(cursor)
        headers = {
            "accept": "application/graphql+json, application/json",
            "content-type": "application/json",
            "origin": "https://app.rocketmoney.com",
            "referer": "https://app.rocketmoney.com/",
            **self.headers,
        }

        if self.transport:
            return self.transport(payload, headers)

        return self._fetch_page_http(payload, headers)

    def _fetch_page_http(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=30) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body_text = _read_error_body(exc)
            raise RuntimeError(f"Rocket Money request failed with HTTP {exc.code}: {body_text}") from exc

    def extract(self, source: Any = None) -> ExtractedPayload:
        started_at = _utc_now()
        cursor = self.start_cursor
        seen_ids: set[str] = set()
        pages: list[dict[str, Any]] = []
        transactions: list[dict[str, Any]] = []
        duplicate_count = 0
        stopped_by_max_pages = False

        while True:
            if self.max_pages is not None and len(pages) >= self.max_pages:
                stopped_by_max_pages = True
                break

            page = self.fetch_page(cursor)
            if page.get("errors"):
                messages = "; ".join(str(item.get("message", item)) for item in page["errors"])
                raise RuntimeError(f"Rocket Money GraphQL returned errors: {messages}")

            connection = page.get("data", {}).get("viewer", {}).get("transactions", {})
            if not connection:
                raise RuntimeError("Rocket Money response did not include viewer.transactions")

            page_info = connection.get("pageInfo", {})
            edges = connection.get("edges", [])
            pages.append({
                "requestCursor": cursor,
                "startCursor": page_info.get("startCursor"),
                "endCursor": page_info.get("endCursor"),
                "hasNextPage": bool(page_info.get("hasNextPage")),
                "edgeCount": len(edges),
            })

            for edge in edges:
                node = edge.get("node") or {}
                node_id = node.get("id") or edge.get("cursor")
                if node_id in seen_ids:
                    duplicate_count += 1
                    continue
                seen_ids.add(node_id)
                transactions.append({
                    "_rocketMoneyCursor": edge.get("cursor"),
                    **node,
                })

            if not page_info.get("hasNextPage") or not page_info.get("endCursor"):
                break
            cursor = page_info["endCursor"]

        return ExtractedPayload(
            source_type=self.source_type,
            source_name="Rocket Money GraphQL transactions",
            payload={
                "transactions": transactions,
                "pages": pages,
            },
            metadata={
                "operationName": TRANSACTIONS_OPERATION_NAME,
                "persistedQueryHash": TRANSACTIONS_PERSISTED_QUERY_HASH,
                "pageSize": self.page_size,
                "pageCount": len(pages),
                "transactionCount": len(transactions),
                "duplicateCount": duplicate_count,
                "startedAt": started_at,
                "completedAt": _utc_now(),
                "stoppedBecauseMaxPages": stopped_by_max_pages,
            },
        )
