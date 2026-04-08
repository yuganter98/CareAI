import Link from "next/link";
import { FileText, Pill, AlertTriangle, Home, Settings, BarChart2, Sparkles } from "lucide-react";

export function Sidebar({ transparent = false }: { transparent?: boolean }) {
  const base = transparent
    ? "text-white/60 hover:text-white hover:bg-white/10"
    : "text-slate-600 hover:text-blue-600 hover:bg-blue-50";

  const sectionLabel = transparent ? "text-white/30" : "text-slate-400";

  return (
    <aside className={`w-64 border-r min-h-[calc(100vh-4rem)] hidden md:block ${
      transparent
        ? "border-white/10 bg-white/5 backdrop-blur-md"
        : "bg-slate-50/40"
    }`}>
      <nav className="flex flex-col gap-1.5 p-4 text-sm font-medium">
        <Link href="/dashboard" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${base}`}>
          <Home className="h-4 w-4" />
          Overview
        </Link>
        
        <div className="pt-4 pb-2">
          <p className={`px-3 text-xs font-semibold uppercase tracking-wider ${sectionLabel}`}>Clinical Data</p>
        </div>
        
        <Link href="/reports" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${base}`}>
          <FileText className="h-4 w-4" />
          Medical Reports
        </Link>
        <Link href="/medications" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${base}`}>
          <Pill className="h-4 w-4" />
          Medications
        </Link>
        <Link href="/analytics" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${base}`}>
          <BarChart2 className="h-4 w-4" />
          Analytics
        </Link>
        
        <div className="pt-4 pb-2">
          <p className={`px-3 text-xs font-semibold uppercase tracking-wider ${sectionLabel}`}>AI Copilot</p>
        </div>

        <Link href="/copilot" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${
          transparent ? "text-amber-300/80 hover:text-amber-200 hover:bg-white/10" : "text-slate-600 hover:text-violet-600 hover:bg-violet-50"
        }`}>
          <Sparkles className={`h-4 w-4 ${transparent ? "text-amber-400" : "text-amber-500"}`} />
          Health Copilot
        </Link>
        
        <div className="pt-4 pb-2">
          <p className={`px-3 text-xs font-semibold uppercase tracking-wider ${sectionLabel}`}>Action Agents</p>
        </div>

        <Link href="/emergency" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${
          transparent ? "text-red-300/70 hover:text-red-200 hover:bg-white/10" : "text-slate-600 hover:text-red-600 hover:bg-red-50"
        }`}>
          <AlertTriangle className={`h-4 w-4 ${transparent ? "text-red-400" : "text-red-500"}`} />
          Emergency Protocol
        </Link>
        
        <div className="mt-auto pt-8">
           <Link href="/settings" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all group ${base}`}>
             <Settings className="h-4 w-4" />
             Settings
           </Link>
        </div>
      </nav>
    </aside>
  );
}
