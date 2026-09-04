#!/usr/bin/env python3
"""Validate a scan_market MCP response for the daily job."""

from __future__ import annotations

import argparse
import json
import sys


def extract_scan_payload(outer: dict) -> dict:
    if outer.get("error"):
        raise ValueError(outer["error"].get("message", "jsonrpc_error"))
    result = outer.get("result") or {}
    if result.get("isError"):
        raise ValueError("mcp_tool_error")
    text = (result.get("content") or [{}])[0].get("text", "")
    return json.loads(text) if text else result.get("structuredContent", {})


def validate(payload: dict, expected_date: str) -> tuple[int, str]:
    meta = payload.get("meta") or {}
    pool = payload.get("pool_size") or {}
    market_date = meta.get("market_data_date") or payload.get("market_data_date")
    sources = set(meta.get("source") or [])
    scanned, total = int(pool.get("scanned", 0)), int(pool.get("total", 0))

    if total <= 0 or scanned / total < 0.9:
        return 1, f"scan coverage too low: {scanned}/{total}"
    if market_date == expected_date:
        return 0, f"scan valid: {scanned}/{total}, market_date={market_date}"
    if sources - {"local_cache", "scan_cache"}:
        return 3, f"no market session: latest={market_date}, expected={expected_date}"
    return 1, f"stale local data: market_data_date={market_date}, expected={expected_date}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-date", required=True)
    args = parser.parse_args()
    try:
        payload = extract_scan_payload(json.load(sys.stdin))
        code, message = validate(payload, args.expected_date)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        code, message = 1, f"invalid scan response: {exc}"
    print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
