from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Literal, Optional
import json


def _now() -> float:
    return time.time()


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


Schema = Literal[
    "oc.task.submit.v1",
    "oc.task.dispatch.v1",
    "oc.task.event.v1",
    "oc.task.result.v1",
    "oc.chat.v1",
    "oc.worker.heartbeat.v1",
]

Capability = Literal["coding", "doc", "qa", "ops"]


@dataclass
class TaskSubmit:
    schema: Literal["oc.task.submit.v1"] = "oc.task.submit.v1"
    task_id: str = ""
    dedupe_key: str = ""
    capability: Capability = "coding"
    title: str = ""
    prompt: str = ""
    model: str = "openai/gpt-5.3-codex"
    workdir: str = ""
    timeout_sec: int = 1800
    created_at: float = 0.0
    from_node: str = ""

    @staticmethod
    def new(*, title: str, prompt: str, from_node: str, capability: Capability = "coding", model: str = "openai/gpt-5.3-codex", workdir: str = "", timeout_sec: int = 1800, dedupe_key: str = "") -> "TaskSubmit":
        return TaskSubmit(
            task_id=f"TASK-{uuid.uuid4().hex[:12]}",
            title=title,
            prompt=prompt,
            from_node=from_node,
            capability=capability,
            model=model,
            workdir=workdir,
            timeout_sec=timeout_sec,
            dedupe_key=dedupe_key,
            created_at=_now(),
        )

    def to_bytes(self) -> bytes:
        return _dumps(asdict(self))


@dataclass
class TaskDispatch:
    schema: Literal["oc.task.dispatch.v1"] = "oc.task.dispatch.v1"
    task_id: str = ""
    capability: Capability = "coding"
    prompt: str = ""
    model: str = "openai/gpt-5.3-codex"
    workdir: str = ""
    timeout_sec: int = 1800
    dedupe_key: str = ""
    requires_approval: bool = False
    created_at: float = 0.0
    reply_subject: str = "oc.task.result"

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "TaskDispatch":
        return TaskDispatch(
            task_id=str(payload.get("task_id", "")),
            capability=str(payload.get("capability", "coding")),
            prompt=str(payload.get("prompt", "")),
            model=str(payload.get("model", "openai/gpt-5.3-codex")),
            workdir=str(payload.get("workdir", "")),
            timeout_sec=int(payload.get("timeout_sec", 1800)),
            dedupe_key=str(payload.get("dedupe_key", "")),
            requires_approval=bool(payload.get("requires_approval", False)),
            created_at=float(payload.get("created_at", 0.0) or 0.0),
            reply_subject=str(payload.get("reply_subject", "oc.task.result")),
        )


@dataclass
class TaskEvent:
    schema: Literal["oc.task.event.v1"] = "oc.task.event.v1"
    task_id: str = ""
    node_id: str = ""
    phase: str = "queued"
    progress: int = 0
    message: str = ""
    ts: float = 0.0
    serve_url: str = ""
    session_id: str = ""

    def to_bytes(self) -> bytes:
        d = asdict(self)
        if not self.ts:
            d["ts"] = _now()
        return _dumps(d)


@dataclass
class TaskResult:
    schema: Literal["oc.task.result.v1"] = "oc.task.result.v1"
    task_id: str = ""
    node_id: str = ""
    exit_code: int = 1
    summary: str = ""
    artifacts: list[str] = None  # type: ignore
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_sec: float = 0.0

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "TaskResult":
        return TaskResult(
            task_id=str(payload.get("task_id", "")),
            node_id=str(payload.get("node_id", payload.get("node", "")) or ""),
            exit_code=int(payload.get("exit_code", 1)),
            summary=str(payload.get("summary", "")),
            artifacts=list(payload.get("artifacts", []) or []),
            stdout_tail=str(payload.get("stdout_tail", payload.get("stdout", "")) or "")[-8000:],
            stderr_tail=str(payload.get("stderr_tail", payload.get("stderr", "")) or "")[-4000:],
            duration_sec=float(payload.get("duration_sec", 0.0) or 0.0),
        )

    def to_bytes(self) -> bytes:
        if self.artifacts is None:
            self.artifacts = []
        return _dumps(asdict(self))


@dataclass
class ChatMessage:
    schema: Literal["oc.chat.v1"] = "oc.chat.v1"
    task_id: str = ""
    session_id: str = ""
    from_id: str = ""
    to_id: str = ""
    text: str = ""
    ts: float = 0.0

    def to_bytes(self) -> bytes:
        d = asdict(self)
        if not self.ts:
            d["ts"] = _now()
        return _dumps(d)


@dataclass
class WorkerHeartbeat:
    schema: Literal["oc.worker.heartbeat.v1"] = "oc.worker.heartbeat.v1"
    node_id: str = ""
    capabilities: list[Capability] = None  # type: ignore
    ts: float = 0.0
    busy: bool = False
    running_task_id: str = ""

    def to_bytes(self) -> bytes:
        d = asdict(self)
        if d.get("capabilities") is None:
            d["capabilities"] = []
        if not d.get("ts"):
            d["ts"] = _now()
        return _dumps(d)
