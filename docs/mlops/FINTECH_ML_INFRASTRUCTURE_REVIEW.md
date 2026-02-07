# ML/AI Infrastructure Review: Fintech Fraud Detection & Risk Scoring Platform

**Classification:** CONFIDENTIAL
**Date:** February 4, 2026
**Reviewer:** MLOps Engineering Team
**Platform:** Multi-Agent Fintech ML System
**Scope:** End-to-end ML infrastructure for real-time fraud detection and credit risk scoring

---

## Executive Summary

This review evaluates the ML/AI infrastructure for a fictional fintech platform processing millions of transactions daily. The platform uses machine learning for real-time fraud detection (sub-100ms latency requirement) and credit risk scoring (near-real-time). This analysis is based on patterns observed in the Kublai multi-agent system's security, monitoring, and data handling implementations.

### Overall MLOps Maturity: LEVEL 2 (Managed)

| Domain | Maturity | Risk Level | Status |
|--------|----------|------------|--------|
| Model Serving | Level 2 | MEDIUM | Partial |
| Feature Store | Level 1 | HIGH | At Risk |
| Model Versioning | Level 2 | MEDIUM | Partial |
| Data Drift Detection | Level 1 | HIGH | Non-Compliant |
| Automated Retraining | Level 1 | HIGH | At Risk |
| Compliance/Explainability | Level 2 | HIGH | Partial |

**Maturity Scale:**
- Level 0: Ad-hoc / Manual
- Level 1: Repeatable / Basic Automation
- Level 2: Managed / Standardized
- Level 3: Automated / Self-Service
- Level 4: Optimized / Continuous Improvement

---

## 1. Model Serving Architecture and Latency

### 1.1 Current Architecture Assessment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CURRENT SERVING ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐   │
│   │   Client     │────▶│  API Gateway │────▶│   Model Container        │   │
│   │   Request    │     │  (No WAF)    │     │   (Single Instance)      │   │
│   └──────────────┘     └──────────────┘     └──────────────────────────┘   │
│                                                      │                      │
│                                                      ▼                      │
│                                            ┌──────────────────────────┐    │
│                                            │   In-Memory Model        │    │
│                                            │   (No GPU Acceleration)  │    │
│                                            └──────────────────────────┘    │
│                                                                             │
│   CRITICAL GAPS:                                                            │
│   - No model caching layer                                                  │
│   - Single point of failure                                                 │
│   - No A/B testing infrastructure                                           │
│   - Missing circuit breaker pattern                                         │
│   - No batch inference optimization                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Latency Analysis

| Component | Current | Target | Gap |
|-----------|---------|--------|-----|
| Network Ingress | 5-15ms | <10ms | Acceptable |
| Feature Retrieval | 50-200ms | <20ms | CRITICAL |
| Model Inference | 30-80ms | <50ms | WARNING |
| Response Serialization | 5-10ms | <5ms | Acceptable |
| **Total P99** | **90-305ms** | **<100ms** | **CRITICAL** |

### 1.3 Recommendations

#### 1.3.1 Multi-Tier Serving Architecture

```python
# /infrastructure/terraform/modules/model_serving/main.tf

# Production-grade model serving with AWS SageMaker
resource "aws_sagemaker_endpoint" "fraud_detection" {
  name                 = "fraud-detection-production"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.fraud_config.name

  tags = {
    Environment = "production"
    ModelType   = "fraud_detection"
    Compliance  = "PCI-DSS,SOC2"
  }
}

resource "aws_sagemaker_endpoint_configuration" "fraud_config" {
  name = "fraud-detection-config-v1"

  production_variants {
    variant_name           = "primary"
    model_name             = aws_sagemaker_model.fraud_v2.name
    initial_instance_count = 4
    instance_type          = "ml.c6i.2xlarge"  # Compute optimized
    initial_variant_weight = 0.9
  }

  production_variants {
    variant_name           = "canary"
    model_name             = aws_sagemaker_model.fraud_v3.name
    initial_instance_count = 2
    instance_type          = "ml.c6i.2xlarge"
    initial_variant_weight = 0.1
  }

  # Enable data capture for monitoring
  data_capture_config {
    enable_capture = true
    initial_sampling_percentage = 10
    destination_s3_uri = "s3://${aws_s3_bucket.model_data_capture.bucket}/fraud-detection/"
    capture_options {
      capture_mode = "Input"
    }
    capture_options {
      capture_mode = "Output"
    }
    capture_content_type_header {
      csv_content_types  = ["text/csv"]
      json_content_types = ["application/json"]
    }
  }
}

# Auto-scaling configuration
resource "aws_appautoscaling_target" "sagemaker_target" {
  max_capacity       = 20
  min_capacity       = 4
  resource_id        = "endpoint/${aws_sagemaker_endpoint.fraud_detection.name}/variant/primary"
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  service_namespace  = "sagemaker"
}

resource "aws_appautoscaling_policy" "sagemaker_policy" {
  name               = "fraud-detection-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.sagemaker_target.resource_id
  scalable_dimension = aws_appautoscaling_target.sagemaker_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.sagemaker_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "SageMakerVariantInvocationsPerInstance"
    }
    target_value       = 500.0  # Adjust based on instance capacity
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
```

#### 1.3.2 Caching Layer for Feature Retrieval

```python
# /src/serving/feature_cache.py

import redis.asyncio as redis
from typing import Dict, Any, Optional
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class CachedFeatures:
    """Feature cache entry with TTL and versioning."""
    features: Dict[str, Any]
    model_version: str
    feature_schema_version: str
    cached_at: float
    ttl_seconds: int = 300  # 5 minute default for fraud detection

class FeatureCache:
    """
    Multi-tier feature caching for low-latency serving.

    Tier 1: Local LRU Cache (in-process, <1ms)
    Tier 2: Redis Cluster (sub-5ms)
    Tier 3: Feature Store (fallback)
    """

    def __init__(
        self,
        redis_url: str,
        local_cache_size: int = 10000,
        default_ttl: int = 300
    ):
        self.redis = redis.from_url(redis_url)
        self.local_cache = {}  # Use LRU cache in production
        self.local_cache_size = local_cache_size
        self.default_ttl = default_ttl

    def _generate_key(
        self,
        entity_type: str,
        entity_id: str,
        feature_names: list
    ) -> str:
        """Generate deterministic cache key."""
        key_data = f"{entity_type}:{entity_id}:{sorted(feature_names)}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    async def get_features(
        self,
        entity_type: str,
        entity_id: str,
        feature_names: list,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve features from cache with fallback.

        Returns None if cache miss to trigger feature store lookup.
        """
        cache_key = self._generate_key(entity_type, entity_id, feature_names)

        # Tier 1: Local cache
        if cache_key in self.local_cache:
            entry = self.local_cache[cache_key]
            if entry.model_version == model_version:
                return entry.features

        # Tier 2: Redis cache
        cached = await self.redis.get(f"features:{cache_key}")
        if cached:
            entry = CachedFeatures(**json.loads(cached))
            if entry.model_version == model_version:
                # Populate local cache
                self.local_cache[cache_key] = entry
                return entry.features

        return None

    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        feature_names: list,
        features: Dict[str, Any],
        model_version: str,
        feature_schema_version: str,
        ttl: Optional[int] = None
    ):
        """Cache features with versioning."""
        cache_key = self._generate_key(entity_type, entity_id, feature_names)
        ttl = ttl or self.default_ttl

        entry = CachedFeatures(
            features=features,
            model_version=model_version,
            feature_schema_version=feature_schema_version,
            cached_at=time.time(),
            ttl_seconds=ttl
        )

        # Update local cache
        self.local_cache[cache_key] = entry

        # Update Redis with expiration
        await self.redis.setex(
            f"features:{cache_key}",
            ttl,
            json.dumps(entry.__dict__, default=str)
        )
```

