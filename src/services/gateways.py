import json
from urllib.request import Request, urlopen


class RegistrationStub:
    """Cadastro fixo para o cenário fictício; não consulta bases pessoais reais."""

    def is_valid(self, document):
        return document != "blocked"


class AntifraudGateway:
    def __init__(self, url, timeout=2):
        self.url = url
        self.timeout = timeout

    def notify(self, payload):
        request = Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Idempotency-Key": payload["id"]},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            response.read()
