"use client";

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { useEffect, useState } from "react";
import { CareAI } from "@/lib/api";
import { Loader2, TrendingUp } from "lucide-react";

const METRIC_COLORS: Record<string, { stroke: string; fill: string }> = {
  glucose:     { stroke: "#60a5fa", fill: "url(#gradBlue)"    },
  hemoglobin:  { stroke: "#a78bfa", fill: "url(#gradViolet)" },
  creatinine:  { stroke: "#34d399", fill: "url(#gradEmerald)"},
  cholesterol: { stroke: "#fbbf24", fill: "url(#gradAmber)"  },
  platelets:   { stroke: "#f87171", fill: "url(#gradRed)"    },
};
const DEFAULT_GRADIENT = { stroke: "#60a5fa", fill: "url(#gradBlue)" };

export function ChartComponent({ transparent = false }: { transparent?: boolean }) {
  const [data, setData] = useState<any[]>([]);
  const [metricName, setMetricName] = useState<string>("telemetry");
  const [allMetrics, setAllMetrics] = useState<Record<string, any[]>>({});
  const [metricKeys, setMetricKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    CareAI.getChartTrends()
      .then((res: any) => {
        if (res && Object.keys(res).length > 0) {
          setAllMetrics(res);
          const keys = Object.keys(res);
          setMetricKeys(keys);
          const defaultKey = keys.find(k => k.includes("glucose")) || keys[0];
          setMetricName(defaultKey);
          setData(res[defaultKey]);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const colors = METRIC_COLORS[metricName] || DEFAULT_GRADIENT;

  return (
    <div className="w-full h-full min-h-[300px] flex flex-col">
      <div className="mb-5 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-xl ${transparent ? "bg-white/10" : "bg-blue-50"}`}>
            <TrendingUp className={`h-4 w-4 ${transparent ? "text-blue-300" : "text-blue-600"}`} />
          </div>
          <div>
            <h3 className={`font-bold text-base ${transparent ? "text-white" : "text-slate-900"}`}>Clinical Trend Matrix</h3>
            <p className={`text-xs ${transparent ? "text-white/40" : "text-slate-400"}`}>AI-plotted biomarker telemetry</p>
          </div>
        </div>
        {!loading && metricKeys.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {metricKeys.map(key => (
              <button
                key={key}
                onClick={() => { setMetricName(key); setData(allMetrics[key]); }}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all capitalize ${
                  metricName === key
                    ? transparent
                      ? "bg-white/20 text-white border-white/30"
                      : "bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-200"
                    : transparent
                      ? "bg-white/5 text-white/50 border-white/10 hover:bg-white/10 hover:text-white"
                      : "bg-white text-slate-500 border-slate-200 hover:border-blue-300 hover:text-blue-600"
                }`}
              >
                {key.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 w-full min-h-[280px] flex items-center justify-center">
        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className={`h-8 w-8 animate-spin ${transparent ? "text-white/50" : "text-blue-600"}`} />
            <span className={`text-xs ${transparent ? "text-white/30" : "text-slate-400"}`}>Loading metrics...</span>
          </div>
        ) : data.length === 0 ? (
          <div className={`h-full w-full flex flex-col items-center justify-center text-center border-2 border-dashed rounded-2xl py-12 ${
            transparent ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-50/50"
          }`}>
            <TrendingUp className={`h-10 w-10 mb-3 ${transparent ? "text-white/15" : "text-slate-200"}`} />
            <p className={`font-medium text-sm ${transparent ? "text-white/40" : "text-slate-400"}`}>No telemetry data yet.</p>
            <p className={`text-xs mt-1 ${transparent ? "text-white/20" : "text-slate-300"}`}>Upload a report to generate trend charts.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data} margin={{ top: 10, right: 10, bottom: 5, left: -10 }}>
              <defs>
                <linearGradient id="gradBlue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#60a5fa" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradViolet" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradEmerald" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34d399" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradAmber" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#fbbf24" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradRed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f87171" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#f87171" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={transparent ? "rgba(255,255,255,0.06)" : "#f1f5f9"} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: transparent ? "rgba(255,255,255,0.35)" : "#94a3b8" }} dy={8} />
              <YAxis 
                domain={['auto', 'auto']} 
                axisLine={false} 
                tickLine={false} 
                tick={{ fontSize: 11, fill: transparent ? "rgba(255,255,255,0.35)" : "#94a3b8" }} 
                dx={-5} 
              />
              <Tooltip
                contentStyle={{
                  borderRadius: "12px",
                  border: transparent ? "1px solid rgba(255,255,255,0.15)" : "1px solid #e2e8f0",
                  boxShadow: "0 10px 25px -5px rgb(0 0 0 / 0.2)",
                  fontWeight: 600, fontSize: 13, padding: "10px 14px",
                  background: transparent ? "rgba(15,23,42,0.85)" : "#fff",
                  color: transparent ? "#fff" : "#1e293b",
                }}
                itemStyle={{ color: colors.stroke }}
                labelStyle={{ color: transparent ? "rgba(255,255,255,0.5)" : "#64748b", fontWeight: 500, fontSize: 11 }}
              />
              <Area type="monotone" dataKey="value" stroke={colors.stroke} strokeWidth={2.5} fill={colors.fill}
                dot={{ r: 4, fill: colors.stroke, strokeWidth: 0 }}
                activeDot={{ r: 6, fill: colors.stroke, strokeWidth: 3, stroke: transparent ? "rgba(255,255,255,0.3)" : "#fff" }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
