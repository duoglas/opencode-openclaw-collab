from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
import socket
import subprocess
import time
from dataclasses import asdict
from typing import Any, Protocol

from .bus import NatsBus
from .protocol import ChatMessage, TaskDispatch, TaskEvent, TaskResult, WorkerHeartbeat
from .store import Store
from .api import make_server
from .queue import enqueue_task, list_pending, get_task_payload, mark_task


DEFAULT_DISPATCH_SUBJECTS = "openclaw.dispatch.v1,op.task.home"
DEFAULT_RESULT_SUBJECTS = "openclaw.result.v1,op.result.controller"


class _Publisher(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None: ...


class _MessageStore(Protocol):
    def add_message(
        self, *, direction: str, subject: str, payload: dict[str, Any]
    ) -> None: ...


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


def normalize_subject_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return ""
    return p if p.endswith(".") else f"{p}."


def build_node_subject(prefix: str, node_id: str) -> str:
    return f"{normalize_subject_prefix(prefix)}{node_id}"


def _extract_trace_id(
    payload: dict[str, object], headers: dict[str, object] | None
) -> str:
    trace = str(
        payload.get("trace_id")
        or payload.get("trace")
        or payload.get("x_trace_id")
        or ""
    ).strip()
    if trace:
        return trace
    if not headers:
        return ""
    normalized = {str(k).strip().lower(): str(v).strip() for k, v in headers.items()}
    return (
        normalized.get("x-trace-id")
        or normalized.get("trace_id")
        or normalized.get("trace-id")
        or ""
    )


def build_chat_store_payload(
    *, subject: str, data: bytes, headers: dict[str, object] | None = None
) -> dict[str, object]:
    raw = data.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"text": raw}

    payload: dict[str, Any] = parsed if isinstance(parsed, dict) else {"value": parsed}
    raw_ts = payload.get("ts") or payload.get("timestamp") or payload.get("created_at")
    try:
        timestamp = float(raw_ts if raw_ts is not None else time.time())
    except (TypeError, ValueError):
        timestamp = time.time()
    trace_id = _extract_trace_id(payload, headers)

    enriched: dict[str, Any] = dict(payload)
    enriched["schema"] = str(enriched.get("schema") or "oc.chat.v1")
    enriched["subject"] = subject
    enriched["trace_id"] = trace_id
    enriched["timestamp"] = timestamp
    enriched["ts"] = timestamp
    return enriched


