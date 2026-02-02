'use client';

import { useMemo, useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import { createNoise2D } from 'simplex-noise';

interface EmpireTerrainProps {
  segments?: number;
}

// Mongol Empire approximate boundaries at its height (1279)
// These are simplified polygon points to create the empire shape
const EMPIRE_BOUNDS = {
  minLat: 22,  // South: Vietnam/South China
  maxLat: 55,  // North: Siberia/Lake Baikal
  minLng: 22,  // West: Eastern Europe/Hungary
  maxLng: 135, // East: Pacific Ocean/Korea
};

// Key points defining the Mongol Empire's rough outline
// Format: [longitude, latitude]
const EMPIRE_OUTLINE: [number, number][] = [
  // Eastern border - Pacific/Korea
  [135, 42], [133, 38], [130, 35], [128, 32], [125, 28], [122, 25], [120, 22],
  // Southern border - Southeast Asia/China
  [118, 22], [115, 24], [112, 22], [108, 20], [105, 22], [100, 25], [95, 22],
  // Southwest - Tibet/Himalayas (avoided)
  [90, 25], [85, 28], [80, 30], [75, 32],
  // Western border - Central Asia/Persia
  [70, 35], [65, 37], [60, 38], [55, 40], [50, 42], [45, 45], [40, 47],
  // Northwest - Russia
  [35, 50], [30, 52], [25, 54], [22, 55],
  // Northern border - Siberia
  [30, 55], [40, 54], [50, 53], [60, 52], [70, 51], [80, 50], [90, 49],
  [100, 50], [110, 51], [120, 52], [130, 53], [135, 52],
];

export function EmpireTerrain({ segments = 150 }: EmpireTerrainProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Convert lat/lng to world coordinates
  const latLngToWorld = (lat: number, lng: number): { x: number; z: number } => {
    const x = ((lng - EMPIRE_BOUNDS.minLng) / (EMPIRE_BOUNDS.maxLng - EMPIRE_BOUNDS.minLng)) * 120 - 60;
    const z = ((lat - EMPIRE_BOUNDS.minLat) / (EMPIRE_BOUNDS.maxLat - EMPIRE_BOUNDS.minLat)) * -70 + 35;
    return { x, z };
  };

  // Check if a point is inside the empire using ray casting algorithm
  const isPointInEmpire = (lat: number, lng: number): boolean => {
    // Simple bounding box check first
    if (lat < EMPIRE_BOUNDS.minLat || lat > EMPIRE_BOUNDS.maxLat ||
        lng < EMPIRE_BOUNDS.minLng || lng > EMPIRE_BOUNDS.maxLng) {
      return false;
    }

    // Ray casting algorithm
    let inside = false;
    for (let i = 0, j = EMPIRE_OUTLINE.length - 1; i < EMPIRE_OUTLINE.length; j = i++) {
      const [lngi, lati] = EMPIRE_OUTLINE[i];
      const [lngj, latj] = EMPIRE_OUTLINE[j];

      if (((lati > lat) !== (latj > lat)) &&
          (lng < (lngj - lngi) * (lat - lati) / (latj - lati) + lngi)) {
        inside = !inside;
      }
    }
    return inside;
  };

  const geometry = useMemo(() => {
    if (!mounted) return null;

    const noise2D = createNoise2D();
    const positions: number[] = [];
    const indices: number[] = [];
    const colors: number[] = [];
    const uvs: number[] = [];

    const width = 120;
    const depth = 70;

    // Generate grid
    for (let z = 0; z <= segments; z++) {
      for (let x = 0; x <= segments; x++) {
        const xPos = (x / segments) * width - width / 2;
        const zPos = (z / segments) * depth - depth / 2;

        // Convert to lat/lng
        const lng = ((xPos + 60) / 120) * (EMPIRE_BOUNDS.maxLng - EMPIRE_BOUNDS.minLng) + EMPIRE_BOUNDS.minLng;
        const lat = ((zPos - 35) / -70) * (EMPIRE_BOUNDS.maxLat - EMPIRE_BOUNDS.minLat) + EMPIRE_BOUNDS.minLat;

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
          r = 0.15; g = 0.2; b = 0.15;
        } else {
          // Gobi Desert - sandy
          const gobiDist = Math.sqrt(Math.pow(lng - 105, 2) + Math.pow(lat - 42, 2));
          if (gobiDist < 12) {
            r = 0.65; g = 0.55; b = 0.35;
          }

          // Northern forests - darker green
          if (lat > 50) {
            r = 0.25; g = 0.4; b = 0.25;
          }

          // Southern China - lighter green
          if (lat < 35) {
            r = 0.4; g = 0.5; b = 0.3;
          }
        }

        colors.push(r, g, b);
      }
    }

    // Generate indices
    for (let z = 0; z < segments; z++) {
      for (let x = 0; x < segments; x++) {
        const a = z * (segments + 1) + x;
        const b = a + 1;
        const c = (z + 1) * (segments + 1) + x;
        const d = c + 1;

        indices.push(a, c, b);
        indices.push(b, c, d);
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    geo.setIndex(indices);
    geo.computeVertexNormals();

    return geo;
  }, [segments, mounted]);

  if (!mounted || !geometry) {
    return null;
  }

  return (
    <mesh ref={meshRef} geometry={geometry} receiveShadow>
      <meshStandardMaterial
        vertexColors
        roughness={0.9}
        metalness={0.05}
        flatShading
      />
    </mesh>
  );
}
