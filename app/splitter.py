"""Core fare-splitting algorithm.

Pure standard library (exact ``fractions.Fraction`` arithmetic), so it can be
unit-tested without any web dependencies and stays free of float rounding
errors. Money amounts are integer cents; theoretical shares are exact
fractions.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Dict, List, Tuple


def tie_key(passenger_id) -> tuple:
    """Total, input-order-independent order used ONLY to break deficit ties.

    Integer ids compare numerically and sort before string ids, which compare
    lexicographically. Because every ranking ends with this key, permuting the
    passengers in the request never changes the outcome.
    """
    if isinstance(passenger_id, bool):  # bool is an int subclass; keep it sane
        return (1, str(passenger_id))
    if isinstance(passenger_id, int):
        return (0, passenger_id)
    return (1, str(passenger_id))


def split_fares(segment_costs: List[int], passengers) -> Tuple[Dict, List[dict]]:
    """Split per-segment costs between passengers, segment by segment.

    ``passengers`` items must expose ``id``, ``board`` and ``alight``
    attributes; a passenger occupies segments ``board <= i < alight``.

    Per segment the cost is shared equally between everyone on board. When the
    cost does not divide evenly, the leftover cents (``cost % n``) go one each
    to the passengers with the largest *deficit* — their cumulative exact
    theoretical share minus what they have actually been allocated so far —
    with ties broken by :func:`tie_key`.

    Returns ``(totals, details)``: ``totals`` maps passenger id -> allocated
    cents (inserted in canonical id order); ``details`` is a per-segment list
    of dicts with keys ``index``, ``cost``, ``passengers`` and ``shares``.
    """
    allocated = {p.id: 0 for p in passengers}
    theoretical = {p.id: Fraction(0) for p in passengers}
    details: List[dict] = []

    for index, cost in enumerate(segment_costs):
        onboard = sorted(
            (p.id for p in passengers if p.board <= index < p.alight),
            key=tie_key,
        )
        if not onboard:
            # Only reachable for zero-cost segments; charged empty segments
            # are rejected during request validation (HTTP 422).
            details.append({"index": index, "cost": cost, "passengers": [], "shares": {}})
            continue

        base, remainder = divmod(cost, len(onboard))
        share = Fraction(cost, len(onboard))
        for pid in onboard:
            theoretical[pid] += share

        # Deficit if everyone on board received only the base amount: how far
        # the passenger's actual allocation would lag their cumulative
        # theoretical share. (Adding the current segment's share and base to
        # every onboard passenger shifts all deficits by the same constant,
        # so the ranking is identical to using pre-segment state.)
        deficits = {pid: theoretical[pid] - (allocated[pid] + base) for pid in onboard}
        ranked = sorted(onboard, key=lambda pid: (-deficits[pid], tie_key(pid)))
        extra = set(ranked[:remainder])

        shares = {pid: base + (1 if pid in extra else 0) for pid in onboard}
        for pid, amount in shares.items():
            allocated[pid] += amount

        details.append(
            {"index": index, "cost": cost, "passengers": onboard, "shares": shares}
        )

    totals = {pid: allocated[pid] for pid in sorted(allocated, key=tie_key)}
    return totals, details