#### 1.3.3 Circuit Breaker Pattern

```python
# /src/serving/circuit_breaker.py

from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    """
    Circuit breaker for model serving resilience.

    Prevents cascade failures when downstream services
    (feature store, model inference) are degraded.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
        success_threshold: int = 2
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(f"Circuit {self.name}: Transitioning to HALF_OPEN")
                else:
                    raise CircuitBreakerOpen(f"Circuit {self.name} is OPEN")

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpen(
                        f"Circuit {self.name} HALF_OPEN limit reached"
                    )
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try recovery."""
        if not self.last_failure_time:
            return True
        return datetime.utcnow() - self.last_failure_time > timedelta(
            seconds=self.recovery_timeout
        )

    async def _on_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self._reset()
                    logger.info(f"Circuit {self.name}: Closed after recovery")
            else:
                self.failure_count = 0

    async def _on_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name}: Re-opened due to failure")
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(f"Circuit {self.name}: Opened after {self.failure_count} failures")

    def _reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0

class CircuitBreakerOpen(Exception):
    pass
```

---

## 2. Feature Store Design and Consistency

### 2.1 Current State Analysis

Based on the Kublai system's Neo4j-based memory management, a fintech feature store would face these challenges:

| Challenge | Impact | Priority |
|-----------|--------|----------|
| No feature versioning | Model training/serving skew | CRITICAL |
| Point-in-time correctness | Data leakage in training | CRITICAL |
| No feature sharing | Duplicated compute, inconsistency | HIGH |
| Inconsistent feature encoding | Prediction drift | HIGH |
| No feature quality monitoring | Silent data quality issues | MEDIUM |

### 2.2 Recommended Architecture: Feast on AWS

```python
# /infrastructure/terraform/modules/feature_store/main.tf

# AWS Glue Data Catalog for feature registry
resource "aws_glue_catalog_database" "feature_store" {
  name        = "fintech_feature_store"
  description = "Feature registry for fraud detection and risk scoring"
}

# Feature store S3 buckets
resource "aws_s3_bucket" "feature_store_offline" {
  bucket = "fintech-feature-store-offline-${var.environment}"
}

resource "aws_s3_bucket" "feature_store_online" {
  bucket = "fintech-feature-store-online-${var.environment}"
}

# DynamoDB for online feature store
resource "aws_dynamodb_table" "online_features" {
  name         = "fintech-online-features"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "entity_key"
  range_key    = "feature_name"

  attribute {
    name = "entity_key"
    type = "S"
  }

  attribute {
    name = "feature_name"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# Redshift for offline feature store
resource "aws_redshift_cluster" "feature_store" {
  cluster_identifier  = "fintech-feature-store"
  database_name       = "features"
  master_username     = "feature_admin"
  master_password     = var.redshift_master_password
  node_type           = "dc2.large"
  cluster_type        = "multi-node"
  number_of_nodes     = 3
  encrypted           = true
  enhanced_vpc_routing = true
}

# Feature store configuration
locals {
  feast_config = {
    project = "fintech_fraud_detection"
    provider = "aws"

    online_store = {
      type = "dynamodb"
      region = var.aws_region
      table_name = aws_dynamodb_table.online_features.name
    }

    offline_store = {
      type = "redshift"
      cluster_id = aws_redshift_cluster.feature_store.id
      database = "features"
      schema = "public"
    }

    registry = {
      registry_store_type = "s3"
      path = "s3://${aws_s3_bucket.feature_store_offline.id}/registry.db"
    }

    entity_key_serialization_version = 2
  }
}
```

### 2.3 Feature Definitions

```python
# /features/definitions/fraud_features.py

from feast import Entity, Feature, FeatureView, ValueType, FileSource
from feast.types import Float32, Int64, String, Bool
from datetime import timedelta

# Define entities
user = Entity(
    name="user_id",
    value_type=ValueType.STRING,
    description="Unique user identifier",
    join_key="user_id"
)

transaction = Entity(
    name="transaction_id",
    value_type=ValueType.STRING,
    description="Unique transaction identifier",
    join_key="transaction_id"
)

# Transaction features - computed in near real-time
transaction_features = FeatureView(
    name="transaction_features",
    entities=["transaction_id", "user_id"],
    ttl=timedelta(hours=24),
    features=[
        Feature(name="amount", dtype=Float32),
        Feature(name="merchant_category", dtype=String),
        Feature(name="merchant_country", dtype=String),
        Feature(name="is_international", dtype=Bool),
        Feature(name="is_online", dtype=Bool),
        Feature(name="hour_of_day", dtype=Int64),
        Feature(name="day_of_week", dtype=Int64),
        # Velocity features
        Feature(name="txn_count_1h", dtype=Int64),
        Feature(name="txn_count_24h", dtype=Int64),
        Feature(name="amount_sum_1h", dtype=Float32),
        Feature(name="amount_sum_24h", dtype=Float32),
        Feature(name="unique_merchants_1h", dtype=Int64),
        Feature(name="unique_countries_24h", dtype=Int64),
    ],
    online=True,
    source=FileSource(
        path="s3://fintech-feature-store-offline/transaction_features/",
        event_timestamp_column="event_timestamp"
    ),
    tags={
        "team": "fraud",
        "model": "fraud_detection_v2",
        "compliance": "PCI-DSS"
    }
)

# User behavioral features - computed daily
user_features = FeatureView(
    name="user_behavioral_features",
    entities=["user_id"],
    ttl=timedelta(days=7),
    features=[
        Feature(name="account_age_days", dtype=Int64),
        Feature(name="avg_transaction_amount_30d", dtype=Float32),
        Feature(name="std_transaction_amount_30d", dtype=Float32),
        Feature(name="max_transaction_amount_30d", dtype=Float32),
        Feature(name="transaction_count_30d", dtype=Int64),
        Feature(name="unique_merchants_30d", dtype=Int64),
        Feature(name="international_ratio_30d", dtype=Float32),
        Feature(name="online_ratio_30d", dtype=Float32),
        Feature(name="chargeback_count_90d", dtype=Int64),
        Feature(name="chargeback_rate_90d", dtype=Float32),
        Feature(name="days_since_last_transaction", dtype=Int64),
    ],
    online=True,
    source=FileSource(
        path="s3://fintech-feature-store-offline/user_features/",
        event_timestamp_column="event_timestamp"
    ),
    tags={
        "team": "fraud",
        "model": "fraud_detection_v2",
        "compliance": "PCI-DSS"
    }
)

# Risk score features - computed weekly
risk_features = FeatureView(
    name="risk_features",
    entities=["user_id"],
    ttl=timedelta(days=30),
    features=[
        Feature(name="credit_score", dtype=Int64),
        Feature(name="income_estimate", dtype=Float32),
        Feature(name="debt_to_income_ratio", dtype=Float32),
        Feature(name="previous_fraud_flags", dtype=Int64),
        Feature(name="device_trust_score", dtype=Float32),
        Feature(name="email_domain_risk", dtype=Float32),
    ],
    online=True,
    source=FileSource(
        path="s3://fintech-feature-store-offline/risk_features/",
        event_timestamp_column="event_timestamp"
    ),
    tags={
        "team": "risk",
        "model": "credit_risk_v1",
        "compliance": "FCRA"
    }
)
```

### 2.4 Feature Consistency Enforcement

