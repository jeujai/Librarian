-- PostgreSQL Users and Permissions Setup
-- This script creates database users and sets up permissions

-- Create application user if it does not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ml_app_user') THEN
        CREATE ROLE ml_app_user WITH LOGIN PASSWORD 'ml_app_password';
        RAISE NOTICE 'Created ml_app_user role';
    ELSE
        RAISE NOTICE 'ml_app_user role already exists';
    END IF;
END $$;

-- Create read-only user for reporting
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ml_readonly') THEN
        CREATE ROLE ml_readonly WITH LOGIN PASSWORD 'ml_readonly_password';
        RAISE NOTICE 'Created ml_readonly role';
    ELSE
        RAISE NOTICE 'ml_readonly role already exists';
    END IF;
END $$;

-- Create backup user
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ml_backup') THEN
        CREATE ROLE ml_backup WITH LOGIN PASSWORD 'ml_backup_password';
        RAISE NOTICE 'Created ml_backup role';
    ELSE
        RAISE NOTICE 'ml_backup role already exists';
    END IF;
END $$;

-- Grant necessary permissions to application user
GRANT CONNECT ON DATABASE multimodal_librarian TO ml_app_user;
GRANT USAGE ON SCHEMA public TO ml_app_user;
GRANT CREATE ON SCHEMA public TO ml_app_user;

-- Grant read-only permissions
GRANT CONNECT ON DATABASE multimodal_librarian TO ml_readonly;
GRANT USAGE ON SCHEMA public TO ml_readonly;

-- Grant backup permissions
GRANT CONNECT ON DATABASE multimodal_librarian TO ml_backup;
GRANT USAGE ON SCHEMA public TO ml_backup;

-- Log user setup completion
DO $$
BEGIN
    RAISE NOTICE 'Database users and permissions configured successfully';
END $$;