async def publish_result_to_subjects(
    *, bus: _Publisher, store: _MessageStore, subjects: list[str], result: TaskResult
) -> None:
    payload = json.loads(result.to_bytes().decode())
    blob = result.to_bytes()
    for subject in subjects:
        store.add_message(direction="out", subject=subject, payload=payload)
        await bus.publish(subject, blob)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenCode NATS bridge daemon (MVP)")
    p.add_argument("--nats", default=os.getenv("NATS_URL", "nats://127.0.0.1:4222"))
    p.add_argument(
        "--creds",
        default=os.getenv("NATS_CREDS", ""),
        help="path to NATS .creds (JWT auth)",
    )
    p.add_argument(
        "--node",
        default=os.getenv("OC_NODE_ID", os.getenv("NODE_ID", socket.gethostname())),
    )
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
    p.add_argument(
        "--dispatch", default=os.getenv("DISPATCH_SUBJECT", "")
    )  # legacy single-subject fallback
    p.add_argument(
        "--chat-to-prefix", default=os.getenv("CHAT_TO_PREFIX", "oc.chat.to.")
    )
    p.add_argument(
        "--chat-from-prefix", default=os.getenv("CHAT_FROM_PREFIX", "oc.chat.from.")
    )
    p.add_argument("--chat-to-subject", default=os.getenv("CHAT_TO_SUBJECT", ""))
    p.add_argument("--chat", default=os.getenv("CHAT_TO_SUBJECT", ""))
    p.add_argument(
        "--result-subjects",
        default=os.getenv("RESULT_SUBJECTS", DEFAULT_RESULT_SUBJECTS),
        help="comma-separated subjects to publish results to (new+legacy)",
    )
    p.add_argument(
        "--result", default=os.getenv("RESULT_SUBJECT", "")
    )  # legacy single-subject fallback
    p.add_argument(
        "--events-prefix", default=os.getenv("EVENTS_PREFIX", "oc.task.event")
    )
    p.add_argument(
        "--heartbeat", default=os.getenv("HEARTBEAT_SUBJECT", "oc.worker.heartbeat")
    )
    p.add_argument(
        "--db",
        default=os.getenv(
            "OCBRIDGE_DB", os.path.expanduser("~/.local/share/ocbridge/bridge.db")
        ),
    )
    p.add_argument(
        "--opencode-serve-host", default=os.getenv("OPENCODE_SERVE_HOST", "127.0.0.1")
    )
    p.add_argument(
        "--opencode-serve-port",
        type=int,
        default=int(os.getenv("OPENCODE_SERVE_PORT", "4096")),
    )
    p.add_argument(
        "--run-timeout", type=int, default=int(os.getenv("RUN_TIMEOUT", "900"))
    )
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
    chat_to_subject = (
        args.chat_to_subject
        or args.chat
        or build_node_subject(args.chat_to_prefix, args.node)
    )
    chat_from_subject = build_node_subject(args.chat_from_prefix, args.node)
    if not dispatch_subjects:
        raise RuntimeError("no dispatch subjects configured")
    if not result_subjects:
        raise RuntimeError("no result subjects configured")

    bus = NatsBus(args.nats, f"ocbridge-{args.node}", creds_path=args.creds)
    await bus.connect()

    serve_url = await ensure_opencode_serve(
        args.opencode_serve_host, args.opencode_serve_port
    )
    loop = asyncio.get_running_loop()

    def publish_from_api(subject: str, blob: bytes, payload: dict[str, object]) -> None:
        async def _publish() -> None:
            store.add_message(direction="out", subject=subject, payload=payload)
            await bus.publish(subject, blob)

        future = asyncio.run_coroutine_threadsafe(_publish(), loop)

        def _consume_result(done_future: concurrent.futures.Future[None]) -> None:
            try:
                done_future.result()
            except Exception:
                return

        future.add_done_callback(_consume_result)

    # Start local API for Route-A (TUI plugin) integration.
    # Keep it intentionally simple: HTTP on localhost exposing status/inbox.
    api_host = os.getenv("OCBRIDGE_API_HOST", "127.0.0.1")
    api_port = int(os.getenv("OCBRIDGE_API_PORT", "7341"))
    # Executor queue for manual-mode run requests.
    exec_queue: asyncio.Queue[str] = asyncio.Queue()

    # Keep a handle to the HTTP server so we can toggle mode dynamically (/mode)
    # and enqueue manual runs (/run).
    global _ocbridge_httpd  # noqa: PLW0603
    _ocbridge_httpd = make_server(
        args.db,
        host=api_host,
        port=api_port,
        mode=args.mode,
        node_id=args.node,
        nats_url=args.nats,
        exec_queue=exec_queue,
        publish_callback=publish_from_api,
        chat_from_prefix=args.chat_from_prefix,
    )
    loop.run_in_executor(None, _ocbridge_httpd.serve_forever)

    async def publish_event(
        task_id: str,
        phase: str,
        message: str = "",
        progress: int = 0,
        session_id: str = "",
    ) -> None:
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
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=args.run_timeout
            )
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
            await publish_event(
                task.task_id,
                "finished" if proc.returncode == 0 else "failed",
                f"exit={proc.returncode}",
            )
            try:
                store._conn.execute(
                    "UPDATE messages SET status=? WHERE task_id=?",
                    ("done" if proc.returncode == 0 else "failed", task.task_id),
                )
                store._conn.commit()
            except Exception:
                pass
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
            try:
                store._conn.execute(
                    "UPDATE messages SET status='timeout' WHERE task_id=?",
                    (task.task_id,),
                )
                store._conn.commit()
            except Exception:
                pass

    async def handle_dispatch(msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
            task = TaskDispatch.from_payload(payload)
            enqueue_task(store, payload, subject=msg.subject)
        except Exception:
            return

        # manual mode: only enqueue into inbox. The TUI plugin can later claim/run it.
        # dynamic mode: the local API can change _ocbridge_httpd.mode at runtime.
        current_mode = getattr(globals().get("_ocbridge_httpd"), "mode", args.mode)  # type: ignore
        if current_mode == "manual":
            await publish_event(task.task_id, "queued", "stored (manual mode)")
            return

        # auto mode: run immediately, but also do a best-effort compensation scan at startup and periodically.
        try:
            store._conn.execute(
                "UPDATE messages SET status='running' WHERE task_id=?", (task.task_id,)
            )
            store._conn.commit()
        except Exception:
            pass

        await _run_task(task)

    async def handle_chat(msg) -> None:
        payload = build_chat_store_payload(
            subject=msg.subject,
            data=msg.data,
            headers=getattr(msg, "header", None),
        )
        payload.setdefault("reply_subject", chat_from_subject)
        store.add_message(direction="in", subject=msg.subject, payload=payload)

    # subscribe to dispatch (new + legacy)
    for dispatch_subject in dispatch_subjects:
        await bus.subscribe(dispatch_subject, cb=handle_dispatch)
    await bus.subscribe(chat_to_subject, cb=handle_chat)

    async def compensate_loop() -> None:
        """Auto-compensation (MVP): in auto mode, periodically scan for pending+unclaimed tasks
        and move them to ready so the existing executor path can run them.

        Note: this is intentionally conservative to avoid stealing claimed tasks.
        """
        if args.mode != "auto":
            return
        interval = int(os.getenv("OCBRIDGE_COMPENSATE_INTERVAL", "10"))
        while True:
            try:
                rows = list_pending(store, limit=50)
                for r in rows:
                    payload = (r.get("payload") or {}) if isinstance(r, dict) else {}
                    task_id = str(payload.get("task_id") or r.get("task_id") or "").strip()
                    claimed_by = str(r.get("claimed_by") or "").strip()
                    if not task_id or claimed_by:
                        continue
                    # mark ready and enqueue for execution
                    mark_task(store, task_id, "ready")
                    try:
                        await exec_queue.put(task_id)
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(max(2, interval))

    async def manual_exec_loop() -> None:
        # Wait for /run OR compensate loop to enqueue task_id, then execute with the same logic as auto mode.
        while True:
            task_id = await exec_queue.get()
            try:
                payload = get_task_payload(store, task_id)
                if not payload:
                    continue
                task = TaskDispatch.from_payload(payload)
                # mark running
                try:
                    store._conn.execute(
                        "UPDATE messages SET status='running' WHERE task_id=?",
                        (task_id,),
                    )
                    store._conn.commit()
                except Exception:
                    pass
                await _run_task(task)
            finally:
                exec_queue.task_done()

    async def heartbeat_loop() -> None:
        while True:
            hb = WorkerHeartbeat(
                node_id=args.node, capabilities=[args.cap], ts=time.time(), busy=False
            )
            payload = json.loads(hb.to_bytes().decode())
            store.add_message(direction="out", subject=args.heartbeat, payload=payload)
            await bus.publish(args.heartbeat, hb.to_bytes())
            await asyncio.sleep(60)

    await asyncio.gather(manual_exec_loop(), compensate_loop(), heartbeat_loop())


if __name__ == "__main__":
    asyncio.run(main())
