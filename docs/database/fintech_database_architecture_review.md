# Enterprise Fintech Platform Database Architecture Review

**Date:** 2026-02-04
**Platform:** PostgreSQL 14 with Multi-Region Read Replicas
**Scope:** Schema Design, Indexing, Partitioning, Backup/DR, Performance Optimization, Data Archival, Replication

---

## Executive Summary

This document provides comprehensive database architecture recommendations for an enterprise fintech platform with strict regulatory requirements (7-year data retention), high availability needs, and multi-region deployment. The architecture leverages PostgreSQL 14's advanced features including declarative partitioning, parallel query execution, and logical replication.

**Key Recommendations at a Glance:**
- Implement native range partitioning by transaction date for transaction tables
- Use BRIN indexes for time-series data with composite B-tree indexes for lookups
- Deploy multi-tier caching with Redis Cluster for hot data
- Implement tiered data archival strategy (Hot -> Warm -> Cold)
- Use synchronous replication for critical financial transactions with async for reads
- Target RPO < 1 minute, RTO < 5 minutes for disaster recovery

---

## 1. Schema Design for Financial Transactions

### 1.1 Core Transaction Schema

```sql
-- =====================================================
-- 1.1.1 Core Transaction Table (Partitioned)
-- =====================================================

CREATE TABLE transactions (
    -- Primary Identification
    transaction_id          BIGSERIAL,
    transaction_uuid        UUID DEFAULT gen_random_uuid() NOT NULL,
    reference_number        VARCHAR(64) NOT NULL,

    -- Transaction Details
    transaction_type        VARCHAR(32) NOT NULL,  -- 'payment', 'transfer', 'refund', etc.
    status                  VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'reversed')),
    amount                  NUMERIC(19, 4) NOT NULL,
    currency_code           CHAR(3) NOT NULL DEFAULT 'USD',

    -- Account References
    source_account_id       BIGINT NOT NULL,
    destination_account_id  BIGINT,

    -- Temporal Tracking
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    settlement_date         DATE NOT NULL,

    -- Risk & Compliance
    risk_score              DECIMAL(3, 2),
    compliance_flags        JSONB DEFAULT '{}',
    regulatory_region       VARCHAR(8) NOT NULL,  -- 'US', 'EU', 'UK', etc.

    -- Audit Trail (Immutable)
    created_by              VARCHAR(64) NOT NULL,
    updated_by              VARCHAR(64) NOT NULL,
    version                 INTEGER NOT NULL DEFAULT 1,

    -- Partition Key
    partition_date          DATE NOT NULL DEFAULT CURRENT_DATE,

    PRIMARY KEY (transaction_id, partition_date)
) PARTITION BY RANGE (partition_date);

-- =====================================================
-- 1.1.2 Transaction Audit Log (Immutable)
-- =====================================================

CREATE TABLE transaction_audit_log (
    audit_id                BIGSERIAL PRIMARY KEY,
    transaction_id          BIGINT NOT NULL,
    partition_date          DATE NOT NULL,
    action                  VARCHAR(16) NOT NULL,  -- 'INSERT', 'UPDATE', 'DELETE'
    old_values              JSONB,
    new_values              JSONB,
    changed_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by              VARCHAR(64) NOT NULL,
    session_id              VARCHAR(128),
    ip_address              INET
);

-- =====================================================
-- 1.1.3 Account Balance Table
-- =====================================================

CREATE TABLE account_balances (
    account_id              BIGINT PRIMARY KEY,
    available_balance       NUMERIC(19, 4) NOT NULL DEFAULT 0,
    pending_balance         NUMERIC(19, 4) NOT NULL DEFAULT 0,
    reserved_balance        NUMERIC(19, 4) NOT NULL DEFAULT 0,
    currency_code           CHAR(3) NOT NULL,
    last_transaction_id     BIGINT,
    last_transaction_at     TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version                 INTEGER NOT NULL DEFAULT 1  -- Optimistic locking
);

-- =====================================================
-- 1.1.4 Transaction Metadata (JSONB for flexibility)
-- =====================================================

CREATE TABLE transaction_metadata (
    transaction_id          BIGINT PRIMARY KEY,
    partition_date          DATE NOT NULL,
    merchant_data           JSONB,
    customer_data           JSONB,
    device_fingerprint      JSONB,
    geolocation_data        JSONB,
    custom_fields           JSONB DEFAULT '{}'
);
```

### 1.2 Schema Design Principles

| Principle | Implementation | Rationale |
|-----------|---------------|-----------|
| **ACID Compliance** | PostgreSQL MVCC with SERIALIZABLE for critical operations | Financial data integrity requires strict consistency |
| **Audit Immutability** | Separate audit table with append-only pattern | Regulatory compliance (SOX, PCI-DSS) |
| **Optimistic Locking** | Version column on balance table | Prevents lost updates in concurrent environments |
| **Temporal Design** | settlement_date + created_at | Supports business-day processing and audit trails |
| **JSONB Flexibility** | metadata tables for extensible attributes | Accommodates varying regulatory requirements |

### 1.3 Constraints and Data Integrity

```sql
-- Check constraints for data quality
ALTER TABLE transactions ADD CONSTRAINT chk_positive_amount
    CHECK (amount > 0);

ALTER TABLE transactions ADD CONSTRAINT chk_currency_format
    CHECK (currency_code ~ '^[A-Z]{3}$');

-- Foreign key with deferred checking for batch operations
ALTER TABLE transaction_metadata
    ADD CONSTRAINT fk_metadata_transaction
    FOREIGN KEY (transaction_id, partition_date)
    REFERENCES transactions(transaction_id, partition_date)
    DEFERRABLE INITIALLY DEFERRED;

-- Partial unique index for active transactions only
CREATE UNIQUE INDEX idx_unique_pending_reference
    ON transactions(reference_number)
    WHERE status IN ('pending', 'processing');
```

---

## 2. Indexing Strategy

### 2.1 Index Architecture Overview

