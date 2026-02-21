# -----------------------------------------------------------------------------
# whatsapp-simulator — app/main.py
# -----------------------------------------------------------------------------
import os
import time
import uuid
import asyncio
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# -----------------------------------------------------------------------------
# Config (env)
# -----------------------------------------------------------------------------
TARGET_WEBHOOK_URL = os.getenv("TARGET_WEBHOOK_URL", "").strip()
SIMULATOR_KEY = os.getenv("SIMULATOR_KEY", "").strip()

DEFAULT_INSTANCE = os.getenv("DEFAULT_INSTANCE", "agente001").strip()
DEFAULT_FROM_NUMBER = os.getenv("DEFAULT_FROM_NUMBER", "5531999999999").strip()

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


def mk_id(prefix: str = "sim") -> str:
    """Gera message_id controlável (bom para testar dedup)."""
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


async def send_sim(
    *,
    instance: str,
    from_number: str,
    text: str,
    message_id: Optional[str] = None,
    push_name: str = "Teste",
    event: str = "messages.upsert",
    status: str = "MESSAGE",
):
    """
    Envia payload simplificado ao whatsapp-agent-dev /webhook.
    O whatsapp-agent converte internamente para formato Evolution (DEV-only).
    """
    if not TARGET_WEBHOOK_URL:
        raise RuntimeError("TARGET_WEBHOOK_URL não definido")

    payload = {
        "source": "simulator",
        "instance": instance,
        "message_id": message_id or mk_id(),
        "from_number": from_number,
        "push_name": push_name,
        "text": text,
        "event": event,
        "status": status,
    }

    headers = {}
    if SIMULATOR_KEY:
        headers["X-SIMULATOR-KEY"] = SIMULATOR_KEY

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(TARGET_WEBHOOK_URL, json=payload, headers=headers)
        return r.status_code, r.text


@app.get("/", response_class=HTMLResponse)
async def home(req: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "target": TARGET_WEBHOOK_URL,
            "default_instance": DEFAULT_INSTANCE,
            "default_from": DEFAULT_FROM_NUMBER,
        },
    )


@app.post("/send", response_class=HTMLResponse)
async def send_form(
    req: Request,
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form(DEFAULT_FROM_NUMBER),
    text: str = Form("Oi"),
    push_name: str = Form("Teste"),
):
    code, body = await send_sim(
        instance=instance.strip(),
        from_number=from_number.strip(),
        text=text.strip(),
        push_name=push_name.strip() or "Teste",
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "target": TARGET_WEBHOOK_URL,
            "default_instance": instance.strip(),
            "default_from": from_number.strip(),
            "result": f"HTTP {code}: {body[:800]}",
        },
    )


@app.post("/scenario/lead3", response_class=HTMLResponse)
async def scenario_lead3(
    req: Request,
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form(DEFAULT_FROM_NUMBER),
):
    """
    Cenário: lead em 3 passos.
    Ajuste os textos conforme suas rules.py (intenção -> nome -> telefone/assunto).
    """
    instance = instance.strip()
    from_number = from_number.strip()

    steps = [
        "Quero atendimento",
        "Nome: Fulano de Tal",
        "Telefone: 31999999999\nAssunto: Suporte",
    ]

    out = []
    for text in steps:
        code, _ = await send_sim(instance=instance, from_number=from_number, text=text)
        out.append(f"{text} -> HTTP {code}")
        await asyncio.sleep(0.6)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "target": TARGET_WEBHOOK_URL,
            "default_instance": instance,
            "default_from": from_number,
            "result": "\n".join(out),
        },
    )


@app.post("/scenario/dedup", response_class=HTMLResponse)
async def scenario_dedup(
    req: Request,
    instance: str = Form(DEFAULT_INSTANCE),
    from_number: str = Form(DEFAULT_FROM_NUMBER),
):
    """
    Cenário: dedup.
    Envia duas vezes o MESMO message_id.
    """
    instance = instance.strip()
    from_number = from_number.strip()

    mid = mk_id("dedup")
    out = []

    for i in range(2):
        code, _ = await send_sim(
            instance=instance,
            from_number=from_number,
            text="Oi (dedup)",
            message_id=mid,
        )
        out.append(f"try#{i+1} mid={mid} -> HTTP {code}")
        await asyncio.sleep(0.3)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "target": TARGET_WEBHOOK_URL,
            "default_instance": instance,
            "default_from": from_number,
            "result": "\n".join(out),
        },
    )
