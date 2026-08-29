"""Holder counts and top-ten concentration, read straight from an RPC node.

Both numbers come from `getTokenLargestAccounts`, which every free Solana
endpoint throttles or gates behind a token - it is an indexed call. So:

  * with DESK_RPC set to your own node, this returns live numbers;
  * with no node, it returns None, and the caller must treat None as
    "unknown", never as "fine".

WARDEN is deliberately fail-closed on that None: an unknown counterparty is
refused the same as a missing one.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

RPC_URL = os.environ.get("DESK_RPC", "")
LARGEST_ACCOUNTS_CAP = 20  # what getTokenLargestAccounts returns at most


@dataclass(frozen=True)
class Holders:
    """What the chain says about who is holding.

    `count` is exact only while it stays under the RPC's twenty-account
    ceiling; at the ceiling `exact` is False and the true number is higher.
    """

    count: int
    exact: bool
    top10_share: float


def _rpc(method: str, params: list) -> dict | None:
    if not RPC_URL:
        return None
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    request = urllib.request.Request(
        RPC_URL,
        data=payload.encode(),
        headers={"Content-Type": "application/json", "User-Agent": "warden-desk/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except Exception:
        return None
    if "error" in body:
        return None
    return body.get("result")


def holders(mint: str) -> Holders | None:
    """Live holder picture, or None when no node is configured or it refused."""
    result = _rpc("getTokenLargestAccounts", [mint])
    if not result or "value" not in result:
        return None

    balances = [
        float(entry["uiAmount"] or 0)
        for entry in result["value"]
        if float(entry.get("uiAmount") or 0) > 0
    ]
    if not balances:
        return Holders(count=0, exact=True, top10_share=0.0)

    supply_result = _rpc("getTokenSupply", [mint])
    supply = 0.0
    if supply_result:
        supply = float(supply_result.get("value", {}).get("uiAmount") or 0)

    top10 = sum(sorted(balances, reverse=True)[:10])
    share = (top10 / supply) if supply else 1.0

    return Holders(
        count=len(balances),
        exact=len(result["value"]) < LARGEST_ACCOUNTS_CAP,
        top10_share=min(share, 1.0),
    )


def configured() -> bool:
    """Is a node available at all? Printed by `desk.py index --check`."""
    return bool(RPC_URL)