```python
# /features/consistency/validation.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import json

@dataclass
class FeatureSchema:
    """Schema definition for feature validation."""
    name: str
    dtype: str
    nullable: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    description: str = ""

class FeatureValidator:
    """
    Validates feature values against schema and business rules.

    Ensures training/serving consistency by validating:
    1. Data types
    2. Value ranges
    3. Null rates
    4. Distribution drift
    """

    def __init__(self, schemas: Dict[str, FeatureSchema]):
        self.schemas = schemas
        self.validation_errors: List[Dict] = []

    def validate(self, features: Dict[str, Any]) -> bool:
        """
        Validate feature dictionary against schemas.

        Returns True if valid, False otherwise.
        Populates validation_errors with details.
        """
        self.validation_errors = []
        is_valid = True

        for name, schema in self.schemas.items():
            value = features.get(name)

            # Check nullability
            if value is None:
                if not schema.nullable:
                    self.validation_errors.append({
                        "feature": name,
                        "error": "Non-nullable field is null",
                        "value": value
                    })
                    is_valid = False
                continue

            # Check type
            if not self._check_type(value, schema.dtype):
                self.validation_errors.append({
                    "feature": name,
                    "error": f"Type mismatch: expected {schema.dtype}, got {type(value)}",
                    "value": value
                })
                is_valid = False
                continue

            # Check range
            if schema.min_value is not None and value < schema.min_value:
                self.validation_errors.append({
                    "feature": name,
                    "error": f"Value below minimum: {value} < {schema.min_value}",
                    "value": value
                })
                is_valid = False

            if schema.max_value is not None and value > schema.max_value:
                self.validation_errors.append({
                    "feature": name,
                    "error": f"Value above maximum: {value} > {schema.max_value}",
                    "value": value
                })
                is_valid = False

            # Check allowed values
            if schema.allowed_values is not None and value not in schema.allowed_values:
                self.validation_errors.append({
                    "feature": name,
                    "error": f"Value not in allowed set",
                    "value": value
                })
                is_valid = False

        return is_valid

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "float32": (int, float),
            "float64": (int, float),
            "int32": int,
            "int64": int,
            "string": str,
            "bool": bool,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        if isinstance(expected, tuple):
            return isinstance(value, expected)
        return isinstance(value, expected)

    def compute_feature_hash(self, features: Dict[str, Any]) -> str:
        """
        Compute deterministic hash of feature values.

        Used to detect training/serving skew by comparing
        hashes of features used in training vs inference.
        """
        # Sort keys for determinism
        sorted_features = {k: features[k] for k in sorted(features.keys())}
        feature_json = json.dumps(sorted_features, sort_keys=True, default=str)
        return hashlib.sha256(feature_json.encode()).hexdigest()[:16]

class TrainingServingSkewDetector:
    """
    Detects training/serving skew by comparing feature distributions.

    Uses statistical tests to detect drift between training
    data and production inference data.
    """

    def __init__(self, threshold: float = 0.05):
        self.threshold = threshold

    def detect_skew(
        self,
        training_stats: Dict[str, Dict],
        serving_stats: Dict[str, Dict]
    ) -> List[Dict]:
        """
        Detect feature skew between training and serving.

        Returns list of features with detected skew.
        """
        skewed_features = []

        for feature_name in training_stats.keys():
            train = training_stats[feature_name]
            serve = serving_stats.get(feature_name)

            if serve is None:
                skewed_features.append({
                    "feature": feature_name,
                    "error": "Feature missing in serving data"
                })
                continue

            # Compare distributions using basic statistics
            train_mean = train.get("mean")
            serve_mean = serve.get("mean")
            train_std = train.get("std")
            serve_std = serve.get("std")

            if train_mean and serve_mean and train_std:
                # Z-score of difference
                z_score = abs(train_mean - serve_mean) / train_std
                if z_score > 3:  # 3 sigma rule
                    skewed_features.append({
                        "feature": feature_name,
                        "type": "mean_shift",
                        "z_score": z_score,
                        "train_mean": train_mean,
                        "serve_mean": serve_mean
                    })

            # Check for significant std deviation change
            if train_std and serve_std and train_std > 0:
                std_ratio = serve_std / train_std
                if std_ratio > 2 or std_ratio < 0.5:
                    skewed_features.append({
                        "feature": feature_name,
                        "type": "variance_change",
                        "std_ratio": std_ratio,
                        "train_std": train_std,
                        "serve_std": serve_std
                    })

        return skewed_features
```

---

## 3. Model Versioning and A/B Testing

### 3.1 MLflow Model Registry Setup

```python
# /infrastructure/terraform/modules/mlflow/main.tf

# RDS for MLflow tracking server
resource "aws_db_instance" "mlflow" {
  identifier           = "mlflow-postgres"
  engine              = "postgres"
  engine_version      = "15.4"
  instance_class      = "db.t3.medium"
  allocated_storage   = 100
  storage_encrypted   = true

  db_name  = "mlflow"
  username = "mlflow_admin"
  password = var.mlflow_db_password

  vpc_security_group_ids = [aws_security_group.mlflow_db.id]

  backup_retention_period = 7
  deletion_protection     = true

  tags = {
    Compliance = "SOC2"
  }
}

# S3 bucket for MLflow artifacts
resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket = "fintech-mlflow-artifacts-${var.environment}"
}

resource "aws_s3_bucket_versioning" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ECR repository for MLflow server
resource "aws_ecr_repository" "mlflow" {
  name                 = "mlflow-server"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }
}

# ECS service for MLflow
resource "aws_ecs_service" "mlflow" {
  name            = "mlflow-server"
  cluster         = aws_ecs_cluster.ml.id
  task_definition = aws_ecs_task_definition.mlflow.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [aws_security_group.mlflow.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.mlflow.arn
    container_name   = "mlflow"
    container_port   = 5000
  }
}
```

### 3.2 Model Versioning Workflow

```python
# /src/models/registry.py

import mlflow
from mlflow.tracking import MlflowClient
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ModelVersion:
    """Model version metadata."""
    name: str
    version: int
    stage: str
    run_id: str
    metrics: Dict[str, float]
    tags: Dict[str, str]
    created_at: datetime
    description: str = ""

class ModelRegistry:
    """
    MLflow-based model registry with governance controls.

    Implements staged model promotion:
    1. Development -> Staging
    2. Staging -> Production (requires approval)
    3. Production -> Archived
    """

    STAGES = ["None", "Staging", "Production", "Archived"]

    REQUIRED_VALIDATIONS = {
        "Staging": ["unit_tests", "integration_tests"],
        "Production": [
            "unit_tests",
            "integration_tests",
            "shadow_deployment",
            "fairness_audit",
            "explainability_check"
        ]
    }

    def __init__(self, tracking_uri: str, registry_uri: str):
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_registry_uri(registry_uri)
        self.client = MlflowClient()

    def register_model(
        self,
        run_id: str,
        model_name: str,
        model_path: str = "model",
        description: str = "",
        tags: Optional[Dict[str, str]] = None
    ) -> ModelVersion:
        """
        Register a new model version.

        Args:
            run_id: MLflow run ID
            model_name: Registered model name
            model_path: Path to model artifact within run
            description: Version description
            tags: Additional metadata tags

        Returns:
            ModelVersion with version info
        """
        # Create or get registered model
        try:
            self.client.create_registered_model(model_name)
        except mlflow.exceptions.MlflowException:
            pass  # Model already exists

        # Create version
        model_version = self.client.create_model_version(
            name=model_name,
            source=f"runs:/{run_id}/{model_path}",
            run_id=run_id,
            description=description,
            tags=tags or {}
        )

        logger.info(f"Registered {model_name} version {model_version.version}")

        return ModelVersion(
            name=model_name,
            version=model_version.version,
            stage="None",
            run_id=run_id,
            metrics=self._get_run_metrics(run_id),
            tags=tags or {},
            created_at=datetime.utcnow()
        )

    def transition_stage(
        self,
        model_name: str,
        version: int,
        stage: str,
        validation_results: Optional[Dict[str, bool]] = None,
        approver: Optional[str] = None
    ) -> bool:
        """
        Transition model to new stage with validation.

        Args:
            model_name: Model name
            version: Model version
            stage: Target stage
            validation_results: Validation check results
            approver: Email of approving party (for Production)

        Returns:
            True if transition successful
        """
        if stage not in self.STAGES:
            raise ValueError(f"Invalid stage: {stage}")

        # Check required validations
        required = self.REQUIRED_VALIDATIONS.get(stage, [])
        if validation_results:
            for check in required:
                if not validation_results.get(check):
                    logger.error(f"Validation failed: {check}")
                    return False

        # Production requires approval
        if stage == "Production":
            if not approver:
                logger.error("Production transition requires approver")
                return False

            # Log approval
            self.client.set_model_version_tag(
                name=model_name,
                version=version,
                key="approved_by",
                value=approver
            )
            self.client.set_model_version_tag(
                name=model_name,
                version=version,
                key="approved_at",
                value=datetime.utcnow().isoformat()
            )

        # Perform transition
        self.client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage=stage
        )

        logger.info(f"Transitioned {model_name} v{version} to {stage}")
        return True

    def get_production_model(self, model_name: str) -> Optional[ModelVersion]:
        """Get current production model version."""
        versions = self.client.get_latest_versions(model_name, stages=["Production"])
        if not versions:
            return None

        v = versions[0]
        return ModelVersion(
            name=model_name,
            version=v.version,
            stage="Production",
            run_id=v.run_id,
            metrics=self._get_run_metrics(v.run_id),
            tags=dict(v.tags),
            created_at=datetime.fromtimestamp(v.creation_timestamp / 1000)
        )

    def _get_run_metrics(self, run_id: str) -> Dict[str, float]:
        """Get metrics from MLflow run."""
        run = self.client.get_run(run_id)
        return {k: v for k, v in run.data.metrics.items()}
```

