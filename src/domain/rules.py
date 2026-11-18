MAX_AMOUNT_CENTS = 10**12


class WalletError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_amount(value, *, allow_zero=False):
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= MAX_AMOUNT_CENTS:
        raise WalletError("Valor deve ser inteiro em centavos entre o mínimo permitido e 10^12")
    return value


def transfer_balances(source, target, amount):
    validate_amount(amount)
    if source < amount:
        raise WalletError("Saldo insuficiente", 409)
    return source - amount, target + amount
