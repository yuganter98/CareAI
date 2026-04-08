"use client";
import { useEffect, useState } from "react";
import {
  FileText, Activity, TrendingUp,
  Loader2, Sparkles, ArrowUpRight, Brain, Shield, Heart
} from "lucide-react";
import { ChartComponent } from "@/components/dashboard/ChartComponent";
import { CareAI } from "@/lib/api";
import Link from "next/link";

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [greeting, setGreeting] = useState("");
  const [userName, setUserName] = useState("");

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setGreeting("Good morning");
    else if (hour < 17) setGreeting("Good afternoon");
    else setGreeting("Good evening");

    async function loadRealData() {
      try {
        const [meds, reports, insightsData, profile] = await Promise.all([
          CareAI.getMedications().catch(() => ({ medications: [] })),
          CareAI.getMyReports().catch(() => []),
          CareAI.getInsights().catch(() => null),
          CareAI.getProfile().catch(() => null),
        ]);
        if (profile?.name) setUserName(profile.name.split(" ")[0]);
        setData({
          prescriptionsCount: meds?.medications?.length || 0,
          reportsAnalyzed: reports?.length || 0,
          riskLevel: reports?.length > 0 ? "MEDIUM" : "N/A",
          trend: insightsData?.insights?.length > 0 ? "Tracking" : "Awaiting Data",
          insightsArray: insightsData?.insights || [],
        });
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadRealData();
  }, []);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center flex-col gap-4">
        <div className="relative">
          <div className="h-16 w-16 rounded-full bg-white/10 backdrop-blur-xl animate-pulse border border-white/20" />
          <Loader2 className="h-8 w-8 animate-spin text-white absolute top-4 left-4" />
        </div>
        <p className="text-sm text-white/50 font-medium animate-pulse">Loading your health dashboard...</p>
      </div>
    );
  }

  // Risk indicator colors
  const riskDot = data.riskLevel === "HIGH" ? "bg-red-500" : data.riskLevel === "MEDIUM" ? "bg-amber-400" : "bg-emerald-400";

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-[1200px]">

      {/* ── Hero greeting ── */}
      <div className="flex items-center justify-between pt-2">
        <div>
          <div className="flex items-center gap-3 mb-3">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400" />
            </span>
            <span className="text-emerald-300/80 text-xs font-semibold tracking-wider uppercase">System Online</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">
            {greeting}{userName ? `, ${userName}` : ""} 👋
          </h1>
          <p className="text-white/50 mt-2 text-sm max-w-lg">
            Your AI-powered clinical intelligence overview — insights from all reports, metrics, and trends.
          </p>
        </div>
        <div className="flex gap-3 shrink-0">
          <Link
            href="/copilot"
            className="flex items-center gap-2 px-5 py-3 bg-white/10 backdrop-blur-md text-white text-sm font-semibold rounded-xl hover:bg-white/20 transition-all active:scale-95 border border-white/15 shadow-lg"
          >
            <Sparkles className="h-4 w-4 text-amber-300" /> Ask Copilot
          </Link>
          <Link
            href="/reports"
            className="flex items-center gap-2 px-5 py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-500 transition-all active:scale-95 shadow-lg shadow-blue-600/30"
          >
            <FileText className="h-4 w-4" /> Upload Report
          </Link>
        </div>
      </div>

      {/* ── Glassmorphic stat cards ── */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl p-5 hover:bg-white/15 transition-all">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="h-4 w-4 text-amber-300" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/50">Risk Level</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${riskDot} opacity-75`} />
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${riskDot}`} />
            </span>
            <span className="text-2xl font-bold text-white">{data.riskLevel}</span>
          </div>
          <p className="text-[11px] text-white/30 mt-2">Based on latest analysis</p>
        </div>

        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl p-5 hover:bg-white/15 transition-all">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="h-4 w-4 text-blue-300" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/50">Prescriptions</span>
          </div>
          <span className="text-2xl font-bold text-white">{data.prescriptionsCount}</span>
          <p className="text-[11px] text-white/30 mt-2">Active medications tracked</p>
        </div>

        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl p-5 hover:bg-white/15 transition-all">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="h-4 w-4 text-violet-300" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/50">Reports</span>
          </div>
          <span className="text-2xl font-bold text-white">{data.reportsAnalyzed}</span>
          <p className="text-[11px] text-white/30 mt-2">Documents analyzed by AI</p>
        </div>

        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl p-5 hover:bg-white/15 transition-all">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-4 w-4 text-emerald-300" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/50">Trend</span>
          </div>
          <span className="text-xl font-bold text-emerald-300">{data.trend}</span>
          <p className="text-[11px] text-white/30 mt-2">ML-powered pattern analysis</p>
        </div>
      </div>

      {/* ── Chart + Insights (glassmorphic panels) ── */}
      <div className="grid gap-5 lg:grid-cols-7">
        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl p-6 lg:col-span-4 min-h-[420px] flex flex-col">
          <ChartComponent transparent />
        </div>

        <div className="backdrop-blur-xl bg-white/10 border border-white/15 rounded-2xl lg:col-span-3 flex flex-col max-h-[420px] overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10 flex items-center gap-3 sticky top-0 backdrop-blur-xl bg-white/5 z-10">
            <div className="p-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600">
              <Brain className="h-4 w-4 text-white" />
            </div>
            <h3 className="font-bold text-white">AI Clinical Insights</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            {data?.insightsArray && data.insightsArray.length > 0 ? (
              <ul className="space-y-3">
                {data.insightsArray.map((insight: string, idx: number) => (
                  <li key={idx} className="flex gap-3 text-sm text-white/70 items-start p-3 rounded-xl hover:bg-white/5 transition-colors">
                    <div className="mt-1.5 shrink-0">
                      <div className="h-2 w-2 rounded-full bg-blue-400 ring-4 ring-blue-400/10" />
                    </div>
                    <span className="leading-relaxed">{insight}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center py-8">
                <div className="bg-white/5 p-4 rounded-2xl mb-4 border border-white/10">
                  <Heart className="h-8 w-8 text-white/20" />
                </div>
                <p className="text-white/40 font-medium text-sm">No insights generated yet.</p>
                <p className="text-white/20 text-xs mt-1">Upload a report to unlock AI analysis.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Quick Actions (glassmorphic) ── */}
      <div className="grid gap-4 md:grid-cols-3 pb-4">
        <Link href="/reports" className="group p-5 rounded-2xl backdrop-blur-xl bg-white/5 border border-white/10 hover:bg-white/15 transition-all flex items-center gap-4">
          <div className="p-3 rounded-xl bg-blue-500/20 group-hover:bg-blue-500/30 transition-colors">
            <FileText className="h-5 w-5 text-blue-300" />
          </div>
          <div className="flex-1">
            <h4 className="font-semibold text-white text-sm">Upload Reports</h4>
            <p className="text-xs text-white/40 mt-0.5">Process new lab results</p>
          </div>
          <ArrowUpRight className="h-4 w-4 text-white/20 group-hover:text-white/60 transition-colors" />
        </Link>

        <Link href="/analytics" className="group p-5 rounded-2xl backdrop-blur-xl bg-white/5 border border-white/10 hover:bg-white/15 transition-all flex items-center gap-4">
          <div className="p-3 rounded-xl bg-violet-500/20 group-hover:bg-violet-500/30 transition-colors">
            <TrendingUp className="h-5 w-5 text-violet-300" />
          </div>
          <div className="flex-1">
            <h4 className="font-semibold text-white text-sm">View Analytics</h4>
            <p className="text-xs text-white/40 mt-0.5">Compare metrics over time</p>
          </div>
          <ArrowUpRight className="h-4 w-4 text-white/20 group-hover:text-white/60 transition-colors" />
        </Link>

        <Link href="/copilot" className="group p-5 rounded-2xl backdrop-blur-xl bg-white/5 border border-white/10 hover:bg-white/15 transition-all flex items-center gap-4">
          <div className="p-3 rounded-xl bg-amber-500/20 group-hover:bg-amber-500/30 transition-colors">
            <Sparkles className="h-5 w-5 text-amber-300" />
          </div>
          <div className="flex-1">
            <h4 className="font-semibold text-white text-sm">Health Copilot</h4>
            <p className="text-xs text-white/40 mt-0.5">Ask AI about your health</p>
          </div>
          <ArrowUpRight className="h-4 w-4 text-white/20 group-hover:text-white/60 transition-colors" />
        </Link>
      </div>
    </div>
  );
}
