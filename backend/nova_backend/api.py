"""Read-only HTTP access to previously imported sales reports."""

import logging
from datetime import date as Date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from nova_backend import analytics, queries
from nova_backend.config import get_settings
from nova_backend.db import get_session
from nova_backend.pagination import InvalidCursor
from nova_backend.schemas import (
    FilteredOrderOut,
    ImportOut,
    ImportParams,
    ItemOut,
    ItemParams,
    OrderFilterParams,
    OrderLineOut,
    OrderOut,
    Page,
    SaleParams,
    StoreOut,
    StoreParams,
    TopDishesOut,
    TopDishParams,
)

logger = logging.getLogger(__name__)
app = FastAPI(
    title="NOVA sales backend",
    version="0.1.0",
    description=(
        "Read-only access to imported synthetic sales reports. Dates filter store-local "
        "placement dates with inclusive start and exclusive end. Import completion time "
        "does not establish provider data freshness. No request downloads provider data."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": [
                {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]
        },
    )


@app.exception_handler(InvalidCursor)
async def cursor_error(_request: Request, exc: InvalidCursor) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    logger.error("Request failed; check local server diagnostics", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


SessionDependency = Annotated[Session, Depends(get_session)]


@app.get("/stores", response_model=Page[StoreOut])
def stores(params: Annotated[StoreParams, Query()], session: SessionDependency):
    return queries.list_stores(session, params)


@app.get("/orders", response_model=Page[OrderOut])
def orders(params: Annotated[SaleParams, Query()], session: SessionDependency):
    return queries.list_orders(session, params)


@app.get("/orders/filter", response_model=Page[FilteredOrderOut])
def filter_orders(params: Annotated[OrderFilterParams, Query()], session: SessionDependency):
    """Orders by store, date or date range, time of day, and dish name, oldest first."""
    return analytics.filter_orders(session, params)


@app.get("/dishes/top", response_model=TopDishesOut)
def top_dishes(params: Annotated[TopDishParams, Query()], session: SessionDependency):
    """The most frequently ordered dishes in a period, ranked by units sold."""
    return analytics.top_dishes(session, params)


@app.get("/order-lines", response_model=Page[OrderLineOut])
def order_lines(params: Annotated[SaleParams, Query()], session: SessionDependency):
    return queries.list_order_lines(session, params)


@app.get("/items", response_model=Page[ItemOut])
def items(params: Annotated[ItemParams, Query()], session: SessionDependency):
    return queries.list_items(session, params)


@app.get("/imports", response_model=Page[ImportOut])
def imports(params: Annotated[ImportParams, Query()], session: SessionDependency):
    return queries.list_imports(session, params)


@app.get("/tablet")
def tablet(
    session: SessionDependency,
    date: Date = Query(..., description="Store-local forecast date, YYYY-MM-DD"),
    source: Literal["doordash", "grubhub"] | None = None,
):
    """Sales-only synthetic K-Station forecast and observed history for the tablet."""
    from nova_backend.tablet import tablet_analysis

    try:
        return tablet_analysis(session, date, source)
    except ValueError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/tablet/outlook")
def tablet_outlook(
    session: SessionDependency,
    date: Date = Query(..., description="Start of the seven-day sales outlook"),
    source: Literal["doordash", "grubhub"] | None = None,
):
    """Seven-day dish sales outlook using only history before the start date."""
    from nova_backend.tablet import tablet_outlook as analyze

    try:
        return analyze(session, date, source)
    except ValueError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