```sql
-- =====================================================
-- 2.1.1 BRIN Indexes for Time-Series Data (High Performance, Low Overhead)
-- =====================================================

-- BRIN index for partition_date - excellent for range queries on time-series
CREATE INDEX idx_transactions_partition_date_brin
    ON transactions USING BRIN (partition_date)
    WITH (pages_per_range = 128);

-- BRIN for created_at within partition
CREATE INDEX idx_transactions_created_brin
    ON transactions USING BRIN (created_at)
    WITH (pages_per_range = 64);

-- =====================================================
-- 2.1.2 B-Tree Indexes for Lookup Patterns
-- =====================================================

-- Primary lookup by transaction UUID (globally unique)
CREATE UNIQUE INDEX idx_transactions_uuid
    ON transactions(transaction_uuid);

-- Account-based queries (most common access pattern)
CREATE INDEX idx_transactions_source_account
    ON transactions(source_account_id, partition_date DESC, created_at DESC);

CREATE INDEX idx_transactions_destination_account
    ON transactions(destination_account_id, partition_date DESC, created_at DESC);

-- Status-based queries for operations dashboards
CREATE INDEX idx_transactions_status_created
    ON transactions(status, created_at)
    WHERE status IN ('pending', 'processing');

-- Reference number lookups
CREATE INDEX idx_transactions_reference
    ON transactions(reference_number);

-- =====================================================
-- 2.1.3 Composite Indexes for Common Query Patterns
-- =====================================================

-- Dashboard query: recent transactions by account with status filter
CREATE INDEX idx_transactions_account_status_date
    ON transactions(source_account_id, status, created_at DESC);

-- Compliance reporting by region and date
CREATE INDEX idx_transactions_region_date
    ON transactions(regulatory_region, partition_date, created_at);

-- Risk analysis queries
CREATE INDEX idx_transactions_risk_score
    ON transactions(risk_score, created_at)
    WHERE risk_score > 0.7;

-- =====================================================
-- 2.1.4 GIN Index for JSONB Queries
-- =====================================================

CREATE INDEX idx_transaction_metadata_custom_fields
    ON transaction_metadata USING GIN (custom_fields jsonb_path_ops);

CREATE INDEX idx_transaction_metadata_merchant
    ON transaction_metadata USING GIN (merchant_data jsonb_path_ops);

-- =====================================================
-- 2.1.5 Covering Indexes (INCLUDE for Index-Only Scans)
-- =====================================================

-- Covering index for account statement generation
CREATE INDEX idx_transactions_account_covering
    ON transactions(source_account_id, partition_date DESC, created_at DESC)
    INCLUDE (transaction_uuid, amount, currency_code, status, transaction_type);
```

### 2.2 Index Selection Decision Matrix

| Query Pattern | Index Type | Rationale |
|--------------|------------|-----------|
| Time-range scans | BRIN | 10-100x smaller than B-tree, excellent correlation |
| UUID lookups | B-tree UNIQUE | Fast exact match, enforces uniqueness |
| Account + Date range | Composite B-tree | Supports range scans with equality prefix |
| JSONB containment | GIN | Efficient JSONB @> operations |
| Status filtering | Partial B-tree | Smaller index, faster for active queries |
| Statement generation | Covering B-tree | Index-only scan avoids heap access |

### 2.3 Index Maintenance Strategy

```sql
-- Automated index maintenance (run during low-traffic periods)

-- Reindex BRIN indexes monthly (minimal impact)
REINDEX INDEX CONCURRENTLY idx_transactions_partition_date_brin;

-- Reindex B-tree indexes based on bloat detection
SELECT schemaname, tablename, indexname,
       pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
       idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Update statistics with increased granularity for partitioned tables
ANALYZE transactions (transaction_type, status, source_account_id);
```

---

## 3. Partitioning Approach

### 3.1 Native Declarative Partitioning Strategy

```sql
-- =====================================================
-- 3.1.1 Monthly Partitions for Transaction Table
-- =====================================================

-- Create partitions for current year and next year
CREATE TABLE transactions_y2026m01 PARTITION OF transactions
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE transactions_y2026m02 PARTITION OF transactions
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Continue pattern for all months...

-- =====================================================
-- 3.1.2 Partition Management Functions
-- =====================================================

CREATE OR REPLACE FUNCTION create_monthly_partition(
    p_table_name TEXT,
    p_year INTEGER,
    p_month INTEGER
) RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    partition_name := p_table_name || '_y' || p_year || 'm' || LPAD(p_month::TEXT, 2, '0');
    start_date := make_date(p_year, p_month, 1);
    end_date := start_date + INTERVAL '1 month';

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES FROM (%L) TO (%L)
         PARTITION BY HASH (transaction_id)',
        partition_name, p_table_name, start_date, end_date
    );

    -- Create sub-partitions for high-volume months (hash partitioning)
    FOR i IN 0..7 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I_%s PARTITION OF %I
             FOR VALUES WITH (MODULUS 8, REMAINDER %s)',
            partition_name, i, partition_name, i
        );
    END LOOP;

    RETURN partition_name;
END;
$$;

-- =====================================================
-- 3.1.3 Automated Partition Creation (Cron Job)
-- =====================================================

CREATE OR REPLACE FUNCTION maintain_partitions()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    current_month DATE;
    next_month DATE;
    partition_exists BOOLEAN;
BEGIN
    current_month := DATE_TRUNC('month', CURRENT_DATE);
    next_month := current_month + INTERVAL '3 months';

    -- Create partitions 3 months ahead
    WHILE current_month < next_month LOOP
        SELECT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            AND c.relname = 'transactions_y' ||
                EXTRACT(YEAR FROM current_month) || 'm' ||
                LPAD(EXTRACT(MONTH FROM current_month)::TEXT, 2, '0')
        ) INTO partition_exists;

        IF NOT partition_exists THEN
            PERFORM create_monthly_partition(
                'transactions',
                EXTRACT(YEAR FROM current_month)::INTEGER,
                EXTRACT(MONTH FROM current_month)::INTEGER
            );
            RAISE NOTICE 'Created partition for %', current_month;
        END IF;

        current_month := current_month + INTERVAL '1 month';
    END LOOP;
END;
$$;

-- Schedule with pg_cron (if available) or external scheduler
SELECT cron.schedule('maintain-partitions', '0 1 * * *', 'SELECT maintain_partitions()');
```

