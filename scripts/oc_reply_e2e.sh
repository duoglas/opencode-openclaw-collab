#!/usr/bin/env bash
set -euo pipefail

API_BASE="${OCBRIDGE_API:-http://127.0.0.1:7341}"
NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "PYTHON_BIN '$PYTHON_BIN' not executable. Set PYTHON_BIN to a Python with nats-py installed." >&2
  exit 1
fi

API_BASE="$API_BASE" NATS_URL="$NATS_URL" "$PYTHON_BIN" - <<'PY'
import asyncio
import json
import os
import time
import urllib.request

from nats.aio.client import Client as NATS


def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    raw = None
    headers = {"content-type": "application/json"}
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=raw, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body or "{}")


async def main() -> None:
    api_base = os.environ["API_BASE"].rstrip("/")
    nats_url = os.environ["NATS_URL"]

    st = http_json("GET", f"{api_base}/status")
    node_id = str(st.get("node") or "").strip()
    if not node_id:
        raise RuntimeError("/status did not return node id; ensure bridge daemon started with NODE_ID")

    task_id = f"TASK-E2E-{int(time.time() * 1000)}"
    e2e_text = f"routeA-e2e-{int(time.time() * 1000)}"
    from_subject = f"oc.chat.from.{node_id}"
    to_subject = f"oc.chat.to.{node_id}"

    nc = NATS()
    await nc.connect(servers=[nats_url], name=f"ocreply-e2e-{node_id}")
    loop = asyncio.get_running_loop()
    received: asyncio.Future[bytes] = loop.create_future()

    async def on_chat(msg) -> None:
        data = msg.data
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return
        if payload.get("task_id") == task_id and payload.get("text") == e2e_text:
            if not received.done():
                received.set_result(data)

    sub = await nc.subscribe(from_subject, cb=on_chat)
    await nc.flush()

    simulated_inbound = {
        "schema": "oc.chat.v1",
        "task_id": task_id,
        "from_id": "openclaw",
        "to_id": f"node:{node_id}",
        "text": "simulated inbound to-node message",
        "ts": time.time(),
    }
    await nc.publish(to_subject, json.dumps(simulated_inbound, ensure_ascii=False).encode("utf-8"))
    await nc.flush()

    out = http_json(
        "POST",
        f"{api_base}/publish",
        {
            "kind": "chat",
            "task_id": task_id,
            "text": e2e_text,
        },
    )
    if not out.get("ok"):
        raise RuntimeError(f"/publish failed: {out}")

    blob = await asyncio.wait_for(received, timeout=8)
    published = json.loads(blob.decode("utf-8"))

    assert published.get("schema") == "oc.chat.v1", published
    assert published.get("task_id") == task_id, published
    assert published.get("text") == e2e_text, published
    assert published.get("from_id") == f"node:{node_id}", published

    await sub.unsubscribe()
    await nc.drain()
    print(f"E2E OK: {to_subject} simulated, /publish -> {from_subject} received expected payload")


if __name__ == "__main__":
    asyncio.run(main())
PY
