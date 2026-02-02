'use client';

import { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { AgentStatus } from '@/app/types/agents';

interface StatusIndicatorProps {
  status: AgentStatus;
  position: { x: number; y: number; z: number };
}

const STATUS_COLORS: Record<AgentStatus, string> = {
  idle: '#22c55e',      // Green
  working: '#3b82f6',   // Blue
  reviewing: '#f59e0b', // Amber
  alert: '#ef4444',     // Red
  offline: '#6b7280',   // Gray
};

export function StatusIndicator({ status, position }: StatusIndicatorProps) {
  const indicatorRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
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

  return (
    <group position={[position.x, position.y, position.z]}>
      {/* Main indicator */}
      <mesh ref={indicatorRef} position={[0, 2.5, 0]}>
        <sphereGeometry args={[0.25, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.5}
        />
      </mesh>

      {/* Rotating ring */}
      <mesh ref={ringRef} position={[0, 2.5, 0]}>
        <ringGeometry args={[0.4, 0.45, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
      </mesh>

      {/* Status label background */}
      <mesh position={[0, 2.5, 0]}>
        <planeGeometry args={[1.2, 0.4]} />
        <meshBasicMaterial color="rgba(0,0,0,0.7)" transparent />
      </mesh>
    </group>
  );
}
