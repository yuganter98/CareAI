"use client";

import { useState, useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import {
  ArrowLeft, MessageSquare, Loader2, FileText, Send,
  CheckCircle2, XCircle, Clock, Activity, ChevronDown, ChevronUp,
  Wifi, WifiOff, Radio
} from "lucide-react";
import Link from "next/link";
import { CareAI } from "@/lib/api";
import { useAgentStream, type AgentState } from "@/hooks/useAgentStream";

// ─── Markdown helpers ─────────────────────────────────────────────────────────
const parseBold = (text: string) =>
  text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>
  );

const formatMessage = (text: string) =>
  text.split("\n").map((line, i) => {
    if (line.trim() === "```markdown" || line.trim() === "```") return null;
    if (line.trim().startsWith("* ") || line.trim().startsWith("- "))
      return <li key={i} className="ml-5 list-disc mb-1.5 leading-relaxed">{parseBold(line.trim().substring(2))}</li>;
    if (line.trim() === "") return <div key={i} className="h-2" />;
    return <p key={i} className="mb-2.5 leading-relaxed">{parseBold(line)}</p>;
  });

// ─── Agent visual metadata ───────────────────────────────────────────────────
const AGENT_META: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  ReportAnalyzerAgent: { label: "Report Analyzer",  color: "text-blue-600",    bg: "bg-blue-50 border-blue-200",     icon: "📄" },
  DiagnosisAgent:      { label: "Diagnosis Engine",  color: "text-violet-600",  bg: "bg-violet-50 border-violet-200", icon: "🔬" },
  InsightsAgent:       { label: "Insights Agent",    color: "text-emerald-600", bg: "bg-emerald-50 border-emerald-200",icon: "💡" },
  EmergencyAgent:      { label: "Emergency Agent",   color: "text-red-600",     bg: "bg-red-50 border-red-200",       icon: "🚨" },
};

// ─── Status icon ──────────────────────────────────────────────────────────────
function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />;
  if (status === "failed")    return <XCircle      className="h-4 w-4 text-red-500 shrink-0" />;
  return <Loader2 className="h-4 w-4 text-blue-500 animate-spin shrink-0" />;
}

