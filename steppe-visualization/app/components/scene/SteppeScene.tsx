'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { EmpireTerrain } from './EmpireTerrain';
import { Rivers } from './Rivers';
import { SkyEnvironment } from './SkyEnvironment';
import { AgentsLayer } from '../agents/AgentsLayer';
import { useAgentStore } from '@/app/stores/agentStore';
import { Agent } from '@/app/types/agents';
import * as THREE from 'three';

// Touch and keyboard controls
function TouchAndKeyControls({ target, setTarget }: { target: [number, number, number] | null; setTarget: (t: [number, number, number] | null) => void }) {
  const { camera, gl } = useThree();
  const keysPressed = useRef<Set<string>>(new Set());
  const moveSpeed = 1.2;

  // Touch state
  const touchesRef = useRef<Touch[]>([]);
  const lastTouchDistanceRef = useRef<number>(0);
  const lastTouchCenterRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  useEffect(() => {
    const canvas = gl.domElement;

    const handleKeyDown = (e: KeyboardEvent) => {
      keysPressed.current.add(e.key.toLowerCase());
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      keysPressed.current.delete(e.key.toLowerCase());
    };

    // Touch event handlers
    const handleTouchStart = (e: TouchEvent) => {
      e.preventDefault();
      touchesRef.current = Array.from(e.touches);

      if (touchesRef.current.length === 2) {
        // Two finger touch - prepare for pan
        const touch1 = touchesRef.current[0];
        const touch2 = touchesRef.current[1];
        lastTouchDistanceRef.current = Math.hypot(
          touch2.clientX - touch1.clientX,
          touch2.clientY - touch1.clientY
        );
        lastTouchCenterRef.current = {
          x: (touch1.clientX + touch2.clientX) / 2,
          y: (touch1.clientY + touch2.clientY) / 2,
        };
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
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
        const currentTarget = target || [0, 0, 0];

        // Calculate camera right and forward vectors
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
        right.y = 0;
        right.normalize();

        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
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
        lastTouchCenterRef.current = { x: centerX, y: centerY };

        // Pinch zoom
        const distance = Math.hypot(
          touch2.clientX - touch1.clientX,
          touch2.clientY - touch1.clientY
        );
        const distanceDelta = lastTouchDistanceRef.current - distance;
        const zoomSpeed = 0.1;

        // Move camera along look direction for zoom
        const lookDirection = new THREE.Vector3().subVectors(
          new THREE.Vector3(...(target || [0, 0, 0])),
          camera.position
        ).normalize();

        camera.position.addScaledVector(lookDirection, distanceDelta * zoomSpeed);

        lastTouchDistanceRef.current = distance;
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      e.preventDefault();
      touchesRef.current = Array.from(e.touches);
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd, { passive: false });

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      canvas.removeEventListener('touchstart', handleTouchStart);
      canvas.removeEventListener('touchmove', handleTouchMove);
      canvas.removeEventListener('touchend', handleTouchEnd);
    };
  }, [camera, gl, target, setTarget]);

  // WASD keyboard movement - moves camera forward/back/left/right
  useFrame(() => {
    const keys = keysPressed.current;
    if (keys.size === 0) return;

    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
    right.y = 0;
    right.normalize();

    const movement = new THREE.Vector3();

    if (keys.has('w') || keys.has('arrowup')) movement.add(forward);
    if (keys.has('s') || keys.has('arrowdown')) movement.sub(forward);
    if (keys.has('a') || keys.has('arrowleft')) movement.sub(right);
    if (keys.has('d') || keys.has('arrowright')) movement.add(right);

    if (movement.length() > 0) {
      movement.normalize().multiplyScalar(moveSpeed);
      // Move both camera and target together to maintain orbit relationship
      camera.position.x += movement.x;
      camera.position.z += movement.z;
      const currentTarget = target || [0, 0, 0];
      setTarget([
        currentTarget[0] + movement.x,
        currentTarget[1],
        currentTarget[2] + movement.z
      ]);
    }
  });

  return null;
}

export function SteppeScene() {
  const { agents, selectedAgentId, selectAgent } = useAgentStore();
  const [cameraTarget, setCameraTarget] = useState<[number, number, number] | null>(null);

  const handleSelectAgent = useCallback((agent: Agent) => {
    selectAgent(agent.id);
    setCameraTarget([agent.position.x, agent.position.elevation + 5, agent.position.z]);
  }, [selectAgent]);

  const handleBackgroundClick = useCallback(() => {
    selectAgent(null);
    setCameraTarget(null);
  }, [selectAgent]);

  return (
    <div className="w-full h-full" onClick={handleBackgroundClick}>
      <Canvas shadows>
        <PerspectiveCamera
          makeDefault
          position={[0, 80, 20]}
          fov={25}
          near={0.1}
          far={1000}
        />

        <TouchAndKeyControls target={cameraTarget} setTarget={setCameraTarget} />

        <OrbitControls
          enablePan={false}
          enableZoom={false}  // We handle zoom via touch pinch and scroll
          enableRotate={true}
          minDistance={30}
          maxDistance={120}
          minPolarAngle={0}
          maxPolarAngle={Math.PI / 2.5}
          target={cameraTarget || [0, 0, 0]}
          mouseButtons={{
            LEFT: THREE.MOUSE.ROTATE,  // Click and hold to orbit/pivot
            MIDDLE: undefined,
            RIGHT: undefined
          }}
          touches={{
            ONE: THREE.TOUCH.ROTATE    // One finger = orbit/pivot
            // Two fingers handled by custom pan/zoom
          }}
          reverseOrbit
          reverseHorizontalOrbit
        />

        <SkyEnvironment />

        {/* Main terrain - Mongol Empire shape */}
        <EmpireTerrain segments={150} />

        {/* Rivers */}
        <Rivers />

        {/* Agents */}
        <AgentsLayer
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={handleSelectAgent}
        />
      </Canvas>
    </div>
  );
}
