'use client';

import { useMemo } from 'react';
import * as THREE from 'three';

// Major rivers in the Mongol Empire
const RIVERS = [
  {
    name: 'Volga',
    points: [
      { lat: 48.5, lng: 45.0 }, // Sarai Batu area
      { lat: 48.0, lng: 44.5 },
      { lat: 47.0, lng: 44.0 },
      { lat: 46.0, lng: 44.5 },
      { lat: 45.0, lng: 45.0 },
    ],
  },
  {
    name: 'Orkhon',
    points: [
      { lat: 47.5, lng: 102.0 },
      { lat: 47.2, lng: 102.5 }, // Karakorum
      { lat: 47.0, lng: 103.0 },
      { lat: 46.5, lng: 104.0 },
    ],
  },
  {
    name: 'Ili',
    points: [
      { lat: 45.0, lng: 76.0 },
      { lat: 44.5, lng: 77.0 },
      { lat: 44.0, lng: 78.5 }, // Almaliq area
      { lat: 43.5, lng: 80.0 },
    ],
  },
];

function latLngToWorld(lat: number, lng: number): { x: number; z: number } {
  const x = ((lng - 20) / 110) * 100 - 50;
  const z = ((lat - 35) / 20) * -50 + 25;
  return { x, z };
}

export function Rivers() {
  const riverGeometries = useMemo(() => {
    return RIVERS.map((river) => {
      const points = river.points.map((p) => {
        const { x, z } = latLngToWorld(p.lat, p.lng);
        return new THREE.Vector3(x, 0.2, z);
      });

      const curve = new THREE.CatmullRomCurve3(points);
      const geometry = new THREE.TubeGeometry(curve, 32, 0.3, 8, false);

      return { name: river.name, geometry };
    });
  }, []);

  return (
    <>
      {riverGeometries.map((river) => (
        <mesh key={river.name} geometry={river.geometry}>
          <meshStandardMaterial
            color="#1e3a5f"
            transparent
            opacity={0.7}
            roughness={0.2}
            metalness={0.8}
          />
        </mesh>
      ))}
    </>
  );
}
