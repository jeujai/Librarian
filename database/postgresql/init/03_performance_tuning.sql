-- PostgreSQL Performance Tuning for Local Development
-- This script applies performance optimizations and creates monitoring functions

-- Create function to log performance settings
CREATE OR REPLACE FUNCTION log_performance_settings()
RETURNS void AS $
BEGIN
    RAISE NOTICE 'Current PostgreSQL performance settings:';
    RAISE NOTICE 'shared_buffers: %', current_setting('shared_buffers');
    RAISE NOTICE 'effective_cache_size: %', current_setting('effective_cache_size');
    RAISE NOTICE 'maintenance_work_mem: %', current_setting('maintenance_work_mem');
    RAISE NOTICE 'work_mem: %', current_setting('work_mem');
    RAISE NOTICE 'checkpoint_completion_target: %', current_setting('checkpoint_completion_target');
    RAISE NOTICE 'wal_buffers: %', current_setting('wal_buffers');
    RAISE NOTICE 'default_statistics_target: %', current_setting('default_statistics_target');
    RAISE NOTICE 'max_connections: %', current_setting('max_connections');
    RAISE NOTICE 'random_page_cost: %', current_setting('random_page_cost');
    RAISE NOTICE 'max_parallel_workers_per_gather: %', current_setting('max_parallel_workers_per_gather');
END;
$ LANGUAGE plpgsql;

-- Log current settings
SELECT log_performance_settings();

-- Create maintenance functions
CREATE OR REPLACE FUNCTION analyze_all_tables()
RETURNS void AS $
DECLARE
    table_record RECORD;
    start_time timestamp;
    end_time timestamp;
    table_count integer := 0;
BEGIN
    start_time := clock_timestamp();
    
    FOR table_record IN 
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
    LOOP
        EXECUTE 'ANALYZE ' || quote_ident(table_record.schemaname) || '.' || quote_ident(table_record.tablename);
        table_count := table_count + 1;
    END LOOP;
    
    end_time := clock_timestamp();
    RAISE NOTICE 'Analyzed % tables in % seconds', table_count, EXTRACT(EPOCH FROM (end_time - start_time));
END;
$ LANGUAGE plpgsql;

-- Create vacuum function
CREATE OR REPLACE FUNCTION vacuum_all_tables()
RETURNS void AS $
DECLARE
    table_record RECORD;
    start_time timestamp;
    end_time timestamp;
    table_count integer := 0;
BEGIN
    start_time := clock_timestamp();
    
    FOR table_record IN 
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
    LOOP
        EXECUTE 'VACUUM ANALYZE ' || quote_ident(table_record.schemaname) || '.' || quote_ident(table_record.tablename);
        table_count := table_count + 1;
    END LOOP;
    
    end_time := clock_timestamp();
    RAISE NOTICE 'Vacuumed and analyzed % tables in % seconds', table_count, EXTRACT(EPOCH FROM (end_time - start_time));
END;
$ LANGUAGE plpgsql;

-- Create performance monitoring function
CREATE OR REPLACE FUNCTION get_performance_stats()
RETURNS TABLE(
    metric_name text,
    metric_value text,
    description text
) AS $
BEGIN
    RETURN QUERY
    SELECT 
        'Database Size'::text,
        pg_size_pretty(pg_database_size(current_database()))::text,
        'Total size of current database'::text
    UNION ALL
    SELECT 
        'Shared Buffers Hit Ratio'::text,
        ROUND(
            (sum(blks_hit) * 100.0 / NULLIF(sum(blks_hit) + sum(blks_read), 0))::numeric, 2
        )::text || '%',
        'Percentage of blocks served from shared buffers'::text
    FROM pg_stat_database
    WHERE datname = current_database()
    UNION ALL
    SELECT 
        'Active Connections'::text,
        count(*)::text,
        'Number of active database connections'::text
    FROM pg_stat_activity
    WHERE state = 'active'
    UNION ALL
    SELECT 
        'Total Connections'::text,
        count(*)::text,
        'Total number of database connections'::text
    FROM pg_stat_activity
    UNION ALL
    SELECT 
        'Checkpoint Write Time'::text,
        ROUND(checkpoints_timed::numeric / NULLIF(checkpoints_timed + checkpoints_req, 0) * 100, 2)::text || '%',
        'Percentage of checkpoints that were scheduled vs requested'::text
    FROM pg_stat_bgwriter;
END;
$ LANGUAGE plpgsql;

