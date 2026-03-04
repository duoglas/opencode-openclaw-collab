# Multi-node test (Docker Compose)

## Quick start

```bash
cd /home/duoglas/.openclaw/workspace-taizi/opencode-openclaw-collab

docker compose -f compose/docker-compose.multinode.yml up -d --build

# Verify JetStream
curl -s http://127.0.0.1:8222/jsz | head -c 200 ; echo

# Tail bridge logs
docker compose -f compose/docker-compose.multinode.yml logs -f bridge1
```

## Notes
- This compose file is for local multi-node testing. Production deployment should use JWT/NKey and ACL.
- If `ghcr.io/opencode-ai/opencode:latest` is not available, replace `worker1` with a locally built image.
