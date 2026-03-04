from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import time
from dataclasses import asdict

from .bus import NatsBus
from .protocol import ChatMessage, TaskDispatch, TaskEvent, TaskResult, WorkerHeartbeat
from .store import Store


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenCode NATS bridge daemon (MVP)")
    p.add_argument("--nats", default=os.getenv("NATS_URL", "nats://127.0.0.1:4222"))
    p.add_argument("--node", default=os.getenv("NODE_ID", socket.gethostname()))
    p.add_argument("--cap", default=os.getenv("CAPABILITY", "coding"))
    p.add_argument("--dispatch", default=os.getenv("DISPATCH_SUBJECT", "oc.task.dispatch.coding"))
    p.add_argument("--chat", default=os.getenv("CHAT_TO_SUBJECT", ""))
    p.add_argument("--result", default=os.getenv("RESULT_SUBJECT", "oc.task.result"))
    p.add_argument("--events-prefix", default=os.getenv("EVENTS_PREFIX", "oc.task.event"))
    p.add_argument("--heartbeat", default=os.getenv("HEARTBEAT_SUBJECT", "oc.worker.heartbeat"))
    p.add_argument("--db", default=os.getenv("OCBRIDGE_DB", os.path.expanduser("~/.local/share/ocbridge/bridge.db")))
    p.add_argument("--opencode-serve-host", default=os.getenv("OPENCODE_SERVE_HOST", "127.0.0.1"))
    p.add_argument("--opencode-serve-port", type=int, default=int(os.getenv("OPENCODE_SERVE_PORT", "4096")))
    p.add_argument("--run-timeout", type=int, default=int(os.getenv("RUN_TIMEOUT", "900")))
    return p.parse_args()


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


async def ensure_opencode_serve(host: str, port: int) -> str:
    """Ensure opencode serve is up locally.

    For MVP we best-effort start it if missing.
    """
    url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        return url

    opencode_bin = "opencode"
    subprocess.Popen(
        [opencode_bin, "serve", "--hostname", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=os.environ.copy(),
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        if _is_port_open(host, port):
            return url
        await asyncio.sleep(0.2)

    return url


async def main() -> None:
    args = parse_args()
    store = Store(args.db)

    bus = NatsBus(args.nats, f"ocbridge-{args.node}")
    await bus.connect()

    serve_url = await ensure_opencode_serve(args.opencode_serve_host, args.opencode_serve_port)

    async def publish_event(task_id: str, phase: str, message: str = "", progress: int = 0, session_id: str = "") -> None:
        subject = f"{args.events_prefix}.{task_id}"
        ev = TaskEvent(
            task_id=task_id,
            node_id=args.node,
            phase=phase,
            progress=progress,
            message=message,
            ts=time.time(),
            serve_url=serve_url,
            session_id=session_id,
        )
        payload = json.loads(ev.to_bytes().decode())
        store.add_message(direction="out", subject=subject, payload=payload)
        await bus.publish(subject, ev.to_bytes())

    async def handle_dispatch(msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
            store.add_message(direction="in", subject=msg.subject, payload=payload)
            task = TaskDispatch.from_payload(payload)
        except Exception as exc:
            return

        await publish_event(task.task_id, "queued", "accepted")
        await publish_event(task.task_id, "running", f"model={task.model}")

        cmd = [
            "opencode",
            "run",
            "--attach",
            serve_url,
            "--model",
            task.model,
            task.prompt,
        ]
        started = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.run_timeout)
            res = TaskResult(
                task_id=task.task_id,
                node_id=args.node,
                exit_code=proc.returncode,
                summary="ok" if proc.returncode == 0 else "failed",
                artifacts=[],
                stdout_tail=(proc.stdout or "")[-8000:],
                stderr_tail=(proc.stderr or "")[-4000:],
                duration_sec=round(time.time() - started, 2),
            )
            res_payload = json.loads(res.to_bytes().decode())
            store.add_message(direction="out", subject=args.result, payload=res_payload)
            await bus.publish(args.result, res.to_bytes())
            await publish_event(task.task_id, "finished" if proc.returncode == 0 else "failed", f"exit={proc.returncode}")
        except subprocess.TimeoutExpired:
            res = TaskResult(
                task_id=task.task_id,
                node_id=args.node,
                exit_code=124,
                summary="timeout",
                artifacts=[],
                stdout_tail="",
                stderr_tail=f"timeout after {args.run_timeout}s",
                duration_sec=round(time.time() - started, 2),
            )
            res_payload = json.loads(res.to_bytes().decode())
            store.add_message(direction="out", subject=args.result, payload=res_payload)
            await bus.publish(args.result, res.to_bytes())
            await publish_event(task.task_id, "failed", "timeout")

    # subscribe to dispatch
    await bus.subscribe(args.dispatch, cb=handle_dispatch)

    async def heartbeat_loop() -> None:
        while True:
            hb = WorkerHeartbeat(node_id=args.node, capabilities=[args.cap], ts=time.time(), busy=False)
            payload = json.loads(hb.to_bytes().decode())
            store.add_message(direction="out", subject=args.heartbeat, payload=payload)
            await bus.publish(args.heartbeat, hb.to_bytes())
            await asyncio.sleep(60)

    await heartbeat_loop()


if __name__ == "__main__":
    asyncio.run(main())
