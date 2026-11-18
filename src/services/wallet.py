import json
import logging
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from src.domain.rules import WalletError, transfer_balances, validate_amount

logger = logging.getLogger(__name__)


def utc_now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


class WalletService:
    def __init__(self, database, registry, gateway):
        self.db, self.registry, self.gateway = database, registry, gateway

    def create_account(self, name, document, initial_balance_cents):
        validate_amount(initial_balance_cents, allow_zero=True)
        if not name.strip() or not document.strip():
            raise WalletError("Nome e documento são obrigatórios")
        if not self.registry.is_valid(document):
            raise WalletError("Cadastro recusado", 422)
        account_id = str(uuid4())
        try:
            with self.db.transaction() as db:
                db.execute(
                    "INSERT INTO accounts VALUES (?, ?, ?, ?)",
                    (account_id, name.strip(), document, initial_balance_cents),
                )
                if initial_balance_cents:
                    db.execute(
                        """INSERT INTO entries
                        (account_id, type, amount_cents, created_at) VALUES (?, 'credit', ?, ?)""",
                        (account_id, initial_balance_cents, utc_now()),
                    )
        except sqlite3.IntegrityError as exc:
            raise WalletError("Documento já cadastrado", 409) from exc
        return self.account(account_id)

    @staticmethod
    def _account(db, account_id):
        row = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise WalletError("Conta não encontrada", 404)
        return dict(row)

    def account(self, account_id):
        with self.db.transaction() as db:
            return self._account(db, account_id)

    def transfer(self, source, target, amount, key):
        validate_amount(amount)
        if not key.strip() or len(key) > 128:
            raise WalletError("Idempotency-Key deve ter de 1 a 128 caracteres")
        if source == target:
            raise WalletError("As contas devem ser diferentes")
        with self.db.transaction() as db:
            previous = db.execute("SELECT * FROM transfers WHERE idem_key=?", (key,)).fetchone()
            if previous:
                if (previous["source"], previous["target"], previous["amount"]) != (
                    source,
                    target,
                    amount,
                ):
                    raise WalletError("Chave reutilizada com dados diferentes", 409)
                result = self._transfer_result(previous)
            else:
                origin, destination = self._account(db, source), self._account(db, target)
                balances = transfer_balances(
                    origin["balance_cents"], destination["balance_cents"], amount
                )
                for balance, account_id in zip(balances, (source, target), strict=True):
                    db.execute(
                        "UPDATE accounts SET balance_cents=? WHERE id=?", (balance, account_id)
                    )
                result = {
                    "id": str(uuid4()),
                    "source": source,
                    "target": target,
                    "amount_cents": amount,
                    "created_at": utc_now(),
                }
                db.execute(
                    "INSERT INTO transfers VALUES (?, ?, ?, ?, ?, ?)",
                    (result["id"], key, source, target, amount, result["created_at"]),
                )
                for account_id, entry_type in ((source, "debit"), (target, "credit")):
                    db.execute(
                        """INSERT INTO entries
                        (account_id, transfer_id, type, amount_cents, created_at)
                        VALUES (?, ?, ?, ?, ?)""",
                        (account_id, result["id"], entry_type, amount, result["created_at"]),
                    )
                db.execute(
                    "INSERT INTO outbox (transfer_id, payload) VALUES (?, ?)",
                    (result["id"], json.dumps(result)),
                )
        self._notify(result["id"])
        return result

    @staticmethod
    def _transfer_result(row):
        return {
            "id": row["id"],
            "source": row["source"],
            "target": row["target"],
            "amount_cents": row["amount"],
            "created_at": row["created_at"],
        }

    def _notify(self, transfer_id):
        # A saída persistida permite repetir a notificação sem repetir a transferência.
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT * FROM outbox WHERE transfer_id=? AND delivered=0", (transfer_id,)
            ).fetchone()
            if row:
                try:
                    self.gateway.notify(json.loads(row["payload"]))
                except (OSError, TimeoutError):
                    logger.warning("Notificação pendente para %s", transfer_id)
                else:
                    db.execute("UPDATE outbox SET delivered=1 WHERE transfer_id=?", (transfer_id,))

    def statement(self, account_id, start=None, end=None, entry_type=None):
        if start and end and start > end:
            raise WalletError("Data inicial posterior à final")
        sql = "SELECT * FROM entries WHERE account_id=?"
        params = [account_id]
        for value, condition in (
            (start, "substr(created_at,1,10)>=?"),
            (end, "substr(created_at,1,10)<=?"),
            (entry_type, "type=?"),
        ):
            if value:
                sql += " AND " + condition
                params.append(value)
        with self.db.transaction() as db:
            self._account(db, account_id)
            return [dict(row) for row in db.execute(sql + " ORDER BY id", params)]
