"""Request/response schemas and request validation.

All domain-rule violations (invalid intervals, out-of-range stations,
duplicate ids, empty-load charged segments, missing/duplicate/unknown
payments, unbalanced payment totals, ...) are raised as ``ValueError``
inside Pydantic validators, so FastAPI turns them into a uniform HTTP 422
response.
"""

from __future__ import annotations

from typing import Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

PassengerId = Union[str, int]


class Passenger(BaseModel):
    """One passenger's ride, expressed as station indices.

    A trip with ``N`` segments has stations ``0..N``; a passenger who boards
    at ``board`` and alights at ``alight`` occupies segments
    ``board, board+1, ..., alight-1``.
    """

    model_config = ConfigDict(extra="forbid")

    id: PassengerId = Field(description="unique passenger id (string or integer)")
    board: NonNegativeInt = Field(description="station index where the passenger boards")
    alight: NonNegativeInt = Field(description="station index where the passenger alights")


class Payment(BaseModel):
    """One passenger's payment: how much they actually paid, in cents."""

    model_config = ConfigDict(extra="forbid")

    id: PassengerId = Field(description="id of the passenger who paid")
    amount: NonNegativeInt = Field(description="amount actually paid, in integer cents")


def _check_trip_rules(segments: List[int], passengers: List[Passenger]) -> None:
    """Shared trip validation for /split and /settle (raises ValueError)."""
    n = len(segments)

    seen = set()
    for p in passengers:
        key = str(p.id)
        if key in seen:
            raise ValueError(f"duplicate passenger id: {p.id!r}")
        seen.add(key)
        if p.board >= p.alight:
            raise ValueError(
                f"passenger {p.id!r}: invalid interval board={p.board}, "
                f"alight={p.alight} (board must be < alight)"
            )
        if p.alight > n:
            raise ValueError(
                f"passenger {p.id!r}: alight station {p.alight} is out of range; "
                f"a trip with {n} segment(s) has stations 0..{n}"
            )

    for i, cost in enumerate(segments):
        if cost > 0 and not any(p.board <= i < p.alight for p in passengers):
            raise ValueError(
                f"segment {i} has cost {cost} but no passengers on board "
                f"(empty-load charged segment)"
            )


class SplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: List[NonNegativeInt] = Field(
        min_length=1,
        description="integer cost of each segment in cents, in travel order",
    )
    passengers: List[Passenger] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_trip(self) -> "SplitRequest":
        _check_trip_rules(self.segments, self.passengers)
        return self


class SettleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: List[NonNegativeInt] = Field(
        min_length=1,
        description="integer cost of each segment in cents, in travel order",
    )
    passengers: List[Passenger] = Field(default_factory=list)
    payments: List[Payment] = Field(
        default_factory=list,
        description="exactly one payment record per passenger: who paid how much",
    )

    @model_validator(mode="after")
    def _check_trip_and_payments(self) -> "SettleRequest":
        _check_trip_rules(self.segments, self.passengers)

        passenger_keys = {str(p.id) for p in self.passengers}
        seen = set()
        for pay in self.payments:
            key = str(pay.id)
            if key in seen:
                raise ValueError(f"duplicate payment for passenger {pay.id!r}")
            seen.add(key)
            if key not in passenger_keys:
                raise ValueError(f"payment for unknown passenger {pay.id!r}")
        missing = passenger_keys - seen
        if missing:
            raise ValueError(
                "missing payment for passenger(s): " + ", ".join(sorted(missing))
            )

        total = sum(self.segments)
        paid = sum(p.amount for p in self.payments)
        if paid != total:
            raise ValueError(
                f"payments total {paid} does not match trip cost {total}"
            )
        return self


class SegmentSplit(BaseModel):
    """How one segment's cost was divided."""

    index: int = Field(description="segment index, 0-based, in travel order")
    cost: NonNegativeInt = Field(description="segment cost in cents")
    passengers: List[PassengerId] = Field(description="ids on board during this segment")
    shares: Dict[str, NonNegativeInt] = Field(
        description="cents charged to each on-board passenger; sums to cost"
    )


class SplitResponse(BaseModel):
    total_cost: NonNegativeInt = Field(description="sum of all segment costs in cents")
    totals: Dict[str, NonNegativeInt] = Field(
        description="cents charged to each passenger over the whole trip; sums to total_cost"
    )
    segments: List[SegmentSplit] = Field(description="per-segment split detail")


class Transfer(BaseModel):
    """One transfer settling (part of) a debt, from a debtor to a creditor."""

    model_config = ConfigDict(populate_by_name=True)

    from_: PassengerId = Field(alias="from", description="debtor who pays")
    to: PassengerId = Field(description="creditor who receives")
    amount: PositiveInt = Field(description="transfer amount in cents")


class SettleResponse(BaseModel):
    owed: Dict[str, NonNegativeInt] = Field(
        description="cents each passenger should have paid for the trip; sums to the trip cost"
    )
    paid: Dict[str, NonNegativeInt] = Field(
        description="cents each passenger actually paid"
    )
    balance: Dict[str, int] = Field(
        description="paid - owed per passenger, in cents; positive means they are owed money"
    )
    transfers: List[Transfer] = Field(
        description="minimal debtor->creditor transfers settling every balance"
    )
