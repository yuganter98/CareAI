"use client";

import Link from "next/link";
import { Activity, LogOut, Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CareAI } from "@/lib/api";

export function Navbar({ transparent = false }: { transparent?: boolean }) {
  const router = useRouter();
  const [initials, setInitials] = useState("...");
  const [userName, setUserName] = useState("");

  useEffect(() => {
    CareAI.getProfile()
      .then((user: any) => {
        const name = user.name || user.email || "";
        setUserName(name);
        const parts = name.trim().split(/\s+/);
        if (parts.length >= 2) {
          setInitials((parts[0][0] + parts[parts.length - 1][0]).toUpperCase());
        } else if (parts.length === 1 && parts[0]) {
          setInitials(parts[0].substring(0, 2).toUpperCase());
        }
      })
      .catch(() => setInitials("?"));
  }, []);

  const handleLogout = async () => {
    try {
      await CareAI.logout();
    } catch (e) {
      console.error("Logout failed", e);
    }
    localStorage.removeItem("careai_token"); // backup clear
    router.push("/login");
  };

  return (
    <header className={`sticky top-0 z-50 w-full border-b transition-all ${
      transparent
        ? "border-white/10 bg-white/5 backdrop-blur-xl"
        : "border-slate-200/80 bg-white/80 backdrop-blur-xl"
    }`}>
      <div className="flex h-16 items-center px-6 justify-between max-w-[1600px] mx-auto">
        <Link href="/dashboard" className="flex items-center space-x-2.5 group">
          <div className="bg-gradient-to-br from-blue-600 to-violet-600 p-1.5 rounded-xl shadow-md shadow-blue-200/50 group-hover:shadow-lg transition-all">
             <Activity className="h-5 w-5 text-white" />
          </div>
          <span className={`text-xl font-bold tracking-tight ${
            transparent ? "text-white" : "bg-gradient-to-r from-slate-900 to-slate-600 bg-clip-text text-transparent"
          }`}>CareAI</span>
        </Link>
        
        <div className="flex items-center space-x-6">
          <nav className="hidden md:flex items-center space-x-1 text-sm font-medium">
            <Link href="/dashboard" className={`px-3 py-2 rounded-lg transition-colors ${
              transparent ? "text-white/70 hover:text-white hover:bg-white/10" : "text-slate-600 hover:text-blue-600 hover:bg-blue-50"
            }`}>Dashboard</Link>
            <Link href="/analytics" className={`px-3 py-2 rounded-lg transition-colors ${
              transparent ? "text-white/70 hover:text-white hover:bg-white/10" : "text-slate-600 hover:text-blue-600 hover:bg-blue-50"
            }`}>Analytics</Link>
            <Link href="/copilot" className={`px-3 py-2 rounded-lg transition-colors ${
              transparent ? "text-white/70 hover:text-white hover:bg-white/10" : "text-slate-600 hover:text-violet-600 hover:bg-violet-50"
            }`}>Copilot</Link>
          </nav>
          
          <div className={`flex items-center gap-3 ml-2 border-l pl-5 ${transparent ? "border-white/15" : "border-slate-200"}`}>
            <button className={`relative p-2 rounded-lg transition-colors ${
              transparent ? "text-white/50 hover:text-white hover:bg-white/10" : "text-slate-400 hover:text-blue-600 hover:bg-blue-50"
            }`}>
              <Bell className="h-4 w-4" />
              <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-red-500 rounded-full" />
            </button>

            <Link
              href="/settings"
              className="h-9 w-9 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold cursor-pointer hover:scale-105 active:scale-95 transition-all shadow-md shadow-blue-200/50"
              title={userName || "Profile"}
            >
              {initials}
            </Link>

            <button 
              onClick={handleLogout} 
              className={`flex items-center gap-2 text-sm font-medium p-2 rounded-lg transition-colors ${
                transparent ? "text-white/50 hover:text-red-300 hover:bg-white/10" : "text-slate-400 hover:text-red-600 hover:bg-red-50"
              }`}
              title="Sign Out"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden lg:inline">Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
