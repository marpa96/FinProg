"""Rocket Money per-transaction detail extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from .graphql import ROCKET_MONEY_GRAPHQL_URL


TRANSACTION_DETAILS_OPERATION_NAME = "TransactionDetails"
TRANSACTION_DETAILS_PERSISTED_QUERY_HASH = "439bb0fef65c4ac722b5b38cadb4a0bdc5db5a7d0ac3bd9e54906e2bee6a32da"
TRANSACTION_HISTORY_OPERATION_NAME = "TransactionHistoryPage"
TRANSACTION_HISTORY_PERSISTED_QUERY_HASH = "7d2cd25316182356147c7f61e604ed68196d38f1edd398aa50776e18096321df"

DetailTransport = Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]
DetailProgressCallback = Callable[[dict[str, Any]], None]


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


@dataclass
class RocketMoneyTransactionDetailExtractor:
    headers: dict[str, str]
    endpoint: str = ROCKET_MONEY_GRAPHQL_URL
    transport: DetailTransport | None = None
    progress_callback: DetailProgressCallback | None = None

    def build_payload(self, operation_name: str, query_hash: str, variables: dict[str, Any]) -> dict[str, Any]:
        return {
            "operationName": operation_name,
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": query_hash,
                }
            },
        }

    def fetch_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "accept": "application/graphql+json, application/json",
            "content-type": "application/json",
            "origin": "https://app.rocketmoney.com",
            "referer": "https://app.rocketmoney.com/",
            **self.headers,
        }
        if self.transport:
            return self.transport(payload, headers)

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(http_request, timeout=30) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body_text = _read_error_body(exc)
            raise RuntimeError(f"Rocket Money detail request failed with HTTP {exc.code}: {body_text}") from exc

    def fetch_transaction_bundle(self, transaction_id: str) -> dict[str, Any]:
        details_payload = self.build_payload(
            TRANSACTION_DETAILS_OPERATION_NAME,
            TRANSACTION_DETAILS_PERSISTED_QUERY_HASH,
            {"id": transaction_id},
        )
        history_payload = self.build_payload(
            TRANSACTION_HISTORY_OPERATION_NAME,
            TRANSACTION_HISTORY_PERSISTED_QUERY_HASH,
            {"id": transaction_id, "startDate": None, "endDate": None},
        )

        details = self.fetch_payload(details_payload)
        history = self.fetch_payload(history_payload)

        if details.get("errors"):
            raise RuntimeError(f"Rocket Money detail GraphQL returned errors: {details['errors']}")
        if history.get("errors"):
            raise RuntimeError(f"Rocket Money history GraphQL returned errors: {history['errors']}")

        return {
            "transactionDetails": details.get("data", {}).get("node"),
            "transactionHistory": history.get("data", {}).get("node"),
        }

    def fetch_many(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        bundles: dict[str, dict[str, Any]] = {}
        total = len(transaction_ids)
        for index, transaction_id in enumerate(transaction_ids, start=1):
            bundles[transaction_id] = self.fetch_transaction_bundle(transaction_id)
            if self.progress_callback:
                self.progress_callback(
                    {
                        "current": index,
                        "total": total,
                        "transactionId": transaction_id,
                    }
                )
        return bundles
