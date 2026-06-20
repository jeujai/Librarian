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

## Dual-branch workflow

This repo maintains two branches synced via `scripts/sync-branches.sh`. See memory: dual-branch sync.
