-- PostgreSQL Extensions Initialization
-- This script installs required PostgreSQL extensions

-- Enable required extensions for the multimodal librarian
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- Log extension installation
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL extensions installed successfully';
END $$;