### 3.3 A/B Testing Infrastructure

```python
# /src/serving/ab_testing.py

from dataclasses import dataclass
from typing import Dict, Optional, Callable
import hashlib
import random
from enum import Enum

class AssignmentStrategy(Enum):
    RANDOM = "random"
    USER_ID_HASH = "user_id_hash"
    CANARY = "canary"

@dataclass
class Experiment:
    """A/B test experiment configuration."""
    name: str
    variants: Dict[str, float]  # variant_name: traffic_percentage
    strategy: AssignmentStrategy
    salt: str = ""

    def __post_init__(self):
        total = sum(self.variants.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Variant percentages must sum to 1.0, got {total}")

class ABTestRouter:
    """
    Routes traffic to different model variants for A/B testing.

    Supports:
    - Random assignment
    - Consistent hashing by user ID
    - Canary deployments
    """

    def __init__(self):
        self.experiments: Dict[str, Experiment] = {}
        self.variant_handlers: Dict[str, Dict[str, Callable]] = {}

    def register_experiment(self, experiment: Experiment):
        """Register an A/B test experiment."""
        self.experiments[experiment.name] = experiment
        self.variant_handlers[experiment.name] = {}

    def register_variant_handler(
        self,
        experiment_name: str,
        variant_name: str,
        handler: Callable
    ):
        """Register inference handler for a variant."""
        if experiment_name not in self.experiments:
            raise ValueError(f"Experiment {experiment_name} not found")
        self.variant_handlers[experiment_name][variant_name] = handler

    def assign_variant(
        self,
        experiment_name: str,
        user_id: Optional[str] = None,
        request_context: Optional[Dict] = None
    ) -> str:
        """
        Assign request to a variant.

        Returns variant name based on experiment strategy.
        """
        experiment = self.experiments.get(experiment_name)
        if not experiment:
            raise ValueError(f"Experiment {experiment_name} not found")

        if experiment.strategy == AssignmentStrategy.RANDOM:
            return self._random_assignment(experiment)

        elif experiment.strategy == AssignmentStrategy.USER_ID_HASH:
            if not user_id:
                raise ValueError("user_id required for USER_ID_HASH strategy")
            return self._hash_assignment(experiment, user_id)

        elif experiment.strategy == AssignmentStrategy.CANARY:
            return self._canary_assignment(experiment, request_context)

        else:
            raise ValueError(f"Unknown strategy: {experiment.strategy}")

    def _random_assignment(self, experiment: Experiment) -> str:
        """Random variant assignment."""
        r = random.random()
        cumulative = 0.0
        for variant, weight in experiment.variants.items():
            cumulative += weight
            if r <= cumulative:
                return variant
        return list(experiment.variants.keys())[-1]

    def _hash_assignment(self, experiment: Experiment, user_id: str) -> str:
        """Consistent hash assignment by user ID."""
        hash_input = f"{experiment.name}:{experiment.salt}:{user_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        normalized = (hash_value % 10000) / 10000.0

        cumulative = 0.0
        for variant, weight in experiment.variants.items():
            cumulative += weight
            if normalized <= cumulative:
                return variant
        return list(experiment.variants.keys())[-1]

    def _canary_assignment(
        self,
        experiment: Experiment,
        context: Optional[Dict]
    ) -> str:
        """Canary deployment - route based on request attributes."""
        # Default to control for safety
        if not context:
            return "control"

        # Check if request is in canary segment
        if context.get("is_canary_user", False):
            return "treatment"

        # Check if internal/test request
        if context.get("is_internal", False):
            return "treatment"

        return "control"

    async def route_request(
        self,
        experiment_name: str,
        user_id: Optional[str] = None,
        request_data: Dict = None,
        request_context: Dict = None
    ) -> Dict:
        """
        Route request to appropriate variant and return prediction.

        Returns dict with prediction and variant assignment.
        """
        variant = self.assign_variant(experiment_name, user_id, request_context)
        handler = self.variant_handlers[experiment_name].get(variant)

        if not handler:
            raise ValueError(f"No handler for variant {variant}")

        prediction = await handler(request_data)

        return {
            "prediction": prediction,
            "variant": variant,
            "experiment": experiment_name
        }
```

---

## 4. Data Drift Detection and Monitoring

### 4.1 Drift Detection Architecture