-- Create index usage monitoring function
CREATE OR REPLACE FUNCTION get_index_usage_stats()
RETURNS TABLE(
    schemaname text,
    tablename text,
    indexname text,
    idx_scan bigint,
    idx_tup_read bigint,
    idx_tup_fetch bigint,
    usage_ratio numeric
) AS $
BEGIN
    RETURN QUERY
    SELECT 
        s.schemaname::text,
        s.tablename::text,
        s.indexrelname::text,
        s.idx_scan,
        s.idx_tup_read,
        s.idx_tup_fetch,
        CASE 
            WHEN s.idx_scan = 0 THEN 0
            ELSE ROUND((s.idx_tup_fetch::numeric / NULLIF(s.idx_tup_read, 0)) * 100, 2)
        END as usage_ratio
    FROM pg_stat_user_indexes s
    JOIN pg_index i ON s.indexrelid = i.indexrelid
    WHERE s.schemaname NOT IN ('information_schema', 'pg_catalog')
    ORDER BY s.idx_scan DESC;
END;
$ LANGUAGE plpgsql;

-- Create slow query monitoring function (requires pg_stat_statements)
CREATE OR REPLACE FUNCTION get_slow_queries(limit_count integer DEFAULT 10)
RETURNS TABLE(
    query_text text,
    calls bigint,
    total_time_ms numeric,
    mean_time_ms numeric,
    rows_returned bigint
) AS $
BEGIN
    -- Check if pg_stat_statements is available
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') THEN
        RAISE NOTICE 'pg_stat_statements extension not available. Install it for query performance monitoring.';
        RETURN;
    END IF;
    
    RETURN QUERY
    EXECUTE format('
        SELECT 
            query::text,
            calls,
            ROUND(total_exec_time::numeric, 2) as total_time_ms,
            ROUND(mean_exec_time::numeric, 2) as mean_time_ms,
            rows
        FROM pg_stat_statements
        WHERE query NOT LIKE ''%%pg_stat_statements%%''
        ORDER BY mean_exec_time DESC
        LIMIT %s
    ', limit_count);
END;
$ LANGUAGE plpgsql;

-- Create table bloat monitoring function
CREATE OR REPLACE FUNCTION get_table_bloat_stats()
RETURNS TABLE(
    schemaname text,
    tablename text,
    table_size text,
    bloat_ratio numeric,
    wasted_space text
) AS $
BEGIN
    RETURN QUERY
    SELECT 
        s.schemaname::text,
        s.tablename::text,
        pg_size_pretty(pg_total_relation_size(s.schemaname||'.'||s.tablename))::text,
        CASE 
            WHEN s.n_tup_del = 0 THEN 0
            ELSE ROUND((s.n_tup_del::numeric / NULLIF(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0)) * 100, 2)
        END as bloat_ratio,
        pg_size_pretty(
            CASE 
                WHEN s.n_tup_del = 0 THEN 0
                ELSE (s.n_tup_del::numeric / NULLIF(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0)) * 
                     pg_total_relation_size(s.schemaname||'.'||s.tablename)
            END::bigint
        )::text as wasted_space
    FROM pg_stat_user_tables s
    WHERE s.schemaname NOT IN ('information_schema', 'pg_catalog')
    ORDER BY bloat_ratio DESC;
END;
$ LANGUAGE plpgsql;

-- Create development-specific optimization settings
DO $
BEGIN
    -- Set development-friendly statistics target for better query planning
    EXECUTE 'ALTER DATABASE ' || current_database() || ' SET default_statistics_target = 100';
    
    -- Enable JIT compilation for complex queries (if available)
    BEGIN
        EXECUTE 'ALTER DATABASE ' || current_database() || ' SET jit = on';
        EXECUTE 'ALTER DATABASE ' || current_database() || ' SET jit_above_cost = 100000';
        EXECUTE 'ALTER DATABASE ' || current_database() || ' SET jit_optimize_above_cost = 500000';
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'JIT compilation not available in this PostgreSQL version';
    END;
    
    -- Set reasonable work_mem for development queries
    EXECUTE 'ALTER DATABASE ' || current_database() || ' SET work_mem = ''8MB''';
    
    -- Enable parallel query execution for development
    EXECUTE 'ALTER DATABASE ' || current_database() || ' SET max_parallel_workers_per_gather = 2';
    
    RAISE NOTICE 'Development-specific optimizations applied';
END $;

-- Log performance tuning completion
DO $
BEGIN
    RAISE NOTICE 'PostgreSQL performance tuning configured successfully for local development';
    RAISE NOTICE 'Available performance monitoring functions:';
    RAISE NOTICE '  - SELECT * FROM get_performance_stats();';
    RAISE NOTICE '  - SELECT * FROM get_index_usage_stats();';
    RAISE NOTICE '  - SELECT * FROM get_slow_queries(10);';
    RAISE NOTICE '  - SELECT * FROM get_table_bloat_stats();';
    RAISE NOTICE '  - SELECT analyze_all_tables();';
    RAISE NOTICE '  - SELECT vacuum_all_tables();';
END $;