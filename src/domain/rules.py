class WalletError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_amount(value, *, allow_zero=False):
    raise NotImplementedError


def transfer_balances(source, target, amount):
    raise NotImplementedError
