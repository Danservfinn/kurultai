module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/fs [external] (fs, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("fs", () => require("fs"));

module.exports = mod;
}),
"[externals]/path [external] (path, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("path", () => require("path"));

module.exports = mod;
}),
"[project]/molt/steppe-visualization/app/api/tasks/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "GET",
    ()=>GET,
    "dynamic",
    ()=>dynamic,
    "revalidate",
    ()=>revalidate
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/server.js [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$externals$5d2f$fs__$5b$external$5d$__$28$fs$2c$__cjs$29$__ = __turbopack_context__.i("[externals]/fs [external] (fs, cjs)");
var __TURBOPACK__imported__module__$5b$externals$5d2f$path__$5b$external$5d$__$28$path$2c$__cjs$29$__ = __turbopack_context__.i("[externals]/path [external] (path, cjs)");
;
;
;
// Local workspace path for development
const WORKSPACE_PATH = process.env.WORKSPACE_PATH || '/Users/kurultai/molt/data/workspace';
// Task directories
const TASK_DIRS = {
    inbox: 'tasks/inbox',
    assigned: 'tasks/assigned',
    inProgress: 'tasks/in-progress',
    review: 'tasks/review',
    done: 'tasks/done'
};
const dynamic = 'force-dynamic';
const revalidate = 0;
async function readTaskFiles(dir, status) {
    const fullPath = __TURBOPACK__imported__module__$5b$externals$5d2f$path__$5b$external$5d$__$28$path$2c$__cjs$29$__["default"].join(WORKSPACE_PATH, dir);
    try {
        await __TURBOPACK__imported__module__$5b$externals$5d2f$fs__$5b$external$5d$__$28$fs$2c$__cjs$29$__["promises"].access(fullPath);
    } catch  {
        return []; // Directory doesn't exist
    }
    const tasks = [];
    try {
        const entries = await __TURBOPACK__imported__module__$5b$externals$5d2f$fs__$5b$external$5d$__$28$fs$2c$__cjs$29$__["promises"].readdir(fullPath, {
            withFileTypes: true
        });
        for (const entry of entries){
            if (entry.isFile() && entry.name.endsWith('.md')) {
                const filePath = __TURBOPACK__imported__module__$5b$externals$5d2f$path__$5b$external$5d$__$28$path$2c$__cjs$29$__["default"].join(fullPath, entry.name);
                const content = await __TURBOPACK__imported__module__$5b$externals$5d2f$fs__$5b$external$5d$__$28$fs$2c$__cjs$29$__["promises"].readFile(filePath, 'utf-8');
                // Parse metadata from frontmatter or content
                const metadata = parseTaskMetadata(content);
                tasks.push({
                    path: __TURBOPACK__imported__module__$5b$externals$5d2f$path__$5b$external$5d$__$28$path$2c$__cjs$29$__["default"].join(dir, entry.name),
                    status,
                    content,
                    metadata
                });
            }
        }
    } catch (error) {
    // Silently fail if directory read fails
    }
    return tasks;
}
function parseTaskMetadata(content) {
    const metadata = {};
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
async function GET() {
    const allTasks = [];
    // Read from all task directories
    for (const [status, dir] of Object.entries(TASK_DIRS)){
        const tasks = await readTaskFiles(dir, status);
        allTasks.push(...tasks);
    }
    // Group by agent
    const tasksByAgent = {};
    for (const task of allTasks){
        const assignedTo = task.metadata?.assignedTo?.toLowerCase() || '';
        const agentId = mapAssignedToAgentId(assignedTo);
        if (!tasksByAgent[agentId]) {
            tasksByAgent[agentId] = [];
        }
        tasksByAgent[agentId].push(task);
    }
    return __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
        tasks: allTasks,
        tasksByAgent,
        summary: {
            total: allTasks.length,
            byStatus: Object.entries(TASK_DIRS).reduce((acc, [status, dir])=>{
                acc[status] = allTasks.filter((t)=>t.status === dir).length;
                return acc;
            }, {})
        }
    });
}
function mapAssignedToAgentId(assignedTo) {
    const mapping = {
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
        '@chagatai': 'chagatai'
    };
    return mapping[assignedTo] || 'unassigned';
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__2a932acb._.js.map