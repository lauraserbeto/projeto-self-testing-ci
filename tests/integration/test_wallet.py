from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from src.domain.rules import WalletError


def test_stub_rejects_unknown_registration(wallet, gateway):
    with pytest.raises(WalletError, match="Cadastro recusado"):
        wallet.create_account("X", "unknown", 0)
    gateway.notify.assert_not_called()


@pytest.mark.parametrize("name,document", [("  ", "doc-c"), ("Carla", "  ")])
def test_empty_registration(wallet, name, document):
    with pytest.raises(WalletError, match="obrigatórios"):
        wallet.create_account(name, document, 0)


def test_duplicate_document_rolls_back(wallet, accounts):
    with pytest.raises(WalletError, match="já cadastrado"):
        wallet.create_account("Outra Ana", "doc-a", 500)
    assert wallet.account(accounts[0]["id"])["balance_cents"] == 10000


def test_mock_checks_payload_and_exactly_once(wallet, accounts, gateway, database):
    a, b = accounts
    result = wallet.transfer(a["id"], b["id"], 1234, "key-1")
    assert wallet.transfer(a["id"], b["id"], 1234, "key-1") == result
    gateway.notify.assert_called_once_with(result)
    assert wallet.account(a["id"])["balance_cents"] == 8766
    assert wallet.account(b["id"])["balance_cents"] == 1234
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM transfers").fetchone()[0] == 1
        assert (
            db.execute("SELECT count(*) FROM entries WHERE transfer_id IS NOT NULL").fetchone()[0]
            == 2
        )
        assert db.execute("SELECT delivered FROM outbox").fetchone()[0] == 1


def test_conflicting_idempotency_key(wallet, accounts, gateway):
    a, b = accounts
    wallet.transfer(a["id"], b["id"], 100, "same")
    with pytest.raises(WalletError, match="dados diferentes"):
        wallet.transfer(a["id"], b["id"], 101, "same")
    assert wallet.account(b["id"])["balance_cents"] == 100
    assert gateway.notify.call_count == 1


@pytest.mark.parametrize("key", [" ", "x" * 129])
def test_invalid_key(wallet, accounts, key):
    a, b = accounts
    with pytest.raises(WalletError, match="Idempotency-Key"):
        wallet.transfer(a["id"], b["id"], 1, key)


def test_same_account(wallet, accounts):
    with pytest.raises(WalletError, match="diferentes"):
        wallet.transfer(accounts[0]["id"], accounts[0]["id"], 1, "same-account")


@pytest.mark.parametrize("missing_source", [True, False])
def test_missing_account_keeps_database_unchanged(wallet, accounts, gateway, missing_source):
    a, b = accounts
    with pytest.raises(WalletError, match="não encontrada"):
        wallet.transfer(
            "missing" if missing_source else a["id"],
            b["id"] if missing_source else "missing",
            1,
            "absent",
        )
    assert wallet.account(a["id"])["balance_cents"] == 10000
    assert wallet.statement(b["id"]) == []
    gateway.notify.assert_not_called()


def test_insufficient_balance_has_no_side_effects(wallet, accounts, gateway):
    a, b = accounts
    with pytest.raises(WalletError, match="Saldo insuficiente"):
        wallet.transfer(a["id"], b["id"], 10001, "insufficient")
    assert wallet.account(a["id"])["balance_cents"] == 10000
    assert wallet.statement(b["id"]) == []
    gateway.notify.assert_not_called()


def test_gateway_failure_keeps_outbox_and_retry_does_not_debit_twice(
    wallet, accounts, gateway, database
):
    a, b = accounts
    gateway.notify.side_effect = OSError("offline")
    result = wallet.transfer(a["id"], b["id"], 200, "retry")
    with database.transaction() as db:
        assert db.execute("SELECT delivered FROM outbox").fetchone()[0] == 0
    gateway.notify.side_effect = None
    assert wallet.transfer(a["id"], b["id"], 200, "retry") == result
    assert wallet.account(a["id"])["balance_cents"] == 9800
    assert gateway.notify.call_count == 2
    with database.transaction() as db:
        assert db.execute("SELECT delivered FROM outbox").fetchone()[0] == 1


def test_statement_filters_are_inclusive(wallet, accounts, database):
    a, b = accounts
    result = wallet.transfer(a["id"], b["id"], 100, "filter")
    day = result["created_at"][:10]
    assert len(wallet.statement(a["id"], day, day, "debit")) == 1
    assert len(wallet.statement(a["id"], entry_type="credit")) == 1
    assert wallet.statement(a["id"], "2000-01-01", "2000-12-31") == []
    assert wallet.statement(a["id"], start="2999-01-01") == []
    assert wallet.statement(b["id"], entry_type="debit") == []
    entries = wallet.statement(b["id"])
    assert entries[0]["transfer_id"] == result["id"]


def test_inverted_dates(wallet, accounts):
    with pytest.raises(WalletError, match="posterior"):
        wallet.statement(accounts[0]["id"], "2026-02-01", "2026-01-01")


def test_concurrent_replays_produce_one_transfer(wallet, accounts, gateway):
    a, b = accounts
    barrier = Barrier(50)

    def call(_):
        barrier.wait(timeout=15)
        return wallet.transfer(a["id"], b["id"], 100, "concurrent")

    with ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(call, range(50)))
    assert len({result["id"] for result in results}) == 1
    assert wallet.account(a["id"])["balance_cents"] == 9900
    assert wallet.account(b["id"])["balance_cents"] == 100
    gateway.notify.assert_called_once_with(results[0])


def test_concurrent_distinct_transfers_never_overdraw(wallet, accounts, gateway):
    a, b = accounts
    barrier = Barrier(50)

    def call(index):
        barrier.wait(timeout=15)
        try:
            wallet.transfer(a["id"], b["id"], 1000, f"debit-{index}")
            return True
        except WalletError as exc:
            assert exc.status == 409
            return False

    with ThreadPoolExecutor(max_workers=50) as executor:
        successes = list(executor.map(call, range(50)))
    assert sum(successes) == 10
    assert wallet.account(a["id"])["balance_cents"] == 0
    assert wallet.account(b["id"])["balance_cents"] == 10000
    assert gateway.notify.call_count == 10
