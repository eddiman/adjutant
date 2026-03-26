import React, {Suspense, useEffect, useState, useRef} from 'react';
import {Canvas, useFrame, extend} from '@react-three/fiber';
import {
  PerspectiveCamera,
  Environment,
  MeshDistortMaterial,
  ContactShadows,
  OrbitControls,
} from '@react-three/drei';
import {useSpring} from '@react-spring/core';
import {a} from '@react-spring/three';
import * as THREE from 'three';
import {
  Mesh,
  SphereGeometry,
  PointLight,
  AmbientLight,
} from 'three';

// R3F v9 requires explicit registration of Three.js objects
extend({Mesh, SphereGeometry, PointLight, AmbientLight});

// Wrap MeshDistortMaterial for react-spring animation
const AnimatedMaterial = a(MeshDistortMaterial);

/**
 * The 3D scene containing the wobbling sphere, adapted for the Adjutant
 * color palette. Always renders the dark-mode (blue) variant.
 */
function Scene() {
  const sphere = useRef<THREE.Mesh>(null);
  const light = useRef<THREE.PointLight>(null);
  const [down, setDown] = useState(false);
  const [hovered, setHovered] = useState(false);

  // Cursor styling on hover
  useEffect(() => {
    document.body.style.cursor = hovered
      ? 'none'
      : `url('data:image/svg+xml;base64,${btoa(
          '<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="16" cy="16" r="10" fill="#e48dbf"/></svg>',
        )}'), auto`;
    return () => {
      document.body.style.cursor = 'auto';
    };
  }, [hovered]);

  // Float the sphere and follow the mouse
  useFrame((state) => {
    if (light.current) {
      light.current.position.x = state.pointer.x * 20;
      light.current.position.y = state.pointer.y * 20;
    }
    if (sphere.current) {
      sphere.current.position.x = THREE.MathUtils.lerp(
        sphere.current.position.x,
        hovered ? state.pointer.x / 2 : 0,
        0.2,
      );
      sphere.current.position.y = THREE.MathUtils.lerp(
        sphere.current.position.y,
        Math.sin(state.clock.elapsedTime / 1.5) / 6 +
          (hovered ? state.pointer.y / 2 : 0),
        0.2,
      );
    }
  });

  const sphereColor = hovered
    ? '#e48dbf' // pink accent on hover
    : '#4670cc'; // royal blue

  const [{wobble, coat, ambient, env, color}] = useSpring(
    {
      wobble: down ? 1.2 : hovered ? 1.05 : 1,
      coat: !hovered ? 0.04 : 1,
      ambient: !hovered ? 1.5 : 0.5,
      env: !hovered ? 0.4 : 1,
      color: sphereColor,
      config: (n: string) =>
        n === 'wobble' && hovered
          ? {mass: 2, tension: 1000, friction: 10}
          : {},
    },
    [hovered, down],
  );

  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 0, 4]} fov={75}>
        <a.ambientLight intensity={ambient} />
        <a.pointLight
          ref={light}
          position-z={-15}
          intensity={env}
          color="#e48dbf"
        />
      </PerspectiveCamera>
      <Suspense fallback={null}>
        <a.mesh
          ref={sphere}
          scale={wobble}
          onPointerOver={() => setHovered(true)}
          onPointerOut={() => setHovered(false)}
          onPointerDown={() => setDown(true)}
          onPointerUp={() => {
            setDown(false);
          }}>
          <sphereGeometry args={[1, 64, 64]} />
          <AnimatedMaterial
            distort={0.4}
            speed={2}
            color={color}
            envMapIntensity={env}
            clearcoat={coat}
            clearcoatRoughness={0}
            metalness={0.1}
          />
        </a.mesh>
        <Environment preset="warehouse" />
        <ContactShadows
          rotation={[Math.PI / 2, 0, 0]}
          position={[0, -1.6, 0]}
          opacity={0.8}
          width={15}
          height={15}
          blur={2.5}
          far={1.6}
        />
      </Suspense>
    </>
  );
}

/**
 * The full Canvas wrapper. This component must only be rendered in the
 * browser (wrap with Docusaurus <BrowserOnly>).
 */
export default function WobblingScene() {
  return (
    <Canvas
      dpr={[1, 2]}
      style={{width: '100%', height: '100%', background: 'transparent'}}>
      <Scene />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        maxPolarAngle={Math.PI / 2}
        minPolarAngle={Math.PI / 2}
      />
    </Canvas>
  );
}
