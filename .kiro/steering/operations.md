---
inclusion: auto
---

# Operations Reference

## Docker Compose

- The main compose file is `docker-compose.yml` (not `docker-compose.local.yml` which doesn't exist)
- Use `docker compose` (not `docker-compose` which isn't installed)

## Database Credentials (Docker)

All databases run inside Docker with these credentials:

| Service    | User       | Password   | Database/DB Name         | Port  |
|------------|------------|------------|--------------------------|-------|
| PostgreSQL | postgres   | postgres   | multimodal_librarian     | 5432  |
| Neo4j      | neo4j      | password       | neo4j                | 7687  |
| Milvus     | (none)     | (none)     | default                  | 19530 |
| Redis      | (none)     | (none)     | 0                        | 6379  |

## PostgreSQL Schema

- The application schema is `multimodal_librarian` (not `public`)
- When purging/resetting PostgreSQL, target the `multimodal_librarian` schema
- There are NO application tables in the `public` schema — `public_schema_init.sql` was emptied to prevent accidental creation
- **IMPORTANT**: If only purging data (no structural changes), TRUNCATE tables instead of dropping them. Dropping the schema destroys tables, types, functions, and constraints that the app needs.
- Data-only purge: `SELECT 'TRUNCATE TABLE multimodal_librarian.' || tablename || ' CASCADE;' FROM pg_tables WHERE schemaname = 'multimodal_librarian';` then execute the output
- Full structural reset (only if schema changed): `DROP SCHEMA IF EXISTS multimodal_librarian CASCADE; CREATE SCHEMA multimodal_librarian;`

## Neo4j Auth

- Inside Docker the password is set via `NEO4J_AUTH=neo4j/neo4j_password` in docker-compose.yml
- The reset script running from the host fails because `.env.local` has different credentials
- Use `docker compose exec neo4j cypher-shell -u neo4j -p neo4j_password` for direct access

## Resetting Databases — Procedure

1. **Stop the app first**: `docker compose stop app` — prevents stale connections, cached state, and the app auto-recreating tables mid-purge
2. Purge each database (see commands below)
3. Restart the app: `docker compose start app`

## Resetting Databases via Docker

```bash
# PostgreSQL - reset the multimodal_librarian schema
docker compose exec postgres psql -U postgres -d multimodal_librarian -c "DROP SCHEMA IF EXISTS multimodal_librarian CASCADE; CREATE SCHEMA multimodal_librarian;"

# Neo4j - delete all nodes and relationships
docker compose exec neo4j cypher-shell -u neo4j -p neo4j_password "MATCH (n) DETACH DELETE n"

# Redis - flush all
docker compose exec redis redis-cli FLUSHALL

# Milvus - use the reset script or API
venv/bin/python scripts/reset-all-databases.py --databases milvus --force
```

## Container Networking Gotchas

- The Milvus client defaults to `localhost` but inside the Docker container it needs to connect to `milvus` (the Docker service name). When running ad-hoc Python scripts inside the app container (e.g. `docker exec librarian-app-1 python3 -c "..."`), you must override the host to `milvus` instead of relying on the default.
- Similarly, other services use their Docker service names: `postgres`, `neo4j`, `redis`, `model-server`, `minio`, `etcd`.

## Document Upload

- Upload endpoint: `POST /api/documents/upload` (multipart form with `file` field)
- The file must be a PDF
- Example: `curl -X POST http://localhost:8000/api/documents/upload -F "file=@/path/to/file.pdf"`
