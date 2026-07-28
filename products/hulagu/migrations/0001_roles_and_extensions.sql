-- Hulagu roles are deliberately separated before any application objects exist.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_owner') THEN
    CREATE ROLE hulagu_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_migrator') THEN
    CREATE ROLE hulagu_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_app') THEN
    CREATE ROLE hulagu_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_runner') THEN
    CREATE ROLE hulagu_runner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_deletion') THEN
    CREATE ROLE hulagu_deletion LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'hulagu_readonly') THEN
    CREATE ROLE hulagu_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS hulagu AUTHORIZATION hulagu_owner;
CREATE SCHEMA IF NOT EXISTS hulagu_api AUTHORIZATION hulagu_owner;
REVOKE ALL ON SCHEMA hulagu, hulagu_api FROM PUBLIC;
GRANT USAGE ON SCHEMA hulagu TO hulagu_app;
GRANT USAGE ON SCHEMA hulagu_api TO hulagu_app, hulagu_runner, hulagu_deletion, hulagu_readonly;
