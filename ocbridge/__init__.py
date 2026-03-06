"""ocbridge: OpenCode <-> OpenClaw (NATS) bridge runtime.

This package will host:
- nats bridge daemon (long-lived)
- message protocol definitions
- local store (sqlite/jsonl)
- optional OpenCode command integration helpers

Design reference:
- docs/03-opencode-plugin-NATS双向通信设计.md
"""

__version__ = "0.2.0"
