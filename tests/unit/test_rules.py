import pytest

from src.domain.rules import WalletError, transfer_balances, validate_amount


@pytest.mark.parametrize("value", [1, 2, 10, 99, 100, 101, 999999999, 10**12])
def test_accepts_positive_cents(value):
    assert validate_amount(value) == value


def test_initial_balance_can_be_zero():
    assert validate_amount(0, allow_zero=True) == 0


@pytest.mark.parametrize("value", [0, -1, -100, 1.5, "100", True, False, None, 10**12 + 1])
def test_rejects_invalid_amount(value):
    with pytest.raises(WalletError, match="centavos"):
        validate_amount(value)


@pytest.mark.parametrize(
    "source,target,amount,expected",
    [
        (100, 20, 30, (70, 50)),
        (100, 0, 100, (0, 100)),
        (1, 0, 1, (0, 1)),
        (10**12, 0, 10**12, (0, 10**12)),
        (100, 999, 1, (99, 1000)),
    ],
)
def test_transfer_conserves_total(source, target, amount, expected):
    result = transfer_balances(source, target, amount)
    assert result == expected
    assert sum(result) == source + target


def test_insufficient_balance():
    with pytest.raises(WalletError, match="Saldo insuficiente") as error:
        transfer_balances(10, 0, 11)
    assert error.value.status == 409


@pytest.mark.parametrize("amount", [0, -10, 1.2, True])
def test_transfer_rejects_invalid_amount(amount):
    with pytest.raises(WalletError):
        transfer_balances(100, 100, amount)