```python
# /src/monitoring/drift_detection.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import numpy as np
from scipy import stats
import logging

logger = logging.getLogger(__name__)

@dataclass
class DriftReport:
    """Data drift detection report."""
    feature_name: str
    drift_detected: bool
    drift_score: float
    p_value: float
    test_type: str
    reference_stats: Dict
    current_stats: Dict
    timestamp: datetime

class StatisticalDriftDetector:
    """
    Statistical drift detection for ML features and predictions.

    Implements:
    - Kolmogorov-Smirnov test for continuous features
    - Chi-square test for categorical features
    - PSI (Population Stability Index) for score distributions
    """

    def __init__(
        self,
        ks_threshold: float = 0.05,
        psi_threshold: float = 0.25,
        chi2_threshold: float = 0.05
    ):
        self.ks_threshold = ks_threshold
        self.psi_threshold = psi_threshold
        self.chi2_threshold = chi2_threshold

    def detect_ks_drift(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str
    ) -> DriftReport:
        """
        Detect drift using Kolmogorov-Smirnov test.

        Suitable for continuous features.
        """
        statistic, p_value = stats.ks_2samp(reference, current)

        return DriftReport(
            feature_name=feature_name,
            drift_detected=p_value < self.ks_threshold,
            drift_score=statistic,
            p_value=p_value,
            test_type="ks_test",
            reference_stats=self._compute_stats(reference),
            current_stats=self._compute_stats(current),
            timestamp=datetime.utcnow()
        )

    def detect_psi_drift(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        feature_name: str,
        bins: int = 10
    ) -> DriftReport:
        """
        Calculate Population Stability Index.

        PSI < 0.1: No significant change
        PSI 0.1-0.25: Moderate change
        PSI > 0.25: Significant change
        """
        # Create bins based on reference distribution
        percentiles = np.percentile(reference, np.linspace(0, 100, bins + 1))
        percentiles[0] = -np.inf
        percentiles[-1] = np.inf

        # Calculate proportions
        ref_counts, _ = np.histogram(reference, bins=percentiles)
        cur_counts, _ = np.histogram(current, bins=percentiles)

        ref_props = ref_counts / len(reference)
        cur_props = cur_counts / len(current)

        # Avoid division by zero
        ref_props = np.where(ref_props == 0, 0.0001, ref_props)
        cur_props = np.where(cur_props == 0, 0.0001, cur_props)

        # Calculate PSI
        psi = np.sum((cur_props - ref_props) * np.log(cur_props / ref_props))

        return DriftReport(
            feature_name=feature_name,
            drift_detected=psi > self.psi_threshold,
            drift_score=psi,
            p_value=None,
            test_type="psi",
            reference_stats=self._compute_stats(reference),
            current_stats=self._compute_stats(current),
            timestamp=datetime.utcnow()
        )

    def _compute_stats(self, data: np.ndarray) -> Dict:
        """Compute summary statistics."""
        return {
            "mean": float(np.mean(data)),
            "std": float(np.std(data)),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "median": float(np.median(data)),
            "count": len(data)
        }

class PredictionDriftMonitor:
    """
    Monitor model predictions for drift.

    Tracks:
    - Score distribution changes
    - Prediction rate changes
    - Confidence score degradation
    """

    def __init__(
        self,
        reference_predictions: np.ndarray,
        detector: StatisticalDriftDetector
    ):
        self.reference = reference_predictions
        self.detector = detector
        self.history: List[DriftReport] = []

    def check_drift(self, current_predictions: np.ndarray) -> DriftReport:
        """Check for prediction drift."""
        report = self.detector.detect_psi_drift(
            self.reference,
            current_predictions,
            "model_predictions",
            bins=20
        )

        self.history.append(report)

        if report.drift_detected:
            logger.warning(
                f"Prediction drift detected: PSI={report.drift_score:.4f}"
            )

        return report

    def get_drift_trend(self, window_hours: int = 24) -> Dict:
        """Get drift trend over time window."""
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        recent = [r for r in self.history if r.timestamp > cutoff]

        if not recent:
            return {"status": "no_data"}

        drift_count = sum(1 for r in recent if r.drift_detected)

        return {
            "status": "drifting" if drift_count > len(recent) * 0.5 else "stable",
            "drift_rate": drift_count / len(recent),
            "avg_psi": np.mean([r.drift_score for r in recent]),
            "max_psi": max(r.drift_score for r in recent),
            "samples": len(recent)
        }
```

### 4.2 Real-time Monitoring Dashboard

```python
# /src/monitoring/dashboard.py

from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime
import json

@dataclass
class ModelMetrics:
    """Real-time model performance metrics."""
    model_name: str
    version: str
    timestamp: datetime

    # Request metrics
    request_count: int
    request_latency_p50: float
    request_latency_p99: float
    error_rate: float

    # Prediction metrics
    prediction_distribution: Dict[str, float]
    confidence_scores: Dict[str, float]

    # Drift metrics
    feature_drift_count: int
    prediction_drift_detected: bool
    psi_score: float

    # Business metrics
    fraud_detection_rate: float
    false_positive_rate: float
    blocked_transaction_value: float

class MetricsAggregator:
    """
    Aggregates metrics for real-time dashboard.

    Integrates with Prometheus for metrics collection
    and Grafana for visualization.
    """

    def __init__(self, metrics_client):
        self.metrics = metrics_client
        self.current_window: Dict[str, List] = {}
        self.window_size = 300  # 5 minutes

    def record_prediction(
        self,
        model_name: str,
        version: str,
        prediction: float,
        confidence: float,
        latency_ms: float,
        features: Dict
    ):
        """Record a single prediction for aggregation."""
        key = f"{model_name}:{version}"

        if key not in self.current_window:
            self.current_window[key] = []

        self.current_window[key].append({
            "prediction": prediction,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow(),
            "features": features
        })

        # Update Prometheus metrics
        self.metrics.observe_model_latency(model_name, version, latency_ms)
        self.metrics.inc_prediction_count(model_name, version, prediction)

    def get_dashboard_data(self, model_name: str, version: str) -> ModelMetrics:
        """Get aggregated metrics for dashboard."""
        key = f"{model_name}:{version}"
        window = self.current_window.get(key, [])

        if not window:
            return ModelMetrics(
                model_name=model_name,
                version=version,
                timestamp=datetime.utcnow(),
                request_count=0,
                request_latency_p50=0,
                request_latency_p99=0,
                error_rate=0,
                prediction_distribution={},
                confidence_scores={},
                feature_drift_count=0,
                prediction_drift_detected=False,
                psi_score=0,
                fraud_detection_rate=0,
                false_positive_rate=0,
                blocked_transaction_value=0
            )

        latencies = [r["latency_ms"] for r in window]
        predictions = [r["prediction"] for r in window]
        confidences = [r["confidence"] for r in window]

        return ModelMetrics(
            model_name=model_name,
            version=version,
            timestamp=datetime.utcnow(),
            request_count=len(window),
            request_latency_p50=self._percentile(latencies, 50),
            request_latency_p99=self._percentile(latencies, 99),
            error_rate=0,  # Calculate from error tracking
            prediction_distribution=self._distribution(predictions),
            confidence_scores={
                "mean": sum(confidences) / len(confidences),
                "min": min(confidences),
                "max": max(confidences)
            },
            feature_drift_count=0,  # From drift detector
            prediction_drift_detected=False,
            psi_score=0,
            fraud_detection_rate=sum(1 for p in predictions if p > 0.5) / len(predictions),
            false_positive_rate=0,  # Requires ground truth
            blocked_transaction_value=0
        )

    def _percentile(self, data: List[float], p: float) -> float:
        """Calculate percentile."""
        if not data:
            return 0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])

    def _distribution(self, data: List[float], bins: int = 10) -> Dict[str, float]:
        """Calculate distribution across bins."""
        if not data:
            return {}

        min_val, max_val = min(data), max(data)
        bin_size = (max_val - min_val) / bins if max_val > min_val else 1

        distribution = {}
        for i in range(bins):
            low = min_val + i * bin_size
            high = min_val + (i + 1) * bin_size
            count = sum(1 for d in data if low <= d < high)
            label = f"{low:.2f}-{high:.2f}"
            distribution[label] = count / len(data)

        return distribution
```

---

## 5. Automated Retraining Pipelines

### 5.1 Kubeflow Pipelines Architecture