### 3.2 Partition Pruning Optimization

```sql
-- Enable partition pruning (PostgreSQL 14+)
SET enable_partition_pruning = on;

-- Query examples that benefit from partition pruning

-- EXAMPLE 1: Single partition access
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM transactions
WHERE partition_date >= '2026-01-01'
  AND partition_date < '2026-02-01'
  AND source_account_id = 12345;
-- Expected: Only scans transactions_y2026m01 partition

-- EXAMPLE 2: Multi-partition with pruning
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM transactions
WHERE partition_date >= '2026-01-01'
  AND partition_date < '2026-04-01'
  AND status = 'completed';
-- Expected: Scans only 3 partitions (Jan, Feb, Mar)

-- EXAMPLE 3: Partition-wise aggregation
SET enable_partitionwise_aggregate = on;

EXPLAIN (ANALYZE, BUFFERS)
SELECT partition_date, COUNT(*), SUM(amount)
FROM transactions
WHERE partition_date >= '2026-01-01'
GROUP BY partition_date;
-- Expected: Parallel aggregation per partition
```

### 3.3 Partition Maintenance and Archival

```sql
-- =====================================================
-- 3.3.1 Detach Old Partitions for Archival
-- =====================================================

CREATE OR REPLACE FUNCTION archive_old_partitions(
    retention_months INTEGER DEFAULT 13
) RETURNS TABLE (
    partition_name TEXT,
    action_taken TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_date DATE;
    partition_record RECORD;
BEGIN
    cutoff_date := DATE_TRUNC('month', CURRENT_DATE) - (retention_months || ' months')::INTERVAL;

    FOR partition_record IN
        SELECT c.relname as part_name,
               pg_get_expr(c.relpartbound, c.oid) as bounds
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relispartition = true
          AND c.relname LIKE 'transactions_y%'
          AND pg_get_expr(c.relpartbound, c.oid) ~ 'to \(''([0-9]{4}-[0-9]{2}-[0-9]{2})''\)'
    LOOP
        -- Extract end date from partition bounds
        IF partition_record.bounds::TEXT ~ 'to \(''([0-9]{4}-[0-9]{2}-[0-9]{2})''\)' THEN
            DECLARE
                partition_end_date DATE;
            BEGIN
                partition_end_date := (regexp_match(partition_record.bounds::TEXT,
                    'to \(''([0-9]{4}-[0-9]{2}-[0-9]{2})''\)'))[1]::DATE;

                IF partition_end_date < cutoff_date THEN
                    -- Detach partition
                    EXECUTE format('ALTER TABLE transactions DETACH PARTITION %I',
                                   partition_record.part_name);

                    partition_name := partition_record.part_name;
                    action_taken := 'DETACHED for archival';
                    RETURN NEXT;
                END IF;
            END;
        END IF;
    END LOOP;
END;
$$;
```

---

## 4. Backup and Disaster Recovery

### 4.1 Backup Architecture

```bash
#!/bin/bash
# =====================================================
# 4.1.1 Comprehensive Backup Script
# =====================================================

# Configuration
PGHOST="primary.db.internal"
PGUSER="backup_user"
PGDATABASE="fintech_prod"
BACKUP_DIR="/backup/postgresql"
S3_BUCKET="s3://fintech-db-backups"
RETENTION_DAYS=30

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 1. Base Backup (pg_basebackup for PITR)
echo "Creating base backup..."
pg_basebackup \
    -h $PGHOST \
    -U $PGUSER \
    -D "$BACKUP_DIR/base/$TIMESTAMP" \
    -Ft \
    -z \
    -P \
    -X stream \
    -l "fintech_backup_$TIMESTAMP"

# 2. Continuous WAL Archiving (already configured in postgresql.conf)
# archive_command = 'test ! -f /backup/wal/%f && cp %p /backup/wal/%f'

# 3. Logical Backup for specific tables (compliance requirements)
echo "Creating logical backups..."
pg_dump \
    -h $PGHOST \
    -U $PGUSER \
    -d $PGDATABASE \
    --table=transactions \
    --table=transaction_audit_log \
    --format=directory \
    --jobs=4 \
    --compress=9 \
    -f "$BACKUP_DIR/logical/$TIMESTAMP"

# 4. Upload to S3
echo "Uploading to S3..."
aws s3 sync "$BACKUP_DIR/base/$TIMESTAMP" "$S3_BUCKET/base/$TIMESTAMP/"
aws s3 sync "$BACKUP_DIR/logical/$TIMESTAMP" "$S3_BUCKET/logical/$TIMESTAMP/"

# 5. Cleanup old backups
find "$BACKUP_DIR/base" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +
find "$BACKUP_DIR/logical" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +
```

### 4.2 PostgreSQL Configuration for PITR

```ini
# =====================================================
# 4.2.1 postgresql.conf - WAL Archiving Settings
# =====================================================

# WAL Level for replication and PITR
wal_level = replica
wal_log_hints = on

# Archiving
archive_mode = on
archive_command = 'test ! -f /backup/wal/%f && cp %p /backup/wal/%f && aws s3 cp /backup/wal/%f s3://fintech-db-backups/wal/%f'
archive_timeout = 300  # Force archive every 5 minutes

# Replication slots for standby servers
max_replication_slots = 10
max_wal_senders = 10

# Checkpoint settings for recovery performance
checkpoint_timeout = 10min
checkpoint_completion_target = 0.9
max_wal_size = 4GB
min_wal_size = 1GB

# Recovery target settings
recovery_target_timeline = 'latest'
recovery_target_action = 'promote'
```

### 4.3 Recovery Procedures

