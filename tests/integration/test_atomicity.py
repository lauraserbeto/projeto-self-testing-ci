import sqlite3

import pytest

from src.repositories.database import Database
from src.services.wallet import WalletService


def test_mid_transaction_failure_rolls_back_balances_and_ledger(
    wallet, accounts, database, gateway
):
    a, b = accounts
    with database.transaction() as db:
        db.execute("""CREATE TRIGGER fail_credit BEFORE INSERT ON entries
            WHEN NEW.type='credit' AND NEW.transfer_id IS NOT NULL
            BEGIN SELECT RAISE(ABORT, 'falha simulada'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="falha simulada"):
        wallet.transfer(a["id"], b["id"], 100, "rollback")
    assert wallet.account(a["id"])["balance_cents"] == 10000
    assert wallet.account(b["id"])["balance_cents"] == 0
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM transfers").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM entries").fetchone()[0] == 1
    gateway.notify.assert_not_called()


def test_balances_and_idempotency_survive_reopening_file(tmp_path, wallet, gateway):
    path = str(tmp_path / "persistent.db")
    db = Database(path)
    service = WalletService(db, wallet.registry, gateway)
    try:
        a = service.create_account("Ana", "doc-a", 100)
        b = service.create_account("Bruno", "doc-b", 0)
        result = service.transfer(a["id"], b["id"], 10, "persistent")
    finally:
        db.close()
    reopened = Database(path)
    service = WalletService(reopened, wallet.registry, gateway)
    try:
        assert service.transfer(a["id"], b["id"], 10, "persistent") == result
        assert service.account(a["id"])["balance_cents"] == 90
        assert service.account(b["id"])["balance_cents"] == 10
        gateway.notify.assert_called_once_with(result)
    finally:
        reopened.close()
