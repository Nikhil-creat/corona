"use client";
import dynamic from "next/dynamic";
import ApprovalPanel from "@/components/ApprovalPanel";
import Hud from "@/components/Hud";
import InspectorDrawer from "@/components/InspectorDrawer";
import { useStream } from "@/lib/useStream";

const Scene = dynamic(() => import("@/components/Scene"), { ssr: false });

export default function Page() {
  useStream();
  return (
    <main className="relative h-screen w-screen">
      <Scene />
      <Hud />
      <ApprovalPanel />
      <InspectorDrawer />
    </main>
  );
}