```bash
# =====================================================
# 4.3.1 Point-in-Time Recovery Script
# =====================================================

#!/bin/bash

RECOVERY_TARGET_TIME="2026-02-04 15:30:00"
BACKUP_DIR="/backup/postgresql/base/latest"
DATA_DIR="/var/lib/postgresql/14/main"

# 1. Stop PostgreSQL
systemctl stop postgresql

# 2. Clear data directory
rm -rf $DATA_DIR/*

# 3. Extract base backup
tar -xzf $BACKUP_DIR/base.tar.gz -C $DATA_DIR

# 4. Configure recovery
cat > $DATA_DIR/recovery.signal << EOF
restore_command = 'cp /backup/wal/%f %p'
recovery_target_time = '$RECOVERY_TARGET_TIME'
recovery_target_inclusive = true
EOF

# 5. Start PostgreSQL
systemctl start postgresql

# 6. Monitor recovery progress
tail -f /var/log/postgresql/postgresql-14-main.log | grep -i recovery
```

### 4.4 RPO/RTO Targets and Implementation

| Metric | Target | Implementation |
|--------|--------|----------------|
| **RPO** | < 1 minute | Synchronous replication + WAL archiving |
| **RTO** | < 5 minutes | Automated failover with Patroni |
| **Backup Retention** | 7 years | S3 Glacier Deep Archive for compliance |
| **PITR Window** | 35 days | Local WAL retention + S3 backup |

---

## 5. Performance Optimization Opportunities

### 5.1 Connection Pooling with PgBouncer

```ini
; =====================================================
; 5.1.1 PgBouncer Configuration (pgbouncer.ini)
; =====================================================

[databases]
fintech_prod = host=primary.db.internal port=5432 dbname=fintech_prod
fintech_replica = host=replica.db.internal port=5432 dbname=fintech_prod

[pgbouncer]
listen_port = 6432
listen_addr = 0.0.0.0
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

# Pool settings
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 50
min_pool_size = 10
reserve_pool_size = 25
reserve_pool_timeout = 3

# Connection limits per database
max_db_connections = 200
max_user_connections = 100

# Timeouts (critical for fintech reliability)
server_idle_timeout = 600
server_lifetime = 3600
server_connect_timeout = 15
query_timeout = 300
query_wait_timeout = 120
client_idle_timeout = 0
client_login_timeout = 60

# Logging
log_connections = 1
log_disconnections = 1
log_pooler_errors = 1
stats_period = 60
```

### 5.2 Query Optimization Examples

```sql
-- =====================================================
-- 5.2.1 Optimized Account Statement Query
-- =====================================================

-- BEFORE: Sequential scan with filter
SELECT * FROM transactions
WHERE source_account_id = 12345
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC;

-- AFTER: Index-only scan with covering index
SELECT transaction_uuid, amount, currency_code, status,
       transaction_type, created_at
FROM transactions
WHERE source_account_id = 12345
  AND partition_date >= '2026-01-01'
  AND partition_date < '2026-02-01'
ORDER BY partition_date DESC, created_at DESC
LIMIT 100;

-- =====================================================
-- 5.2.2 Batch Transaction Processing (Cursor-based)
-- =====================================================

CREATE OR REPLACE FUNCTION process_pending_transactions_batch()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    processed_count INTEGER := 0;
    batch_size INTEGER := 1000;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT transaction_id, partition_date, amount, source_account_id
        FROM transactions
        WHERE status = 'pending'
          AND created_at < NOW() - INTERVAL '5 minutes'
        ORDER BY created_at
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    LOOP
        -- Process transaction
        UPDATE transactions
        SET status = 'processing',
            updated_at = NOW(),
            version = version + 1
        WHERE transaction_id = rec.transaction_id
          AND partition_date = rec.partition_date;

        processed_count := processed_count + 1;
    END LOOP;

    RETURN processed_count;
END;
$$;

-- =====================================================
-- 5.2.3 Efficient Aggregation with Materialized View
-- =====================================================

CREATE MATERIALIZED VIEW daily_transaction_summary AS
SELECT
    partition_date,
    regulatory_region,
    transaction_type,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount,
    COUNT(DISTINCT source_account_id) as unique_accounts
FROM transactions
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY partition_date, regulatory_region, transaction_type;

CREATE UNIQUE INDEX idx_daily_summary_unique
    ON daily_transaction_summary(partition_date, regulatory_region, transaction_type);

-- Refresh concurrently to avoid blocking
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_transaction_summary;
```

### 5.3 Vacuum and Autovacuum Tuning

```ini
# =====================================================
# 5.3.1 postgresql.conf - Autovacuum Optimization
# =====================================================

# General autovacuum settings
autovacuum = on
autovacuum_max_workers = 6
autovacuum_naptime = 30s

# Aggressive settings for high-churn transaction tables
autovacuum_vacuum_scale_factor = 0.05
autovacuum_vacuum_threshold = 1000
autovacuum_analyze_scale_factor = 0.025
autovacuum_analyze_threshold = 500

# Cost limits (increase for faster vacuum)
autovacuum_vacuum_cost_limit = 2000
autovacuum_vacuum_cost_delay = 2ms

# Freeze protection
autovacuum_freeze_min_age = 50000000
autovacuum_freeze_table_age = 150000000
autovacuum_multixact_freeze_min_age = 5000000
autovacuum_multixact_freeze_table_age = 150000000

# Table-specific settings (run via ALTER TABLE)
ALTER TABLE transactions SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_cost_limit = 3000,
    fillfactor = 85  -- Leave room for HOT updates
);
```

### 5.4 Memory and Resource Configuration

```ini
# =====================================================
# 5.4.1 postgresql.conf - Memory Optimization
# =====================================================

# Shared memory
shared_buffers = 16GB  # 25% of total RAM
effective_cache_size = 48GB  # 75% of total RAM
work_mem = 64MB  # Per-operation, adjust based on concurrent queries
maintenance_work_mem = 2GB  # For VACUUM, CREATE INDEX

# Parallel query (PostgreSQL 14+)
max_parallel_workers_per_gather = 8
max_parallel_workers = 16
max_parallel_maintenance_workers = 4
parallel_tuple_cost = 0.05
parallel_setup_cost = 500

# WAL performance
wal_buffers = 256MB
wal_writer_delay = 10ms
wal_writer_flush_after = 1MB

# Checkpoint performance
checkpoint_timeout = 15min
max_wal_size = 8GB
min_wal_size = 2GB
checkpoint_completion_target = 0.9

# Async commit for non-critical operations (balance durability/perf)
synchronous_commit = on  # Keep on for fintech; use 'local' for reporting only
commit_delay = 0
commit_siblings = 5
```

