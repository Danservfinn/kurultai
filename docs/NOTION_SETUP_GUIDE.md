# Notion Task Tracker Setup Guide

This guide walks you through setting up a Notion database for shared task tracking with the Kurultai system.

## Overview

The Notion Task Tracker provides:
- **Visual Kanban Board**: Track tasks through Backlog → To Do → In Progress → Review → Done
- **Bidirectional Sync**: Changes in Notion sync to Neo4j and vice versa
- **Agent Assignment**: Assign tasks to specific Kurultai agents (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei)
- **Priority Management**: P0 (Critical) through P3 (Low) priority levels
- **Task Metadata**: Tags, due dates, duration estimates, and completion notes

## Prerequisites

1. A Notion account (free tier works)
2. A Notion workspace where you can create pages

## Step 1: Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"New integration"**
3. Give it a name: `Kurultai Task Tracker`
4. Select the workspace where you want to use it
5. Click **"Submit"**
6. Copy the **"Internal Integration Token"** (starts with `secret_`)
7. Save this token securely - you'll need it for the next step

## Step 2: Set Up Environment Variables

Add the Notion token to your environment:

```bash
# Add to your .env file
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Or export it in your shell:
```bash
export NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Step 3: Create the Database

Run the database creation script:

```bash
cd /data/workspace/souls/main
python tools/create_notion_task_database.py
```

This will:
1. Search for accessible pages in your Notion workspace
2. Create a new database called "Kurultai Task Tracker"
3. Configure all required properties (Status, Priority, Agent, etc.)
4. Create sample tasks to demonstrate the structure
5. Save the database ID to `.env.notion`

## Step 4: Share with Your Integration

After running the script, you need to share the created database with your integration:

1. In Notion, navigate to your new "Kurultai Task Tracker" database
2. Click the **"..."** (three dots) in the top-right corner
3. Scroll down to **"Add connections"**
4. Select your **"Kurultai Task Tracker"** integration
5. Click **"Confirm"**

## Step 5: Update Environment Configuration

Add the database ID to your main `.env` file:

```bash
# From the script output, copy these values:
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_TASK_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Database Schema

The created database includes these properties:

| Property | Type | Description |
|----------|------|-------------|
| **Name** | Title | Task title/description |
| **Status** | Select | Backlog, Pending Review, To Do, In Progress, Review, Done, Blocked |
| **Priority** | Select | P0 (Critical), P1 (High), P2 (Normal), P3 (Low) |
| **Agent** | Select | Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei, any |
| **Neo4j Task ID** | Rich Text | Internal task ID for bidirectional sync |
| **Requester** | Rich Text | Who requested this task |
| **Created From** | Select | Notion, Discord, Signal, Telegram, GitHub, Cron, Manual |
| **Type** | Select | Research, Analysis, Development, Writing, Operations, Strategy, Bug Fix, Feature, Documentation |
| **Duration** | Number | Estimated duration in minutes |
| **Tags** | Multi-select | urgent, blocked, needs-review, high-value, quick-win, ops, code, strategy |
| **Due Date** | Date | Optional deadline |
| **Description** | Rich Text | Detailed task description |
| **Completion Notes** | Rich Text | Notes added when task is completed |

## Usage

### Creating Tasks

1. Open your "Kurultai Task Tracker" database in Notion
2. Click **"+ New"** to create a task
3. Fill in the properties:
   - **Name**: Task title
   - **Status**: Start with "Backlog" or "To Do"
   - **Priority**: P0 for urgent, P2 for normal
   - **Agent**: Select the appropriate agent or "any"
   - **Type**: Category of work
4. The task will automatically sync to Neo4j and be picked up by the task execution system

### Managing Tasks

- **Move cards** between columns to update status
- **Assign agents** using the Agent dropdown
- **Set priorities** to control execution order
- **Add tags** for filtering and organization

### Viewing Tasks

The database comes with several default views:
- **Board View**: Kanban-style columns by status
- **Table View**: Spreadsheet-style with all properties
- **Calendar View**: Tasks by due date

You can create custom views filtered by:
- Agent assignment
- Priority level
- Task type
- Tags

## Troubleshooting

### "No accessible pages found"

**Solution**: You need to share a page with your integration:
1. Create a new page in Notion
2. Click **"..."** → **"Add connections"**
3. Select your integration
4. Run the script again

### "API Error 401"

**Solution**: Your token is invalid or expired:
1. Go back to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Find your integration
3. Click **"Show"** next to the token
4. Copy the token again and update your environment variable

### Tasks not syncing

**Solution**: Check the integration has access:
1. Open the database in Notion
2. Click **"..."** → **"Add connections"**
3. Ensure your integration is listed
4. If not, add it again

### Database not found in script output

**Solution**: The script will list accessible pages. Make sure:
1. You've created at least one page in your workspace
2. You've shared that page with your integration
3. The integration has permission to create databases

## Integration with Kurultai

Once set up, the Notion database integrates with the Kurultai system:

1. **Task Polling** (every 60 seconds): New tasks in Notion are detected and synced to Neo4j
2. **Status Sync**: Changes in Neo4j (task started, completed) sync back to Notion
3. **Agent Assignment**: Tasks assigned to specific agents are routed to those agents
4. **Bidirectional Updates**: Changes in either system reflect in the other

## Advanced Configuration

### Customizing Status Options

Edit `tools/create_notion_task_database.py` and modify the `DATABASE_SCHEMA` constant:

```python
"Status": {
    "select": {
        "options": [
            {"name": "Your Custom Status", "color": "blue"},
            # ... add more
        ]
    }
}
```

### Adding Custom Properties

Add new properties to the schema:

```python
"Custom Field": {
    "rich_text": {}  # or "select": {}, "number": {}, etc.
}
```

See [Notion API documentation](https://developers.notion.com/reference/property-object) for all property types.

## Next Steps

1. **Test the integration**: Create a task in Notion and verify it appears in Neo4j
2. **Set up webhooks** (optional): For real-time sync instead of polling
3. **Configure notifications**: Get alerts when tasks are assigned or completed
4. **Create templates**: Set up recurring task templates in Notion

## Support

For issues or questions:
1. Check the logs: `logs/notion_integration.log`
2. Review the [Notion API docs](https://developers.notion.com/)
3. Consult the Kurultai operational architecture documentation
