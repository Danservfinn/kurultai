# Agent Harness Health Dashboard - Neo4j Queries

## Latest Health Check

```cypher
MATCH (h:AgentHarnessHealthCheck)
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
LIMIT 1
```

## Health Trend (Last 24 Hours)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
```

## Health Score Over Time (Graph)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('P7D')
RETURN date(h.timestamp) as date,
       avg(h.health_score) as avg_health_score,
       min(h.health_score) as min_score,
       max(h.health_score) as max_score
ORDER BY date DESC
```

## Component Health (Last 24 Hours)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
RETURN 
  avg(h.hooks_executable * 100.0 / h.hooks_total) as hooks_executable_pct,
  avg(h.hooks_integrated * 100.0 / 2) as hooks_integrated_pct,
  avg(h.specs_exist * 100.0 / h.specs_total) as specs_pct,
  avg(h.examples_exist * 100.0 / h.examples_total) as examples_pct,
  avg(h.agents_documented * 100.0 / h.agents_total) as agents_pct,
  avg(h.readme_exists * 100.0) as readme_pct,
  avg(h.neo4j_logging * 100.0) as neo4j_logging_pct
```

## Issues Detected (Last 24 Hours)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
  AND h.health_score < 100
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total,
       (h.total_checks - h.passed_checks) as issues
ORDER BY h.timestamp DESC
```

## Agent Documentation Status

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT24H')
RETURN 
  avg(h.agents_documented) as avg_agents_documented,
  max(h.agents_documented) as max_documented,
  min(h.agents_documented) as min_documented
```

## Alert: Health Score Below Threshold

```cypher
// Alert if health score drops below 80%
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('PT1H')
  AND h.health_score < 80
RETURN h.timestamp as timestamp,
       h.health_score as health_score,
       h.passed_checks as passed,
       h.total_checks as total
ORDER BY h.timestamp DESC
```

## Summary Statistics (Last 7 Days)

```cypher
MATCH (h:AgentHarnessHealthCheck)
WHERE h.timestamp > datetime() - duration('P7D')
RETURN 
  count(h) as total_checks,
  avg(h.health_score) as avg_health_score,
  min(h.health_score) as min_score,
  max(h.health_score) as max_score,
  stdev(h.health_score) as stddev
```

## Usage

Run these queries in Neo4j Browser or via Python:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))

with driver.session() as session:
    result = session.run("""
        MATCH (h:AgentHarnessHealthCheck)
        RETURN h.timestamp as timestamp,
               h.health_score as health_score
        ORDER BY h.timestamp DESC
        LIMIT 10
    """)
    
    for record in result:
        print(f"{record['timestamp']}: {record['health_score']}%")

driver.close()
```