---

## 6. Data Archival Strategy

### 6.1 Tiered Storage Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA TIER ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   HOT TIER   │    │  WARM TIER   │    │  COLD TIER   │      │
│  │   (0-13mo)   │    │  (13-36mo)   │    │  (36mo-7yr)  │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────┤      │
│  │ PostgreSQL   │    │ PostgreSQL   │    │ S3 Glacier   │      │
│  │ Primary      │    │ Archive DB   │    │ Deep Archive │      │
│  │ SSD Storage  │    │ Standard IO  │    │ + Parquet    │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────┤      │
│  │ Latency: 1ms │    │ Latency: 10ms│    │ Latency: 5min│      │
│  │ Access: Real │    │ Access: Query│    │ Access: Batch│      │
│  │ time         │    │ time         │    │ restore      │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Automated Archival Implementation

```sql
-- =====================================================
-- 6.2.1 Archive Table Schema (Compressed Storage)
-- =====================================================

CREATE TABLE transactions_archive (
    LIKE transactions INCLUDING ALL,
    archived_at TIMESTAMPTZ DEFAULT NOW(),
    archive_batch_id UUID
) WITH (fillfactor = 100, compression = 'zstd');

-- Partition archive table by year for efficient management
CREATE TABLE transactions_archive_y2024 PARTITION OF transactions_archive
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

-- =====================================================
-- 6.2.2 Archival Function
-- =====================================================

CREATE OR REPLACE FUNCTION archive_transactions_batch(
    p_cutoff_date DATE,
    p_batch_size INTEGER DEFAULT 10000
)
RETURNS TABLE (
    archived_count INTEGER,
    batch_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch_id UUID := gen_random_uuid();
    v_archived INTEGER := 0;
BEGIN
    -- Insert into archive table
    WITH archived AS (
        DELETE FROM transactions
        WHERE partition_date < p_cutoff_date
          AND status IN ('completed', 'failed', 'reversed')
          AND completed_at < NOW() - INTERVAL '30 days'
        RETURNING *
    )
    INSERT INTO transactions_archive (
        transaction_id, transaction_uuid, reference_number,
        transaction_type, status, amount, currency_code,
        source_account_id, destination_account_id,
        created_at, updated_at, completed_at, settlement_date,
        risk_score, compliance_flags, regulatory_region,
        created_by, updated_by, version, partition_date,
        archive_batch_id
    )
    SELECT
        transaction_id, transaction_uuid, reference_number,
        transaction_type, status, amount, currency_code,
        source_account_id, destination_account_id,
        created_at, updated_at, completed_at, settlement_date,
        risk_score, compliance_flags, regulatory_region,
        created_by, updated_by, version, partition_date,
        v_batch_id
    FROM archived;

    GET DIAGNOSTICS v_archived = ROW_COUNT;

    archived_count := v_archived;
    batch_id := v_batch_id;
    RETURN NEXT;
END;
$$;

-- =====================================================
-- 6.2.3 S3 Export for Cold Storage
-- =====================================================

CREATE EXTENSION IF NOT EXISTS aws_s3;  -- If using AWS RDS

-- Alternative: Export to Parquet using pg_duckdb or external process
CREATE OR REPLACE FUNCTION export_to_cold_storage(
    p_year INTEGER,
    p_s3_path TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_copy_command TEXT;
BEGIN
    -- Export to CSV for S3 (can be converted to Parquet by Lambda)
    v_copy_command := format(
        'COPY (SELECT * FROM transactions_archive WHERE partition_date >= %L AND partition_date < %L)
         TO PROGRAM ''aws s3 cp - %s/transactions_%s.csv --storage-class DEEP_ARCHIVE''
         WITH (FORMAT CSV, HEADER)',
        make_date(p_year, 1, 1),
        make_date(p_year + 1, 1, 1),
        p_s3_path,
        p_year
    );

    EXECUTE v_copy_command;

    RETURN format('Exported transactions for year %s to %s', p_year, p_s3_path);
END;
$$;
```

### 6.3 Data Retention Compliance

```sql
-- =====================================================
-- 6.3.1 Retention Policy Enforcement
-- =====================================================

-- Create retention policy table
CREATE TABLE data_retention_policies (
    policy_id SERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL UNIQUE,
    retention_years INTEGER NOT NULL,
    archive_after_months INTEGER NOT NULL,
    compliance_framework VARCHAR(32),  -- 'SOX', 'PCI-DSS', 'GDPR', etc.
    last_purged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert policies
INSERT INTO data_retention_policies
    (table_name, retention_years, archive_after_months, compliance_framework)
VALUES
    ('transactions', 7, 13, 'SOX'),
    ('transaction_audit_log', 7, 13, 'SOX'),
    ('transaction_metadata', 7, 13, 'PCI-DSS'),
    ('session_logs', 2, 3, 'GDPR');

-- =====================================================
-- 6.3.2 Purge Function (GDPR Right to be Forgotten)
-- =====================================================

CREATE OR REPLACE FUNCTION purge_customer_data(
    p_customer_id BIGINT,
    p_verification_code VARCHAR(64)
)
RETURNS TABLE (
    table_name TEXT,
    records_purged INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    -- Verify authorization code (implementation depends on your system)
    -- This is a placeholder for actual verification logic

    -- Anonymize transactions (keep financial records, remove PII)
    UPDATE transaction_metadata
    SET customer_data = jsonb_build_object(
        'anonymized', true,
        'original_customer_id', encode(digest(p_customer_id::TEXT, 'sha256'), 'hex'),
        'anonymized_at', NOW()
    )
    WHERE customer_data->>'customer_id' = p_customer_id::TEXT;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    table_name := 'transaction_metadata';
    records_purged := v_count;
    RETURN NEXT;

    -- Log the purge action for compliance audit
    INSERT INTO gdpr_purge_log (
        customer_id_hash,
        verification_code,
        purged_at,
        purged_by
    ) VALUES (
        encode(digest(p_customer_id::TEXT, 'sha256'), 'hex'),
        p_verification_code,
        NOW(),
        current_user
    );
END;
$$;
```

