import { NextResponse } from 'next/server';

// Mock memory stats for now - in production this would query Neo4j
export async function GET() {
  // Simulated Neo4j counts
  const stats = {
    research_count: 47,
    content_count: 23,
    analysis_count: 15,
    application_count: 8,
    insight_count: 31,
    concept_count: 124,
    task_count: 89,
    notification_count: 12,
  };

  return NextResponse.json(stats);
}
