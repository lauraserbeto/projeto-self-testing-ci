import socket
import threading
import time
from contextlib import contextmanager
from unittest.mock import Mock

import httpx
import pytest
import uvicorn

from src.repositories.database import Database
from src.services.gateways import AntifraudGateway
from src.services.wallet import WalletService


class ApprovedRegistrationStub:
    def is_valid(self, document):
        return document in {"doc-a", "doc-b", "doc-c"}


@pytest.fixture
def database():
    db = Database()
    yield db
    db.close()


@pytest.fixture
def gateway():
    return Mock(spec=AntifraudGateway)


@pytest.fixture
def wallet(database, gateway):
    return WalletService(database, ApprovedRegistrationStub(), gateway)


@pytest.fixture
def accounts(wallet):
    return (
        wallet.create_account("Ana", "doc-a", 10000),
        wallet.create_account("Bruno", "doc-b", 0),
    )


@contextmanager
def running_server(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Servidor de teste não iniciou")
            time.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


@pytest.fixture
def http_api(database):
    from scripts.fake_gateway import app as gateway_app
    from src.controllers.api import create_app

    with running_server(gateway_app) as gateway_url:
        with running_server(
            create_app(database=database, gateway=AntifraudGateway(gateway_url + "/check"))
        ) as url:
            with httpx.Client(base_url=url, timeout=10) as client:
                yield client