---

## 7. Replication Lag Handling

### 7.1 Replication Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION REPLICATION                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐                                               │
│  │   PRIMARY        │◄─── Application Writes                        │
│  │   us-east-1      │                                               │
│  │   (Synchronous)  │                                               │
│  └────────┬─────────┘                                               │
│           │                                                          │
│     ┌─────┴─────┬──────────────┬──────────────┐                     │
│     │           │              │              │                     │
│     ▼           ▼              ▼              ▼                     │
│ ┌────────┐ ┌────────┐   ┌──────────┐   ┌──────────┐                │
│ │Sync    │ │Sync    │   │Async     │   │Async     │                │
│ │Replica │ │Replica │   │Replica   │   │Replica   │                │
│ │us-west │ │eu-west │   │ap-south  │   │dr-site   │                │
│ └────────┘ └────────┘   └──────────┘   └──────────┘                │
│     │           │              │              │                     │
│     └───────────┴──────────────┴──────────────┘                     │
│                  WAL Streaming (replication slots)                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 Replication Configuration

```ini
# =====================================================
# 7.2.1 Primary Server Configuration
# =====================================================

# postgresql.conf on primary
wal_level = replica
max_wal_senders = 16
max_replication_slots = 16
wal_keep_size = 16GB
max_slot_wal_keep_size = 32GB

# Synchronous replication for critical regions
synchronous_commit = remote_apply
synchronous_standby_names = 'FIRST 2 (replica_us_west, replica_eu_west)'

# Monitoring
track_commit_timestamp = on
```

```ini
# =====================================================
# 7.2.2 Replica Configuration
# =====================================================

# postgresql.conf on replica
hot_standby = on
hot_standby_feedback = on
max_standby_streaming_delay = 30s
max_standby_archive_delay = 60s

# Read-only workload optimization
random_page_cost = 1.1  # SSD storage
effective_cache_size = 48GB
```

### 7.3 Lag Monitoring and Alerting

```sql
-- =====================================================
-- 7.3.1 Replication Lag Monitoring View
-- =====================================================

CREATE OR REPLACE VIEW replication_status AS
SELECT
    client_addr,
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_size_pretty(pg_wal_lsn_diff(sent_lsn, replay_lsn)) as lag_bytes,
    EXTRACT(EPOCH FROM (NOW() - backend_start))::INTEGER as connected_seconds,
    sync_state
FROM pg_stat_replication;

-- =====================================================
-- 7.3.2 Lag Alert Query
-- =====================================================

SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, replay_lsn) as lag_bytes,
    CASE
        WHEN pg_wal_lsn_diff(sent_lsn, replay_lsn) > 1073741824 THEN 'CRITICAL'  -- 1GB
        WHEN pg_wal_lsn_diff(sent_lsn, replay_lsn) > 104857600 THEN 'WARNING'    -- 100MB
        ELSE 'OK'
    END as alert_level
FROM pg_stat_replication
WHERE application_name LIKE 'replica_%';

-- =====================================================
-- 7.3.3 Application-Level Lag Handling
-- =====================================================

-- Function to check if replica is safe to read from
CREATE OR REPLACE FUNCTION is_replica_current(
    p_max_lag_seconds INTEGER DEFAULT 5
)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
AS $$
    SELECT CASE
        WHEN pg_is_in_recovery() THEN
            -- Check if recovery lag is acceptable
            EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp())) < p_max_lag_seconds
        ELSE
            TRUE  -- This is the primary
    END;
$$;

-- Read routing with lag awareness
CREATE OR REPLACE FUNCTION get_transaction_with_fallback(
    p_transaction_uuid UUID
)
RETURNS TABLE (LIKE transactions)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Try replica first if current
    IF is_replica_current() THEN
        RETURN QUERY
        SELECT * FROM transactions
        WHERE transaction_uuid = p_transaction_uuid;

        IF FOUND THEN
            RETURN;
        END IF;
    END IF;

    -- Fallback to primary
    RETURN QUERY
    SELECT * FROM transactions
    WHERE transaction_uuid = p_transaction_uuid;
END;
$$;
```

### 7.4 Handling Large Replication Lag

```sql
-- =====================================================
-- 7.4.1 Pause Replication for Maintenance (Emergency)
-- =====================================================

-- On replica: pause replication
SELECT pg_wal_replay_pause();

-- Check pause state
SELECT pg_is_wal_replay_paused();

-- Resume replication
SELECT pg_wal_replay_resume();

-- =====================================================
-- 7.4.2 Replication Slot Management (Prevent WAL Bloat)
-- =====================================================

-- Create replication slot for each replica
SELECT pg_create_physical_replication_slot('replica_us_west', true);
SELECT pg_create_physical_replication_slot('replica_eu_west', true);

-- Monitor slot lag
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained_wal
FROM pg_replication_slots;

-- Drop inactive slots (after confirming replica is gone)
SELECT pg_drop_replication_slot('old_replica_slot');
```

---

## 8. Redis Caching Strategy

