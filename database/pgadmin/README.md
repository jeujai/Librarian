# pgAdmin Configuration for Local Development

This directory contains configuration files for pgAdmin, the PostgreSQL administration tool used in local development.

## Quick Start

1. **Start services with admin tools profile:**
   ```bash
   docker-compose -f docker-compose.local.yml --profile admin-tools up -d
   ```

2. **Access pgAdmin:**
   - URL: http://localhost:5050
   - Email: admin@multimodal-librarian.local
   - Password: admin

3. **The PostgreSQL server is pre-configured** and should appear automatically in the server list.

## Server Configuration

The PostgreSQL server is automatically configured with these settings:

- **Server Name:** Multimodal Librarian - Local PostgreSQL
- **Host:** postgres (Docker service name)
- **Port:** 5432
- **Database:** multimodal_librarian
- **Username:** ml_user
- **Password:** ml_password (you'll be prompted to enter this)

## Files

- `servers.json` - Pre-configured server definitions for pgAdmin
- `README.md` - This documentation file

## Common Tasks

### Viewing Database Schema

1. Connect to the server (enter password: `ml_password`)
2. Navigate to: Servers → Multimodal Librarian → Databases → multimodal_librarian → Schemas → public → Tables

### Running Queries

1. Right-click on the database → Query Tool
2. Write your SQL queries and execute them

### Monitoring Performance

1. Navigate to: Servers → Multimodal Librarian → Databases → multimodal_librarian
2. Right-click → Dashboard to see performance metrics

### Backup and Restore

1. **Backup:** Right-click database → Backup...
2. **Restore:** Right-click database → Restore...

## Environment Variables

You can customize pgAdmin settings in your `.env.local` file:

```bash
# pgAdmin Configuration
PGADMIN_DEFAULT_EMAIL=your-email@example.com
PGADMIN_DEFAULT_PASSWORD=your-secure-password
PGADMIN_PORT=5050
```

## Troubleshooting

### Cannot Connect to PostgreSQL Server

1. **Check if PostgreSQL is running:**
   ```bash
   docker-compose -f docker-compose.local.yml ps postgres
   ```

2. **Check PostgreSQL logs:**
   ```bash
   docker-compose -f docker-compose.local.yml logs postgres
   ```

3. **Verify network connectivity:**
   ```bash
   docker-compose -f docker-compose.local.yml exec pgadmin ping postgres
   ```

### pgAdmin Won't Start

1. **Check pgAdmin logs:**
   ```bash
   docker-compose -f docker-compose.local.yml logs pgadmin
   ```

2. **Reset pgAdmin data:**
   ```bash
   docker-compose -f docker-compose.local.yml down
   docker volume rm multimodal-librarian-local_pgadmin_data
   docker-compose -f docker-compose.local.yml --profile admin-tools up -d
   ```

### Server Configuration Not Loading

1. **Check if servers.json is mounted correctly:**
   ```bash
   docker-compose -f docker-compose.local.yml exec pgadmin ls -la /pgadmin4/
   ```

2. **Manually add server:**
   - Click "Add New Server"
   - Use the connection details listed above

## Security Notes

- **Default credentials are for development only** - change them for any shared environments
- **No SSL/TLS** is configured for local development
- **Network access** is restricted to the Docker network

## Advanced Configuration

### Custom pgAdmin Configuration

Create a `config_local.py` file to override pgAdmin settings:

```python
# Custom pgAdmin configuration
ENHANCED_COOKIE_PROTECTION = False
LOGIN_BANNER = "Multimodal Librarian - Local Development"
UPGRADE_CHECK_ENABLED = False
```

Mount it in docker-compose.local.yml:
```yaml
volumes:
  - ./database/pgadmin/config_local.py:/pgadmin4/config_local.py:ro
```

### Database Connection Pooling

Monitor connection pooling in pgAdmin:
1. Navigate to Server → Statistics
2. Check "Database connections" and "Active connections"

### Query Performance Analysis

Use pgAdmin's query analysis tools:
1. Query Tool → Explain → Explain Analyze
2. View execution plans and performance metrics

## Integration with Application

The application connects to the same PostgreSQL instance that pgAdmin manages:

- **Connection String:** `postgresql://ml_user:ml_password@postgres:5432/multimodal_librarian`
- **Pool Size:** 10 connections (configurable via `POSTGRES_POOL_SIZE`)
- **Max Overflow:** 20 connections

## Useful Queries

### Check Application Tables
```sql
SELECT schemaname, tablename, tableowner 
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;
```

### Monitor Active Connections
```sql
SELECT pid, usename, application_name, client_addr, state, query_start, query
FROM pg_stat_activity
WHERE state = 'active';
```

### Check Database Size
```sql
SELECT pg_size_pretty(pg_database_size('multimodal_librarian')) as database_size;
```

### View Recent Log Entries (if logging is enabled)
```sql
SELECT * FROM pg_stat_statements 
ORDER BY calls DESC 
LIMIT 10;
```