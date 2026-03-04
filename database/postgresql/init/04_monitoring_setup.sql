-- PostgreSQL Monitoring Setup
-- This script sets up monitoring views and functions

-- Create monitoring schema
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Create view for connection monitoring
CREATE OR REPLACE VIEW monitoring.active_connections AS
SELECT 
    pid,
    usename,
    application_name,
    client_addr,
    client_hostname,
    client_port,
    backend_start,
    xact_start,
    query_start,
    state_change,
    state,
    backend_xid,
    backend_xmin,
    query,
    backend_type
FROM pg_stat_activity
WHERE state != 'idle';

-- Create view for database statistics
CREATE OR REPLACE VIEW monitoring.database_stats AS
SELECT 
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts,
    temp_files,
    temp_bytes,
    deadlocks,
    blk_read_time,
    blk_write_time,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- Create view for table statistics
CREATE OR REPLACE VIEW monitoring.table_stats AS
SELECT 
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY schemaname, tablename;

-- Create view for index usage
CREATE OR REPLACE VIEW monitoring.index_usage AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY schemaname, tablename, indexname;

-- Create function to get database size information
CREATE OR REPLACE FUNCTION monitoring.get_database_sizes()
RETURNS TABLE(
    database_name name,
    size_bytes bigint,
    size_pretty text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        datname::name,
        pg_database_size(datname),
        pg_size_pretty(pg_database_size(datname))
    FROM pg_database
    WHERE datname = current_database();
END;
$$ LANGUAGE plpgsql;

-- Create function to get table sizes
CREATE OR REPLACE FUNCTION monitoring.get_table_sizes()
RETURNS TABLE(
    schema_name name,
    table_name name,
    size_bytes bigint,
    size_pretty text,
    index_size_bytes bigint,
    index_size_pretty text,
    total_size_bytes bigint,
    total_size_pretty text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        schemaname::name,
        tablename::name,
        pg_relation_size(schemaname||'.'||tablename),
        pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)),
        pg_indexes_size(schemaname||'.'||tablename),
        pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)),
        pg_total_relation_size(schemaname||'.'||tablename),
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
    FROM pg_tables
    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
END;
$$ LANGUAGE plpgsql;

-- Create function for health check
CREATE OR REPLACE FUNCTION monitoring.health_check()
RETURNS TABLE(
    check_name text,
    status text,
    details text
) AS $$
BEGIN
    -- Check database connectivity
    RETURN QUERY SELECT 'database_connectivity'::text, 'OK'::text, 'Database is accessible'::text;
    
    -- Check active connections
    RETURN QUERY 
    SELECT 
        'active_connections'::text,
        CASE WHEN count(*) < 50 THEN 'OK' ELSE 'WARNING' END::text,
        ('Active connections: ' || count(*))::text
    FROM pg_stat_activity 
    WHERE state = 'active';
    
    -- Check for long-running queries
    RETURN QUERY
    SELECT 
        'long_running_queries'::text,
        CASE WHEN count(*) = 0 THEN 'OK' ELSE 'WARNING' END::text,
        ('Long-running queries (>5min): ' || count(*))::text
    FROM pg_stat_activity 
    WHERE state = 'active' 
    AND query_start < now() - interval '5 minutes';
    
    -- Check database size
    RETURN QUERY
    SELECT 
        'database_size'::text,
        'INFO'::text,
        ('Database size: ' || pg_size_pretty(pg_database_size(current_database())))::text;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions on monitoring schema
GRANT USAGE ON SCHEMA monitoring TO ml_app_user, ml_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA monitoring TO ml_app_user, ml_readonly;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA monitoring TO ml_app_user, ml_readonly;

-- Log monitoring setup completion
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL monitoring setup completed successfully';
END $$;
-- Create performance monitoring function
CREATE OR REPLACE FUNCTION monitoring.get_performance_summary()
RETURNS TABLE(
    metric_category text,
    metric_name text,
    current_value text,
    status text,
    recommendation text
) AS $
DECLARE
    hit_ratio numeric;
    active_conns integer;
    checkpoint_ratio numeric;
    unused_indexes integer;
BEGIN
    -- Buffer hit ratio
    SELECT ROUND((sum(blks_hit) * 100.0 / NULLIF(sum(blks_hit) + sum(blks_read), 0))::numeric, 2)
    INTO hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database();
    
    RETURN QUERY SELECT 
        'Memory'::text,
        'Buffer Hit Ratio'::text,
        hit_ratio::text || '%',
        CASE 
            WHEN hit_ratio > 95 THEN 'GOOD'
            WHEN hit_ratio > 90 THEN 'OK'
            ELSE 'NEEDS_ATTENTION'
        END::text,
        CASE 
            WHEN hit_ratio <= 90 THEN 'Consider increasing shared_buffers'
            ELSE 'Buffer hit ratio is healthy'
        END::text;
    
    -- Active connections
    SELECT count(*) INTO active_conns
    FROM pg_stat_activity 
    WHERE state = 'active';
    
    RETURN QUERY SELECT 
        'Connections'::text,
        'Active Connections'::text,
        active_conns::text,
        CASE 
            WHEN active_conns < 20 THEN 'GOOD'
            WHEN active_conns < 50 THEN 'OK'
            ELSE 'NEEDS_ATTENTION'
        END::text,
        CASE 
            WHEN active_conns >= 50 THEN 'High connection count - consider connection pooling'
            ELSE 'Connection count is healthy'
        END::text;
    
    -- Checkpoint frequency
    SELECT checkpoints_req::numeric / NULLIF(checkpoints_timed + checkpoints_req, 0)
    INTO checkpoint_ratio
    FROM pg_stat_bgwriter;
    
    RETURN QUERY SELECT 
        'I/O'::text,
        'Checkpoint Frequency'::text,
        ROUND(checkpoint_ratio * 100, 2)::text || '% requested',
        CASE 
            WHEN checkpoint_ratio < 0.1 THEN 'GOOD'
            WHEN checkpoint_ratio < 0.3 THEN 'OK'
            ELSE 'NEEDS_ATTENTION'
        END::text,
        CASE 
            WHEN checkpoint_ratio >= 0.3 THEN 'Too many requested checkpoints - consider increasing checkpoint_timeout or max_wal_size'
            ELSE 'Checkpoint frequency is healthy'
        END::text;
    
    -- Unused indexes
    SELECT count(*) INTO unused_indexes
    FROM pg_stat_user_indexes 
    WHERE idx_scan = 0;
    
    RETURN QUERY SELECT 
        'Indexes'::text,
        'Unused Indexes'::text,
        unused_indexes::text,
        CASE 
            WHEN unused_indexes = 0 THEN 'GOOD'
            WHEN unused_indexes < 5 THEN 'OK'
            ELSE 'NEEDS_ATTENTION'
        END::text,
        CASE 
            WHEN unused_indexes > 0 THEN 'Consider dropping unused indexes to improve write performance'
            ELSE 'All indexes are being used'
        END::text;
