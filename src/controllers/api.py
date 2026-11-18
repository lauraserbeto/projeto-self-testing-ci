import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictInt

from src.domain.rules import WalletError
from src.repositories.database import Database
from src.services.gateways import AntifraudGateway, RegistrationStub
from src.services.wallet import WalletService


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    document: str = Field(min_length=1, max_length=40)
    initial_balance_cents: StrictInt = Field(ge=0, le=10**12)


class TransferInput(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    amount_cents: StrictInt = Field(gt=0, le=10**12)


def create_app(database=None, registry=None, gateway=None):
    @asynccontextmanager
    async def lifespan(app):
        own_database = database is None
        db = database if database is not None else Database(os.getenv("DATABASE_PATH", "wallet.db"))
        app.state.wallet = WalletService(
            db,
            registry if registry is not None else RegistrationStub(),
            gateway
            if gateway is not None
            else AntifraudGateway(
                os.getenv("ANTIFRAUD_URL", "http://127.0.0.1:8001/check"),
                float(os.getenv("ANTIFRAUD_TIMEOUT", "2")),
            ),
        )
        try:
            yield
        finally:
            if own_database:
                db.close()

    app = FastAPI(title="Wallet API", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(WalletError)
    async def wallet_error(request: Request, exc: WalletError):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/accounts", status_code=201)
    def create_account(body: AccountInput, request: Request):
        return request.app.state.wallet.create_account(**body.model_dump())

    @app.get("/accounts/{account_id}")
    def get_account(account_id: str, request: Request):
        return request.app.state.wallet.account(account_id)

    @app.post("/transfers", status_code=201)
    def transfer(
        body: TransferInput,
        request: Request,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ):
        return request.app.state.wallet.transfer(
            body.source, body.target, body.amount_cents, idempotency_key
        )

    @app.get("/accounts/{account_id}/statement")
    def statement(
        account_id: str,
        request: Request,
        start: date | None = None,
        end: date | None = None,
        type: Literal["debit", "credit"] | None = None,
    ):
        return request.app.state.wallet.statement(
            account_id, start.isoformat() if start else None, end.isoformat() if end else None, type
        )

    return app
