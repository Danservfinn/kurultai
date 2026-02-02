import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';

export const dynamic = 'force-static';
export const revalidate = 5;

const DELIVERABLES_PATH = process.env.DELIVERABLES_PATH || '/data/workspace/deliverables';

export async function GET() {
  try {
    // Check if directory exists
    try {
      await fs.access(DELIVERABLES_PATH);
    } catch {
      // Return empty array if path doesn't exist
      return NextResponse.json({ files: [] });
    }

    // Read directory recursively
    const files = await getAllFiles(DELIVERABLES_PATH);

    return NextResponse.json({ files });
  } catch (error) {
    console.error('Error reading deliverables:', error);
    return NextResponse.json(
      { error: 'Failed to read deliverables' },
      { status: 500 }
    );
  }
}

async function getAllFiles(dir: string, basePath: string = ''): Promise<string[]> {
  const files: string[] = [];

  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      const relativePath = path.join(basePath, entry.name);

      if (entry.isDirectory()) {
        const subFiles = await getAllFiles(fullPath, relativePath);
        files.push(...subFiles);
      } else {
        files.push(relativePath);
      }
    }
  } catch {
    // Directory might not exist or be accessible
  }

  return files;
}
