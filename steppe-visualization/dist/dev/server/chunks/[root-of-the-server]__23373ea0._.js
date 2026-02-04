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
"[project]/molt/steppe-visualization/app/api/agents/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
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
;
// Gateway configuration
const GATEWAY_URL = process.env.GATEWAY_URL || 'http://localhost:18789';
const GATEWAY_TOKEN = process.env.GATEWAY_TOKEN || '';
// Agent definitions matching the mission-control plan
const AGENT_DEFINITIONS = [
    {
        id: 'main',
        name: 'Kublai',
        role: 'coordinator',
        sessionId: 'agent:main:main'
    },
    {
        id: 'researcher',
        name: 'Möngke',
        role: 'researcher',
        sessionId: 'agent:researcher:main'
    },
    {
        id: 'writer',
        name: 'Ögedei',
        role: 'writer',
        sessionId: 'agent:writer:main'
    },
    {
        id: 'developer',
        name: 'Temüjin',
        role: 'developer',
        sessionId: 'agent:developer:main'
    },
    {
        id: 'analyst',
        name: 'Jochi',
        role: 'analyst',
        sessionId: 'agent:analyst:main'
    },
    {
        id: 'ops',
        name: 'Chagatai',
        role: 'operations',
        sessionId: 'agent:ops:main'
    }
];
const dynamic = 'force-dynamic';
const revalidate = 0;
async function fetchFromGateway(endpoint) {
    try {
        const headers = {
            'Accept': 'application/json'
        };
        if (GATEWAY_TOKEN) {
            headers['Authorization'] = `Bearer ${GATEWAY_TOKEN}`;
        }
        const response = await fetch(`${GATEWAY_URL}${endpoint}`, {
            headers,
            signal: AbortSignal.timeout(5000)
        });
        if (response.ok) {
            const data = await response.json();
            return {
                success: true,
                data
            };
        }
        return {
            success: false,
            error: `HTTP ${response.status}`
        };
    } catch (error) {
        return {
            success: false,
            error: error instanceof Error ? error.message : 'Unknown error'
        };
    }
}
async function GET() {
    // Try to fetch from gateway
    const sessionsResult = await fetchFromGateway('/api/sessions');
    if (sessionsResult.success && sessionsResult.data) {
        // Map gateway sessions to agent status
        const agents = AGENT_DEFINITIONS.map((def)=>{
            const sessionData = sessionsResult.data.find((s)=>s.sessionId === def.sessionId);
            return {
                ...def,
                status: sessionData ? 'working' : 'idle',
                lastActive: sessionData?.lastActivity || null,
                messageCount: sessionData?.messageCount || 0
            };
        });
        return __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            source: 'gateway',
            agents
        });
    }
    // Fallback: Return agent definitions with simulated status
    return __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
        source: 'fallback',
        agents: AGENT_DEFINITIONS.map((def)=>({
                ...def,
                status: 'idle',
                lastActive: null,
                messageCount: 0
            })),
        gatewayError: sessionsResult.error
    });
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__23373ea0._.js.map