"""Request/response schemas and request validation.

All domain-rule violations (invalid intervals, out-of-range stations,
duplicate ids, empty-load charged segments, ...) are raised as
``ValueError`` inside Pydantic validators, so FastAPI turns them into a
uniform HTTP 422 response.
"""

from __future__ import annotations

from typing import Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator

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


class SplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: List[NonNegativeInt] = Field(
        min_length=1,
        description="integer cost of each segment in cents, in travel order",
    )
    passengers: List[Passenger] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_trip(self) -> "SplitRequest":
        n = len(self.segments)

        seen = set()
        for p in self.passengers:
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

        for i, cost in enumerate(self.segments):
            if cost > 0 and not any(p.board <= i < p.alight for p in self.passengers):
                raise ValueError(
                    f"segment {i} has cost {cost} but no passengers on board "
                    f"(empty-load charged segment)"
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
