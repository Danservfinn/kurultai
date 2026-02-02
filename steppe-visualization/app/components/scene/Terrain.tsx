'use client';

import { useMemo, useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import { createNoise2D } from 'simplex-noise';

interface TerrainProps {
  width?: number;
  depth?: number;
  segments?: number;
}

export function Terrain({ width = 100, depth = 50, segments = 100 }: TerrainProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const geometry = useMemo(() => {
    if (!mounted) return null;

    const noise2D = createNoise2D();
    const positions: number[] = [];
    const indices: number[] = [];
    const colors: number[] = [];
    const uvs: number[] = [];

    // Generate heightmap - almost flat with subtle variations
    for (let z = 0; z <= segments; z++) {
      for (let x = 0; x <= segments; x++) {
        const xPos = (x / segments) * width - width / 2;
        const zPos = (z / segments) * depth - depth / 2;

        // Normalize to lat/lng for height calculation
        const lng = ((xPos + 50) / 100) * 110 + 20; // 20°E to 130°E
        const lat = ((zPos - 25) / -50) * 20 + 35; // 35°N to 55°N

        // Very subtle base terrain - almost flat
        let height = noise2D(xPos * 0.05, zPos * 0.05) * 0.3;
        height += noise2D(xPos * 0.1, zPos * 0.1) * 0.15;
        height += noise2D(xPos * 0.2, zPos * 0.2) * 0.05;

        // Very gentle mountain ranges - barely noticeable
        // Altai Mountains (west, around 85-90°E, 45-50°N)
        const altaiDist = Math.sqrt(Math.pow(lng - 87, 2) + Math.pow(lat - 47, 2));
        if (altaiDist < 15) {
          height += (15 - altaiDist) * 0.1;
        }

        // Tian Shan (around 80°E, 42°N)
        const tianShanDist = Math.sqrt(Math.pow(lng - 80, 2) + Math.pow(lat - 42, 2));
        if (tianShanDist < 12) {
          height += (12 - tianShanDist) * 0.15;
        }

        // Khangai Mountains (around 100°E, 47°N - near Karakorum)
        const khangaiDist = Math.sqrt(Math.pow(lng - 100, 2) + Math.pow(lat - 47, 2));
        if (khangaiDist < 10) {
          height += (10 - khangaiDist) * 0.08;
        }

        // Gobi Desert - very slight depression
        const gobiDist = Math.sqrt(Math.pow(lng - 105, 2) + Math.pow(lat - 42, 2));
        if (gobiDist < 20) {
          height -= (20 - gobiDist) * 0.05;
        }

        // Keep height very low - almost flat
        height = Math.max(-0.5, Math.min(1.5, height * 0.3));

        positions.push(xPos, height, zPos);
        uvs.push(x / segments, z / segments);

        // Color based on elevation and region
        let r = 0.4, g = 0.5, b = 0.3; // Default grass

        if (height > 0.8) {
          // Mountains - gray/brown
          r = 0.5; g = 0.45; b = 0.4;
        } else if (height > 0.4) {
          // Hills - yellow-green
          r = 0.5; g = 0.55; b = 0.3;
        } else if (gobiDist < 15) {
          // Desert - sandy
          r = 0.7; g = 0.6; b = 0.4;
        }

        // Darken lower areas
        if (height < 0) {
          r *= 0.8; g *= 0.8; b *= 0.9;
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
  }, [width, depth, segments, mounted]);

  if (!mounted || !geometry) {
    return null;
  }

  return (
    <mesh ref={meshRef} geometry={geometry} receiveShadow>
      <meshStandardMaterial
        vertexColors
        roughness={0.8}
        metalness={0.1}
        flatShading
      />
    </mesh>
  );
}
