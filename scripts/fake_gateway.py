from fastapi import FastAPI, Header

app = FastAPI(title="Gateway fictício")
received = set()


@app.post("/check")
async def check(payload: dict, idempotency_key: str = Header()):
    received.add(idempotency_key)
    return {"accepted": True, "transfer_id": payload["id"]}