// ─── Duration formatter ───────────────────────────────────────────────────────
function formatDuration(ms: number | null): string | null {
  if (ms == null) return null;
  if (ms < 1)     return "< 1ms";
  if (ms < 1000)  return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ─── Connection badge ─────────────────────────────────────────────────────────
function ConnectionBadge({ mode }: { mode: "ws" | "polling" | "disconnected" }) {
  if (mode === "ws") return (
    <span className="flex items-center gap-1.5 text-[11px] text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 font-semibold">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
      </span>
      Live
    </span>
  );
  if (mode === "polling") return (
    <span className="flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200 font-semibold">
      <Radio className="h-3 w-3" /> Polling
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-[11px] text-slate-400 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200 font-semibold">
      <WifiOff className="h-3 w-3" /> Offline
    </span>
  );
}

// ─── Agent Execution Timeline ─────────────────────────────────────────────────
function AgentTimeline({ reportId }: { reportId: string }) {
  const { agents, connected, loading } = useAgentStream(reportId);
  const [open, setOpen] = useState(true);

  // Count completed agents
  const completed = agents.filter(a => a.status === "completed").length;
  const total     = agents.length;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-6 py-4 bg-slate-50 border-b border-slate-200 hover:bg-slate-100 transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <Activity className="h-5 w-5 text-blue-600" />
          <span className="font-semibold text-slate-800">Agent Execution Timeline</span>
          {!loading && total > 0 && (
            <span className="text-xs bg-blue-100 text-blue-700 px-2.5 py-0.5 rounded-full font-bold">
              {completed}/{total} complete
            </span>
          )}
          <ConnectionBadge mode={connected} />
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>

      {/* Body */}
      {open && (
        <div className="p-6">
          {loading ? (
            <div className="flex items-center gap-3 text-slate-400 justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm font-medium">Fetching agent execution history...</span>
            </div>
          ) : agents.length === 0 ? (
            <div className="text-center py-8">
              <Activity className="h-10 w-10 text-slate-200 mx-auto mb-3" />
              <p className="text-sm text-slate-400 font-medium">No agent activity yet.</p>
              <p className="text-xs text-slate-300 mt-1">Process a report to see live execution traces here.</p>
            </div>
          ) : (
            <div className="relative">
              {/* Vertical spine */}
              <div className="absolute left-5 top-4 bottom-4 w-px bg-gradient-to-b from-blue-200 via-violet-200 to-emerald-200 z-0" />

              <ol className="space-y-4 relative z-10">
                {agents.map((agent) => {
                  const meta = AGENT_META[agent.agent_name] ?? {
                    label: agent.agent_name, color: "text-slate-600",
                    bg: "bg-slate-50 border-slate-200", icon: "⚙️"
                  };
                  const dur = formatDuration(agent.duration_ms);

                  return (
                    <li
                      key={agent.agent_name}
                      className="flex items-start gap-4 animate-in fade-in slide-in-from-left-4 duration-300"
                    >
                      {/* Step node */}
                      <div className={`h-10 w-10 rounded-full flex items-center justify-center border-2 shrink-0 ${meta.bg} z-10 shadow-sm`}>
                        <StatusIcon status={agent.status} />
                      </div>

                      {/* Card */}
                      <div className={`flex-1 rounded-xl border p-4 ${meta.bg} transition-all ${
                        agent.status === "started" ? "ring-2 ring-blue-300 ring-offset-1" : ""
                      }`}>
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-base">{meta.icon}</span>
                            <span className={`font-bold text-sm ${meta.color}`}>{meta.label}</span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-slate-400">
                            {dur && (
                              <span className="flex items-center gap-1 bg-white/60 px-2 py-0.5 rounded-md border border-slate-200/50">
                                <Clock className="h-3 w-3" /> {dur}
                              </span>
                            )}
                            <span>{new Date(agent.timestamp).toLocaleTimeString()}</span>
                          </div>
                        </div>

                        {/* Status line */}
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className={`text-xs font-semibold uppercase tracking-wider ${
                            agent.status === "completed" ? "text-emerald-600" :
                            agent.status === "failed"    ? "text-red-600"     :
                            "text-blue-600"
                          }`}>
                            {agent.status === "started" ? "Running..." : agent.status}
                          </span>
                          {agent.message && (
                            <span className="text-xs text-slate-400 truncate max-w-[300px]">— {agent.message}</span>
                          )}
                        </div>

                        {/* Progress bar for running agents */}
                        {agent.status === "started" && (
                          <div className="mt-3 h-1 w-full bg-blue-100 rounded-full overflow-hidden">
                            <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: "60%" }} />
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function ReportAnalysisPage() {
  const pathname = usePathname();
  const reportId = pathname.split("/").pop() || "";
  const bottomRef = useRef<HTMLDivElement>(null);

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState<{ role: string; text: string }[]>([]);

  const askQuestion = async () => {
    if (!question.trim()) return;
    const q = question;
    setQuestion("");
    setConversation(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);
    try {
      const res = await CareAI.queryRAG(reportId, q);
      setConversation(prev => [...prev, { role: "ai", text: res.answer }]);
    } catch (err: any) {
      setConversation(prev => [...prev, { role: "error", text: "Failed: " + err.message }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation, loading]);

  return (
    <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500 max-w-4xl mx-auto pb-10">
      <Link href="/reports" className="text-sm font-medium text-slate-500 hover:text-slate-900 flex items-center gap-2">
        <ArrowLeft className="h-4 w-4" /> Back to Vault
      </Link>

      <div className="flex items-center gap-4 border-b pb-4">
        <div className="bg-blue-100 p-3 rounded-xl text-blue-600">
          <FileText className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Medical Analysis Console</h1>
          <p className="text-slate-500 text-sm font-mono">Document ID: {reportId.substring(0, 16)}…</p>
        </div>
      </div>

      {/* ── Real-time Agent Timeline ── */}
      <AgentTimeline reportId={reportId} />

      {/* ── RAG Chat ── */}
      <div className="bg-white rounded-2xl border shadow-sm flex flex-col h-[580px] overflow-hidden">
        <div className="bg-slate-50 border-b px-6 py-4 flex items-center gap-3">
          <MessageSquare className="h-5 w-5 text-blue-600" />
          <h2 className="font-semibold text-slate-800">CareAI RAG Assistant</h2>
          <span className="ml-auto text-xs text-slate-400">Queries run against local FAISS embeddings</span>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/50">
          {conversation.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400">
              <MessageSquare className="h-10 w-10 mb-2 opacity-30" />
              <p className="font-medium">Ask anything about this specific document.</p>
              <p className="text-sm mt-1 opacity-70">e.g. "What are my main abnormalities?"</p>
            </div>
          ) : (
            conversation.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-2xl px-5 py-4 ${
                  msg.role === "user"  ? "bg-blue-600 text-white shadow" :
                  msg.role === "error" ? "bg-red-50 text-red-600 border border-red-200" :
                  "bg-white border border-slate-200 text-slate-700 shadow-sm"
                }`}>
                  <div className={`text-sm ${msg.role === "user" ? "text-white" : ""}`}>
                    {msg.role === "user" ? msg.text : formatMessage(msg.text)}
                  </div>
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border text-slate-500 shadow-sm px-5 py-3 rounded-2xl flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                <span className="text-sm">Searching embeddings via LM Studio…</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t p-4 bg-white">
          <form onSubmit={(e) => { e.preventDefault(); askQuestion(); }} className="flex items-center gap-3 relative">
            <input
              type="text"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              placeholder="e.g. What are the main abnormalities found in this report?"
              className="flex-1 border rounded-xl py-3.5 pl-4 pr-12 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="absolute right-2.5 bg-blue-600 p-2 rounded-lg text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
