module.exports = [
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[project]/molt/steppe-visualization/app/components/scene/EmpireTerrain.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "EmpireTerrain",
    ()=>EmpireTerrain
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/three/build/three.core.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$simplex$2d$noise$2f$dist$2f$esm$2f$simplex$2d$noise$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/simplex-noise/dist/esm/simplex-noise.js [app-ssr] (ecmascript)");
'use client';
;
;
;
;
// Mongol Empire approximate boundaries at its height (1279)
// These are simplified polygon points to create the empire shape
const EMPIRE_BOUNDS = {
    minLat: 22,
    maxLat: 55,
    minLng: 22,
    maxLng: 135
};
// Key points defining the Mongol Empire's rough outline
// Format: [longitude, latitude]
const EMPIRE_OUTLINE = [
    // Eastern border - Pacific/Korea
    [
        135,
        42
    ],
    [
        133,
        38
    ],
    [
        130,
        35
    ],
    [
        128,
        32
    ],
    [
        125,
        28
    ],
    [
        122,
        25
    ],
    [
        120,
        22
    ],
    // Southern border - Southeast Asia/China
    [
        118,
        22
    ],
    [
        115,
        24
    ],
    [
        112,
        22
    ],
    [
        108,
        20
    ],
    [
        105,
        22
    ],
    [
        100,
        25
    ],
    [
        95,
        22
    ],
    // Southwest - Tibet/Himalayas (avoided)
    [
        90,
        25
    ],
    [
        85,
        28
    ],
    [
        80,
        30
    ],
    [
        75,
        32
    ],
    // Western border - Central Asia/Persia
    [
        70,
        35
    ],
    [
        65,
        37
    ],
    [
        60,
        38
    ],
    [
        55,
        40
    ],
    [
        50,
        42
    ],
    [
        45,
        45
    ],
    [
        40,
        47
    ],
    // Northwest - Russia
    [
        35,
        50
    ],
    [
        30,
        52
    ],
    [
        25,
        54
    ],
    [
        22,
        55
    ],
    // Northern border - Siberia
    [
        30,
        55
    ],
    [
        40,
        54
    ],
    [
        50,
        53
    ],
    [
        60,
        52
    ],
    [
        70,
        51
    ],
    [
        80,
        50
    ],
    [
        90,
        49
    ],
    [
        100,
        50
    ],
    [
        110,
        51
    ],
    [
        120,
        52
    ],
    [
        130,
        53
    ],
    [
        135,
        52
    ]
];
function EmpireTerrain({ segments = 150 }) {
    const meshRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const [mounted, setMounted] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        setMounted(true);
    }, []);
    // Convert lat/lng to world coordinates
    const latLngToWorld = (lat, lng)=>{
        const x = (lng - EMPIRE_BOUNDS.minLng) / (EMPIRE_BOUNDS.maxLng - EMPIRE_BOUNDS.minLng) * 120 - 60;
        const z = (lat - EMPIRE_BOUNDS.minLat) / (EMPIRE_BOUNDS.maxLat - EMPIRE_BOUNDS.minLat) * -70 + 35;
        return {
            x,
            z
        };
    };
    // Check if a point is inside the empire using ray casting algorithm
    const isPointInEmpire = (lat, lng)=>{
        // Simple bounding box check first
        if (lat < EMPIRE_BOUNDS.minLat || lat > EMPIRE_BOUNDS.maxLat || lng < EMPIRE_BOUNDS.minLng || lng > EMPIRE_BOUNDS.maxLng) {
            return false;
        }
        // Ray casting algorithm
        let inside = false;
        for(let i = 0, j = EMPIRE_OUTLINE.length - 1; i < EMPIRE_OUTLINE.length; j = i++){
            const [lngi, lati] = EMPIRE_OUTLINE[i];
            const [lngj, latj] = EMPIRE_OUTLINE[j];
            if (lati > lat !== latj > lat && lng < (lngj - lngi) * (lat - lati) / (latj - lati) + lngi) {
                inside = !inside;
            }
        }
        return inside;
    };
    const geometry = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        if (!mounted) return null;
        const noise2D = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$simplex$2d$noise$2f$dist$2f$esm$2f$simplex$2d$noise$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["createNoise2D"])();
        const positions = [];
        const indices = [];
        const colors = [];
        const uvs = [];
        const width = 120;
        const depth = 70;
        // Generate grid
        for(let z = 0; z <= segments; z++){
            for(let x = 0; x <= segments; x++){
                const xPos = x / segments * width - width / 2;
                const zPos = z / segments * depth - depth / 2;
                // Convert to lat/lng
                const lng = (xPos + 60) / 120 * (EMPIRE_BOUNDS.maxLng - EMPIRE_BOUNDS.minLng) + EMPIRE_BOUNDS.minLng;
                const lat = (zPos - 35) / -70 * (EMPIRE_BOUNDS.maxLat - EMPIRE_BOUNDS.minLat) + EMPIRE_BOUNDS.minLat;
                // Check if inside empire
                const inEmpire = isPointInEmpire(lat, lng);
                // Height based on terrain features
                let height = 0;
                if (inEmpire) {
                    // Subtle terrain variation within empire
                    height = noise2D(xPos * 0.03, zPos * 0.03) * 0.2;
                    height += noise2D(xPos * 0.08, zPos * 0.08) * 0.1;
                    // Gobi Desert - slight depression
                    const gobiDist = Math.sqrt(Math.pow(lng - 105, 2) + Math.pow(lat - 42, 2));
                    if (gobiDist < 15) {
                        height -= 0.1;
                    }
                    // Mongolian heartland - slight elevation
                    const heartlandDist = Math.sqrt(Math.pow(lng - 100, 2) + Math.pow(lat - 47, 2));
                    if (heartlandDist < 10) {
                        height += 0.15;
                    }
                } else {
                    // Outside empire - deep drop-off
                    height = -2;
                }
                positions.push(xPos, height, zPos);
                uvs.push(x / segments, z / segments);
                // Color based on region
                let r = 0.35, g = 0.45, b = 0.28; // Default steppe green
                if (!inEmpire) {
                    // Outside empire - darker
                    r = 0.15;
                    g = 0.2;
                    b = 0.15;
                } else {
                    // Gobi Desert - sandy
                    const gobiDist = Math.sqrt(Math.pow(lng - 105, 2) + Math.pow(lat - 42, 2));
                    if (gobiDist < 12) {
                        r = 0.65;
                        g = 0.55;
                        b = 0.35;
                    }
                    // Northern forests - darker green
                    if (lat > 50) {
                        r = 0.25;
                        g = 0.4;
                        b = 0.25;
                    }
                    // Southern China - lighter green
                    if (lat < 35) {
                        r = 0.4;
                        g = 0.5;
                        b = 0.3;
                    }
                }
                colors.push(r, g, b);
            }
        }
        // Generate indices
        for(let z = 0; z < segments; z++){
            for(let x = 0; x < segments; x++){
                const a = z * (segments + 1) + x;
                const b = a + 1;
                const c = (z + 1) * (segments + 1) + x;
                const d = c + 1;
                indices.push(a, c, b);
                indices.push(b, c, d);
            }
        }
        const geo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["BufferGeometry"]();
        geo.setAttribute('position', new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Float32BufferAttribute"](positions, 3));
        geo.setAttribute('color', new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Float32BufferAttribute"](colors, 3));
        geo.setAttribute('uv', new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Float32BufferAttribute"](uvs, 2));
        geo.setIndex(indices);
        geo.computeVertexNormals();
        return geo;
    }, [
        segments,
        mounted
    ]);
    if (!mounted || !geometry) {
        return null;
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
        ref: meshRef,
        geometry: geometry,
        receiveShadow: true,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
            vertexColors: true,
            roughness: 0.9,
            metalness: 0.05,
            flatShading: true
        }, void 0, false, {
            fileName: "[project]/molt/steppe-visualization/app/components/scene/EmpireTerrain.tsx",
            lineNumber: 184,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/scene/EmpireTerrain.tsx",
        lineNumber: 183,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/scene/Rivers.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Rivers",
    ()=>Rivers
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/three/build/three.core.js [app-ssr] (ecmascript)");
'use client';
;
;
;
// Major rivers in the Mongol Empire
const RIVERS = [
    {
        name: 'Volga',
        points: [
            {
                lat: 48.5,
                lng: 45.0
            },
            {
                lat: 48.0,
                lng: 44.5
            },
            {
                lat: 47.0,
                lng: 44.0
            },
            {
                lat: 46.0,
                lng: 44.5
            },
            {
                lat: 45.0,
                lng: 45.0
            }
        ]
    },
    {
        name: 'Orkhon',
        points: [
            {
                lat: 47.5,
                lng: 102.0
            },
            {
                lat: 47.2,
                lng: 102.5
            },
            {
                lat: 47.0,
                lng: 103.0
            },
            {
                lat: 46.5,
                lng: 104.0
            }
        ]
    },
    {
        name: 'Ili',
        points: [
            {
                lat: 45.0,
                lng: 76.0
            },
            {
                lat: 44.5,
                lng: 77.0
            },
            {
                lat: 44.0,
                lng: 78.5
            },
            {
                lat: 43.5,
                lng: 80.0
            }
        ]
    }
];
function latLngToWorld(lat, lng) {
    const x = (lng - 20) / 110 * 100 - 50;
    const z = (lat - 35) / 20 * -50 + 25;
    return {
        x,
        z
    };
}
function Rivers() {
    const riverGeometries = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        return RIVERS.map((river)=>{
            const points = river.points.map((p)=>{
                const { x, z } = latLngToWorld(p.lat, p.lng);
                return new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](x, 0.2, z);
            });
            const curve = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["CatmullRomCurve3"](points);
            const geometry = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["TubeGeometry"](curve, 32, 0.3, 8, false);
            return {
                name: river.name,
                geometry
            };
        });
    }, []);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
        children: riverGeometries.map((river)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                geometry: river.geometry,
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                    color: "#1e3a5f",
                    transparent: true,
                    opacity: 0.7,
                    roughness: 0.2,
                    metalness: 0.8
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/Rivers.tsx",
                    lineNumber: 63,
                    columnNumber: 11
                }, this)
            }, river.name, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/scene/Rivers.tsx",
                lineNumber: 62,
                columnNumber: 9
            }, this))
    }, void 0, false);
}
}),
"[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "SkyEnvironment",
    ()=>SkyEnvironment
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$Sky$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/drei/core/Sky.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$Stars$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/drei/core/Stars.js [app-ssr] (ecmascript)");
'use client';
;
;
function SkyEnvironment() {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Fragment"], {
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$Sky$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Sky"], {
                distance: 450000,
                sunPosition: [
                    100,
                    20,
                    100
                ],
                inclination: 0.49,
                azimuth: 0.25,
                mieCoefficient: 0.005,
                mieDirectionalG: 0.8,
                rayleigh: 0.5,
                turbidity: 8
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx",
                lineNumber: 8,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$Stars$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Stars"], {
                radius: 100,
                depth: 50,
                count: 5000,
                factor: 4,
                saturation: 0,
                fade: true,
                speed: 1
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx",
                lineNumber: 18,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("ambientLight", {
                intensity: 0.4
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx",
                lineNumber: 19,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("directionalLight", {
                position: [
                    100,
                    50,
                    100
                ],
                intensity: 1.2,
                castShadow: true,
                "shadow-mapSize": [
                    2048,
                    2048
                ],
                "shadow-camera-left": -50,
                "shadow-camera-right": 50,
                "shadow-camera-top": 50,
                "shadow-camera-bottom": -50
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx",
                lineNumber: 20,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentMesh",
    ()=>AgentMesh
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/three/build/three.core.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/events-5a94e5eb.esm.js [app-ssr] (ecmascript) <export D as useFrame>");
'use client';
;
;
;
;
function AgentMesh({ agent, isSelected, isHovered }) {
    const groupRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const glowRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    // Procedural agent geometry - stylized human figure
    const { bodyGeometry, headGeometry, crownGeometry } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        // Body - cylinder
        const bodyGeo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["CylinderGeometry"](0.3, 0.4, 1.2, 8);
        bodyGeo.translate(0, 0.6, 0);
        // Head - sphere
        const headGeo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["SphereGeometry"](0.35, 16, 16);
        headGeo.translate(0, 1.5, 0);
        // Crown/helmet - torus or cone depending on role
        let crownGeo;
        if (agent.role === 'coordinator') {
            // Crown for Kublai
            crownGeo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ConeGeometry"](0.4, 0.3, 8);
            crownGeo.translate(0, 1.85, 0);
        } else if (agent.role === 'developer') {
            // Helmet for Temujin
            crownGeo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["SphereGeometry"](0.38, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2);
            crownGeo.translate(0, 1.5, 0);
        } else {
            // Simple cap for others
            crownGeo = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["CylinderGeometry"](0.25, 0.3, 0.2, 8);
            crownGeo.translate(0, 1.8, 0);
        }
        return {
            bodyGeometry: bodyGeo,
            headGeometry: headGeo,
            crownGeometry: crownGeo
        };
    }, [
        agent.role
    ]);
    // Animation - gentle breathing/floating
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__["useFrame"])((state)=>{
        if (groupRef.current) {
            const time = state.clock.getElapsedTime();
            // Breathing animation
            groupRef.current.position.y = agent.position.elevation + Math.sin(time * 2) * 0.05;
            // Working animation - faster movement when working
            if (agent.status === 'working') {
                groupRef.current.rotation.y = Math.sin(time * 3) * 0.1;
            }
        }
        if (glowRef.current) {
            const time = state.clock.getElapsedTime();
            const baseIntensity = agent.status === 'working' ? 2 : 1;
            const pulseSpeed = agent.status === 'alert' ? 8 : 2;
            const material = glowRef.current.material;
            material.opacity = (0.3 + Math.sin(time * pulseSpeed) * 0.2) * baseIntensity;
        }
    });
    const glowColor = agent.theme.glow;
    const scale = isSelected ? 1.3 : isHovered ? 1.15 : 1;
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        ref: groupRef,
        position: [
            agent.position.x,
            agent.position.elevation,
            agent.position.z
        ],
        scale: [
            scale,
            scale,
            scale
        ],
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                ref: glowRef,
                position: [
                    0,
                    1,
                    0
                ],
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("sphereGeometry", {
                        args: [
                            1.2,
                            16,
                            16
                        ]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                        lineNumber: 80,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshBasicMaterial", {
                        color: glowColor,
                        transparent: true,
                        opacity: 0.3
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                        lineNumber: 81,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                lineNumber: 79,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                geometry: bodyGeometry,
                castShadow: true,
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                    color: agent.theme.primary,
                    roughness: 0.7,
                    metalness: 0.3
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                    lineNumber: 86,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                lineNumber: 85,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                geometry: headGeometry,
                castShadow: true,
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                    color: agent.theme.secondary,
                    roughness: 0.5,
                    metalness: 0.2
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                    lineNumber: 95,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                lineNumber: 94,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                geometry: crownGeometry,
                castShadow: true,
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                    color: agent.theme.glow,
                    roughness: 0.3,
                    metalness: 0.8,
                    emissive: agent.theme.glow,
                    emissiveIntensity: 0.3
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                    lineNumber: 104,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                lineNumber: 103,
                columnNumber: 7
            }, this),
            isSelected && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                position: [
                    0,
                    0.1,
                    0
                ],
                rotation: [
                    -Math.PI / 2,
                    0,
                    0
                ],
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("ringGeometry", {
                        args: [
                            1,
                            1.3,
                            32
                        ]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                        lineNumber: 116,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshBasicMaterial", {
                        color: agent.theme.glow,
                        transparent: true,
                        opacity: 0.8
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                        lineNumber: 117,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
                lineNumber: 115,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx",
        lineNumber: 73,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentCamp",
    ()=>AgentCamp
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
'use client';
;
;
function AgentCamp({ agent }) {
    const campElements = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        const elements = [];
        const { x, z, elevation } = agent.position;
        // Base platform
        elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
            position: [
                x,
                elevation - 0.1,
                z
            ],
            receiveShadow: true,
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("cylinderGeometry", {
                    args: [
                        2.5,
                        2.5,
                        0.2,
                        16
                    ]
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 19,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                    color: "#5c4a3d",
                    roughness: 0.9
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 20,
                    columnNumber: 9
                }, this)
            ]
        }, "platform", true, {
            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
            lineNumber: 18,
            columnNumber: 7
        }, this));
        // Camp-specific elements based on type
        switch(agent.camp.type){
            case 'forge':
                // Temujin's forge
                elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1,
                        elevation + 0.3,
                        z + 1
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.4,
                                0.6,
                                0.3
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 30,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#2a2a2a",
                            roughness: 0.5,
                            metalness: 0.8
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 31,
                            columnNumber: 13
                        }, this)
                    ]
                }, "anvil", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 29,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1.5,
                        elevation + 1.5,
                        z - 1
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("cylinderGeometry", {
                            args: [
                                0.05,
                                0.05,
                                3,
                                8
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 34,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#8b4513"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 35,
                            columnNumber: 13
                        }, this)
                    ]
                }, "banner", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 33,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1.5,
                        elevation + 2.5,
                        z - 1
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.8,
                                0.5,
                                0.05
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 38,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: agent.theme.glow
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 39,
                            columnNumber: 13
                        }, this)
                    ]
                }, "flag", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 37,
                    columnNumber: 11
                }, this));
                break;
            case 'caravanserai':
                // Trading post for Ogedei/Chagatai
                elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1.2,
                        elevation + 0.8,
                        z
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("coneGeometry", {
                            args: [
                                1,
                                1.6,
                                8
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 48,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#d4a574",
                            roughness: 0.8
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 49,
                            columnNumber: 13
                        }, this)
                    ]
                }, "tent", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 47,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1,
                        elevation + 0.2,
                        z + 1
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.5,
                                0.4,
                                0.5
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 52,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#8b4513"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 53,
                            columnNumber: 13
                        }, this)
                    ]
                }, "crate1", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 51,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 0.8,
                        elevation + 0.25,
                        z + 1.3
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.4,
                                0.5,
                                0.4
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 56,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#a0522d"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 57,
                            columnNumber: 13
                        }, this)
                    ]
                }, "crate2", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 55,
                    columnNumber: 11
                }, this));
                break;
            case 'observatory':
                // Scholarly retreat for Mongke
                elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1,
                        elevation + 0.3,
                        z + 0.5
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                1,
                                0.6,
                                0.6
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 66,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#654321"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 67,
                            columnNumber: 13
                        }, this)
                    ]
                }, "table", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 65,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1,
                        elevation + 0.65,
                        z + 0.5
                    ],
                    rotation: [
                        Math.PI / 2,
                        0,
                        0
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("cylinderGeometry", {
                            args: [
                                0.1,
                                0.1,
                                0.4,
                                8
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 70,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#f5f5dc"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 71,
                            columnNumber: 13
                        }, this)
                    ]
                }, "scroll", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 69,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1,
                        elevation + 0.8,
                        z - 0.5
                    ],
                    rotation: [
                        Math.PI / 4,
                        0,
                        Math.PI / 6
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("cylinderGeometry", {
                            args: [
                                0.08,
                                0.1,
                                1.2,
                                8
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 74,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#4a4a4a",
                            metalness: 0.6
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 75,
                            columnNumber: 13
                        }, this)
                    ]
                }, "telescope", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 73,
                    columnNumber: 11
                }, this));
                break;
            case 'palace':
                // Imperial palace for Kublai
                elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 0.8,
                        elevation + 0.5,
                        z
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.8,
                                1,
                                0.6
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 84,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: agent.theme.secondary,
                            metalness: 0.4
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 85,
                            columnNumber: 13
                        }, this)
                    ]
                }, "throne", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 83,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 0.8,
                        elevation + 1.3,
                        z
                    ],
                    rotation: [
                        0,
                        Math.PI / 4,
                        0
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("coneGeometry", {
                            args: [
                                1.2,
                                0.6,
                                4
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 88,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: agent.theme.primary
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 89,
                            columnNumber: 13
                        }, this)
                    ]
                }, "canopy", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 87,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1.2,
                        elevation + 1.2,
                        z + 1
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("cylinderGeometry", {
                            args: [
                                0.03,
                                0.03,
                                2.4,
                                6
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 92,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: agent.theme.glow
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 93,
                            columnNumber: 13
                        }, this)
                    ]
                }, "banner1", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 91,
                    columnNumber: 11
                }, this));
                break;
            case 'counting-house':
                // Administrative center for Jochi
                elements.push(/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1,
                        elevation + 0.35,
                        z
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                1.2,
                                0.7,
                                0.6
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 102,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#5c4033"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 103,
                            columnNumber: 13
                        }, this)
                    ]
                }, "desk", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 101,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x + 1,
                        elevation + 0.75,
                        z
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.4,
                                0.2,
                                0.3
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 106,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#8b4513"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 107,
                            columnNumber: 13
                        }, this)
                    ]
                }, "abacus", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 105,
                    columnNumber: 11
                }, this), /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                    position: [
                        x - 1,
                        elevation + 0.3,
                        z + 0.8
                    ],
                    castShadow: true,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("boxGeometry", {
                            args: [
                                0.6,
                                0.4,
                                0.4
                            ]
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 110,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                            color: "#ffd700",
                            metalness: 0.5
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                            lineNumber: 111,
                            columnNumber: 13
                        }, this)
                    ]
                }, "chest", true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
                    lineNumber: 109,
                    columnNumber: 11
                }, this));
                break;
        }
        return elements;
    }, [
        agent
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        children: campElements
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx",
        lineNumber: 120,
        columnNumber: 10
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "StatusIndicator",
    ()=>StatusIndicator
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/three/build/three.core.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/events-5a94e5eb.esm.js [app-ssr] (ecmascript) <export D as useFrame>");
'use client';
;
;
;
;
const STATUS_COLORS = {
    idle: '#22c55e',
    working: '#3b82f6',
    reviewing: '#f59e0b',
    alert: '#ef4444',
    offline: '#6b7280'
};
function StatusIndicator({ status, position }) {
    const indicatorRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    const ringRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__["useFrame"])((state)=>{
        const time = state.clock.getElapsedTime();
        if (indicatorRef.current) {
            // Floating animation
            indicatorRef.current.position.y = position.y + 2.5 + Math.sin(time * 3) * 0.1;
            // Pulse effect for working/alert
            if (status === 'working' || status === 'alert') {
                const pulseSpeed = status === 'alert' ? 10 : 4;
                const scale = 1 + Math.sin(time * pulseSpeed) * 0.15;
                indicatorRef.current.scale.set(scale, scale, scale);
            }
        }
        if (ringRef.current) {
            ringRef.current.rotation.z = time * 0.5;
            ringRef.current.rotation.x = Math.sin(time * 0.5) * 0.2;
        }
    });
    const color = STATUS_COLORS[status];
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        position: [
            position.x,
            position.y,
            position.z
        ],
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                ref: indicatorRef,
                position: [
                    0,
                    2.5,
                    0
                ],
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("sphereGeometry", {
                        args: [
                            0.25,
                            16,
                            16
                        ]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 52,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshStandardMaterial", {
                        color: color,
                        emissive: color,
                        emissiveIntensity: 0.5
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 53,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                lineNumber: 51,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                ref: ringRef,
                position: [
                    0,
                    2.5,
                    0
                ],
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("ringGeometry", {
                        args: [
                            0.4,
                            0.45,
                            16
                        ]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 62,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshBasicMaterial", {
                        color: color,
                        transparent: true,
                        opacity: 0.6,
                        side: __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["DoubleSide"]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 63,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                lineNumber: 61,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("mesh", {
                position: [
                    0,
                    2.5,
                    0
                ],
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("planeGeometry", {
                        args: [
                            1.2,
                            0.4
                        ]
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 68,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("meshBasicMaterial", {
                        color: "rgba(0,0,0,0.7)",
                        transparent: true
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                        lineNumber: 69,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
                lineNumber: 67,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx",
        lineNumber: 49,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentTaskLabel",
    ()=>AgentTaskLabel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/events-5a94e5eb.esm.js [app-ssr] (ecmascript) <export D as useFrame>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$web$2f$Html$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/drei/web/Html.js [app-ssr] (ecmascript)");
'use client';
;
;
;
;
const STATUS_COLORS = {
    idle: '#22c55e',
    working: '#3b82f6',
    reviewing: '#f59e0b',
    alert: '#ef4444',
    offline: '#6b7280'
};
function AgentTaskLabel({ agent }) {
    const groupRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    // Animation - float above agent
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__["useFrame"])((state)=>{
        if (groupRef.current) {
            const time = state.clock.getElapsedTime();
            groupRef.current.position.y = agent.position.elevation + 3.5 + Math.sin(time * 2) * 0.1;
        }
    });
    const statusColor = STATUS_COLORS[agent.status];
    const queueCount = agent.queue?.length || 0;
    const hasTask = !!agent.currentTask;
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        ref: groupRef,
        position: [
            agent.position.x,
            agent.position.elevation + 3.5,
            agent.position.z
        ],
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$web$2f$Html$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Html"], {
            center: true,
            distanceFactor: 12,
            style: {
                pointerEvents: 'none',
                userSelect: 'none'
            },
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex flex-col items-center gap-2",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "px-3 py-1 rounded-full text-sm font-bold uppercase tracking-wider text-white shadow-lg",
                        style: {
                            backgroundColor: statusColor,
                            boxShadow: `0 0 15px ${statusColor}`
                        },
                        children: agent.status
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                        lineNumber: 51,
                        columnNumber: 11
                    }, this),
                    hasTask && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "bg-black/80 backdrop-blur-sm rounded-lg px-4 py-3 text-center min-w-[220px] border border-white/20",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "text-white text-base font-medium truncate",
                                children: agent.currentTask?.title
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 64,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "text-white/60 text-sm mt-1",
                                children: [
                                    agent.currentTask?.progress,
                                    "%"
                                ]
                            }, void 0, true, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 67,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "w-full h-2 bg-white/20 rounded-full mt-2 overflow-hidden",
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "h-full rounded-full transition-all duration-300",
                                    style: {
                                        width: `${agent.currentTask?.progress}%`,
                                        backgroundColor: agent.theme.glow
                                    }
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                    lineNumber: 72,
                                    columnNumber: 17
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 71,
                                columnNumber: 15
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                        lineNumber: 63,
                        columnNumber: 13
                    }, this),
                    queueCount > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-2 bg-black/60 backdrop-blur-sm rounded-full px-3 py-1.5 border border-white/10",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-white/80 text-sm",
                                children: "Queue:"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 86,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-base font-bold",
                                style: {
                                    color: agent.theme.glow
                                },
                                children: queueCount
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 87,
                                columnNumber: 15
                            }, this),
                            agent.queue?.slice(0, 3).map((task, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "w-2 h-2 rounded-full",
                                    style: {
                                        backgroundColor: task.priority === 'high' ? '#ef4444' : task.priority === 'medium' ? '#f59e0b' : '#22c55e'
                                    },
                                    title: task.title
                                }, task.id, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                    lineNumber: 94,
                                    columnNumber: 17
                                }, this)),
                            queueCount > 3 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-white/50 text-xs",
                                children: [
                                    "+",
                                    queueCount - 3
                                ]
                            }, void 0, true, {
                                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                                lineNumber: 109,
                                columnNumber: 17
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                        lineNumber: 85,
                        columnNumber: 13
                    }, this),
                    !hasTask && queueCount === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "bg-black/60 backdrop-blur-sm rounded-full px-4 py-2 text-white/50 text-base",
                        children: "Awaiting orders"
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                        lineNumber: 116,
                        columnNumber: 13
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "mt-1 px-3 py-1 rounded text-base font-semibold text-white/90 bg-black/40 backdrop-blur-sm border border-white/10 whitespace-nowrap",
                        style: {
                            textShadow: '0 2px 4px rgba(0,0,0,0.8)'
                        },
                        children: agent.displayName
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                        lineNumber: 122,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
                lineNumber: 49,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
            lineNumber: 41,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx",
        lineNumber: 37,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/Agent.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Agent",
    ()=>Agent
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentMesh$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/AgentMesh.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentCamp$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/AgentCamp.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$StatusIndicator$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/StatusIndicator.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentTaskLabel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/AgentTaskLabel.tsx [app-ssr] (ecmascript)");
'use client';
;
;
;
;
;
;
function Agent({ agent, isSelected, onSelect }) {
    const [isHovered, setIsHovered] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        onClick: (e)=>{
            e.stopPropagation();
            onSelect(agent);
        },
        onPointerOver: (e)=>{
            e.stopPropagation();
            setIsHovered(true);
            document.body.style.cursor = 'pointer';
        },
        onPointerOut: ()=>{
            setIsHovered(false);
            document.body.style.cursor = 'auto';
        },
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentCamp$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentCamp"], {
                agent: agent
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/Agent.tsx",
                lineNumber: 36,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentMesh$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentMesh"], {
                agent: agent,
                isSelected: isSelected,
                isHovered: isHovered
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/Agent.tsx",
                lineNumber: 39,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$StatusIndicator$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["StatusIndicator"], {
                status: agent.status,
                position: {
                    x: agent.position.x,
                    y: agent.position.elevation,
                    z: agent.position.z
                }
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/Agent.tsx",
                lineNumber: 46,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentTaskLabel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentTaskLabel"], {
                agent: agent
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/Agent.tsx",
                lineNumber: 56,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/Agent.tsx",
        lineNumber: 20,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/agents/AgentsLayer.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentsLayer",
    ()=>AgentsLayer
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$Agent$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/Agent.tsx [app-ssr] (ecmascript)");
'use client';
;
;
;
function AgentsLayer({ agents, selectedAgentId, onSelectAgent }) {
    // Sort agents by z-position for proper rendering order
    const sortedAgents = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        return [
            ...agents
        ].sort((a, b)=>a.position.z - b.position.z);
    }, [
        agents
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("group", {
        children: sortedAgents.map((agent)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$Agent$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Agent"], {
                agent: agent,
                isSelected: selectedAgentId === agent.id,
                onSelect: onSelectAgent
            }, agent.id, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentsLayer.tsx",
                lineNumber: 22,
                columnNumber: 9
            }, this))
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/agents/AgentsLayer.tsx",
        lineNumber: 20,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/lib/agents.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
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
}),
"[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "useAgentStore",
    ()=>useAgentStore
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$zustand$2f$esm$2f$react$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/zustand/esm/react.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$lib$2f$agents$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/lib/agents.ts [app-ssr] (ecmascript)");
'use client';
;
;
const useAgentStore = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$zustand$2f$esm$2f$react$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["create"])((set, get)=>({
        // Initial data
        agents: __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$lib$2f$agents$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AGENTS"],
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
}),
"[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "SteppeScene",
    ()=>SteppeScene
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$react$2d$three$2d$fiber$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/react-three-fiber.esm.js [app-ssr] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/events-5a94e5eb.esm.js [app-ssr] (ecmascript) <export D as useFrame>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__C__as__useThree$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/fiber/dist/events-5a94e5eb.esm.js [app-ssr] (ecmascript) <export C as useThree>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$OrbitControls$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/drei/core/OrbitControls.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$PerspectiveCamera$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@react-three/drei/core/PerspectiveCamera.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$EmpireTerrain$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/scene/EmpireTerrain.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$Rivers$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/scene/Rivers.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$SkyEnvironment$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/scene/SkyEnvironment.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentsLayer$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/agents/AgentsLayer.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/three/build/three.core.js [app-ssr] (ecmascript)");
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
;
// Touch and keyboard controls
function TouchAndKeyControls({ target, setTarget }) {
    const { camera, gl } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__C__as__useThree$3e$__["useThree"])();
    const keysPressed = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(new Set());
    const moveSpeed = 1.2;
    // Touch state
    const touchesRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])([]);
    const lastTouchDistanceRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(0);
    const lastTouchCenterRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])({
        x: 0,
        y: 0
    });
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        const canvas = gl.domElement;
        const handleKeyDown = (e)=>{
            keysPressed.current.add(e.key.toLowerCase());
        };
        const handleKeyUp = (e)=>{
            keysPressed.current.delete(e.key.toLowerCase());
        };
        // Touch event handlers
        const handleTouchStart = (e)=>{
            e.preventDefault();
            touchesRef.current = Array.from(e.touches);
            if (touchesRef.current.length === 2) {
                // Two finger touch - prepare for pan
                const touch1 = touchesRef.current[0];
                const touch2 = touchesRef.current[1];
                lastTouchDistanceRef.current = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY);
                lastTouchCenterRef.current = {
                    x: (touch1.clientX + touch2.clientX) / 2,
                    y: (touch1.clientY + touch2.clientY) / 2
                };
            }
        };
        const handleTouchMove = (e)=>{
            e.preventDefault();
            const touches = Array.from(e.touches);
            if (touches.length === 2 && touchesRef.current.length === 2) {
                // Two finger pan
                const touch1 = touches[0];
                const touch2 = touches[1];
                const centerX = (touch1.clientX + touch2.clientX) / 2;
                const centerY = (touch1.clientY + touch2.clientY) / 2;
                const deltaX = centerX - lastTouchCenterRef.current.x;
                const deltaY = centerY - lastTouchCenterRef.current.y;
                // Pan speed for touch
                const panSpeed = 0.5;
                const currentTarget = target || [
                    0,
                    0,
                    0
                ];
                // Calculate camera right and forward vectors
                const right = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](1, 0, 0).applyQuaternion(camera.quaternion);
                right.y = 0;
                right.normalize();
                const forward = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](0, 0, -1).applyQuaternion(camera.quaternion);
                forward.y = 0;
                forward.normalize();
                // Move camera and target (opposite direction of finger movement for natural feel)
                const moveX = -right.x * deltaX * panSpeed - forward.x * deltaY * panSpeed;
                const moveZ = -right.z * deltaX * panSpeed - forward.z * deltaY * panSpeed;
                camera.position.x += moveX;
                camera.position.z += moveZ;
                setTarget([
                    currentTarget[0] + moveX,
                    currentTarget[1],
                    currentTarget[2] + moveZ
                ]);
                // Update for next frame
                lastTouchCenterRef.current = {
                    x: centerX,
                    y: centerY
                };
                // Pinch zoom
                const distance = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY);
                const distanceDelta = lastTouchDistanceRef.current - distance;
                const zoomSpeed = 0.1;
                // Move camera along look direction for zoom
                const lookDirection = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"]().subVectors(new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](...target || [
                    0,
                    0,
                    0
                ]), camera.position).normalize();
                camera.position.addScaledVector(lookDirection, distanceDelta * zoomSpeed);
                lastTouchDistanceRef.current = distance;
            }
        };
        const handleTouchEnd = (e)=>{
            e.preventDefault();
            touchesRef.current = Array.from(e.touches);
        };
        window.addEventListener('keydown', handleKeyDown);
        window.addEventListener('keyup', handleKeyUp);
        canvas.addEventListener('touchstart', handleTouchStart, {
            passive: false
        });
        canvas.addEventListener('touchmove', handleTouchMove, {
            passive: false
        });
        canvas.addEventListener('touchend', handleTouchEnd, {
            passive: false
        });
        return ()=>{
            window.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('keyup', handleKeyUp);
            canvas.removeEventListener('touchstart', handleTouchStart);
            canvas.removeEventListener('touchmove', handleTouchMove);
            canvas.removeEventListener('touchend', handleTouchEnd);
        };
    }, [
        camera,
        gl,
        target,
        setTarget
    ]);
    // WASD keyboard movement - moves camera forward/back/left/right
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$events$2d$5a94e5eb$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__D__as__useFrame$3e$__["useFrame"])(()=>{
        const keys = keysPressed.current;
        if (keys.size === 0) return;
        const forward = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](0, 0, -1).applyQuaternion(camera.quaternion);
        forward.y = 0;
        forward.normalize();
        const right = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"](1, 0, 0).applyQuaternion(camera.quaternion);
        right.y = 0;
        right.normalize();
        const movement = new __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Vector3"]();
        if (keys.has('w') || keys.has('arrowup')) movement.add(forward);
        if (keys.has('s') || keys.has('arrowdown')) movement.sub(forward);
        if (keys.has('a') || keys.has('arrowleft')) movement.sub(right);
        if (keys.has('d') || keys.has('arrowright')) movement.add(right);
        if (movement.length() > 0) {
            movement.normalize().multiplyScalar(moveSpeed);
            // Move both camera and target together to maintain orbit relationship
            camera.position.x += movement.x;
            camera.position.z += movement.z;
            const currentTarget = target || [
                0,
                0,
                0
            ];
            setTarget([
                currentTarget[0] + movement.x,
                currentTarget[1],
                currentTarget[2] + movement.z
            ]);
        }
    });
    return null;
}
function SteppeScene() {
    const { agents, selectedAgentId, selectAgent } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useAgentStore"])();
    const [cameraTarget, setCameraTarget] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const handleSelectAgent = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])((agent)=>{
        selectAgent(agent.id);
        setCameraTarget([
            agent.position.x,
            agent.position.elevation + 5,
            agent.position.z
        ]);
    }, [
        selectAgent
    ]);
    const handleBackgroundClick = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(()=>{
        selectAgent(null);
        setCameraTarget(null);
    }, [
        selectAgent
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "w-full h-full",
        onClick: handleBackgroundClick,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$fiber$2f$dist$2f$react$2d$three$2d$fiber$2e$esm$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$locals$3e$__["Canvas"], {
            shadows: true,
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$PerspectiveCamera$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["PerspectiveCamera"], {
                    makeDefault: true,
                    position: [
                        0,
                        80,
                        20
                    ],
                    fov: 25,
                    near: 0.1,
                    far: 1000
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 193,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(TouchAndKeyControls, {
                    target: cameraTarget,
                    setTarget: setCameraTarget
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 201,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$react$2d$three$2f$drei$2f$core$2f$OrbitControls$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["OrbitControls"], {
                    enablePan: false,
                    enableZoom: false,
                    enableRotate: true,
                    minDistance: 30,
                    maxDistance: 120,
                    minPolarAngle: 0,
                    maxPolarAngle: Math.PI / 2.5,
                    target: cameraTarget || [
                        0,
                        0,
                        0
                    ],
                    mouseButtons: {
                        LEFT: __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["MOUSE"].ROTATE,
                        MIDDLE: undefined,
                        RIGHT: undefined
                    },
                    touches: {
                        ONE: __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$three$2f$build$2f$three$2e$core$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["TOUCH"].ROTATE // One finger = orbit/pivot
                    },
                    reverseOrbit: true,
                    reverseHorizontalOrbit: true
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 203,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$SkyEnvironment$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["SkyEnvironment"], {}, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 225,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$EmpireTerrain$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["EmpireTerrain"], {
                    segments: 150
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 228,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$Rivers$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Rivers"], {}, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 231,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$agents$2f$AgentsLayer$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentsLayer"], {
                    agents: agents,
                    selectedAgentId: selectedAgentId,
                    onSelectAgent: handleSelectAgent
                }, void 0, false, {
                    fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
                    lineNumber: 234,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
            lineNumber: 192,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx",
        lineNumber: 191,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "cn",
    ()=>cn
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/clsx/dist/clsx.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/tailwind-merge/dist/bundle-mjs.mjs [app-ssr] (ecmascript)");
;
;
function cn(...inputs) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["twMerge"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["clsx"])(inputs));
}
}),
"[project]/molt/steppe-visualization/components/ui/button.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Button",
    ()=>Button,
    "buttonVariants",
    ()=>buttonVariants
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/class-variance-authority/dist/index.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-slot/dist/index.mjs [app-ssr] (ecmascript) <export * as Slot>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
;
;
;
;
const buttonVariants = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cva"])("inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive", {
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
    const Comp = asChild ? __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__["Slot"].Root : "button";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(Comp, {
        "data-slot": "button",
        "data-variant": variant,
        "data-size": size,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])(buttonVariants({
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
;
}),
"[project]/molt/steppe-visualization/app/components/ui/Header.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Header",
    ()=>Header
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$map$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Map$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/map.js [app-ssr] (ecmascript) <export default as Map>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$settings$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Settings$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/settings.js [app-ssr] (ecmascript) <export default as Settings>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$question$2d$mark$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__HelpCircle$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/circle-question-mark.js [app-ssr] (ecmascript) <export default as HelpCircle>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$layout$2d$grid$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__LayoutGrid$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/layout-grid.js [app-ssr] (ecmascript) <export default as LayoutGrid>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/button.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/client/app-dir/link.js [app-ssr] (ecmascript)");
'use client';
;
;
;
;
function Header({ onToggleMap, onToggleSettings, onToggleHelp }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
        className: "fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 bg-gradient-to-b from-black/60 to-transparent",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex items-center gap-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "w-10 h-10 rounded-full bg-gradient-to-br from-amber-500 to-red-600 flex items-center justify-center shadow-lg shadow-amber-500/20",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$map$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Map$3e$__["Map"], {
                            className: "w-5 h-5 text-white"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                            lineNumber: 18,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 17,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                className: "text-xl font-bold text-white tracking-tight",
                                children: "Mongol Empire Command"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                                lineNumber: 21,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "text-sm text-white/60",
                                children: "AI Agent Visualization • 6 Khans • Real-time Activity"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                                lineNumber: 24,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 20,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                lineNumber: 16,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex items-center gap-2",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                        href: "/mission-control",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Button"], {
                            variant: "ghost",
                            size: "icon",
                            className: "text-white/70 hover:text-white hover:bg-white/10",
                            title: "Mission Control",
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$layout$2d$grid$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__LayoutGrid$3e$__["LayoutGrid"], {
                                className: "w-5 h-5"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                                lineNumber: 38,
                                columnNumber: 13
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                            lineNumber: 32,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 31,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Button"], {
                        variant: "ghost",
                        size: "icon",
                        onClick: onToggleMap,
                        className: "text-white/70 hover:text-white hover:bg-white/10",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$map$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Map$3e$__["Map"], {
                            className: "w-5 h-5"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                            lineNumber: 47,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 41,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Button"], {
                        variant: "ghost",
                        size: "icon",
                        onClick: onToggleSettings,
                        className: "text-white/70 hover:text-white hover:bg-white/10",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$settings$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Settings$3e$__["Settings"], {
                            className: "w-5 h-5"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                            lineNumber: 55,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 49,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Button"], {
                        variant: "ghost",
                        size: "icon",
                        onClick: onToggleHelp,
                        className: "text-white/70 hover:text-white hover:bg-white/10",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$question$2d$mark$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__HelpCircle$3e$__["HelpCircle"], {
                            className: "w-5 h-5"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                            lineNumber: 63,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                        lineNumber: 57,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
                lineNumber: 30,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/components/ui/Header.tsx",
        lineNumber: 15,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "MiniMap",
    ()=>MiniMap
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
'use client';
;
;
;
// Map bounds for conversion
const MAP_BOUNDS = {
    minLat: 35,
    maxLat: 55,
    minLng: 20,
    maxLng: 130
};
function latLngToMiniMap(lat, lng) {
    const x = (lng - MAP_BOUNDS.minLng) / (MAP_BOUNDS.maxLng - MAP_BOUNDS.minLng) * 100;
    const y = (lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat) * 100;
    return {
        x,
        y: 100 - y
    }; // Invert Y so north is up
}
function MiniMap({ agents, selectedAgentId, onSelectAgent }) {
    const agentPositions = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useMemo"])(()=>{
        return agents.map((agent)=>({
                ...agent,
                miniMapPos: latLngToMiniMap(agent.coordinates.lat, agent.coordinates.lng)
            }));
    }, [
        agents
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "fixed bottom-6 left-6 z-40 w-72 h-56 bg-black/80 backdrop-blur-sm rounded-xl border border-white/10 shadow-2xl overflow-hidden",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "absolute top-3 left-3 text-sm font-semibold text-white/80",
                children: "Empire Map"
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                lineNumber: 37,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "absolute inset-0 mt-8 mb-2 mx-2 rounded-lg bg-gradient-to-br from-[#4a6741] via-[#5c4a3d] to-[#8b7355]",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "absolute top-[20%] left-[10%] w-[15%] h-[20%] bg-[#6b5b4f] rounded-full opacity-50 blur-sm"
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                        lineNumber: 44,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "absolute top-[40%] left-[25%] w-[12%] h-[15%] bg-[#6b5b4f] rounded-full opacity-50 blur-sm"
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                        lineNumber: 45,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("svg", {
                        className: "absolute inset-0 w-full h-full",
                        viewBox: "0 0 100 100",
                        preserveAspectRatio: "none",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("path", {
                                d: "M 25 15 Q 23 25 25 35",
                                stroke: "#1e3a5f",
                                strokeWidth: "1.5",
                                fill: "none",
                                opacity: "0.6"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                                lineNumber: 50,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("path", {
                                d: "M 75 35 Q 73 40 76 45",
                                stroke: "#1e3a5f",
                                strokeWidth: "1.5",
                                fill: "none",
                                opacity: "0.6"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                                lineNumber: 52,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("path", {
                                d: "M 60 45 Q 62 50 64 52",
                                stroke: "#1e3a5f",
                                strokeWidth: "1.5",
                                fill: "none",
                                opacity: "0.6"
                            }, void 0, false, {
                                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                                lineNumber: 54,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                        lineNumber: 48,
                        columnNumber: 9
                    }, this),
                    agentPositions.map((agent)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: ()=>onSelectAgent(agent.id),
                            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("absolute w-4 h-4 -ml-2 -mt-2 rounded-full border-2 transition-all duration-200", selectedAgentId === agent.id ? "scale-150 border-white shadow-lg shadow-white/50" : "scale-100 border-white/50 hover:scale-125"),
                            style: {
                                left: `${agent.miniMapPos.x}%`,
                                top: `${agent.miniMapPos.y}%`,
                                backgroundColor: agent.theme.primary
                            },
                            title: `${agent.displayName} - ${agent.historicalCapital}`
                        }, agent.id, false, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                            lineNumber: 59,
                            columnNumber: 11
                        }, this))
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                lineNumber: 42,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "absolute bottom-2 right-2 flex flex-col gap-1 text-xs text-white/60",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "★ Capital"
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                        lineNumber: 80,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "═ River"
                    }, void 0, false, {
                        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                        lineNumber: 81,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
                lineNumber: 79,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx",
        lineNumber: 36,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/components/ui/card.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
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
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
;
;
function Card({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("bg-card text-card-foreground flex flex-col gap-6 rounded-xl border py-6 shadow-sm", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 7,
        columnNumber: 5
    }, this);
}
function CardHeader({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-header",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 20,
        columnNumber: 5
    }, this);
}
function CardTitle({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-title",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("leading-none font-semibold", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 33,
        columnNumber: 5
    }, this);
}
function CardDescription({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-description",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("text-muted-foreground text-sm", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 43,
        columnNumber: 5
    }, this);
}
function CardAction({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-action",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 53,
        columnNumber: 5
    }, this);
}
function CardContent({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-content",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("px-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 66,
        columnNumber: 5
    }, this);
}
function CardFooter({ className, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        "data-slot": "card-footer",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("flex items-center px-6 [.border-t]:pt-6", className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/card.tsx",
        lineNumber: 76,
        columnNumber: 5
    }, this);
}
;
}),
"[project]/molt/steppe-visualization/components/ui/badge.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Badge",
    ()=>Badge,
    "badgeVariants",
    ()=>badgeVariants
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/class-variance-authority/dist/index.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-slot/dist/index.mjs [app-ssr] (ecmascript) <export * as Slot>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
;
;
;
;
const badgeVariants = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$class$2d$variance$2d$authority$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cva"])("inline-flex items-center justify-center rounded-full border border-transparent px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive transition-[color,box-shadow] overflow-hidden", {
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
    const Comp = asChild ? __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$slot$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Slot$3e$__["Slot"].Root : "span";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(Comp, {
        "data-slot": "badge",
        "data-variant": variant,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])(badgeVariants({
            variant
        }), className),
        ...props
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/components/ui/badge.tsx",
        lineNumber: 39,
        columnNumber: 5
    }, this);
}
;
}),
"[project]/molt/steppe-visualization/components/ui/progress.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Progress",
    ()=>Progress
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-progress/dist/index.mjs [app-ssr] (ecmascript) <export * as Progress>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
function Progress({ className, value, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__["Progress"].Root, {
        "data-slot": "progress",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full", className),
        ...props,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$progress$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__Progress$3e$__["Progress"].Indicator, {
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
;
}),
"[project]/molt/steppe-visualization/components/ui/scroll-area.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ScrollArea",
    ()=>ScrollArea,
    "ScrollBar",
    ()=>ScrollBar
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/@radix-ui/react-scroll-area/dist/index.mjs [app-ssr] (ecmascript) <export * as ScrollArea>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
function ScrollArea({ className, children, ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Root, {
        "data-slot": "scroll-area",
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("relative", className),
        ...props,
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Viewport, {
                "data-slot": "scroll-area-viewport",
                className: "focus-visible:ring-ring/50 size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:outline-1",
                children: children
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
                lineNumber: 19,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(ScrollBar, {}, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/components/ui/scroll-area.tsx",
                lineNumber: 25,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].Corner, {}, void 0, false, {
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
function ScrollBar({ className, orientation = "vertical", ...props }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].ScrollAreaScrollbar, {
        "data-slot": "scroll-area-scrollbar",
        orientation: orientation,
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])("flex touch-none p-px transition-colors select-none", orientation === "vertical" && "h-full w-2.5 border-l border-l-transparent", orientation === "horizontal" && "h-2.5 flex-col border-t border-t-transparent", className),
        ...props,
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f40$radix$2d$ui$2f$react$2d$scroll$2d$area$2f$dist$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__$2a$__as__ScrollArea$3e$__["ScrollArea"].ScrollAreaThumb, {
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
;
}),
"[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentDetailPanel",
    ()=>AgentDetailPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$x$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__X$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/x.js [app-ssr] (ecmascript) <export default as X>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$clock$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Clock$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/clock.js [app-ssr] (ecmascript) <export default as Clock>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$file$2d$text$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__FileText$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/file-text.js [app-ssr] (ecmascript) <export default as FileText>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$map$2d$pin$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__MapPin$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/map-pin.js [app-ssr] (ecmascript) <export default as MapPin>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$crown$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Crown$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/crown.js [app-ssr] (ecmascript) <export default as Crown>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$list$2d$ordered$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__ListOrdered$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/list-ordered.js [app-ssr] (ecmascript) <export default as ListOrdered>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$alert$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__AlertCircle$3e$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/lucide-react/dist/esm/icons/circle-alert.js [app-ssr] (ecmascript) <export default as AlertCircle>");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$framer$2d$motion$2f$dist$2f$es$2f$render$2f$components$2f$motion$2f$proxy$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/framer-motion/dist/es/render/components/motion/proxy.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$framer$2d$motion$2f$dist$2f$es$2f$components$2f$AnimatePresence$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/framer-motion/dist/es/components/AnimatePresence/index.mjs [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/button.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/card.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/badge.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$progress$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/progress.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$scroll$2d$area$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/components/ui/scroll-area.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/lib/utils.ts [app-ssr] (ecmascript)");
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
function AgentDetailPanel({ agent, activities, isOpen, onClose }) {
    if (!agent) return null;
    const status = STATUS_CONFIG[agent.status];
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$framer$2d$motion$2f$dist$2f$es$2f$components$2f$AnimatePresence$2f$index$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AnimatePresence"], {
        children: isOpen && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$framer$2d$motion$2f$dist$2f$es$2f$render$2f$components$2f$motion$2f$proxy$2e$mjs__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["motion"].div, {
            initial: {
                x: '100%',
                opacity: 0
            },
            animate: {
                x: 0,
                opacity: 1
            },
            exit: {
                x: '100%',
                opacity: 0
            },
            transition: {
                type: 'spring',
                damping: 25,
                stiffness: 200
            },
            className: "fixed top-0 right-0 z-50 h-full w-96 bg-black/90 backdrop-blur-xl border-l border-white/10 shadow-2xl",
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$scroll$2d$area$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ScrollArea"], {
                className: "h-full",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "p-6 space-y-6",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex items-start justify-between",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-3",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "w-12 h-12 rounded-full flex items-center justify-center shadow-lg",
                                            style: {
                                                background: `linear-gradient(135deg, ${agent.theme.primary}, ${agent.theme.secondary})`
                                            },
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$crown$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Crown$3e$__["Crown"], {
                                                className: "w-6 h-6 text-white"
                                            }, void 0, false, {
                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                lineNumber: 64,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 58,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                                                    className: "text-xl font-bold text-white",
                                                    children: agent.displayName
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 67,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-sm text-white/60 capitalize",
                                                    children: [
                                                        agent.role,
                                                        " Agent"
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 68,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 66,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 57,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$button$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Button"], {
                                    variant: "ghost",
                                    size: "icon",
                                    onClick: onClose,
                                    className: "text-white/50 hover:text-white hover:bg-white/10",
                                    children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$x$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__X$3e$__["X"], {
                                        className: "w-5 h-5"
                                    }, void 0, false, {
                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                        lineNumber: 77,
                                        columnNumber: 19
                                    }, this)
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 71,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 56,
                            columnNumber: 15
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex items-center gap-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Badge"], {
                                    variant: "outline",
                                    className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])('text-white border-none', status.color.replace('bg-', 'bg-').replace('500', '500/20')),
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$lib$2f$utils$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["cn"])('w-2 h-2 rounded-full mr-2', status.color)
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 90,
                                            columnNumber: 19
                                        }, this),
                                        status.label
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 83,
                                    columnNumber: 17
                                }, this),
                                agent.currentTask && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: "text-sm text-white/60",
                                    children: [
                                        Math.round(agent.currentTask.progress),
                                        "% complete"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 94,
                                    columnNumber: 19
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 82,
                            columnNumber: 15
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                            className: "bg-white/5 border-white/10 p-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-2 text-amber-400 mb-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$map$2d$pin$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__MapPin$3e$__["MapPin"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 103,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-sm font-medium",
                                            children: agent.historicalCapital
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 104,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 102,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-sm text-white/70 leading-relaxed",
                                    children: agent.historicalContext
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 106,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "mt-3 text-xs text-white/40",
                                    children: [
                                        agent.coordinates.lat.toFixed(1),
                                        "°N, ",
                                        agent.coordinates.lng.toFixed(1),
                                        "°E"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 109,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 101,
                            columnNumber: 15
                        }, this),
                        agent.currentTask && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                    className: "text-sm font-semibold text-white/80 flex items-center gap-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$clock$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Clock$3e$__["Clock"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 118,
                                            columnNumber: 21
                                        }, this),
                                        "Current Task"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 117,
                                    columnNumber: 19
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                    className: "bg-white/5 border-white/10 p-4 space-y-3",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                                    className: "text-white font-medium",
                                                    children: agent.currentTask.title
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 123,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-sm text-white/60 mt-1",
                                                    children: agent.currentTask.description
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 124,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 122,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "space-y-1",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "flex justify-between text-xs text-white/50",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            children: "Progress"
                                                        }, void 0, false, {
                                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                            lineNumber: 130,
                                                            columnNumber: 25
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            children: [
                                                                Math.round(agent.currentTask.progress),
                                                                "%"
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                            lineNumber: 131,
                                                            columnNumber: 25
                                                        }, this)
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 129,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$progress$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Progress"], {
                                                    value: agent.currentTask.progress,
                                                    className: "h-2"
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 133,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 128,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex justify-between text-xs text-white/40",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    children: [
                                                        "Started ",
                                                        new Date(agent.currentTask.startedAt).toLocaleTimeString()
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 136,
                                                    columnNumber: 23
                                                }, this),
                                                agent.currentTask.estimatedCompletion && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    children: [
                                                        "Est. ",
                                                        new Date(agent.currentTask.estimatedCompletion).toLocaleTimeString()
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 138,
                                                    columnNumber: 25
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 135,
                                            columnNumber: 21
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 121,
                                    columnNumber: 19
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 116,
                            columnNumber: 17
                        }, this),
                        agent.queue.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                    className: "text-sm font-semibold text-white/80 flex items-center gap-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$list$2d$ordered$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__ListOrdered$3e$__["ListOrdered"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 149,
                                            columnNumber: 21
                                        }, this),
                                        "Task Queue (",
                                        agent.queue.length,
                                        ")"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 148,
                                    columnNumber: 19
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "space-y-2",
                                    children: agent.queue.map((task, index)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3 hover:bg-white/10 transition-colors",
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "flex items-start gap-3",
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                        className: "flex-shrink-0 w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-xs text-white/60",
                                                        children: index + 1
                                                    }, void 0, false, {
                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                        lineNumber: 159,
                                                        columnNumber: 27
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                        className: "flex-1 min-w-0",
                                                        children: [
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                className: "flex items-center gap-2",
                                                                children: [
                                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                                                        className: "text-sm font-medium text-white truncate",
                                                                        children: task.title
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                        lineNumber: 164,
                                                                        columnNumber: 31
                                                                    }, this),
                                                                    task.priority === 'high' && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$circle$2d$alert$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__AlertCircle$3e$__["AlertCircle"], {
                                                                        className: "w-3 h-3 text-red-400"
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                        lineNumber: 168,
                                                                        columnNumber: 33
                                                                    }, this)
                                                                ]
                                                            }, void 0, true, {
                                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                lineNumber: 163,
                                                                columnNumber: 29
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                className: "flex items-center gap-3 mt-1",
                                                                children: [
                                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Badge"], {
                                                                        variant: "outline",
                                                                        className: `
                                  text-xs border-none
                                  ${task.priority === 'high' ? 'bg-red-500/20 text-red-300' : ''}
                                  ${task.priority === 'medium' ? 'bg-amber-500/20 text-amber-300' : ''}
                                  ${task.priority === 'low' ? 'bg-green-500/20 text-green-300' : ''}
                                `,
                                                                        children: task.priority
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                        lineNumber: 172,
                                                                        columnNumber: 31
                                                                    }, this),
                                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                        className: "text-xs text-white/40",
                                                                        children: [
                                                                            "~",
                                                                            task.estimatedDuration,
                                                                            " min"
                                                                        ]
                                                                    }, void 0, true, {
                                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                        lineNumber: 183,
                                                                        columnNumber: 31
                                                                    }, this)
                                                                ]
                                                            }, void 0, true, {
                                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                lineNumber: 171,
                                                                columnNumber: 29
                                                            }, this)
                                                        ]
                                                    }, void 0, true, {
                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                        lineNumber: 162,
                                                        columnNumber: 27
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                lineNumber: 158,
                                                columnNumber: 25
                                            }, this)
                                        }, task.id, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 154,
                                            columnNumber: 23
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 152,
                                    columnNumber: 19
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 147,
                            columnNumber: 17
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                    className: "text-sm font-semibold text-white/80",
                                    children: "Today's Metrics"
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 197,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "grid grid-cols-2 gap-3",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-2xl font-bold text-white",
                                                    children: agent.metrics.tasksCompleted
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 200,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-xs text-white/50",
                                                    children: "Tasks Completed"
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 201,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 199,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-2xl font-bold text-white",
                                                    children: agent.metrics.itemsProduced
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 204,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-xs text-white/50",
                                                    children: "Items Produced"
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 205,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 203,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-2xl font-bold text-white",
                                                    children: [
                                                        Math.floor(agent.metrics.activeTimeMinutes / 60),
                                                        "h ",
                                                        agent.metrics.activeTimeMinutes % 60,
                                                        "m"
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 208,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-xs text-white/50",
                                                    children: "Active Time"
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 211,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 207,
                                            columnNumber: 19
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-2xl font-bold text-white",
                                                    children: new Date(agent.metrics.lastActiveAt).toLocaleTimeString([], {
                                                        hour: '2-digit',
                                                        minute: '2-digit'
                                                    })
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 214,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-xs text-white/50",
                                                    children: "Last Active"
                                                }, void 0, false, {
                                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                    lineNumber: 217,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 213,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 198,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 196,
                            columnNumber: 15
                        }, this),
                        activities.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                    className: "text-sm font-semibold text-white/80 flex items-center gap-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$file$2d$text$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__FileText$3e$__["FileText"], {
                                            className: "w-4 h-4"
                                        }, void 0, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 226,
                                            columnNumber: 21
                                        }, this),
                                        "Recent Activity"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 225,
                                    columnNumber: 19
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "space-y-2",
                                    children: activities.slice(0, 5).map((activity)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                                            className: "bg-white/5 border-white/10 p-3 hover:bg-white/10 transition-colors",
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "flex items-start gap-3",
                                                children: [
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                        className: "text-lg",
                                                        children: ACTIVITY_ICONS[activity.type]
                                                    }, void 0, false, {
                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                        lineNumber: 236,
                                                        columnNumber: 27
                                                    }, this),
                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                        className: "flex-1 min-w-0",
                                                        children: [
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h4", {
                                                                className: "text-sm font-medium text-white truncate",
                                                                children: activity.title
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                lineNumber: 238,
                                                                columnNumber: 29
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                                className: "text-xs text-white/50 mt-0.5",
                                                                children: activity.description
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                lineNumber: 241,
                                                                columnNumber: 29
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                className: "text-xs text-white/30 mt-1",
                                                                children: new Date(activity.timestamp).toLocaleTimeString()
                                                            }, void 0, false, {
                                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                                lineNumber: 244,
                                                                columnNumber: 29
                                                            }, this)
                                                        ]
                                                    }, void 0, true, {
                                                        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                        lineNumber: 237,
                                                        columnNumber: 27
                                                    }, this)
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                                lineNumber: 235,
                                                columnNumber: 25
                                            }, this)
                                        }, activity.id, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 231,
                                            columnNumber: 23
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 229,
                                    columnNumber: 19
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 224,
                            columnNumber: 17
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$card$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Card"], {
                            className: "bg-white/5 border-white/10 p-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                    className: "text-sm font-semibold text-white/80 mb-2 capitalize",
                                    children: agent.camp.type.replace('-', ' ')
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 257,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-sm text-white/60",
                                    children: agent.camp.description
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 260,
                                    columnNumber: 17
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex flex-wrap gap-2 mt-3",
                                    children: agent.camp.props.map((prop)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$components$2f$ui$2f$badge$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Badge"], {
                                            variant: "outline",
                                            className: "text-white/50 border-white/20 text-xs",
                                            children: prop
                                        }, prop, false, {
                                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                            lineNumber: 263,
                                            columnNumber: 21
                                        }, this))
                                }, void 0, false, {
                                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                                    lineNumber: 261,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                            lineNumber: 256,
                            columnNumber: 15
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                    lineNumber: 54,
                    columnNumber: 13
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
                lineNumber: 53,
                columnNumber: 11
            }, this)
        }, void 0, false, {
            fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
            lineNumber: 46,
            columnNumber: 9
        }, this)
    }, void 0, false, {
        fileName: "[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx",
        lineNumber: 44,
        columnNumber: 5
    }, this);
}
}),
"[project]/molt/steppe-visualization/app/hooks/useFileWatcher.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "useFileWatcher",
    ()=>useFileWatcher
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-ssr] (ecmascript)");
'use client';
;
;
// Map file patterns to agents and activity types
const FILE_PATTERNS = [
    {
        pattern: /kublai/i,
        agentId: 'kublai',
        type: 'automation'
    },
    {
        pattern: /mongke/i,
        agentId: 'mongke',
        type: 'research'
    },
    {
        pattern: /ogedei/i,
        agentId: 'ogedei',
        type: 'content'
    },
    {
        pattern: /temujin/i,
        agentId: 'temujin',
        type: 'security'
    },
    {
        pattern: /jochi/i,
        agentId: 'jochi',
        type: 'analysis'
    },
    {
        pattern: /chagatai/i,
        agentId: 'chagatai',
        type: 'operations'
    }
];
const DELIVERABLES_PATH = '/data/workspace/deliverables';
function useFileWatcher() {
    const { updateAgentStatus, addActivity, addDeliverable, updateAgentTask } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useAgentStore"])();
    const watchedFiles = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(new Set());
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        // For client-side, we'll use polling since chokidar requires Node.js
        const pollInterval = setInterval(async ()=>{
            try {
                // Fetch deliverables from API
                const response = await fetch('/api/deliverables');
                if (!response.ok) return;
                const data = await response.json();
                const files = data.files || [];
                // Check for new files
                for (const file of files){
                    if (!watchedFiles.current.has(file)) {
                        watchedFiles.current.add(file);
                        handleNewFile(file);
                    }
                }
            } catch (error) {
            // Silent fail - will retry on next poll
            }
        }, 5000); // Poll every 5 seconds
        return ()=>clearInterval(pollInterval);
    }, []);
    function handleNewFile(filePath) {
        const fileName = filePath.split('/').pop() || '';
        // Find matching agent
        const match = FILE_PATTERNS.find((p)=>p.pattern.test(fileName));
        if (!match) return;
        const { agentId, type } = match;
        // Update agent status
        updateAgentStatus(agentId, 'working');
        // Create activity
        const activity = {
            id: `activity-${Date.now()}`,
            agentId,
            type,
            title: `Created ${fileName}`,
            description: `New deliverable created at ${filePath}`,
            timestamp: new Date(),
            deliverablePath: filePath
        };
        addActivity(activity);
        // Create deliverable
        const deliverable = {
            id: `deliverable-${Date.now()}`,
            agentId,
            type,
            title: fileName,
            path: filePath,
            createdAt: new Date(),
            modifiedAt: new Date(),
            size: 0
        };
        addDeliverable(deliverable);
        // Simulate task progress
        simulateTaskProgress(agentId, fileName);
        // Reset status after delay
        setTimeout(()=>{
            updateAgentStatus(agentId, 'idle');
        }, 30000);
    }
    function simulateTaskProgress(agentId, taskName) {
        const task = {
            id: `task-${Date.now()}`,
            title: `Processing ${taskName}`,
            description: 'Analyzing and integrating deliverable',
            progress: 0,
            startedAt: new Date(),
            estimatedCompletion: new Date(Date.now() + 5 * 60 * 1000)
        };
        updateAgentTask(agentId, task);
        // Simulate progress updates
        let progress = 0;
        const interval = setInterval(()=>{
            progress += 10;
            if (progress >= 100) {
                clearInterval(interval);
                updateAgentTask(agentId, {
                    ...task,
                    progress: 100
                });
                setTimeout(()=>updateAgentTask(agentId, undefined), 2000);
            } else {
                updateAgentTask(agentId, {
                    ...task,
                    progress
                });
            }
        }, 3000);
    }
}
}),
"[project]/molt/steppe-visualization/app/page.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>Home
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$SteppeScene$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/scene/SteppeScene.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$Header$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/ui/Header.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$MiniMap$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/ui/MiniMap.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$AgentDetailPanel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/components/ui/AgentDetailPanel.tsx [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/stores/agentStore.ts [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$hooks$2f$useFileWatcher$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/molt/steppe-visualization/app/hooks/useFileWatcher.ts [app-ssr] (ecmascript)");
'use client';
;
;
;
;
;
;
;
function Home() {
    const { agents, selectedAgentId, isDetailPanelOpen, selectAgent, toggleDetailPanel, getSelectedAgent, getAgentActivities } = (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$stores$2f$agentStore$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useAgentStore"])();
    // Initialize file watcher
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$hooks$2f$useFileWatcher$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useFileWatcher"])();
    const selectedAgent = getSelectedAgent();
    const selectedAgentActivities = selectedAgentId ? getAgentActivities(selectedAgentId) : [];
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
        className: "relative w-screen h-screen bg-black overflow-hidden",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$scene$2f$SteppeScene$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["SteppeScene"], {}, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                lineNumber: 32,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$Header$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Header"], {
                onToggleMap: ()=>{},
                onToggleSettings: ()=>{},
                onToggleHelp: ()=>{}
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                lineNumber: 35,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$MiniMap$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["MiniMap"], {
                agents: agents,
                selectedAgentId: selectedAgentId,
                onSelectAgent: (id)=>{
                    selectAgent(id);
                    toggleDetailPanel(true);
                }
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                lineNumber: 42,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$app$2f$components$2f$ui$2f$AgentDetailPanel$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AgentDetailPanel"], {
                agent: selectedAgent || null,
                activities: selectedAgentActivities,
                isOpen: isDetailPanelOpen,
                onClose: ()=>{
                    selectAgent(null);
                    toggleDetailPanel(false);
                }
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                lineNumber: 52,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "fixed bottom-6 right-6 z-40 text-right",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "bg-black/70 backdrop-blur-sm rounded-lg px-5 py-4 text-white/80 text-base",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "font-semibold mb-2 text-lg",
                            children: "Controls"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 65,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "py-0.5",
                            children: "🖱️ Click + Drag to orbit/pivot"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 66,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "py-0.5",
                            children: "🖱️ Click agent to view details"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 67,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "py-0.5",
                            children: "📜 Scroll / Pinch to zoom"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 68,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "py-0.5",
                            children: "⌨️ WASD / Arrow keys to pan"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 69,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$molt$2f$steppe$2d$visualization$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "py-0.5",
                            children: "👆 2-finger drag to pan map"
                        }, void 0, false, {
                            fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                            lineNumber: 70,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                    lineNumber: 64,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/molt/steppe-visualization/app/page.tsx",
                lineNumber: 63,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/molt/steppe-visualization/app/page.tsx",
        lineNumber: 30,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__055ed4d6._.js.map