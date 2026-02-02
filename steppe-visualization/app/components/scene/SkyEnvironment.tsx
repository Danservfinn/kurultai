'use client';

import { Sky, Stars } from '@react-three/drei';

export function SkyEnvironment() {
  return (
    <>
      <Sky
        distance={450000}
        sunPosition={[100, 20, 100]}
        inclination={0.49}
        azimuth={0.25}
        mieCoefficient={0.005}
        mieDirectionalG={0.8}
        rayleigh={0.5}
        turbidity={8}
      />
      <Stars radius={100} depth={50} count={5000} factor={4} saturation={0} fade speed={1} />
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[100, 50, 100]}
        intensity={1.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-50}
        shadow-camera-right={50}
        shadow-camera-top={50}
        shadow-camera-bottom={-50}
      />
    </>
  );
}