END;
$ LANGUAGE plpgsql;

-- Create query performance monitoring function
CREATE OR REPLACE FUNCTION monitoring.get_query_performance_stats()
RETURNS TABLE(
    metric_name text,
    current_value text,
    threshold text,
    status text
) AS $
DECLARE
    slow_query_count integer;
    avg_query_time numeric;
    lock_wait_count integer;
BEGIN
    -- Count slow queries (>2 seconds)
    SELECT count(*) INTO slow_query_count
    FROM pg_stat_activity 
    WHERE state = 'active' 
    AND query_start < now() - interval '2 seconds'
    AND query NOT LIKE '%pg_stat_activity%';
    
    RETURN QUERY SELECT 
        'Slow Queries (>2s)'::text,
        slow_query_count::text,
        '< 5'::text,
        CASE 
            WHEN slow_query_count = 0 THEN 'GOOD'
            WHEN slow_query_count < 5 THEN 'OK'
            ELSE 'NEEDS_ATTENTION'
        END::text;
    
    -- Count queries waiting for locks
    SELECT count(*) INTO lock_wait_count
    FROM pg_stat_activity 
    WHERE wait_event_type = 'Lock';
    
    RETURN QUERY SELECT 
        'Lock Waits'::text,
        lock_wait_count::text,
        '0'::text,
        CASE 
            WHEN lock_wait_count = 0 THEN 'GOOD'
            ELSE 'NEEDS_ATTENTION'
        END::text;
END;
$ LANGUAGE plpgsql;

-- Create resource usage monitoring function
CREATE OR REPLACE FUNCTION monitoring.get_resource_usage()
RETURNS TABLE(
    resource_type text,
    usage_description text,
    current_value text,
    recommendation text
) AS $
BEGIN
    -- Memory usage
    RETURN QUERY SELECT 
        'Memory'::text,
        'Shared Buffers'::text,
        current_setting('shared_buffers')::text,
        'Optimized for development workload'::text;
    
    RETURN QUERY SELECT 
        'Memory'::text,
        'Work Memory'::text,
        current_setting('work_mem')::text,
        'Per-operation memory for sorts and joins'::text;
    
    RETURN QUERY SELECT 
        'Memory'::text,
        'Maintenance Work Memory'::text,
        current_setting('maintenance_work_mem')::text,
        'Memory for VACUUM, CREATE INDEX operations'::text;
    
    -- Connection usage
    RETURN QUERY SELECT 
        'Connections'::text,
        'Max Connections'::text,
        current_setting('max_connections')::text,
        'Maximum concurrent connections allowed'::text;
    
    RETURN QUERY SELECT 
        'Connections'::text,
        'Current Connections'::text,
        (SELECT count(*)::text FROM pg_stat_activity),
        'Currently active database connections'::text;
    
    -- WAL settings
    RETURN QUERY SELECT 
        'WAL'::text,
        'WAL Buffers'::text,
        current_setting('wal_buffers')::text,
        'Write-ahead log buffer size'::text;
    
    RETURN QUERY SELECT 
        'WAL'::text,
        'Checkpoint Timeout'::text,
        current_setting('checkpoint_timeout')::text,
        'Maximum time between automatic checkpoints'::text;
END;
$ LANGUAGE plpgsql;

-- Update permissions for new functions
GRANT EXECUTE ON FUNCTION monitoring.get_performance_summary() TO ml_app_user, ml_readonly;
GRANT EXECUTE ON FUNCTION monitoring.get_query_performance_stats() TO ml_app_user, ml_readonly;
GRANT EXECUTE ON FUNCTION monitoring.get_resource_usage() TO ml_app_user, ml_readonly;

-- Log enhanced monitoring setup completion
DO $
BEGIN
    RAISE NOTICE 'Enhanced PostgreSQL performance monitoring setup completed';
    RAISE NOTICE 'Available performance monitoring functions:';
    RAISE NOTICE '  - SELECT * FROM monitoring.get_performance_summary();';
    RAISE NOTICE '  - SELECT * FROM monitoring.get_query_performance_stats();';
    RAISE NOTICE '  - SELECT * FROM monitoring.get_resource_usage();';
END $;