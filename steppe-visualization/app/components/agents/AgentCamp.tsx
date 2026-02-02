'use client';

import { useMemo, ReactElement } from 'react';
import * as THREE from 'three';
import { Agent } from '@/app/types/agents';

interface AgentCampProps {
  agent: Agent;
}

export function AgentCamp({ agent }: AgentCampProps) {
  const campElements = useMemo(() => {
    const elements: ReactElement[] = [];
    const { x, z, elevation } = agent.position;

    // Base platform
    elements.push(
      <mesh key="platform" position={[x, elevation - 0.1, z]} receiveShadow>
        <cylinderGeometry args={[2.5, 2.5, 0.2, 16]} />
        <meshStandardMaterial color="#5c4a3d" roughness={0.9} />
      </mesh>
    );

    // Camp-specific elements based on type
    switch (agent.camp.type) {
      case 'forge':
        // Temujin's forge
        elements.push(
          <mesh key="anvil" position={[x + 1, elevation + 0.3, z + 1]} castShadow>
            <boxGeometry args={[0.4, 0.6, 0.3]} />
            <meshStandardMaterial color="#2a2a2a" roughness={0.5} metalness={0.8} />
          </mesh>,
          <mesh key="banner" position={[x - 1.5, elevation + 1.5, z - 1]} castShadow>
            <cylinderGeometry args={[0.05, 0.05, 3, 8]} />
            <meshStandardMaterial color="#8b4513" />
          </mesh>,
          <mesh key="flag" position={[x - 1.5, elevation + 2.5, z - 1]} castShadow>
            <boxGeometry args={[0.8, 0.5, 0.05]} />
            <meshStandardMaterial color={agent.theme.glow} />
          </mesh>
        );
        break;

      case 'caravanserai':
        // Trading post for Ogedei/Chagatai
        elements.push(
          <mesh key="tent" position={[x + 1.2, elevation + 0.8, z]} castShadow>
            <coneGeometry args={[1, 1.6, 8]} />
            <meshStandardMaterial color="#d4a574" roughness={0.8} />
          </mesh>,
          <mesh key="crate1" position={[x - 1, elevation + 0.2, z + 1]} castShadow>
            <boxGeometry args={[0.5, 0.4, 0.5]} />
            <meshStandardMaterial color="#8b4513" />
          </mesh>,
          <mesh key="crate2" position={[x - 0.8, elevation + 0.25, z + 1.3]} castShadow>
            <boxGeometry args={[0.4, 0.5, 0.4]} />
            <meshStandardMaterial color="#a0522d" />
          </mesh>
        );
        break;

      case 'observatory':
        // Scholarly retreat for Mongke
        elements.push(
          <mesh key="table" position={[x + 1, elevation + 0.3, z + 0.5]} castShadow>
            <boxGeometry args={[1, 0.6, 0.6]} />
            <meshStandardMaterial color="#654321" />
          </mesh>,
          <mesh key="scroll" position={[x + 1, elevation + 0.65, z + 0.5]} rotation={[Math.PI / 2, 0, 0]} castShadow>
            <cylinderGeometry args={[0.1, 0.1, 0.4, 8]} />
            <meshStandardMaterial color="#f5f5dc" />
          </mesh>,
          <mesh key="telescope" position={[x - 1, elevation + 0.8, z - 0.5]} rotation={[Math.PI / 4, 0, Math.PI / 6]} castShadow>
            <cylinderGeometry args={[0.08, 0.1, 1.2, 8]} />
            <meshStandardMaterial color="#4a4a4a" metalness={0.6} />
          </mesh>
        );
        break;

      case 'palace':
        // Imperial palace for Kublai
        elements.push(
          <mesh key="throne" position={[x + 0.8, elevation + 0.5, z]} castShadow>
            <boxGeometry args={[0.8, 1, 0.6]} />
            <meshStandardMaterial color={agent.theme.secondary} metalness={0.4} />
          </mesh>,
          <mesh key="canopy" position={[x + 0.8, elevation + 1.3, z]} rotation={[0, Math.PI / 4, 0]} castShadow>
            <coneGeometry args={[1.2, 0.6, 4]} />
            <meshStandardMaterial color={agent.theme.primary} />
          </mesh>,
          <mesh key="banner1" position={[x - 1.2, elevation + 1.2, z + 1]} castShadow>
            <cylinderGeometry args={[0.03, 0.03, 2.4, 6]} />
            <meshStandardMaterial color={agent.theme.glow} />
          </mesh>
        );
        break;

      case 'counting-house':
        // Administrative center for Jochi
        elements.push(
          <mesh key="desk" position={[x + 1, elevation + 0.35, z]} castShadow>
            <boxGeometry args={[1.2, 0.7, 0.6]} />
            <meshStandardMaterial color="#5c4033" />
          </mesh>,
          <mesh key="abacus" position={[x + 1, elevation + 0.75, z]} castShadow>
            <boxGeometry args={[0.4, 0.2, 0.3]} />
            <meshStandardMaterial color="#8b4513" />
          </mesh>,
          <mesh key="chest" position={[x - 1, elevation + 0.3, z + 0.8]} castShadow>
            <boxGeometry args={[0.6, 0.4, 0.4]} />
            <meshStandardMaterial color="#ffd700" metalness={0.5} />
          </mesh>
        );
        break;
    }

    return elements;
  }, [agent]);

  return <group>{campElements}</group>;
}