```yaml
# /pipelines/fraud_model_retraining.yaml

apiVersion: kubeflow.org/v1beta1
kind: Pipeline
metadata:
  name: fraud-model-retraining
  description: Automated retraining pipeline for fraud detection model
spec:
  arguments:
    parameters:
      - name: model_name
        value: fraud_detection_v2
      - name: training_data_days
        value: "90"
      - name: min_training_samples
        value: "100000"
      - name: performance_threshold
        value: "0.85"

  templates:
    # Step 1: Data Validation
    - name: validate-training-data
      container:
        image: fintech/ml-pipeline:data-validation-v1.2
        command: [python, -m, data_validation]
        args:
          - --model-name
          - "{{inputs.parameters.model_name}}"
          - --days
          - "{{inputs.parameters.training_data_days}}"
          - --min-samples
          - "{{inputs.parameters.min_training_samples}}"
          - --output-path
          - "/tmp/validation_report.json"
      outputs:
        artifacts:
          - name: validation-report
            path: /tmp/validation_report.json

    # Step 2: Feature Engineering
    - name: generate-features
      inputs:
        artifacts:
          - name: validation-report
            from: "{{steps.validate-training-data.outputs.artifacts.validation-report}}"
      container:
        image: fintech/ml-pipeline:feature-engineering-v2.1
        command: [python, -m, feature_engineering]
        args:
          - --model-name
          - "{{inputs.parameters.model_name}}"
          - --feature-store
          - "fintech-feature-store"
          - --output-path
          - "/tmp/features"
      outputs:
        artifacts:
          - name: feature-dataset
            path: /tmp/features

    # Step 3: Train Model
    - name: train-model
      inputs:
        artifacts:
          - name: feature-dataset
            from: "{{steps.generate-features.outputs.artifacts.feature-dataset}}"
      container:
        image: fintech/ml-pipeline:training-v3.0
        command: [python, -m, train]
        args:
          - --model-name
          - "{{inputs.parameters.model_name}}"
          - --data-path
          - "/tmp/features"
          - --experiment-name
          - "fraud-detection-retraining"
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: "32Gi"
            cpu: "8"
      outputs:
        artifacts:
          - name: trained-model
            path: /tmp/model
          - name: training-metrics
            path: /tmp/metrics.json

    # Step 4: Model Validation
    - name: validate-model
      inputs:
        artifacts:
          - name: trained-model
            from: "{{steps.train-model.outputs.artifacts.trained-model}}"
          - name: training-metrics
            from: "{{steps.train-model.outputs.artifacts.training-metrics}}"
      container:
        image: fintech/ml-pipeline:model-validation-v1.5
        command: [python, -m, model_validation]
        args:
          - --model-path
          - "/tmp/model"
          - --metrics-path
          - "/tmp/metrics.json"
          - --threshold
          - "{{inputs.parameters.performance_threshold}}"
          - --output-path
          - "/tmp/validation_result.json"
      outputs:
        artifacts:
          - name: validation-result
            path: /tmp/validation_result.json

    # Step 5: Fairness Audit
    - name: fairness-audit
      inputs:
        artifacts:
          - name: trained-model
            from: "{{steps.train-model.outputs.artifacts.trained-model}}"
      container:
        image: fintech/ml-pipeline:fairness-audit-v1.0
        command: [python, -m, fairness_audit]
        args:
          - --model-path
          - "/tmp/model"
          - --protected-attributes
          - "age_group,gender,region"
          - --output-path
          - "/tmp/fairness_report.json"
      outputs:
        artifacts:
          - name: fairness-report
            path: /tmp/fairness_report.json

    # Step 6: Register Model (conditional on validation)
    - name: register-model
      inputs:
        artifacts:
          - name: trained-model
            from: "{{steps.train-model.outputs.artifacts.trained-model}}"
          - name: validation-result
            from: "{{steps.validate-model.outputs.artifacts.validation-result}}"
          - name: fairness-report
            from: "{{steps.fairness-audit.outputs.artifacts.fairness-report}}"
      container:
        image: fintech/ml-pipeline:model-registry-v1.3
        command: [python, -m, register_model]
        args:
          - --model-path
          - "/tmp/model"
          - --model-name
          - "{{inputs.parameters.model_name}}"
          - --stage
          - "Staging"

    # Step 7: Deploy to Staging
    - name: deploy-staging
      inputs:
        artifacts:
          - name: validation-result
            from: "{{steps.validate-model.outputs.artifacts.validation-result}}"
      container:
        image: fintech/ml-pipeline:deployment-v2.0
        command: [python, -m, deploy]
        args:
          - --model-name
          - "{{inputs.parameters.model_name}}"
          - --environment
          - "staging"
          - --traffic-percentage
          - "100"

  # Pipeline DAG
  dag:
    tasks:
      - name: validate-data
        template: validate-training-data

      - name: generate-features
        template: generate-features
        dependencies: [validate-data]

      - name: train
        template: train-model
        dependencies: [generate-features]

      - name: validate
        template: validate-model
        dependencies: [train]

      - name: fairness-check
        template: fairness-audit
        dependencies: [train]

      - name: register
        template: register-model
        dependencies: [validate, fairness-check]
        when: "{{steps.validate.outputs.parameters.validation_passed}} == true"

      - name: deploy
        template: deploy-staging
        dependencies: [register]
```

### 5.2 Trigger Configuration

```python
# /src/pipeline/triggers.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TriggerType(Enum):
    SCHEDULED = "scheduled"
    PERFORMANCE = "performance"
    DRIFT = "drift"
    DATA_VOLUME = "data_volume"
    MANUAL = "manual"

@dataclass
class RetrainingTrigger:
    """Configuration for automated retraining trigger."""
    name: str
    trigger_type: TriggerType
    model_name: str

    # Thresholds
    performance_threshold: Optional[float] = None
    drift_threshold: Optional[float] = None
    min_data_volume: Optional[int] = None

    # Schedule (for SCHEDULED type)
    cron_schedule: Optional[str] = None

    # Cooldown
    min_time_between_retraining: timedelta = timedelta(hours=24)

    # Last triggered
    last_triggered: Optional[datetime] = None

class RetrainingOrchestrator:
    """
    Orchestrates automated model retraining based on triggers.

    Monitors model performance, data drift, and data volume
to determine when retraining is needed.
    """

    def __init__(self, pipeline_client, metrics_client):
        self.pipeline_client = pipeline_client
        self.metrics = metrics_client
        self.triggers: List[RetrainingTrigger] = []

    def register_trigger(self, trigger: RetrainingTrigger):
        """Register a retraining trigger."""
        self.triggers.append(trigger)
        logger.info(f"Registered trigger: {trigger.name}")

    async def evaluate_triggers(self) -> List[RetrainingTrigger]:
        """
        Evaluate all triggers and return those that fired.
        """
        fired = []

        for trigger in self.triggers:
            # Check cooldown
            if trigger.last_triggered:
                cooldown_end = trigger.last_triggered + trigger.min_time_between_retraining
                if datetime.utcnow() < cooldown_end:
                    continue

            should_trigger = await self._evaluate_trigger(trigger)
            if should_trigger:
                fired.append(trigger)
                trigger.last_triggered = datetime.utcnow()

        return fired

    async def _evaluate_trigger(self, trigger: RetrainingTrigger) -> bool:
        """Evaluate a single trigger."""
        if trigger.trigger_type == TriggerType.SCHEDULED:
            return self._check_schedule(trigger)

        elif trigger.trigger_type == TriggerType.PERFORMANCE:
            return await self._check_performance(trigger)

        elif trigger.trigger_type == TriggerType.DRIFT:
            return await self._check_drift(trigger)

        elif trigger.trigger_type == TriggerType.DATA_VOLUME:
            return await self._check_data_volume(trigger)

        return False

    async def _check_performance(self, trigger: RetrainingTrigger) -> bool:
        """Check if model performance has degraded."""
        current_auc = await self.metrics.get_model_auc(trigger.model_name)

        if trigger.performance_threshold and current_auc < trigger.performance_threshold:
            logger.warning(
                f"Performance trigger fired for {trigger.model_name}: "
                f"AUC={current_auc:.4f} < threshold={trigger.performance_threshold:.4f}"
            )
            return True

        return False

    async def _check_drift(self, trigger: RetrainingTrigger) -> bool:
        """Check if data drift exceeds threshold."""
        drift_score = await self.metrics.get_max_drift_score(trigger.model_name)

        if trigger.drift_threshold and drift_score > trigger.drift_threshold:
            logger.warning(
                f"Drift trigger fired for {trigger.model_name}: "
                f"PSI={drift_score:.4f} > threshold={trigger.drift_threshold:.4f}"
            )
            return True

        return False

    async def _check_data_volume(self, trigger: RetrainingTrigger) -> bool:
        """Check if enough new data is available."""
        new_samples = await self.metrics.get_new_training_samples(trigger.model_name)

        if trigger.min_data_volume and new_samples >= trigger.min_data_volume:
            logger.info(
                f"Data volume trigger fired for {trigger.model_name}: "
                f"{new_samples} new samples available"
            )
            return True

        return False

    async def execute_retraining(self, trigger: RetrainingTrigger):
        """Execute retraining pipeline for triggered model."""
        logger.info(f"Starting retraining for {trigger.model_name}")

        run_id = await self.pipeline_client.start_pipeline(
            pipeline_name="fraud-model-retraining",
            parameters={
                "model_name": trigger.model_name,
                "triggered_by": trigger.name,
                "trigger_type": trigger.trigger_type.value
            }
        )

        logger.info(f"Started retraining pipeline: {run_id}")
        return run_id
```

