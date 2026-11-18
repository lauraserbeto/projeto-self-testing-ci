import pytest


def account(client, document, balance):
    response = client.post(
        "/accounts",
        json={
            "name": document,
            "document": document,
            "initial_balance_cents": balance,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_complete_flow_over_real_http(http_api):
    client = http_api
    a, b = account(client, "ana", 10000), account(client, "bruno", 500)
    payload = {"source": a, "target": b, "amount_cents": 2500}
    response = client.post("/transfers", json=payload, headers={"Idempotency-Key": "e2e-1"})
    assert response.status_code == 201
    transfer = response.json()
    retry = client.post("/transfers", json=payload, headers={"Idempotency-Key": "e2e-1"})
    assert retry.json() == transfer
    assert client.get(f"/accounts/{a}").json()["balance_cents"] == 7500
    assert client.get(f"/accounts/{b}").json()["balance_cents"] == 3000
    day = transfer["created_at"][:10]
    debit = client.get(
        f"/accounts/{a}/statement",
        params={
            "start": day,
            "end": day,
            "type": "debit",
        },
    )
    assert debit.status_code == 200
    assert len(debit.json()) == 1
    assert debit.json()[0]["amount_cents"] == 2500
    assert debit.json()[0]["transfer_id"] == transfer["id"]
    credit = client.get(f"/accounts/{b}/statement", params={"type": "credit"}).json()
    assert [entry["amount_cents"] for entry in credit] == [500, 2500]
    from scripts.fake_gateway import received

    assert transfer["id"] in received


def test_business_errors_over_http(http_api):
    client = http_api
    a, b = account(client, "a", 100), account(client, "b", 0)
    data = {"source": a, "target": b, "amount_cents": 101}
    assert (
        client.post("/transfers", json=data, headers={"Idempotency-Key": "poor"}).status_code == 409
    )
    data["amount_cents"] = 1
    assert client.post("/transfers", json=data).status_code == 422
    assert client.get("/accounts/missing").status_code == 404
    assert client.get("/accounts/missing/statement").status_code == 404
    assert client.get(f"/accounts/{a}/statement?type=other").status_code == 422
    assert client.get(f"/accounts/{a}/statement?start=wrong").status_code == 422
    assert client.get(f"/accounts/{a}/statement?start=2026-02-01&end=2026-01-01").status_code == 400
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("amount", [-1, 0, 1.5, True, "10"])
def test_http_rejects_invalid_amounts(http_api, amount):
    response = http_api.post(
        "/transfers",
        json={
            "source": "a",
            "target": "b",
            "amount_cents": amount,
        },
        headers={"Idempotency-Key": "invalid"},
    )
    assert response.status_code == 422
