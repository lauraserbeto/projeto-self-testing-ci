import json
from unittest.mock import MagicMock, patch

from src.services.gateways import AntifraudGateway, RegistrationStub


def test_http_adapter_sends_json_key_and_timeout():
    response = MagicMock()
    with patch("src.services.gateways.urlopen", return_value=response) as request_mock:
        AntifraudGateway("http://gateway/check", timeout=1.5).notify({"id": "tx-1"})
    request_mock.assert_called_once()
    args, kwargs = request_mock.call_args
    assert args[0].full_url == "http://gateway/check"
    assert args[0].method == "POST"
    assert json.loads(args[0].data) == {"id": "tx-1"}
    assert args[0].get_header("Idempotency-key") == "tx-1"
    assert kwargs == {"timeout": 1.5}
    response.__enter__.return_value.read.assert_called_once_with()


def test_fixed_registration_stub():
    stub = RegistrationStub()
    assert stub.is_valid("doc-a") is True
    assert stub.is_valid("blocked") is False