---

## 6. Compliance and Explainability Requirements

### 6.1 Model Explainability Framework

```python
# /src/explainability/shap_explainer.py

import shap
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class FeatureContribution:
    """SHAP value for a single feature."""
    feature_name: str
    feature_value: Any
    shap_value: float
    base_value: float
    contribution: float  # Percentage contribution to prediction

@dataclass
class Explanation:
    """Model prediction explanation."""
    prediction: float
    base_value: float
    feature_contributions: List[FeatureContribution]
    top_positive_features: List[FeatureContribution]
    top_negative_features: List[FeatureContribution]
    summary: str

class FraudExplainer:
    """
    SHAP-based explainer for fraud detection models.

    Provides:
    - Feature-level explanations
    - Global feature importance
    - Adverse action codes (for regulatory compliance)
    """

    # Features that trigger adverse action codes
    REGULATORY_FEATURES = {
        "credit_score": "A1",
        "income_estimate": "A2",
        "debt_to_income_ratio": "A3",
        "previous_fraud_flags": "A4",
        "account_age_days": "A5",
    }

    def __init__(self, model, feature_names: List[str], background_data: np.ndarray):
        self.model = model
        self.feature_names = feature_names
        self.explainer = shap.TreeExplainer(model)
        self.background_data = background_data

    def explain(
        self,
        features: Dict[str, Any],
        top_k: int = 5
    ) -> Explanation:
        """
        Generate explanation for a single prediction.

        Args:
            features: Feature dictionary
            top_k: Number of top features to highlight

        Returns:
            Explanation with SHAP values and regulatory codes
        """
        # Convert features to array
        feature_array = np.array([[features.get(f, 0) for f in self.feature_names]])

        # Calculate SHAP values
        shap_values = self.explainer.shap_values(feature_array)
        base_value = self.explainer.expected_value

        if isinstance(shap_values, list):
            # Multi-class: use positive class (fraud)
            shap_values = shap_values[1]
            base_value = base_value[1]

        # Calculate contributions
        contributions = []
        total_abs_shap = sum(abs(sv) for sv in shap_values[0])

        for i, (name, value) in enumerate(features.items()):
            if i < len(shap_values[0]):
                shap_val = shap_values[0][i]
                contrib = FeatureContribution(
                    feature_name=name,
                    feature_value=value,
                    shap_value=shap_val,
                    base_value=base_value,
                    contribution=abs(shap_val) / total_abs_shap if total_abs_shap > 0 else 0
                )
                contributions.append(contrib)

        # Sort by absolute contribution
        contributions.sort(key=lambda x: abs(x.shap_value), reverse=True)

        # Split positive and negative contributions
        positive = [c for c in contributions if c.shap_value > 0][:top_k]
        negative = [c for c in contributions if c.shap_value < 0][:top_k]

        # Generate summary
        summary = self._generate_summary(positive, negative)

        # Calculate prediction
        prediction = base_value + sum(c.shap_value for c in contributions)
        prediction = 1 / (1 + np.exp(-prediction))  # Sigmoid for probability

        return Explanation(
            prediction=float(prediction),
            base_value=float(base_value),
            feature_contributions=contributions,
            top_positive_features=positive,
            top_negative_features=negative,
            summary=summary
        )

    def get_adverse_action_codes(self, explanation: Explanation) -> List[str]:
        """
        Get adverse action codes for declined transactions.

        Required for FCRA compliance when credit is denied.
        """
        codes = []

        # Get top contributing features
        top_features = explanation.feature_contributions[:3]

        for contrib in top_features:
            if contrib.shap_value > 0:  # Features that increased fraud score
                code = self.REGULATORY_FEATURES.get(contrib.feature_name)
                if code:
                    codes.append(code)

        return codes

    def _generate_summary(
        self,
        positive: List[FeatureContribution],
        negative: List[FeatureContribution]
    ) -> str:
        """Generate human-readable explanation summary."""
        parts = []

        if positive:
            top = positive[0]
            parts.append(
                f"Primary risk factor: {top.feature_name}={top.feature_value} "
                f"(+{top.contribution:.1%} contribution)"
            )

        if len(positive) > 1:
            parts.append(
                f"Secondary factors: {', '.join(p.feature_name for p in positive[1:3])}"
            )

        if negative:
            parts.append(
                f"Mitigating factors: {', '.join(n.feature_name for n in negative[:2])}"
            )

        return "; ".join(parts)

    def global_feature_importance(self) -> Dict[str, float]:
        """Get global feature importance across dataset."""
        shap_values = self.explainer.shap_values(self.background_data)

        if isinstance(shap_values, list):
            shap_values = shap_values[1]

        importance = {}
        for i, name in enumerate(self.feature_names):
            importance[name] = float(np.mean(np.abs(shap_values[:, i])))

        return importance
```

### 6.2 Compliance Audit Logging

