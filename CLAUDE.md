# Project Instructions

## Service lifecycle (CRITICAL — timestamp corruption risk)

Never stop or restart individual database containers. Always use the scripts:

```bash
scripts/stop-databases.sh    # correct stop order: milvus → etcd → minio → postgres → neo4j → redis
scripts/start-databases.sh   # correct start order: etcd → minio → postgres → neo4j → redis → milvus
```

Milvus must stop FIRST (so it flushes to etcd/minio cleanly) and start LAST (so etcd/minio are ready). Violating this order causes "Timestamp lag too large" — the query engine permanently refuses search until etcd/milvus/minio are restored from backup.

`docker restart` on individual services is also unsafe for the same reason.

## Before shutting down Colima or the machine

```bash
scripts/stop-databases.sh
colima stop  # only after databases are cleanly stopped
```

## Milvus backup/restore

```bash
# Backup (stops services, snapshots volumes, restarts)
scripts/backup-physical-volumes.sh

# Restore location
ls /Volumes/CORSAIR/librarian_database_backups/
```

## Model server (host-native)

The model server runs natively on the host (NOT in Docker) so the bi-encoder and cross-encoder can use Apple Metal (MPS). It is not managed by `docker compose`.

```bash
scripts/start-model-server-native.sh   # bind 0.0.0.0:8001; EMBEDDING_DEVICE=mps, CROSS_ENCODER_DEVICE=mps
```

- The app and celery-worker reach it at `http://host.docker.internal:8001` (`MODEL_SERVER_URL`).
- A launchd agent (`com.librarian.model-server.plist`) is provided to auto-start it on boot, but it needs a one-time **Full Disk Access** grant for `/bin/bash` (System Settings → Privacy & Security → Full Disk Access) because the repo lives on an external volume (`/Volumes/CORSAIR`). Without that grant launchd gets "Operation not permitted" — start it manually instead.
- `scripts/stack-up.sh` / `scripts/stack-down.sh` also start/stop it (it is not a compose service in either script).
- If it is down, the app falls back to local CPU embedding — nothing hard-breaks, but MPS only works via this native process.
- Do NOT re-add a `model-server` service to `docker-compose.yml`; it would fight for host port 8001.

## Dual-branch workflow

This repo maintains two branches synced via `scripts/sync-branches.sh`. See memory: dual-branch sync.
