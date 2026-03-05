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
from .api import make_server


DEFAULT_DISPATCH_SUBJECTS = "openclaw.dispatch.v1,op.task.home"
DEFAULT_RESULT_SUBJECTS = "openclaw.result.v1,op.result.controller"


def parse_subject_list(raw: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in (raw or "").split(","):
        s = item.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        items.append(s)
    return items


def resolve_subjects(primary_csv: str, legacy_single: str = "") -> list[str]:
    merged = parse_subject_list(primary_csv)
    if legacy_single and legacy_single not in merged:
        merged.append(legacy_single)
    return merged


async def publish_result_to_subjects(*, bus: NatsBus, store: Store, subjects: list[str], result: TaskResult) -> None:
    payload = json.loads(result.to_bytes().decode())
    blob = result.to_bytes()
    for subject in subjects:
        store.add_message(direction="out", subject=subject, payload=payload)
        await bus.publish(subject, blob)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenCode NATS bridge daemon (MVP)")
    p.add_argument("--nats", default=os.getenv("NATS_URL", "nats://127.0.0.1:4222"))
    p.add_argument("--creds", default=os.getenv("NATS_CREDS", ""), help="path to NATS .creds (JWT auth)")
    p.add_argument("--node", default=os.getenv("NODE_ID", socket.gethostname()))
    p.add_argument("--cap", default=os.getenv("CAPABILITY", "coding"))

    # Execution mode
    # - manual: never run automatically; only enqueue to inbox (TUI can claim/run)
    # - auto: run immediately on dispatch (for unattended workers)
    p.add_argument(
        "--mode",
        default=os.getenv("OCBRIDGE_MODE", "auto"),
        choices=["auto", "manual"],
        help="dispatch handling mode: auto runs immediately; manual only stores to inbox",
    )

    # M1-FREEZE-v1.0 subjects
    p.add_argument(
        "--dispatch-subjects",
        default=os.getenv("DISPATCH_SUBJECTS", DEFAULT_DISPATCH_SUBJECTS),
        help="comma-separated subjects to subscribe for dispatch (new+legacy)",
    )
    p.add_argument("--dispatch", default=os.getenv("DISPATCH_SUBJECT", ""))  # legacy single-subject fallback
    p.add_argument("--chat", default=os.getenv("CHAT_TO_SUBJECT", ""))
    p.add_argument(
        "--result-subjects",
        default=os.getenv("RESULT_SUBJECTS", DEFAULT_RESULT_SUBJECTS),
        help="comma-separated subjects to publish results to (new+legacy)",
    )
    p.add_argument("--result", default=os.getenv("RESULT_SUBJECT", ""))  # legacy single-subject fallback
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

    dispatch_subjects = resolve_subjects(args.dispatch_subjects, args.dispatch)
    result_subjects = resolve_subjects(args.result_subjects, args.result)
    if not dispatch_subjects:
        raise RuntimeError("no dispatch subjects configured")
    if not result_subjects:
        raise RuntimeError("no result subjects configured")

    bus = NatsBus(args.nats, f"ocbridge-{args.node}", creds_path=args.creds)
    await bus.connect()

    serve_url = await ensure_opencode_serve(args.opencode_serve_host, args.opencode_serve_port)

    # Start local API for Route-A (TUI plugin) integration.
    # Keep it intentionally simple: HTTP on localhost exposing status/inbox.
    api_host = os.getenv("OCBRIDGE_API_HOST", "127.0.0.1")
    api_port = int(os.getenv("OCBRIDGE_API_PORT", "7341"))
    # Keep a handle to the HTTP server so we can toggle mode dynamically (/mode).
    global _ocbridge_httpd  # noqa: PLW0603
    _ocbridge_httpd = make_server(args.db, host=api_host, port=api_port, mode=args.mode, node_id=args.node, nats_url=args.nats)
    asyncio.get_running_loop().run_in_executor(None, _ocbridge_httpd.serve_forever)

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

    async def _run_task(task: TaskDispatch) -> None:
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
            await publish_result_to_subjects(
                bus=bus,
                store=store,
                subjects=result_subjects,
                result=res,
            )
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
            await publish_result_to_subjects(
                bus=bus,
                store=store,
                subjects=result_subjects,
                result=res,
            )
            await publish_event(task.task_id, "failed", "timeout")

    async def handle_dispatch(msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
            store.add_message(direction="in", subject=msg.subject, payload=payload)
            task = TaskDispatch.from_payload(payload)
        except Exception:
            return

        # manual mode: only enqueue into inbox. The TUI plugin can later claim/run it.
        # dynamic mode: the local API can change _ocbridge_httpd.mode at runtime.
        current_mode = getattr(globals().get("_ocbridge_httpd"), "mode", args.mode)  # type: ignore
        if current_mode == "manual":
            await publish_event(task.task_id, "queued", "stored (manual mode)")
            return

        await _run_task(task)

    # subscribe to dispatch (new + legacy)
    for dispatch_subject in dispatch_subjects:
        await bus.subscribe(dispatch_subject, cb=handle_dispatch)

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
