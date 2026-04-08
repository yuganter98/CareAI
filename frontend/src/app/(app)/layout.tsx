"use client";

import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { usePathname } from "next/navigation";

export default function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const isDashboard = pathname === "/dashboard";

  return (
    <ProtectedRoute>
      {/* ── Fixed full-screen video backdrop (all pages) ── */}
      <div className="fixed inset-0 z-0 overflow-hidden">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
        >
          <source src="/banner.mp4" type="video/mp4" />
        </video>
        {/* Dark overlay for readability */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900/85 via-slate-900/70 to-blue-900/60" />
      </div>

      {/* ── App shell (sits above the video) ── */}
      <div className="relative z-10 min-h-screen">
        <Navbar transparent={true} />
        <div className="flex max-w-[1600px] mx-auto">
          <Sidebar transparent={true} />
          <main className="flex-1 p-6 md:p-8 overflow-y-auto min-h-[calc(100vh-4rem)] bg-transparent">
            <div className="max-w-5xl mx-auto">
              {children}
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
