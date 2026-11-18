import asyncio

import pytest

from src.domain.rules import WalletError
from src.main import app


def test_default_wiring_and_database_lifecycle(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")

    async def exercise_lifespan():
        async with app.router.lifespan_context(app):
            with pytest.raises(WalletError, match="Cadastro recusado"):
                app.state.wallet.create_account("Carla", "blocked", 0)

    asyncio.run(exercise_lifespan())
