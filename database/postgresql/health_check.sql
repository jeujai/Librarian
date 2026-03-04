-- PostgreSQL Health Check Script for Multimodal Librarian
-- This script performs comprehensive health checks on the database

-- Set output format for better readability
\pset border 2
\pset format aligned

-- Display header
SELECT 'PostgreSQL Health Check for Multimodal Librarian' as "Health Check Report";
SELECT CURRENT_TIMESTAMP as "Check Time";

-- 1. Database Connection and Basic Info
\echo '=== Database Connection and Version ==='
SELECT 
    current_database() as "Database Name",
    current_user as "Current User",
    version() as "PostgreSQL Version";

-- 2. Database Size and Statistics
\echo '=== Database Size and Statistics ==='
SELECT 
    pg_size_pretty(pg_database_size(current_database())) as "Database Size",
    (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')) as "Total Tables",
    (SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog')) as "Total Schemas";

-- 3. Extension Status
\echo '=== Extension Status ==='
SELECT 
    extname as "Extension Name",
    extversion as "Version",
    CASE WHEN extname IS NOT NULL THEN 'Installed' ELSE 'Missing' END as "Status"
FROM pg_extension 
WHERE extname IN ('uuid-ossp', 'pg_trgm', 'btree_gin', 'pg_stat_statements', 'pgcrypto', 'citext')
ORDER BY extname;

-- 4. Schema Status
\echo '=== Schema Status ==='
SELECT 
    schema_name as "Schema Name",
    CASE 
        WHEN schema_name = 'multimodal_librarian' THEN 'Application Schema'
        WHEN schema_name = 'audit' THEN 'Audit Schema'
        WHEN schema_name = 'monitoring' THEN 'Monitoring Schema'
        WHEN schema_name = 'maintenance' THEN 'Maintenance Schema'
        ELSE 'System Schema'
    END as "Purpose"
FROM information_schema.schemata 
WHERE schema_name IN ('multimodal_librarian', 'audit', 'monitoring', 'maintenance', 'public')
ORDER BY schema_name;

-- 5. Table Status in Application Schema
\echo '=== Application Tables Status ==='
SELECT 
    table_name as "Table Name",
    CASE 
        WHEN table_schema = 'multimodal_librarian' THEN 'Application'
        WHEN table_schema = 'audit' THEN 'Audit'
        ELSE 'Public'
    END as "Schema",
    (SELECT count(*) FROM information_schema.columns WHERE columns.table_name = tables.table_name AND columns.table_schema = tables.table_schema) as "Columns"
FROM information_schema.tables 
WHERE table_schema IN ('multimodal_librarian', 'audit', 'public')
AND table_type = 'BASE TABLE'
ORDER BY table_schema, table_name;

-- 6. Index Status
\echo '=== Index Status ==='
SELECT 
    schemaname as "Schema",
    tablename as "Table",
    indexname as "Index Name",
    indexdef as "Definition"
FROM pg_indexes 
WHERE schemaname IN ('multimodal_librarian', 'audit', 'public')
AND indexname LIKE 'idx_%'
ORDER BY schemaname, tablename, indexname;

-- 7. User and Permissions Status
\echo '=== User and Permissions Status ==='
SELECT 
    rolname as "Role Name",
    rolsuper as "Superuser",
    rolcreaterole as "Create Role",
    rolcreatedb as "Create DB",
    rolcanlogin as "Can Login"
FROM pg_roles 
WHERE rolname IN ('ml_app_user', 'ml_readonly', 'ml_backup', current_user)
ORDER BY rolname;

-- 8. Active Connections
\echo '=== Active Connections ==='
SELECT 
    count(*) as "Total Connections",
    count(*) FILTER (WHERE state = 'active') as "Active Queries",
    count(*) FILTER (WHERE state = 'idle') as "Idle Connections"
FROM pg_stat_activity;

-- 9. Database Performance Metrics
\echo '=== Performance Metrics ==='
SELECT 
    numbackends as "Backend Processes",
    xact_commit as "Committed Transactions",
    xact_rollback as "Rolled Back Transactions",
    blks_read as "Blocks Read",
    blks_hit as "Blocks Hit",
    CASE 
        WHEN (blks_read + blks_hit) > 0 
        THEN round((blks_hit::numeric / (blks_read + blks_hit)) * 100, 2)
        ELSE 0 
    END as "Cache Hit Ratio %"
FROM pg_stat_database 
WHERE datname = current_database();

-- 10. Table Sizes (Top 10)
\echo '=== Largest Tables ==='
SELECT 
    schemaname as "Schema",
    tablename as "Table Name",
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as "Total Size",
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as "Table Size",
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as "Index Size"
FROM pg_tables 
WHERE schemaname IN ('multimodal_librarian', 'audit', 'public')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;

-- 11. Migration Status
\echo '=== Migration Status ==='
SELECT 
    migration_name as "Migration",
    applied_at as "Applied At",
    success as "Success"
FROM public.migration_history 
ORDER BY applied_at DESC
LIMIT 10;

-- 12. Monitoring Functions Test
\echo '=== Monitoring Functions Test ==='
SELECT * FROM monitoring.health_check();

-- 13. Maintenance Functions Test
\echo '=== Maintenance Status ==='
SELECT 
    'Expired Sessions Cleanup' as "Function",
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.routines WHERE routine_name = 'cleanup_expired_sessions') 
        THEN 'Available' 
        ELSE 'Missing' 
    END as "Status";

-- 14. Error Check - Long Running Queries
\echo '=== Long Running Queries Check ==='
SELECT 
    pid,
    now() - pg_stat_activity.query_start AS duration,
    query 
FROM pg_stat_activity 
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
AND state = 'active';

-- 15. Disk Space Check
\echo '=== Disk Space Usage ==='
SELECT 
    'Database' as "Component",
    pg_size_pretty(pg_database_size(current_database())) as "Size";

-- 16. Configuration Check
\echo '=== Key Configuration Settings ==='
SELECT 
    name as "Setting",
    setting as "Value",
    unit as "Unit"
FROM pg_settings 
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'maintenance_work_mem',
    'checkpoint_completion_target',
    'wal_buffers',
    'default_statistics_target',
    'max_connections'
)
ORDER BY name;

-- Final Status Summary
\echo '=== Health Check Summary ==='
SELECT 
    CASE 
        WHEN (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'multimodal_librarian') >= 8
        THEN 'HEALTHY'
        ELSE 'NEEDS ATTENTION'
    END as "Overall Status",
    'Check completed successfully' as "Message";

-- Reset output format
\pset border 1
\pset format aligned