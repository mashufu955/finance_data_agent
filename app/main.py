"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.lifespan import lifespan
from app.core.middleware import RequestIDMiddleware
from app.idempotency import IdempotencyMismatchError

app = FastAPI(title="Finance Data Agent API", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)


@app.exception_handler(IdempotencyMismatchError)
async def idempotency_mismatch_handler(request: Request, exc: IdempotencyMismatchError):
    return JSONResponse(
        status_code=409,
        content={"code": "IDEMPOTENCY_PAYLOAD_MISMATCH", "data": None, "message": str(exc.request_no)},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "data": None, "message": str(exc)},
    )


# Import and register all routers
from app.routers import (
    foundation,
    customers,
    accounts,
    transactions,
    reconciliation,
    wealth,
    credit,
    loan,
    repayment,
    risk,
    collection,
    operations,
)

app.include_router(foundation.router)
app.include_router(customers.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(reconciliation.router)
app.include_router(wealth.router)
app.include_router(credit.router)
app.include_router(loan.router)
app.include_router(repayment.router)
app.include_router(risk.router)
app.include_router(collection.router)
app.include_router(operations.router)

from app.api.routers.chat_router import chat_router
app.include_router(chat_router)
