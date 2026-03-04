-- PostgreSQL Maintenance Functions
-- This script creates maintenance and utility functions

-- Create maintenance schema
CREATE SCHEMA IF NOT EXISTS maintenance;

-- Function to clean up expired sessions
CREATE OR REPLACE FUNCTION maintenance.cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Only run if user_sessions table exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_sessions') THEN
        DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE 'Cleaned up % expired sessions', deleted_count;
        RETURN deleted_count;
    ELSE
        RAISE NOTICE 'user_sessions table does not exist yet';
        RETURN 0;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up expired exports
CREATE OR REPLACE FUNCTION maintenance.cleanup_expired_exports()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Only run if export_history table exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'export_history') THEN
        DELETE FROM export_history 
        WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE 'Cleaned up % expired exports', deleted_count;
        RETURN deleted_count;
    ELSE
        RAISE NOTICE 'export_history table does not exist yet';
        RETURN 0;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old audit logs (keep last 90 days)
CREATE OR REPLACE FUNCTION maintenance.cleanup_old_audit_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Only run if audit_log table exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'audit' AND table_name = 'audit_log') THEN
        DELETE FROM audit.audit_log 
        WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '90 days';
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE 'Cleaned up % old audit log entries', deleted_count;
        RETURN deleted_count;
    ELSE
        RAISE NOTICE 'audit.audit_log table does not exist yet';
        RETURN 0;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to update table statistics
CREATE OR REPLACE FUNCTION maintenance.update_statistics()
RETURNS void AS $$
DECLARE
    table_record RECORD;
    start_time TIMESTAMP;
    end_time TIMESTAMP;
BEGIN
    start_time := clock_timestamp();
    
    FOR table_record IN 
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
    LOOP
        EXECUTE 'ANALYZE ' || quote_ident(table_record.schemaname) || '.' || quote_ident(table_record.tablename);
    END LOOP;
    
    end_time := clock_timestamp();
    RAISE NOTICE 'Statistics updated for all tables in % seconds', 
        EXTRACT(EPOCH FROM (end_time - start_time));
END;
$$ LANGUAGE plpgsql;

-- Function to perform routine maintenance
CREATE OR REPLACE FUNCTION maintenance.routine_maintenance()
RETURNS TABLE(
    task text,
    result text,
    duration interval
) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    session_count INTEGER;
    export_count INTEGER;
    audit_count INTEGER;
BEGIN
    RAISE NOTICE 'Starting routine maintenance...';
    
    -- Clean up expired sessions
    start_time := clock_timestamp();
    SELECT maintenance.cleanup_expired_sessions() INTO session_count;
    end_time := clock_timestamp();
    RETURN QUERY SELECT 'cleanup_expired_sessions'::text, 
                       ('Cleaned ' || session_count || ' sessions')::text,
                       (end_time - start_time)::interval;
    
    -- Clean up expired exports
    start_time := clock_timestamp();
    SELECT maintenance.cleanup_expired_exports() INTO export_count;
    end_time := clock_timestamp();
    RETURN QUERY SELECT 'cleanup_expired_exports'::text,
                       ('Cleaned ' || export_count || ' exports')::text,
                       (end_time - start_time)::interval;
    
    -- Clean up old audit logs
    start_time := clock_timestamp();
    SELECT maintenance.cleanup_old_audit_logs() INTO audit_count;
    end_time := clock_timestamp();
    RETURN QUERY SELECT 'cleanup_old_audit_logs'::text,
                       ('Cleaned ' || audit_count || ' audit entries')::text,
                       (end_time - start_time)::interval;
    
    -- Update statistics
    start_time := clock_timestamp();
    PERFORM maintenance.update_statistics();
    end_time := clock_timestamp();
    RETURN QUERY SELECT 'update_statistics'::text,
                       'Statistics updated'::text,
                       (end_time - start_time)::interval;
    
    RAISE NOTICE 'Routine maintenance completed successfully';
END;
$$ LANGUAGE plpgsql;

-- Function to backup database schema
CREATE OR REPLACE FUNCTION maintenance.backup_schema_info()
RETURNS TABLE(
    backup_info text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 'Schema backup info generated at: ' || CURRENT_TIMESTAMP::text;
    
    -- This would typically generate schema backup commands
    -- For now, just return informational message
    RETURN QUERY
    SELECT 'Use pg_dump for full schema backup: pg_dump -s -h localhost -U ml_user multimodal_librarian > schema_backup.sql';
END;
$$ LANGUAGE plpgsql;

-- Grant permissions on maintenance schema
GRANT USAGE ON SCHEMA maintenance TO ml_app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA maintenance TO ml_app_user;

-- Log maintenance functions setup completion
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL maintenance functions setup completed successfully';
END $$;