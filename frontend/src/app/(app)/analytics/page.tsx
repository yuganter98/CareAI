"use client";

import { useState, useEffect } from "react";
import { BarChart2, TrendingUp, Activity } from "lucide-react";
import { CareAI } from "@/lib/api";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from "recharts";

const METRIC_COLORS: Record<string, string> = {
  glucose: "#2563eb",
  hemoglobin: "#16a34a",
  creatinine: "#d97706",
  vitamin_b12: "#7c3aed",
  hba1c: "#dc2626",
  cholesterol: "#0891b2",
  uric_acid: "#db2777",
};

const getColor = (key: string, idx: number) => {
  const fallbacks = ["#2563eb","#16a34a","#d97706","#7c3aed","#dc2626","#0891b2","#db2777"];
  return METRIC_COLORS[key] || fallbacks[idx % fallbacks.length];
};

export default function AnalyticsPage() {
  const [trends, setTrends] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState(true);
  const [activeMetric, setActiveMetric] = useState<string | null>(null);

  useEffect(() => {
    CareAI.getChartTrends()
      .then((res: any) => {
        if (res && Object.keys(res).length > 0) {
          setTrends(res);
          setActiveMetric(Object.keys(res)[0]);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const metricKeys = Object.keys(trends);

  // Build a unified dataset for the bar comparison chart (latest value per metric)
  const latestValues = metricKeys.map((key, i) => {
    const arr = trends[key];
    const latest = arr[arr.length - 1];
    return {
      name: key.replace(/_/g, " ").toUpperCase(),
      value: latest?.value ?? 0,
      unit: latest?.unit ?? "",
      fill: getColor(key, i),
    };
  });

  // Build the detail dataset for the selected metric line chart
  const detailData = activeMetric ? trends[activeMetric] : [];

  if (loading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
          <p className="text-slate-500 font-medium">Loading your telemetry analytics...</p>
        </div>
      </div>
    );
  }

  if (metricKeys.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] text-center gap-4">
        <BarChart2 className="h-16 w-16 text-slate-200" />
        <h2 className="text-2xl font-bold text-slate-700">No analytics data yet</h2>
        <p className="text-slate-500 max-w-sm">Upload and process at least one medical report to unlock the full clinical analytics suite.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 flex items-center gap-3">
          <BarChart2 className="h-8 w-8 text-blue-600" /> Clinical Analytics
        </h1>
        <p className="text-slate-500 mt-2">
          Side-by-side metric comparisons across all your processed reports.
        </p>
      </div>

      {/* Stat Pills Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {latestValues.slice(0, 4).map((m, i) => (
          <div key={i} className="rounded-xl border bg-white shadow-sm p-5 hover:shadow-md transition-shadow">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">{m.name}</p>
            <p className="text-2xl font-bold" style={{ color: m.fill }}>{m.value}</p>
            <p className="text-xs text-slate-400 mt-0.5">{m.unit || "—"}</p>
          </div>
        ))}
      </div>

      {/* Side-by-side Comparison Bar Chart */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6">
        <div className="flex items-center gap-3 mb-6">
          <Activity className="h-5 w-5 text-blue-600" />
          <h2 className="font-bold text-lg text-slate-900">Latest Reading Comparison</h2>
          <span className="ml-auto text-xs text-slate-400">All extracted metrics vs. each other</span>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={latestValues} margin={{ top: 5, right: 20, bottom: 20, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} angle={-20} textAnchor="end" dy={8} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} dx={-5} />
            <Tooltip
              contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              formatter={(value: any, name: any, props: any) => [`${value} ${props.payload?.unit || ""}`, "Latest Value"]}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {latestValues.map((entry, index) => (
                <rect key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Individual Metric Deep-dive Line Chart */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6">
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <TrendingUp className="h-5 w-5 text-blue-600 shrink-0" />
          <h2 className="font-bold text-lg text-slate-900">Time-Series Deep Dive</h2>
          <div className="ml-auto flex flex-wrap gap-2">
            {metricKeys.map((key, i) => (
              <button
                key={key}
                onClick={() => setActiveMetric(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold tracking-wide transition-all border ${
                  activeMetric === key
                    ? "text-white border-transparent shadow-sm"
                    : "text-slate-500 border-slate-200 bg-white hover:border-slate-300"
                }`}
                style={activeMetric === key ? { backgroundColor: getColor(key, i) } : {}}
              >
                {key.replace(/_/g, " ").toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={detailData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} dy={10} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} dx={-10} />
            <Tooltip
              contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              formatter={(value: any) => [value, activeMetric?.replace(/_/g, " ").toUpperCase()]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={activeMetric ? getColor(activeMetric, metricKeys.indexOf(activeMetric)) : "#2563eb"}
              strokeWidth={3}
              dot={{ r: 5, strokeWidth: 0 }}
              activeDot={{ r: 7, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
