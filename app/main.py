"""FastAPI application exposing the carpool fare-splitting API."""

from __future__ import annotations

from fastapi import FastAPI

from .models import (
    SegmentSplit,
    SettleRequest,
    SettleResponse,
    SplitRequest,
    SplitResponse,
    Transfer,
)
from .settlement import settle_transfers
from .splitter import split_fares, tie_key

app = FastAPI(
    title="Carpool Fare Splitter",
    version="1.1.0",
    summary="Split a carpool trip's per-segment costs fairly between "
            "passengers and settle the resulting balances.",
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


@app.post(
    "/settle",
    response_model=SettleResponse,
    responses={422: {"description": "Invalid trip or payments (bad interval, "
                                     "out-of-range station, duplicate id, "
                                     "empty-load charged segment, missing/"
                                     "duplicate/unknown payment, negative "
                                     "amount, payments total != trip cost, "
                                     "malformed payload, ...)"}},
)
def settle(request: SettleRequest) -> SettleResponse:
    owed_by_id, _ = split_fares(request.segments, request.passengers)
    paid_by_key = {str(p.id): p.amount for p in request.payments}

    order = sorted((p.id for p in request.passengers), key=tie_key)
    balances = {pid: paid_by_key[str(pid)] - owed_by_id[pid] for pid in order}
    transfers = settle_transfers(balances)

    return SettleResponse(
        owed={str(pid): owed_by_id[pid] for pid in order},
        paid={str(pid): paid_by_key[str(pid)] for pid in order},
        balance={str(pid): amount for pid, amount in balances.items()},
        transfers=[
            Transfer.model_validate({"from": f, "to": t, "amount": a})
            for f, t, a in transfers
        ],
    )
