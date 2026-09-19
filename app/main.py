"""FastAPI application exposing the carpool fare-splitting API."""

from __future__ import annotations

from fastapi import FastAPI

from .models import SegmentSplit, SplitRequest, SplitResponse
from .splitter import split_fares

app = FastAPI(
    title="Carpool Fare Splitter",
    version="1.0.0",
    summary="Split a carpool trip's per-segment costs fairly between passengers.",
)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "carpool-fare-splitter", "docs": "/docs", "health": "/healthz"}


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


@app.post(
    "/split",
    response_model=SplitResponse,
    responses={422: {"description": "Invalid trip (bad interval, out-of-range "
                                     "station, duplicate id, empty-load charged "
                                     "segment, malformed payload, ...)"}},
)
def split(request: SplitRequest) -> SplitResponse:
    totals, details = split_fares(request.segments, request.passengers)
    return SplitResponse(
        total_cost=sum(request.segments),
        totals={str(pid): amount for pid, amount in totals.items()},
        segments=[
            SegmentSplit(
                index=d["index"],
                cost=d["cost"],
                passengers=d["passengers"],
                shares={str(pid): amount for pid, amount in d["shares"].items()},
            )
            for d in details
        ],
    )
