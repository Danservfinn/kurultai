'use client';

import { useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Agent } from '@/app/types/agents';

interface AgentMeshProps {
  agent: Agent;
  isSelected: boolean;
  isHovered: boolean;
}

export function AgentMesh({ agent, isSelected, isHovered }: AgentMeshProps) {
  const groupRef = useRef<THREE.Group>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  // Procedural agent geometry - stylized human figure
  const { bodyGeometry, headGeometry, crownGeometry } = useMemo(() => {
    // Body - cylinder
    const bodyGeo = new THREE.CylinderGeometry(0.3, 0.4, 1.2, 8);
    bodyGeo.translate(0, 0.6, 0);

    // Head - sphere
    const headGeo = new THREE.SphereGeometry(0.35, 16, 16);
    headGeo.translate(0, 1.5, 0);

    // Crown/helmet - torus or cone depending on role
    let crownGeo: THREE.BufferGeometry;
    if (agent.role === 'coordinator') {
      // Crown for Kublai
      crownGeo = new THREE.ConeGeometry(0.4, 0.3, 8);
      crownGeo.translate(0, 1.85, 0);
    } else if (agent.role === 'developer') {
      // Helmet for Temujin
      crownGeo = new THREE.SphereGeometry(0.38, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2);
      crownGeo.translate(0, 1.5, 0);
    } else {
      // Simple cap for others
      crownGeo = new THREE.CylinderGeometry(0.25, 0.3, 0.2, 8);
      crownGeo.translate(0, 1.8, 0);
    }

    return { bodyGeometry: bodyGeo, headGeometry: headGeo, crownGeometry: crownGeo };
  }, [agent.role]);

  // Animation - gentle breathing/floating
  useFrame((state) => {
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
      const material = glowRef.current.material as THREE.MeshBasicMaterial;
      material.opacity = (0.3 + Math.sin(time * pulseSpeed) * 0.2) * baseIntensity;
    }
  });

  const glowColor = agent.theme.glow;
  const scale = isSelected ? 1.3 : isHovered ? 1.15 : 1;

  return (
    <group
      ref={groupRef}
      position={[agent.position.x, agent.position.elevation, agent.position.z]}
      scale={[scale, scale, scale]}
    >
      {/* Glow effect */}
      <mesh ref={glowRef} position={[0, 1, 0]}>
        <sphereGeometry args={[1.2, 16, 16]} />
        <meshBasicMaterial color={glowColor} transparent opacity={0.3} />
      </mesh>

      {/* Body */}
      <mesh geometry={bodyGeometry} castShadow>
        <meshStandardMaterial
          color={agent.theme.primary}
          roughness={0.7}
          metalness={0.3}
        />
      </mesh>

      {/* Head */}
      <mesh geometry={headGeometry} castShadow>
        <meshStandardMaterial
          color={agent.theme.secondary}
          roughness={0.5}
          metalness={0.2}
        />
      </mesh>

      {/* Crown/Helmet */}
      <mesh geometry={crownGeometry} castShadow>
        <meshStandardMaterial
          color={agent.theme.glow}
          roughness={0.3}
          metalness={0.8}
          emissive={agent.theme.glow}
          emissiveIntensity={0.3}
        />
      </mesh>

      {/* Selection ring */}
      {isSelected && (
        <mesh position={[0, 0.1, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1, 1.3, 32]} />
          <meshBasicMaterial color={agent.theme.glow} transparent opacity={0.8} />
        </mesh>
      )}
    </group>
  );
}
