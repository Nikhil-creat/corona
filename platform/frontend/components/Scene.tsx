"use client";
import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Detailed, Line, OrbitControls, PerformanceMonitor } from "@react-three/drei";
import * as THREE from "three";
import { MAX_EMITTERS, fieldFragment, fieldVertex, nodeFragment, nodeVertex } from "@/lib/shaders";
import { get, set, useStore, type NodeStatus } from "@/lib/store";

const STATUS_COLOR: Record<NodeStatus, THREE.Color> = {
  nominal: new THREE.Color("#38bdf8"), investigating: new THREE.Color("#22d3ee"),
  awaiting_approval: new THREE.Color("#fbbf24"), remediated: new THREE.Color("#34d399"), escalated: new THREE.Color("#f87171"),
};

export function heatOf(t?: { temperature_c: number; stress_pct: number; vibration_mm_s: number }): number {
  if (!t) return 0;
  return Math.min(1, Math.max(t.temperature_c / 115, t.stress_pct / 100, t.vibration_mm_s / 12));
}

function HeatField() {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const uniforms = useMemo(() => ({
    uPts: { value: Array.from({ length: MAX_EMITTERS }, () => new THREE.Vector3()) },
    uCount: { value: 0 }, uSize: { value: 44 }, uTime: { value: 0 },
  }), []);
  useFrame(({ clock }) => {
    const { topology, nodes } = get();
    if (!topology || !mat.current) return;
    const pts = mat.current.uniforms.uPts!.value as THREE.Vector3[];
    topology.nodes.slice(0, MAX_EMITTERS).forEach((n, i) => pts[i]!.set(n.x, n.z, heatOf(nodes[n.id])));
    mat.current.uniforms.uCount!.value = Math.min(topology.nodes.length, MAX_EMITTERS);
    mat.current.uniforms.uTime!.value = clock.elapsedTime;
  });
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]}>
      <planeGeometry args={[44, 44]} />
      <shaderMaterial ref={mat} uniforms={uniforms} vertexShader={fieldVertex} fragmentShader={fieldFragment} transparent depthWrite={false} />
    </mesh>
  );
}

function TwinNode({ id, x, z }: { id: string; x: number; z: number }) {
  const selected = useStore((s) => s.selected === id);
  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: nodeVertex, fragmentShader: nodeFragment,
    uniforms: { uHeat: { value: 0 }, uPulse: { value: 0 }, uTime: { value: 0 }, uStatus: { value: new THREE.Color("#38bdf8") } },
  }), []);
  const group = useRef<THREE.Group>(null);
  useFrame(({ clock }, dt) => {
    const s = get();
    const target = heatOf(s.nodes[id]);
    const u = material.uniforms as Record<string, THREE.IUniform>;
    u.uHeat!.value += (target - (u.uHeat!.value as number)) * Math.min(1, dt * 4);
    const status = s.nodeStatus[id] ?? "nominal";
    (u.uStatus!.value as THREE.Color).lerp(STATUS_COLOR[status], Math.min(1, dt * 6));
    u.uPulse!.value = status === "nominal" ? 0 : 0.5 + 0.5 * Math.sin(clock.elapsedTime * 6);
    u.uTime!.value = clock.elapsedTime;
    if (group.current) group.current.scale.setScalar(selected ? 1.25 : 1);
  });
  return (
    <group ref={group} position={[x, 1.2, z]} onClick={(e) => { e.stopPropagation(); set({ selected: id }); }}>
      {/* dynamic level of detail: full mesh near, simplified mid, box far */}
      <Detailed distances={[0, 22, 46]}>
        <mesh material={material}><icosahedronGeometry args={[1.2, 4]} /></mesh>
        <mesh material={material}><icosahedronGeometry args={[1.2, 1]} /></mesh>
        <mesh material={material}><boxGeometry args={[1.6, 1.6, 1.6]} /></mesh>
      </Detailed>
    </group>
  );
}

function Links() {
  const topology = useStore((s) => s.topology);
  if (!topology) return null;
  const pos = new Map(topology.nodes.map((n) => [n.id, [n.x, 1.2, n.z] as [number, number, number]]));
  return <>{topology.edges.map(([a, b]) => {
    const pa = pos.get(a), pb = pos.get(b);
    return pa && pb ? <Line key={`${a}-${b}`} points={[pa, pb]} color="#1e3a5f" lineWidth={1} transparent opacity={0.6} /> : null;
  })}</>;
}

function World() {
  const topology = useStore((s) => s.topology);
  return (
    <>
      <color attach="background" args={["#05070d"]} />
      <fog attach="fog" args={["#05070d", 40, 110]} />
      <HeatField />
      <Links />
      {topology?.nodes.map((n) => <TwinNode key={n.id} id={n.id} x={n.x} z={n.z} />)}
      <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2.1} minDistance={12} maxDistance={70} />
    </>
  );
}

export default function Scene() {
  const [dpr, setDpr] = useState(1.5);
  return (
    <Canvas camera={{ position: [0, 26, 34], fov: 48 }} dpr={dpr} gl={{ antialias: true, powerPreference: "high-performance" }}
            onPointerMissed={() => set({ selected: null })}>
      {/* adaptive resolution: drops DPR when frame time degrades, restores when headroom returns */}
      <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(1.75)} />
      <World />
    </Canvas>
  );
}
