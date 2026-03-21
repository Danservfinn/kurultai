# Empty Report Fix — Task high-1774022393-15cf1b37

**Date:** 2026-03-20
**Issue:** Report page at https://the.kurult.ai/r/high-1774022393-15cf1b37 was empty despite task being marked COMPLETED

## Root Cause

The task was executed successfully and the result was written to disk (`high-1774022393.verified.done.md`), but the result was **never written to Neo4j**. The report API endpoint (`/api/report/:taskId`) queries Neo4j for:
1. The Task node's `result` field
2. Optional TaskOutput node via `HAS_OUTPUT` relationship

Both were null:
```
{
  "task_id": "high-1774022393-15cf1b37",
  "status": "COMPLETED",
  "result": null,        ← Missing
  "output_text": null    ← Missing
}
```

## Fix Applied

Wrote the task result from the disk file to Neo4j:

```cypher
MATCH (t:Task {task_id: 'high-1774022393-15cf1b37'})
SET t.result = $result, t.updated_at = datetime()
```

Result written: 6,998 characters containing:
- ## Resolution section with full breakdown
- ## Execution Output section
- All recommendations, tables, and verification checklists

## Verification

After fix, Neo4j query returns:
```json
{
  "task_id": "high-1774022393-15cf1b37",
  "status": "COMPLETED",
  "result": "## Resolution\n\nApplied horde-brainstorming skill..."
}
```

## Files Changed

- Neo4j `Task` node: `result` field populated (6,998 chars)

## Next Steps

The Kurultai server was not running at time of fix. To verify:
1. Start the Kurultai server: `cd /Users/kublai/.openclaw/apps/the-kurultai && npm start`
2. Visit: http://localhost:3000/r/high-1774022393-15cf1b37
3. Report should now display the full Resolution content

## Related Issues

This fix addresses the symptom (empty report) but the underlying issue is that the task executor didn't write the result to Neo4j after completion. This may affect other tasks that completed via file-based execution but weren't synced to Neo4j.

**Recommended follow-up:** Audit other `.verified.done.md` tasks to check if their Neo4j `result` fields are populated.
