import os
import time
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

TARGET_WEBHOOK_URL = os.getenv("TARGET_WEBHOOK_URL", "").strip()
SIMULATOR_KEY = os.getenv("SIMULATOR_KEY", "").strip()
DEFAULT_INSTANCE = os.getenv("DEFAULT_INSTANCE", "c1-a1").strip()

app = FastAPI(title="WhatsApp Simulator")
templates = Jinja2Templates(directory="app/templates")


def build_messages_upsert(instance: str, from_number: str, text: str, msg_id: Optional[str] = None):
    # msg_id controlável para testar dedupe
    msg_id = msg_id or f"SIM-{uuid.uuid4().hex[:16].upper()}"
    ts = int(time.time())

    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": f"{from_number}@s.whatsapp.net",
                "fromMe": False,
                "id": msg_id,
                "participant": "",
                "addressingMode": "pn",
            },
            "pushName": "SimUser",
            "status": "SERVER_ACK",
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": ts,
            "instanceId": "SIMULATOR",
            "source": "simulator",
        },
        "destination": TARGET_WEBHOOK_URL,
        "date_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


async def post_to_webhook(payload: dict):
    if not TARGET_WEBHOOK_URL:
        return {"ok": False, "error": "TARGET_WEBHOOK_URL não configurado"}

    headers = {}
    if SIMULATOR_KEY:
        headers["X-SIMULATOR-KEY"] = SIMULATOR_KEY

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(TARGET_WEBHOOK_URL, json=payload, headers=headers)
        return {"ok": r.status_code < 400, "status_code": r.status_code, "body": r.text[:500]}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "target": TARGET_WEBHOOK_URL,
            "default_instance": DEFAULT_INSTANCE,
        },
    )


@app.post("/api/send")
async def api_send(
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form("5531999000001"),
    text: str = Form("Oi"),
):
    payload = build_messages_upsert(instance=instance, from_number=from_number, text=text)
    result = await post_to_webhook(payload)
    return JSONResponse({"payload": payload, "result": result})


@app.post("/api/scenario/menu")
async def scenario_menu(
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form("5531999000001"),
):
    payload = build_messages_upsert(instance=instance, from_number=from_number, text="Oi")
    result = await post_to_webhook(payload)
    return JSONResponse({"scenario": "menu", "result": result})


@app.post("/api/scenario/lead3")
async def scenario_lead3(
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form("5531999000001"),
):
    # 3 mensagens: Nome, Telefone, Assunto
    msgs = [
        "Nome: João da Silva",
        "Telefone: 31 99999-0001",
        "Assunto: Quero atendimento",
    ]
    results = []
    for m in msgs:
        payload = build_messages_upsert(instance=instance, from_number=from_number, text=m)
        results.append(await post_to_webhook(payload))
        time.sleep(0.2)
    return JSONResponse({"scenario": "lead3", "results": results})


@app.post("/api/scenario/lead1")
async def scenario_lead1(
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form("5531999000001"),
):
    payload = build_messages_upsert(
        instance=instance,
        from_number=from_number,
        text="Nome: João da Silva | Telefone: 31 99999-0001 | Assunto: Quero atendimento",
    )
    result = await post_to_webhook(payload)
    return JSONResponse({"scenario": "lead1", "result": result})


@app.post("/api/scenario/dedupe")
async def scenario_dedupe(
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form("5531999000001"),
):
    fixed_id = "SIM-DEDUPE-0001"
    payload1 = build_messages_upsert(instance=instance, from_number=from_number, text="Oi", msg_id=fixed_id)
    payload2 = build_messages_upsert(instance=instance, from_number=from_number, text="Oi", msg_id=fixed_id)

    r1 = await post_to_webhook(payload1)
    r2 = await post_to_webhook(payload2)
    return JSONResponse({"scenario": "dedupe", "results": [r1, r2]})


@app.post("/api/loadtest")
async def loadtest(
    instance: str = Form(DEFAULT_INSTANCE),
    users: int = Form(20),
    message: str = Form("Oi"),
):
    # Dispara N usuários fake com números sequenciais
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        headers = {"X-SIMULATOR-KEY": SIMULATOR_KEY} if SIMULATOR_KEY else {}
        for i in range(users):
            from_number = f"55319990{str(10000+i).zfill(5)}"
            payload = build_messages_upsert(instance=instance, from_number=from_number, text=message)
            r = await client.post(TARGET_WEBHOOK_URL, json=payload, headers=headers)
            results.append({"i": i, "status": r.status_code})
    return JSONResponse({"scenario": "loadtest", "users": users, "results": results[:50]})
