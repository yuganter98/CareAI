"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CareAI } from "@/lib/api";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    // Verify session by calling the backend — httpOnly cookie is sent automatically
    CareAI.getProfile()
      .then(() => setIsAuthenticated(true))
      .catch(() => router.push("/login"));
  }, [router]);

  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen w-full bg-slate-50 flex items-center justify-center text-slate-400 font-medium">
        Loading CareAI...
      </div>
    );
  }

  return <>{children}</>;
}