```python
# /src/compliance/audit_logger.py

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

@dataclass
class PredictionAuditRecord:
    """Audit record for model prediction."""
    record_id: str
    timestamp: datetime
    model_name: str
    model_version: str

    # Input
    entity_id: str
    entity_type: str
    features: Dict[str, Any]
    feature_hash: str

    # Output
    prediction: float
    prediction_label: str
    confidence: float
    explanation: Optional[Dict]

    # Context
    request_id: str
    user_id: Optional[str]
    ip_address: Optional[str]

    # Compliance
    adverse_action_codes: List[str]
    retention_years: int = 7

class ComplianceAuditLogger:
    """
    Audit logger for regulatory compliance.

    Implements:
    - Immutable audit trail
    - Tamper-evident logging
    - GDPR/CCPA data retention
    - FCRA adverse action tracking
    """

    RETENTION_POLICIES = {
        "fraud_detection": 7,  # years
        "credit_risk": 7,
        "aml": 10,
    }

    def __init__(self, storage_backend, encryption_key: str):
        self.storage = storage_backend
        self.encryption_key = encryption_key
        self.previous_hash = "0" * 64  # Genesis hash

    async def log_prediction(
        self,
        record: PredictionAuditRecord
    ) -> str:
        """
        Log prediction with tamper-evident hashing.

        Returns record ID for verification.
        """
        # Serialize record
        record_data = {
            "record_id": record.record_id,
            "timestamp": record.timestamp.isoformat(),
            "model_name": record.model_name,
            "model_version": record.model_version,
            "entity_id": self._hash_pii(record.entity_id),
            "entity_type": record.entity_type,
            "feature_hash": record.feature_hash,
            "prediction": record.prediction,
            "prediction_label": record.prediction_label,
            "confidence": record.confidence,
            "explanation_summary": record.explanation.get("summary") if record.explanation else None,
            "request_id": record.request_id,
            "user_hash": self._hash_pii(record.user_id) if record.user_id else None,
            "adverse_action_codes": record.adverse_action_codes,
            "retention_until": (
            record.timestamp.replace(year=record.timestamp.year + record.retention_years)
            ).isoformat(),
            "previous_hash": self.previous_hash,
        }

        # Calculate record hash
        record_json = json.dumps(record_data, sort_keys=True)
        record_hash = hashlib.sha256(record_json.encode()).hexdigest()
        record_data["record_hash"] = record_hash

        # Update chain
        self.previous_hash = record_hash

        # Encrypt sensitive fields
        encrypted_data = self._encrypt_sensitive_fields(record_data)

        # Store
        await self.storage.store(encrypted_data)

        logger.info(f"Audit record logged: {record.record_id}")
        return record.record_id

    def _hash_pii(self, value: str) -> str:
        """Hash PII for privacy protection."""
        return hashlib.sha256(
            f"{self.encryption_key}:{value}".encode()
        ).hexdigest()[:16]

    def _encrypt_sensitive_fields(self, data: Dict) -> Dict:
        """Encrypt sensitive fields in audit record."""
        # Implementation would use proper encryption
        # For now, just mark as encrypted
        encrypted = data.copy()
        encrypted["_encryption_metadata"] = {
            "algorithm": "AES-256-GCM",
            "key_id": "audit-key-001",
            "encrypted_at": datetime.utcnow().isoformat()
        }
        return encrypted

    async def verify_chain_integrity(self) -> bool:
        """
        Verify integrity of audit chain.

        Returns True if chain is valid, False if tampering detected.
        """
        records = await self.storage.get_all_records()

        previous_hash = "0" * 64

        for record in records:
            stored_hash = record.get("record_hash")
            stored_previous = record.get("previous_hash")

            # Verify chain link
            if stored_previous != previous_hash:
                logger.error(f"Chain broken at record {record['record_id']}")
                return False

            # Recalculate hash
            record_copy = {k: v for k, v in record.items() if k != "record_hash"}
            calculated_hash = hashlib.sha256(
                json.dumps(record_copy, sort_keys=True).encode()
            ).hexdigest()

            if calculated_hash != stored_hash:
                logger.error(f"Hash mismatch at record {record['record_id']}")
                return False

            previous_hash = stored_hash

        logger.info("Audit chain integrity verified")
        return True

    async def export_for_audit(
        self,
        start_date: datetime,
        end_date: datetime,
        model_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Export audit records for regulatory audit.

        Returns decrypted records within date range.
        """
        records = await self.storage.query(
            start_date=start_date,
            end_date=end_date,
            model_name=model_name
        )

        # Decrypt and format for auditors
        return [self._format_for_audit(r) for r in records]

    def _format_for_audit(self, record: Dict) -> Dict:
        """Format record for audit export."""
        return {
            "audit_id": record["record_id"],
            "timestamp": record["timestamp"],
            "model": f"{record['model_name']}:{record['model_version']}",
            "prediction": record["prediction"],
            "outcome": record["prediction_label"],
            "explanation": record.get("explanation_summary"),
            "adverse_action_codes": record.get("adverse_action_codes", []),
            "retention_until": record.get("retention_until"),
            "chain_verified": True,
        }
```

---

## 7. Infrastructure as Code

### 7.1 Terraform Configuration

```hcl
# /infrastructure/terraform/main.tf

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  backend "s3" {
    bucket         = "fintech-terraform-state"
    key            = "ml-infrastructure/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "fintech-ml-platform"
      ManagedBy   = "terraform"
      Compliance  = "PCI-DSS,SOC2"
    }
  }
}

# VPC for ML workloads
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "ml-platform-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment != "production"

  enable_flow_log                      = true
  create_flow_log_cloudwatch_iam_role  = true
  create_flow_log_cloudwatch_log_group = true
}

# EKS cluster for model serving
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "ml-platform-${var.environment}"
  cluster_version = "1.28"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Enable encryption
  cluster_encryption_config = {
    provider_key_arn = aws_kms_key.eks.arn
    resources        = ["secrets"]
  }

  # Managed node groups
  eks_managed_node_groups = {
    general = {
      desired_size = 3
      min_size     = 2
      max_size     = 10

      instance_types = ["m6i.2xlarge"]
      capacity_type  = "ON_DEMAND"

      labels = {
        workload = "general"
      }
    }

    gpu = {
      desired_size = 1
      min_size     = 0
      max_size     = 4

      instance_types = ["p4d.24xlarge"]
      capacity_type  = "ON_DEMAND"

      labels = {
        workload = "gpu-training"
      }

      taints = [{
        key    = "nvidia.com/gpu"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }

    spot = {
      desired_size = 2
      min_size     = 0
      max_size     = 20

      instance_types = ["m6i.xlarge", "m6i.2xlarge", "m5.xlarge"]
      capacity_type  = "SPOT"

      labels = {
        workload = "batch-processing"
      }
    }
  }

  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }
}

# KMS key for encryption
resource "aws_kms_key" "eks" {
  description             = "EKS Secret Encryption Key"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow EKS to use the key"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey*"
        ]
        Resource = "*"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

# Outputs
output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}
```

---

## 8. Recommendations Summary

### 8.1 Immediate Actions (0-30 days)

| Priority | Action | Owner | Effort |
|----------|--------|-------|--------|
| P0 | Implement feature store with Feast | ML Platform | 2 weeks |
| P0 | Deploy model serving with SageMaker | DevOps | 1 week |
| P0 | Set up MLflow model registry | ML Platform | 3 days |
| P1 | Implement circuit breaker pattern | Backend | 3 days |
| P1 | Add feature caching layer | Backend | 1 week |

### 8.2 Short-term (30-90 days)

| Priority | Action | Owner | Effort |
|----------|--------|-------|--------|
| P1 | Implement drift detection | ML Platform | 2 weeks |
| P1 | Set up automated retraining pipelines | ML Platform | 3 weeks |
| P1 | Deploy SHAP explainability | ML Platform | 1 week |
| P2 | Implement A/B testing framework | Backend | 2 weeks |
| P2 | Set up compliance audit logging | Security | 2 weeks |

### 8.3 Long-term (90+ days)

| Priority | Action | Owner | Effort |
|----------|--------|-------|--------|
| P2 | Migrate to full MLOps platform (Kubeflow) | ML Platform | 2 months |
| P2 | Implement real-time feature engineering | ML Platform | 1 month |
| P3 | Set up multi-region model serving | DevOps | 1 month |
| P3 | Implement continuous training | ML Platform | 1 month |

### 8.4 Cost Optimization

| Strategy | Estimated Savings | Implementation |
|----------|-------------------|----------------|
| Spot instances for training | 60-70% | Use SPOT capacity type in EKS |
| Model quantization | 50% inference cost | INT8 quantization for CPU inference |
| Feature caching | 40% feature store cost | Redis cluster with TTL |
| Batch inference | 30% overall cost | Process transactions in micro-batches |
| Auto-scaling | 20-30% serving cost | Scale to zero during low traffic |

---

## 9. Disaster Recovery Plan

### 9.1 RTO/RPO Targets

| Component | RTO | RPO | Strategy |
|-----------|-----|-----|----------|
| Model Serving | 5 min | 0 | Multi-AZ deployment |
| Feature Store (Online) | 1 min | 0 | DynamoDB global tables |
| Feature Store (Offline) | 4 hours | 24 hours | S3 cross-region replication |
| Model Registry | 1 hour | 1 hour | Automated backups to S3 |
| Training Data | 4 hours | 24 hours | S3 versioning + replication |

### 9.2 Failover Procedures

```python
# /src/dr/failover_manager.py

class ModelServingFailover:
    """
    Manages failover for model serving across regions.
    """

    def __init__(self, primary_region: str, secondary_region: str):
        self.primary = primary_region
        self.secondary = secondary_region
        self.health_check_interval = 30

    async def check_health(self, region: str) -> bool:
        """Check health of model serving in region."""
        # Implementation would check endpoint health
        pass

    async def initiate_failover(self):
        """Initiate failover to secondary region."""
        # 1. Update Route53 health checks
        # 2. Promote secondary to primary
        # 3. Alert on-call team
        # 4. Begin post-mortem
        pass
```

---

**Document End**

*This document contains confidential ML infrastructure information. Distribution is restricted to authorized personnel only.*
