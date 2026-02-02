(globalThis.TURBOPACK || (globalThis.TURBOPACK = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/molt/steppe-visualization/app/lib/agents.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AGENTS",
    ()=>AGENTS,
    "getAgentById",
    ()=>getAgentById,
    "getAgentColor",
    ()=>getAgentColor,
    "getElevation",
    ()=>getElevation,
    "latLngToWorld",
    ()=>latLngToWorld
]);
// Convert lat/lng to 3D world coordinates
// Mongol Empire bounds at its height (1279): 22°E to 135°E, 22°N to 55°N
const MAP_BOUNDS = {
    minLat: 22,
    maxLat: 55,
    minLng: 22,
    maxLng: 135
};
function latLngToWorld(lat, lng) {
    const x = (lng - MAP_BOUNDS.minLng) / (MAP_BOUNDS.maxLng - MAP_BOUNDS.minLng) * 120 - 60;
    const z = (lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat) * -70 + 35;
    return {
        x,
        z
    };
}
function getElevation(lat, lng) {
    // Flat elevation - very minimal variation for the new flat terrain
    return 0.5;
}
const AGENTS = [
    {
        id: 'temujin',
        name: 'Temujin',
        role: 'developer',
        displayName: 'Temujin (Genghis Khan)',
        description: 'Founder of the Mongol Empire and the Developer agent - building the foundation',
        historicalCapital: 'Karakorum',
        historicalContext: 'Established Karakorum as the supply base in 1220. The original capital of the Mongol Empire.',
        coordinates: {
            lat: 47.2,
            lng: 102.5
        },
        position: {
            ...latLngToWorld(47.2, 102.5),
            elevation: getElevation(47.2, 102.5)
        },
        theme: {
            primary: '#71717A',
            secondary: '#DC2626',
            glow: '#DC2626'
        },
        status: 'working',
        currentTask: {
            id: 'task-1',
            title: 'Refactoring core architecture',
            description: 'Optimizing the main codebase structure',
            progress: 65,
            startedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
            estimatedCompletion: new Date(Date.now() + 1 * 60 * 60 * 1000)
        },
        queue: [
            {
                id: 'q1',
                title: 'Security audit',
                priority: 'high',
                estimatedDuration: 120
            },
            {
                id: 'q2',
                title: 'API optimization',
                priority: 'medium',
                estimatedDuration: 90
            },
            {
                id: 'q3',
                title: 'Database migration',
                priority: 'high',
                estimatedDuration: 180
            }
        ],
        metrics: {
            tasksCompleted: 12,
            itemsProduced: 8,
            activeTimeMinutes: 340,
            lastActiveAt: new Date()
        },
        camp: {
            type: 'forge',
            description: 'A warrior\'s workshop with tools and armor',
            props: [
                'anvil',
                'weapons',
                'banners'
            ]
        }
    },
    {
        id: 'ogedei',
        name: 'Ogedei',
        role: 'writer',
        displayName: 'Ögedei Khan',
        description: 'Second Great Khan and the Writer agent - crafting content and documentation',
        historicalCapital: 'Samarkand',
        historicalContext: 'While he ruled from Karakorum, Samarkand represents his expansion into Central Asia and the Silk Road.',
        coordinates: {
            lat: 39.6,
            lng: 66.9
        },
        position: {
            ...latLngToWorld(39.6, 66.9),
            elevation: getElevation(39.6, 66.9)
        },
        theme: {
            primary: '#228B22',
            secondary: '#8B4513',
            glow: '#228B22'
        },
        status: 'working',
        currentTask: {
            id: 'task-2',
            title: 'Writing documentation',
            description: 'Creating API reference docs',
            progress: 40,
            startedAt: new Date(Date.now() - 1 * 60 * 60 * 1000),
            estimatedCompletion: new Date(Date.now() + 2 * 60 * 60 * 1000)
        },
        queue: [
            {
                id: 'q4',
                title: 'Blog post draft',
                priority: 'medium',
                estimatedDuration: 60
            },
            {
                id: 'q5',
                title: 'User guide update',
                priority: 'high',
                estimatedDuration: 120
            }
        ],
        metrics: {
            tasksCompleted: 8,
            itemsProduced: 15,
            activeTimeMinutes: 280,
            lastActiveAt: new Date()
        },
        camp: {
            type: 'caravanserai',
            description: 'A bustling Silk Road trading post with scrolls and maps',
            props: [
                'scrolls',
                'maps',
                'trading goods'
            ]
        }
    },
    {
        id: 'mongke',
        name: 'Mongke',
        role: 'researcher',
        displayName: 'Möngke Khan',
        description: 'Fourth Great Khan and the Researcher agent - gathering intelligence and knowledge',
        historicalCapital: 'Bukhara',
        historicalContext: 'Bukhara was a center of Islamic learning. Mongke conducted empire-wide censuses and sent expeditions to gather knowledge.',
        coordinates: {
            lat: 39.8,
            lng: 64.4
        },
        position: {
            ...latLngToWorld(39.8, 64.4),
            elevation: getElevation(39.8, 64.4)
        },
        theme: {
            primary: '#1E40AF',
            secondary: '#C0C0C0',
            glow: '#1E40AF'
        },
        status: 'reviewing',
        currentTask: {
            id: 'task-3',
            title: 'Market analysis report',
            description: 'Analyzing competitor strategies',
            progress: 85,
            startedAt: new Date(Date.now() - 3 * 60 * 60 * 1000),
            estimatedCompletion: new Date(Date.now() + 30 * 60 * 1000)
        },
        queue: [
            {
                id: 'q6',
                title: 'User research study',
                priority: 'high',
                estimatedDuration: 240
            },
            {
                id: 'q7',
                title: 'Data collection',
                priority: 'medium',
                estimatedDuration: 90
            },
            {
                id: 'q8',
                title: 'Trend analysis',
                priority: 'low',
                estimatedDuration: 120
            }
        ],
        metrics: {
            tasksCompleted: 6,
            itemsProduced: 4,
            activeTimeMinutes: 420,
            lastActiveAt: new Date()
        },
        camp: {
            type: 'observatory',
            description: 'A scholarly retreat with astronomical instruments and manuscripts',
            props: [
                'telescope',
                'books',
                'astrolabe'
            ]
        }
    },
    {
        id: 'kublai',
        name: 'Kublai',
        role: 'coordinator',
        displayName: 'Kublai Khan',
        description: 'First Yuan Emperor and the Coordinator agent - orchestrating the empire',
        historicalCapital: 'Shangdu (Xanadu)',
        historicalContext: 'Founded Shangdu (Xanadu) in 1256 as his summer capital before moving to Dadu (Beijing).',
        coordinates: {
            lat: 42.3,
            lng: 116.2
        },
        position: {
            ...latLngToWorld(42.3, 116.2),
            elevation: getElevation(42.3, 116.2)
        },
        theme: {
            primary: '#FFD700',
            secondary: '#1E3A8A',
            glow: '#FFD700'
        },
        status: 'working',
        currentTask: {
            id: 'task-4',
            title: 'Strategic planning',
            description: 'Coordinating cross-team initiatives',
            progress: 25,
            startedAt: new Date(Date.now() - 30 * 60 * 1000),
            estimatedCompletion: new Date(Date.now() + 3 * 60 * 60 * 1000)
        },
        queue: [
            {
                id: 'q9',
                title: 'Review PRs',
                priority: 'high',
                estimatedDuration: 60
            },
            {
                id: 'q10',
                title: 'Team sync',
                priority: 'medium',
                estimatedDuration: 30
            },
            {
                id: 'q11',
                title: 'Q1 roadmap',
                priority: 'high',
                estimatedDuration: 180
            }
        ],
        metrics: {
            tasksCompleted: 20,
            itemsProduced: 12,
            activeTimeMinutes: 380,
            lastActiveAt: new Date()
        },
        camp: {
            type: 'palace',
            description: 'An imperial palace with gardens and administrative halls',
            props: [
                'throne',
                'banners',
                'imperial seals'
            ]
        }
    },
    {
        id: 'chagatai',
        name: 'Chagatai',
        role: 'operations',
        displayName: 'Chagatai Khan',
        description: 'Founder of the Chagatai Khanate and the Operations agent - managing logistics',
        historicalCapital: 'Almaliq',
        historicalContext: 'Almaliq in the Ili River Valley was a key city in the Chagatai Khanate, controlling the northern Silk Road.',
        coordinates: {
            lat: 44.0,
            lng: 78.5
        },
        position: {
            ...latLngToWorld(44.0, 78.5),
            elevation: getElevation(44.0, 78.5)
        },
        theme: {
            primary: '#EA580C',
            secondary: '#CD7F32',
            glow: '#EA580C'
        },
        status: 'working',
        currentTask: {
            id: 'task-5',
            title: 'Infrastructure scaling',
            description: 'Setting up new server instances',
            progress: 55,
            startedAt: new Date(Date.now() - 4 * 60 * 60 * 1000),
            estimatedCompletion: new Date(Date.now() + 2 * 60 * 60 * 1000)
        },
        queue: [
            {
                id: 'q12',
                title: 'CI/CD pipeline update',
                priority: 'high',
                estimatedDuration: 90
            },
            {
                id: 'q13',
                title: 'Monitoring setup',
                priority: 'medium',
                estimatedDuration: 60
            }
        ],
        metrics: {
            tasksCompleted: 15,
            itemsProduced: 6,
            activeTimeMinutes: 460,
            lastActiveAt: new Date()
        },
        camp: {
            type: 'caravanserai',
            description: 'A fortified waystation on the Silk Road',
            props: [
                'horses',
                'supplies',
                'route maps'
            ]
        }
    },
    {
        id: 'jochi',
        name: 'Jochi',
        role: 'analyst',
        displayName: 'Jochi Khan',
        description: 'Eldest son of Genghis Khan and the Analyst agent - tracking metrics and intelligence',
        historicalCapital: 'Sarai Batu',
        historicalContext: 'Sarai Batu on the lower Volga was the capital of the Golden Horde, controlling trade and tribute from Russia.',
        coordinates: {
            lat: 48.5,
            lng: 45.0
        },
        position: {
            ...latLngToWorld(48.5, 45.0),
            elevation: getElevation(48.5, 45.0)
        },
        theme: {
            primary: '#7C3AED',
            secondary: '#F59E0B',
            glow: '#7C3AED'
        },
        status: 'idle',
        queue: [
            {
                id: 'q14',
                title: 'Performance metrics',
                priority: 'high',
                estimatedDuration: 120
            },
            {
                id: 'q15',
                title: 'Revenue analysis',
                priority: 'high',
                estimatedDuration: 90
            },
            {
                id: 'q16',
                title: 'User behavior report',
                priority: 'medium',
                estimatedDuration: 150
            }
        ],
        metrics: {
            tasksCompleted: 10,
            itemsProduced: 7,
            activeTimeMinutes: 290,
            lastActiveAt: new Date(Date.now() - 30 * 60 * 1000)
        },
        camp: {
            type: 'counting-house',
            description: 'A administrative center with tribute records and trade ledgers',
            props: [
                'abacus',
                'scrolls',
                'tribute goods'
            ]
        }
    }
];
function getAgentById(id) {
    return AGENTS.find((a)=>a.id === id);
}
function getAgentColor(role) {
    const colors = {
        coordinator: '#FFD700',
        researcher: '#1E40AF',
        writer: '#228B22',
        developer: '#DC2626',
        analyst: '#7C3AED',
        operations: '#EA580C'
    };
    return colors[role];
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "useAgentStore",
    ()=>useAgentStore
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$zustand$2f$esm$2f$react$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/zustand/esm/react.mjs [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$lib$2f$agents$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/lib/agents.ts [app-client] (ecmascript)");
'use client';
;
;
const useAgentStore = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$zustand$2f$esm$2f$react$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["create"])((set, get)=>({
        // Initial data
        agents: __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$lib$2f$agents$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["AGENTS"],
        activities: [],
        deliverables: [],
        selectedAgentId: null,
        isDetailPanelOpen: false,
        // Actions
        setAgents: (agents)=>set({
                agents
            }),
        updateAgent: (agentId, updates)=>set((state)=>({
                    agents: state.agents.map((agent)=>agent.id === agentId ? {
                            ...agent,
                            ...updates
                        } : agent)
                })),
        updateAgentStatus: (agentId, status)=>set((state)=>({
                    agents: state.agents.map((agent)=>agent.id === agentId ? {
                            ...agent,
                            status,
                            metrics: {
                                ...agent.metrics,
                                lastActiveAt: new Date()
                            }
                        } : agent)
                })),
        updateAgentTask: (agentId, task)=>set((state)=>({
                    agents: state.agents.map((agent)=>agent.id === agentId ? {
                            ...agent,
                            currentTask: task
                        } : agent)
                })),
        addActivity: (activity)=>set((state)=>({
                    activities: [
                        activity,
                        ...state.activities
                    ].slice(0, 100)
                })),
        addDeliverable: (deliverable)=>set((state)=>({
                    deliverables: [
                        deliverable,
                        ...state.deliverables
                    ]
                })),
        selectAgent: (agentId)=>set({
                selectedAgentId: agentId,
                isDetailPanelOpen: agentId !== null
            }),
        toggleDetailPanel: (open)=>set((state)=>({
                    isDetailPanelOpen: open ?? !state.isDetailPanelOpen
                })),
        // Derived getters
        getSelectedAgent: ()=>{
            const { agents, selectedAgentId } = get();
            return agents.find((a)=>a.id === selectedAgentId);
        },
        getAgentActivities: (agentId)=>{
            return get().activities.filter((a)=>a.agentId === agentId);
        },
        getAgentDeliverables: (agentId)=>{
            return get().deliverables.filter((d)=>d.agentId === agentId);
        }
    }));
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "cn",
    ()=>cn
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/clsx/dist/clsx.mjs [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/tailwind-merge/dist/bundle-mjs.mjs [app-client] (ecmascript)");
;
;
function cn(...inputs) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["twMerge"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["clsx"])(inputs));
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/components/ui/card.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Card",
    ()=>Card,
    "CardAction",
    ()=>CardAction,
    "CardContent",
    ()=>CardContent,
    "CardDescription",
    ()=>CardDescription,
    "CardFooter",
    ()=>CardFooter,
    "CardHeader",
    ()=>CardHeader,
    "CardTitle",
    ()=>CardTitle
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
;
;
function Card({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("bg-card text-card-foreground flex flex-col gap-6 rounded-xl border py-6 shadow-sm", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 7,
        columnNumber: 5
    }, this);
}
_c = Card;
function CardHeader({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-header",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 20,
        columnNumber: 5
    }, this);
}
_c1 = CardHeader;
function CardTitle({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-title",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("leading-none font-semibold", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 33,
        columnNumber: 5
    }, this);
}
_c2 = CardTitle;
function CardDescription({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-description",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("text-muted-foreground text-sm", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 43,
        columnNumber: 5
    }, this);
}
_c3 = CardDescription;
function CardAction({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-action",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 53,
        columnNumber: 5
    }, this);
}
_c4 = CardAction;
function CardContent({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-content",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("px-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 66,
        columnNumber: 5
    }, this);
}
_c5 = CardContent;
function CardFooter({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-footer",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("flex items-center px-6 [.border-t]:pt-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 76,
        columnNumber: 5
    }, this);
}
_c6 = CardFooter;
;
var _c, _c1, _c2, _c3, _c4, _c5, _c6;
__turbopack_context__.k.register(_c, "Card");
__turbopack_context__.k.register(_c1, "CardHeader");
__turbopack_context__.k.register(_c2, "CardTitle");
__turbopack_context__.k.register(_c3, "CardDescription");
__turbopack_context__.k.register(_c4, "CardAction");
__turbopack_context__.k.register(_c5, "CardContent");
__turbopack_context__.k.register(_c6, "CardFooter");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/components/ui/badge.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Badge",
    ()=>Badge,
    "badgeVariants",
    ()=>badgeVariants
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/class-variance-authority/dist/index.mjs [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-slot/dist/index.mjs [app-client] (ecmascript) <export * as Slot>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
;
;
;
;
const badgeVariants = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cva"])("inline-flex items-center justify-center rounded-full border border-transparent px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive transition-[color,box-shadow] overflow-hidden", {
    variants: {
        variant: {
            default: "bg-primary text-primary-foreground [a&]:hover:bg-primary/90",
            secondary: "bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90",
            destructive: "bg-destructive text-white [a&]:hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60",
            outline: "border-border text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
            ghost: "[a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
            link: "text-primary underline-offset-4 [a&]:hover:underline"
        }
    },
    defaultVariants: {
        variant: "default"
    }
});
function Badge({ className, variant = "default", asChild = false, ...props }) {
    const Comp = asChild ? __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__["Slot"].Root : "span";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(Comp, {
        "data-slot": "badge",
        "data-variant": variant,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])(badgeVariants({
            variant
        }), className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/badge.tsx",
        lineNumber: 39,
        columnNumber: 5
    }, this);
}
_c = Badge;
;
var _c;
__turbopack_context__.k.register(_c, "Badge");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/components/ui/progress.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Progress",
    ()=>Progress
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-progress/dist/index.mjs [app-client] (ecmascript) <export * as Progress>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
"use client";
;
;
;
function Progress({ className, value, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__["Progress"].Root, {
        "data-slot": "progress",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full", className),
        ...props,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__["Progress"].Indicator, {
            "data-slot": "progress-indicator",
            className: "bg-primary h-full w-full flex-1 transition-all",
            style: {
                transform: `translateX(-${100 - (value || 0)}%)`
            }
        }, void 0, false, {
            fileName: "[project]/molt/steppe-visualization/components/ui/progress.tsx",
            lineNumber: 22,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/progress.tsx",
        lineNumber: 14,
        columnNumber: 5
    }, this);
}
_c = Progress;
;
var _c;
__turbopack_context__.k.register(_c, "Progress");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/components/ui/scroll-area.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ScrollArea",
    ()=>ScrollArea,
    "ScrollBar",
    ()=>ScrollBar
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-scroll-area/dist/index.mjs [app-client] (ecmascript) <export * as ScrollArea>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
"use client";
;
;
;
function ScrollArea({ className, children, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Root, {
        "data-slot": "scroll-area",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("relative", className),
        ...props,
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Viewport, {
                "data-slot": "scroll-area-viewport",
                className: "focus-visible:ring-ring/50 size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:outline-1",
                children: children
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
                lineNumber: 19,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(ScrollBar, {}, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
                lineNumber: 25,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Corner, {}, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
                lineNumber: 26,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
        lineNumber: 14,
        columnNumber: 5
    }, this);
}
_c = ScrollArea;
function ScrollBar({ className, orientation = "vertical", ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].ScrollAreaScrollbar, {
        "data-slot": "scroll-area-scrollbar",
        orientation: orientation,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("flex touch-none p-px transition-colors select-none", orientation === "vertical" && "h-full w-2.5 border-l border-l-transparent", orientation === "horizontal" && "h-2.5 flex-col border-t border-t-transparent", className),
        ...props,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].ScrollAreaThumb, {
            "data-slot": "scroll-area-thumb",
            className: "bg-border relative flex-1 rounded-full"
        }, void 0, false, {
            fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
            lineNumber: 50,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
        lineNumber: 37,
        columnNumber: 5
    }, this);
}
_c1 = ScrollBar;
;
var _c, _c1;
__turbopack_context__.k.register(_c, "ScrollArea");
__turbopack_context__.k.register(_c1, "ScrollBar");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/components/ui/button.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Button",
    ()=>Button,
    "buttonVariants",
    ()=>buttonVariants
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/class-variance-authority/dist/index.mjs [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-slot/dist/index.mjs [app-client] (ecmascript) <export * as Slot>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
;
;
;
;
const buttonVariants = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cva"])("inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive", {
    variants: {
        variant: {
            default: "bg-primary text-primary-foreground hover:bg-primary/90",
            destructive: "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60",
            outline: "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50",
            secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
            ghost: "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
            link: "text-primary underline-offset-4 hover:underline"
        },
        size: {
            default: "h-9 px-4 py-2 has-[>svg]:px-3",
            xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
            sm: "h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5",
            lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
            icon: "size-9",
            "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
            "icon-sm": "size-8",
            "icon-lg": "size-10"
        }
    },
    defaultVariants: {
        variant: "default",
        size: "default"
    }
});
function Button({ className, variant = "default", size = "default", asChild = false, ...props }) {
    const Comp = asChild ? __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__["Slot"].Root : "button";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(Comp, {
        "data-slot": "button",
        "data-variant": variant,
        "data-size": size,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])(buttonVariants({
            variant,
            size,
            className
        })),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/button.tsx",
        lineNumber: 54,
        columnNumber: 5
    }, this);
}
_c = Button;
;
var _c;
__turbopack_context__.k.register(_c, "Button");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/molt/steppe-visualization/app/mission-control/page.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>MissionControlPage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$arrow$2d$left$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__ArrowLeft$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/arrow-left.js [app-client] (ecmascript) <export default as ArrowLeft>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$clock$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Clock$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/clock.js [app-client] (ecmascript) <export default as Clock>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$list$2d$ordered$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__ListOrdered$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/list-ordered.js [app-client] (ecmascript) <export default as ListOrdered>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$activity$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Activity$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/activity.js [app-client] (ecmascript) <export default as Activity>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$alert$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__AlertCircle$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/circle-alert.js [app-client] (ecmascript) <export default as AlertCircle>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$crown$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Crown$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/crown.js [app-client] (ecmascript) <export default as Crown>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/card.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/badge.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$progress$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/progress.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$scroll$2d$area$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/scroll-area.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/button.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
'use client';
;
;
;
;
;
;
;
;
;
const STATUS_CONFIG = {
    idle: {
        label: 'Idle',
        color: 'bg-green-500'
    },
    working: {
        label: 'Working',
        color: 'bg-blue-500'
    },
    reviewing: {
        label: 'Reviewing',
        color: 'bg-amber-500'
    },
    alert: {
        label: 'Alert',
        color: 'bg-red-500'
    },
    offline: {
        label: 'Offline',
        color: 'bg-gray-500'
    }
};
const ACTIVITY_ICONS = {
    research: '🔍',
    content: '📝',
    security: '🔒',
    'code-review': '👁️',
    automation: '⚙️',
    analysis: '📊',
    operations: '📦'
};
function AgentCard({ agent, activities }) {
    const status = STATUS_CONFIG[agent.status];
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
        className: "bg-black/40 border-white/10 backdrop-blur-sm overflow-hidden flex flex-col h-full",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "p-4 border-b border-white/10",
                style: {
                    background: `linear-gradient(135deg, ${agent.theme.primary}20, ${agent.theme.secondary}10)`
                },
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "flex items-start gap-3",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "w-10 h-10 rounded-full flex items-center justify-center shadow-lg flex-shrink-0",
                            style: {
                                background: `linear-gradient(135deg, ${agent.theme.primary}, ${agent.theme.secondary})`
                            },
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$crown$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Crown$3e$__["Crown"], {
                                className: "w-5 h-5 text-white"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                lineNumber: 56,
                                columnNumber: 13
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 50,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex-1 min-w-0",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                            className: "text-lg font-bold text-white truncate",
                                            children: agent.displayName
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 60,
                                            columnNumber: 15
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Badge"], {
                                            variant: "outline",
                                            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])('text-white border-none shrink-0', status.color.replace('bg-', 'bg-').replace('500', '500/20')),
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])('w-1.5 h-1.5 rounded-full mr-1.5', status.color)
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                    lineNumber: 65,
                                                    columnNumber: 17
                                                }, this),
                                                status.label
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 61,
                                            columnNumber: 15
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 59,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-sm text-white/60 capitalize",
                                    children: [
                                        agent.role,
                                        " Agent"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 69,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-xs text-white/40 mt-1",
                                    children: agent.historicalCapital
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 70,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 58,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                    lineNumber: 49,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                lineNumber: 43,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$scroll$2d$area$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["ScrollArea"], {
                className: "flex-1",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "p-4 space-y-4",
                    children: [
                        agent.currentTask && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-2 text-sm font-semibold text-white/80",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$clock$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Clock$3e$__["Clock"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 81,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            children: "Current Task"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 82,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "ml-auto text-white/50",
                                            children: [
                                                Math.round(agent.currentTask.progress),
                                                "%"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 83,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 80,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
                                    className: "bg-white/5 border-white/10 p-3",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                            className: "text-white font-medium text-sm",
                                            children: agent.currentTask.title
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 86,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-xs text-white/50 mt-1 line-clamp-2",
                                            children: agent.currentTask.description
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 87,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$progress$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Progress"], {
                                            value: agent.currentTask.progress,
                                            className: "h-1.5 mt-2"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 88,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 85,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 79,
                            columnNumber: 13
                        }, this),
                        agent.queue.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-2 text-sm font-semibold text-white/80",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$list$2d$ordered$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__ListOrdered$3e$__["ListOrdered"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 97,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            children: [
                                                "Queue (",
                                                agent.queue.length,
                                                ")"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 98,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 96,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "space-y-1.5",
                                    children: [
                                        agent.queue.slice(0, 5).map((task, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
                                                className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])('bg-white/5 border-white/10 p-2.5', task.priority === 'high' && 'border-red-500/30'),
                                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "flex items-start gap-2",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "flex-shrink-0 w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-xs text-white/50",
                                                            children: index + 1
                                                        }, void 0, false, {
                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                            lineNumber: 110,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                            className: "flex-1 min-w-0",
                                                            children: [
                                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                    className: "flex items-center gap-2",
                                                                    children: [
                                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                            className: "text-sm text-white truncate",
                                                                            children: task.title
                                                                        }, void 0, false, {
                                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                            lineNumber: 115,
                                                                            columnNumber: 27
                                                                        }, this),
                                                                        task.priority === 'high' && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$alert$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__AlertCircle$3e$__["AlertCircle"], {
                                                                            className: "w-3 h-3 text-red-400 shrink-0"
                                                                        }, void 0, false, {
                                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                            lineNumber: 116,
                                                                            columnNumber: 56
                                                                        }, this)
                                                                    ]
                                                                }, void 0, true, {
                                                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                    lineNumber: 114,
                                                                    columnNumber: 25
                                                                }, this),
                                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                    className: "flex items-center gap-2 mt-1",
                                                                    children: [
                                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Badge"], {
                                                                            variant: "outline",
                                                                            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])('text-xs border-none', task.priority === 'high' && 'bg-red-500/20 text-red-300', task.priority === 'medium' && 'bg-amber-500/20 text-amber-300', task.priority === 'low' && 'bg-green-500/20 text-green-300'),
                                                                            children: task.priority
                                                                        }, void 0, false, {
                                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                            lineNumber: 119,
                                                                            columnNumber: 27
                                                                        }, this),
                                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                            className: "text-xs text-white/40",
                                                                            children: [
                                                                                "~",
                                                                                task.estimatedDuration,
                                                                                " min"
                                                                            ]
                                                                        }, void 0, true, {
                                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                            lineNumber: 130,
                                                                            columnNumber: 27
                                                                        }, this)
                                                                    ]
                                                                }, void 0, true, {
                                                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                    lineNumber: 118,
                                                                    columnNumber: 25
                                                                }, this)
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                            lineNumber: 113,
                                                            columnNumber: 23
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                    lineNumber: 109,
                                                    columnNumber: 21
                                                }, this)
                                            }, task.id, false, {
                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                lineNumber: 102,
                                                columnNumber: 19
                                            }, this)),
                                        agent.queue.length > 5 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-xs text-white/40 text-center py-1",
                                            children: [
                                                "+",
                                                agent.queue.length - 5,
                                                " more tasks"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 137,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 100,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 95,
                            columnNumber: 13
                        }, this),
                        activities.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-2 text-sm font-semibold text-white/80",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$activity$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__Activity$3e$__["Activity"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 149,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            children: "Activity Log"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 150,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "ml-auto text-xs text-white/40",
                                            children: "Last 24h"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 151,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 148,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "space-y-1.5",
                                    children: activities.slice(0, 10).map((activity)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-2.5",
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "flex items-start gap-2",
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                        className: "text-sm shrink-0",
                                                        children: ACTIVITY_ICONS[activity.type]
                                                    }, void 0, false, {
                                                        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                        lineNumber: 157,
                                                        columnNumber: 23
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                        className: "flex-1 min-w-0",
                                                        children: [
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                                className: "text-xs font-medium text-white truncate",
                                                                children: activity.title
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                lineNumber: 159,
                                                                columnNumber: 25
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                                className: "text-xs text-white/40 truncate",
                                                                children: activity.description
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                lineNumber: 160,
                                                                columnNumber: 25
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                                className: "text-xs text-white/30 mt-0.5",
                                                                children: new Date(activity.timestamp).toLocaleTimeString([], {
                                                                    hour: '2-digit',
                                                                    minute: '2-digit'
                                                                })
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                                lineNumber: 161,
                                                                columnNumber: 25
                                                            }, this)
                                                        ]
                                                    }, void 0, true, {
                                                        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                        lineNumber: 158,
                                                        columnNumber: 23
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                lineNumber: 156,
                                                columnNumber: 21
                                            }, this)
                                        }, activity.id, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 155,
                                            columnNumber: 19
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 153,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 147,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "grid grid-cols-2 gap-2 pt-2 border-t border-white/10",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
                                    className: "bg-white/5 border-white/10 p-2 text-center",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-lg font-bold text-white",
                                            children: agent.metrics.tasksCompleted
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 175,
                                            columnNumber: 15
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-xs text-white/40",
                                            children: "Completed"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 176,
                                            columnNumber: 15
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 174,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Card"], {
                                    className: "bg-white/5 border-white/10 p-2 text-center",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-lg font-bold text-white",
                                            children: agent.metrics.itemsProduced
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 179,
                                            columnNumber: 15
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "text-xs text-white/40",
                                            children: "Produced"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 180,
                                            columnNumber: 15
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 178,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 173,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                    lineNumber: 76,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                lineNumber: 75,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
        lineNumber: 41,
        columnNumber: 5
    }, this);
}
_c = AgentCard;
function MissionControlPage() {
    _s();
    const { agents, getAgentActivities } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useAgentStore"])();
    const [agentActivities, setAgentActivities] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])({});
    // Load activities for all agents
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "MissionControlPage.useEffect": ()=>{
            const activities = {};
            agents.forEach({
                "MissionControlPage.useEffect": (agent)=>{
                    activities[agent.id] = getAgentActivities(agent.id);
                }
            }["MissionControlPage.useEffect"]);
            setAgentActivities(activities);
        }
    }["MissionControlPage.useEffect"], [
        agents,
        getAgentActivities
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
        className: "min-h-screen bg-gradient-to-br from-black via-gray-950 to-black",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "sticky top-0 z-50 bg-black/80 backdrop-blur-xl border-b border-white/10",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "max-w-[1800px] mx-auto px-6 py-4",
                    children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center justify-between",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "flex items-center gap-4",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Button"], {
                                        variant: "ghost",
                                        size: "icon",
                                        onClick: ()=>window.location.href = '/',
                                        className: "text-white/70 hover:text-white hover:bg-white/10",
                                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$arrow$2d$left$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$export__default__as__ArrowLeft$3e$__["ArrowLeft"], {
                                            className: "w-5 h-5"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 215,
                                            columnNumber: 17
                                        }, this)
                                    }, void 0, false, {
                                        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                        lineNumber: 209,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                                className: "text-2xl font-bold text-white tracking-tight",
                                                children: "Mission Control"
                                            }, void 0, false, {
                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                lineNumber: 218,
                                                columnNumber: 17
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                className: "text-sm text-white/60",
                                                children: [
                                                    "Real-time Agent Operations • ",
                                                    agents.length,
                                                    " Active Agents"
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                                lineNumber: 221,
                                                columnNumber: 17
                                            }, this)
                                        ]
                                    }, void 0, true, {
                                        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                        lineNumber: 217,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                lineNumber: 208,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "flex items-center gap-2",
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Badge"], {
                                    variant: "outline",
                                    className: "text-white/70 border-white/20",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                            lineNumber: 228,
                                            columnNumber: 17
                                        }, this),
                                        "Live"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                    lineNumber: 227,
                                    columnNumber: 15
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                lineNumber: 226,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                        lineNumber: 207,
                        columnNumber: 11
                    }, this)
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                    lineNumber: 206,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                lineNumber: 205,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "max-w-[1800px] mx-auto p-6",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                    children: agents.map((agent)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "h-[500px]",
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(AgentCard, {
                                agent: agent,
                                activities: agentActivities[agent.id] || []
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                                lineNumber: 241,
                                columnNumber: 15
                            }, this)
                        }, agent.id, false, {
                            fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                            lineNumber: 240,
                            columnNumber: 13
                        }, this))
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                    lineNumber: 238,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
                lineNumber: 237,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/mission-control/page.tsx",
        lineNumber: 203,
        columnNumber: 5
    }, this);
}
_s(MissionControlPage, "C/MmIMwAFGfzuHW4B1qk8nQALh4=", false, function() {
    return [
        __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useAgentStore"]
    ];
});
_c1 = MissionControlPage;
var _c, _c1;
__turbopack_context__.k.register(_c, "AgentCard");
__turbopack_context__.k.register(_c1, "MissionControlPage");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
]);

//# sourceMappingURL=molt_steppe-visualization_4175a878._.js.map