### 8.1 Cache Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      MULTI-TIER CACHING                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │   L1 Cache   │   │   L2 Cache   │   │   L3 Cache   │            │
│  │  (In-Memory) │   │    (Redis)   │   │  (DB Buffer) │            │
│  ├──────────────┤   ├──────────────┤   ├──────────────┤            │
│  │ Application  │   │ Redis Cluster│   │ PostgreSQL   │            │
│  │  Local Cache │   │  Multi-Region│   │ Shared Buffers│            │
│  ├──────────────┤   ├──────────────┤   ├──────────────┤            │
│  │ Size: ~100MB │   │ Size: 10GB   │   │ Size: 16GB   │            │
│  │ TTL: 60s     │   │ TTL: 300s    │   │ Managed by DB│            │
│  │ Hit: ~50%    │   │ Hit: ~40%    │   │ Hit: ~10%    │            │
│  └──────────────┘   └──────────────┘   └──────────────┘            │
│                                                                      │
│  Cache Key Patterns:                                                 │
│  - txn:{uuid}      → Transaction details                             │
│  - acct:{id}:bal   → Account balance                                 │
│  - stmt:{id}:{date}→ Account statement summary                       │
│  - rate:{from}:{to}→ Exchange rates                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Redis Configuration

```redis
# =====================================================
# 8.2.1 redis.conf - High Availability Setup
# =====================================================

# Memory management
maxmemory 10gb
maxmemory-policy allkeys-lru
maxmemory-samples 10

# Persistence (for session data)
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfsync everysec
no-appendfsync-on-rewrite yes

# Replication
replica-read-only yes
replica-serve-stale-data yes

# Cluster mode
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 5000
cluster-require-full-coverage no

# Performance
tcp-keepalive 300
timeout 0
tcp-backlog 511
```

### 8.3 Cache Implementation Patterns

```python
# =====================================================
# 8.3.1 Python Cache Implementation with Redis
# =====================================================

import json
import hashlib
from functools import wraps
from typing import Optional, Any
import redis
from pydantic import BaseModel

class CacheManager:
    def __init__(self, redis_client: redis.Redis, default_ttl: int = 300):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.local_cache = {}  # L1 cache
        self.local_ttl = 60

    def get_transaction(self, transaction_uuid: str) -> Optional[dict]:
        """Multi-tier cache lookup for transaction."""
        cache_key = f"txn:{transaction_uuid}"

        # L1: Local cache
        if cache_key in self.local_cache:
            return self.local_cache[cache_key]

        # L2: Redis
        cached = self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            self.local_cache[cache_key] = data  # Populate L1
            return data

        # L3: Database (not shown - would query DB here)
        return None

    def set_transaction(self, transaction_uuid: str, data: dict, ttl: int = None):
        """Cache transaction with multi-tier storage."""
        cache_key = f"txn:{transaction_uuid}"

        # Update L1
        self.local_cache[cache_key] = data

        # Update L2 (Redis)
        self.redis.setex(
            cache_key,
            ttl or self.default_ttl,
            json.dumps(data, default=str)
        )

    def invalidate_transaction(self, transaction_uuid: str):
        """Invalidate transaction across all cache tiers."""
        cache_key = f"txn:{transaction_uuid}"
        self.local_cache.pop(cache_key, None)
        self.redis.delete(cache_key)

    def get_account_balance(self, account_id: int) -> Optional[dict]:
        """Cached account balance with short TTL for consistency."""
        cache_key = f"acct:{account_id}:bal"

        # Try L1 first (very short TTL for balance)
        cached = self.local_cache.get(cache_key)
        if cached:
            return cached

        # Try Redis with shorter TTL for balances
        cached = self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            self.local_cache[cache_key] = data
            return data

        return None

def cached_query(ttl: int = 300, key_prefix: str = "query"):
    """Decorator for caching function results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix, func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # Try cache
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

            # Execute and cache
            result = func(self, *args, **kwargs)
            self.redis.setex(cache_key, ttl, json.dumps(result, default=str))
            return result
        return wrapper
    return decorator

# =====================================================
# 8.3.2 Cache-Aside Pattern for Account Operations
# =====================================================

class AccountService:
    def __init__(self, db_pool, cache_manager: CacheManager):
        self.db = db_pool
        self.cache = cache_manager

    async def get_balance(self, account_id: int) -> dict:
        """Get account balance with cache-aside pattern."""
        # Try cache first
        cached = self.cache.get_account_balance(account_id)
        if cached:
            return cached

        # Cache miss - query database
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT account_id, available_balance, pending_balance,
                       reserved_balance, currency_code, updated_at
                FROM account_balances
                WHERE account_id = $1
                """,
                account_id
            )

        if not row:
            raise AccountNotFoundError(account_id)

        result = dict(row)

        # Cache with short TTL for balance data (5 seconds)
        self.cache.set_account_balance(account_id, result, ttl=5)

        return result

    async def update_balance(self, account_id: int, amount: decimal.Decimal):
        """Update balance with cache invalidation."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # Update database
                await conn.execute(
                    """
                    UPDATE account_balances
                    SET available_balance = available_balance + $2,
                        updated_at = NOW(),
                        version = version + 1
                    WHERE account_id = $1
                    """,
                    account_id, amount
                )

                # Invalidate cache immediately
                self.cache.invalidate_account_balance(account_id)
```

---

## 9. Monitoring and Alerting

### 9.1 Key Performance Indicators

```sql
-- =====================================================
-- 9.1.1 Database Health Monitoring View
-- =====================================================

CREATE OR REPLACE VIEW db_health_metrics AS
WITH table_stats AS (
    SELECT
        schemaname,
        relname,
        n_live_tup,
        n_dead_tup,
        CASE WHEN n_live_tup > 0
            THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
            ELSE 0
        END as dead_tuple_ratio,
        last_vacuum,
        last_autovacuum,
        last_analyze,
        seq_scan,
        idx_scan
    FROM pg_stat_user_tables
),
index_stats AS (
    SELECT
        schemaname,
        relname as table_name,
        indexrelname as index_name,
        idx_scan,
        idx_tup_read,
        pg_size_pretty(pg_relation_size(indexrelid)) as index_size
    FROM pg_stat_user_indexes
)
SELECT
    'table_bloat' as metric,
    relname as target,
    dead_tuple_ratio as value,
    CASE
        WHEN dead_tuple_ratio > 20 THEN 'CRITICAL'
        WHEN dead_tuple_ratio > 10 THEN 'WARNING'
        ELSE 'OK'
    END as status
FROM table_stats

UNION ALL

SELECT
    'index_usage' as metric,
    index_name as target,
    idx_scan::numeric as value,
    CASE
        WHEN idx_scan = 0 THEN 'WARNING'
        ELSE 'OK'
    END as status
FROM index_stats;

-- =====================================================
-- 9.1.2 Slow Query Monitoring
-- =====================================================

-- Enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- View slow queries
SELECT
    query,
    calls,
    round(total_exec_time::numeric, 2) as total_time,
    round(mean_exec_time::numeric, 2) as avg_time,
    round(max_exec_time::numeric, 2) as max_time,
    rows,
    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) as hit_percent
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_statements%'
ORDER BY mean_exec_time DESC
LIMIT 20;
```

