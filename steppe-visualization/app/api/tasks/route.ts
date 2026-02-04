import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';

// Local workspace path for development
const WORKSPACE_PATH = process.env.WORKSPACE_PATH || '/Users/kurultai/molt/data/workspace';

// Task directories
const TASK_DIRS = {
  inbox: 'tasks/inbox',
  assigned: 'tasks/assigned',
  inProgress: 'tasks/in-progress',
  review: 'tasks/review',
  done: 'tasks/done',
};

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface TaskFile {
  path: string;
  status: keyof typeof TASK_DIRS;
  content: string;
  metadata?: {
    title?: string;
    assignedTo?: string;
    priority?: string;
    created?: string;
  };
}

async function readTaskFiles(dir: string, status: keyof typeof TASK_DIRS): Promise<TaskFile[]> {
  const fullPath = path.join(WORKSPACE_PATH, dir);

  try {
    await fs.access(fullPath);
  } catch {
    return []; // Directory doesn't exist
  }

  const tasks: TaskFile[] = [];

  try {
    const entries = await fs.readdir(fullPath, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isFile() && entry.name.endsWith('.md')) {
        const filePath = path.join(fullPath, entry.name);
        const content = await fs.readFile(filePath, 'utf-8');

        // Parse metadata from frontmatter or content
        const metadata = parseTaskMetadata(content);

        tasks.push({
          path: path.join(dir, entry.name),
          status,
          content,
          metadata,
        });
      }
    }
  } catch (error) {
    // Silently fail if directory read fails
  }

  return tasks;
}

function parseTaskMetadata(content: string) {
  const metadata: Record<string, string> = {};

  // Look for common task patterns
  const titleMatch = content.match(/^#\s+(.+)$/m);
  if (titleMatch) metadata.title = titleMatch[1];

  const assignedMatch = content.match(/\*\*Assigned To\*\*:\s*(.+)$/m);
  if (assignedMatch) metadata.assignedTo = assignedMatch[1];

  const priorityMatch = content.match(/\*\*Priority\*\*:\s*(\w+)$/m);
  if (priorityMatch) metadata.priority = priorityMatch[1];

  const createdMatch = content.match(/\*\*Created\*\*:\s*(.+)$/m);
  if (createdMatch) metadata.created = createdMatch[1];

  return metadata;
}

export async function GET() {
  const allTasks: TaskFile[] = [];

  // Read from all task directories
  for (const [status, dir] of Object.entries(TASK_DIRS)) {
    const tasks = await readTaskFiles(dir, status as keyof typeof TASK_DIRS);
    allTasks.push(...tasks);
  }

  // Group by agent
  const tasksByAgent: Record<string, TaskFile[]> = {};

  for (const task of allTasks) {
    const assignedTo = task.metadata?.assignedTo?.toLowerCase() || '';
    const agentId = mapAssignedToAgentId(assignedTo);

    if (!tasksByAgent[agentId]) {
      tasksByAgent[agentId] = [];
    }
    tasksByAgent[agentId].push(task);
  }

  return NextResponse.json({
    tasks: allTasks,
    tasksByAgent,
    summary: {
      total: allTasks.length,
      byStatus: Object.entries(TASK_DIRS).reduce((acc, [status, dir]) => {
        acc[status] = allTasks.filter(t => t.status === dir).length;
        return acc;
      }, {} as Record<string, number>),
    }
  });
}

function mapAssignedToAgentId(assignedTo: string): string {
  const mapping: Record<string, string> = {
    'kublai': 'kublai',
    '@kublai': 'kublai',
    'mongke': 'mongke',
    '@mongke': 'mongke',
    'ögedei': 'ogedei',
    'ogedei': 'ogedei',
    '@ogedei': 'ogedei',
    'temüjin': 'temujin',
    'temujin': 'temujin',
    '@temujin': 'temujin',
    'jochi': 'jochi',
    '@jochi': 'jochi',
    'chagatai': 'chagatai',
    '@chagatai': 'chagatai',
  };

  return mapping[assignedTo] || 'unassigned';
}