### 9.2 Alerting Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Replication Lag | > 100 MB | > 1 GB | Scale replicas, check network |
| Connection Usage | > 70% | > 90% | Increase pool size, investigate |
| Disk Usage | > 75% | > 90% | Archive old data, expand storage |
| Dead Tuple Ratio | > 10% | > 20% | Schedule VACUUM FULL |
| Query Latency (p99) | > 100ms | > 500ms | Optimize queries, add indexes |
| Cache Hit Ratio | < 95% | < 90% | Increase shared_buffers |
| Lock Waits | > 10/sec | > 50/sec | Kill blocking queries |

---

## 10. Implementation Checklist

### Phase 1: Foundation (Weeks 1-2)
- [ ] Set up PostgreSQL 14 primary with proper configuration
- [ ] Implement schema with partitioning
- [ ] Create core indexes (B-tree, BRIN, GIN)
- [ ] Set up PgBouncer connection pooling
- [ ] Configure WAL archiving to S3

### Phase 2: High Availability (Weeks 3-4)
- [ ] Deploy synchronous replicas in us-west and eu-west
- [ ] Configure Patroni for automated failover
- [ ] Set up async replicas for read scaling
- [ ] Implement replication lag monitoring

### Phase 3: Performance Optimization (Weeks 5-6)
- [ ] Deploy Redis Cluster for caching layer
- [ ] Implement cache-aside patterns in application
- [ ] Create materialized views for reporting
- [ ] Tune autovacuum settings
- [ ] Optimize queries based on pg_stat_statements

### Phase 4: Data Management (Weeks 7-8)
- [ ] Implement automated partition creation
- [ ] Set up archival process for old partitions
- [ ] Configure S3 lifecycle policies for cold storage
- [ ] Test PITR recovery procedures

### Phase 5: Monitoring (Week 9)
- [ ] Deploy Prometheus/Grafana for metrics
- [ ] Set up PagerDuty alerts for critical thresholds
- [ ] Create runbooks for common issues
- [ ] Document disaster recovery procedures

---

## Appendix A: Configuration Summary

### Critical PostgreSQL Parameters

```ini
# Connection Settings
max_connections = 500
superuser_reserved_connections = 10
listen_addresses = '*'
port = 5432

# Memory Settings
shared_buffers = 16GB
effective_cache_size = 48GB
work_mem = 64MB
maintenance_work_mem = 2GB

# WAL Settings
wal_level = replica
wal_buffers = 256MB
max_wal_size = 8GB
min_wal_size = 2GB
checkpoint_completion_target = 0.9
archive_mode = on
archive_command = 'aws s3 cp %p s3://bucket/wal/%f'

# Replication
max_wal_senders = 16
max_replication_slots = 16
wal_keep_size = 16GB
synchronous_commit = remote_apply
synchronous_standby_names = 'FIRST 2 (replica_1, replica_2)'

# Query Planning
random_page_cost = 1.1
effective_io_concurrency = 200
max_parallel_workers_per_gather = 8
max_parallel_workers = 16

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_min_duration_statement = 1000
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
```

### Hardware Recommendations

| Component | Specification | Notes |
|-----------|--------------|-------|
| CPU | 32+ cores | Intel Xeon or AMD EPYC |
| RAM | 128GB+ | DDR4 ECC |
| Storage | NVMe SSD RAID 10 | 10+ TB usable |
| Network | 10Gbps+ | Low latency between replicas |
| IOPS | 50,000+ | Provisioned IOPS for cloud |

---

## Appendix B: Query Optimization Examples

### Example 1: Account Statement Generation

```sql
-- Optimized query for account statements
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT
    t.transaction_uuid,
    t.transaction_type,
    t.amount,
    t.currency_code,
    t.status,
    t.created_at,
    m.merchant_data->>'name' as merchant_name
FROM transactions t
LEFT JOIN transaction_metadata m
    ON t.transaction_id = m.transaction_id
    AND t.partition_date = m.partition_date
WHERE t.source_account_id = 12345
  AND t.partition_date >= '2026-01-01'
  AND t.partition_date < '2026-02-01'
ORDER BY t.created_at DESC
LIMIT 50;

-- Expected plan: Index-only scan using idx_transactions_account_covering
```

### Example 2: Daily Reconciliation Report

```sql
-- Optimized aggregation with parallel query
SET max_parallel_workers_per_gather = 4;

SELECT
    settlement_date,
    regulatory_region,
    transaction_type,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    COUNT(DISTINCT source_account_id) as unique_accounts
FROM transactions
WHERE partition_date = CURRENT_DATE - 1
GROUP BY settlement_date, regulatory_region, transaction_type;

-- Expected: Parallel Seq Scan with HashAggregate
```

### Example 3: Risk Analysis Query

```sql
-- Optimized risk query with partial index
SELECT
    t.transaction_id,
    t.amount,
    t.risk_score,
    m.device_fingerprint->>'device_id' as device_id
FROM transactions t
JOIN transaction_metadata m
    ON t.transaction_id = m.transaction_id
WHERE t.risk_score > 0.8
  AND t.created_at > NOW() - INTERVAL '24 hours'
ORDER BY t.risk_score DESC, t.amount DESC
LIMIT 100;

-- Expected: Index scan using idx_transactions_risk_score
```

---

**Document Version:** 1.0
**Last Updated:** 2026-02-04
**Author:** Database Architecture Team
**Review Cycle:** Quarterly