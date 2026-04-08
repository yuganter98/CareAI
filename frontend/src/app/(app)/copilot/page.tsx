"use client";

import { useState, useEffect, useRef } from "react";
import {
  Sparkles, Send, Loader2, Bot, User, Stethoscope,
  Brain, Heart, TrendingUp, Shield
} from "lucide-react";
import { CareAI } from "@/lib/api";

// ─── Markdown renderer ───────────────────────────────────────────────────────
const parseBold = (text: string) =>
  text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>
  );

const formatMessage = (text: string) =>
  text.split("\n").map((line, i) => {
    if (line.trim() === "```markdown" || line.trim() === "```") return null;
    if (line.trim() === "---") return <hr key={i} className="my-3 border-white/10" />;
    if (line.trim().startsWith("* ") || line.trim().startsWith("- "))
      return <li key={i} className="ml-5 list-disc mb-1 leading-relaxed text-sm">{parseBold(line.trim().substring(2))}</li>;
    if (line.trim().startsWith("⚕️"))
      return <p key={i} className="text-xs text-white/40 italic mt-2 leading-relaxed">{line}</p>;
    if (line.trim() === "") return <div key={i} className="h-1.5" />;
    return <p key={i} className="mb-2 leading-relaxed text-sm">{parseBold(line)}</p>;
  });

// ─── Suggested questions ──────────────────────────────────────────────────────
const SUGGESTIONS = [
  { icon: <TrendingUp className="h-4 w-4" />, text: "How are my glucose levels trending over time?" },
  { icon: <Heart className="h-4 w-4" />,      text: "Are there any concerning patterns in my reports?" },
  { icon: <Stethoscope className="h-4 w-4" />, text: "What should I discuss with my doctor next visit?" },
  { icon: <Shield className="h-4 w-4" />,      text: "Give me a holistic summary of my health status" },
];

// ─── Types ────────────────────────────────────────────────────────────────────
interface Message {
  role: "user" | "assistant";
  content: string;
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const sendMessage = async (question?: string) => {
    const q = (question || input).trim();
    if (!q || loading) return;
    setInput("");

    const userMsg: Message = { role: "user", content: q };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      // Send full conversation history for multi-turn context
      const history = [...messages, userMsg].map(m => ({
        role: m.role,
        content: m.content,
      }));

      const res = await CareAI.copilotChat(q, history);
      setMessages(prev => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "I'm sorry, I wasn't able to process that request. Please make sure your backend is running and try again."
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] max-w-4xl mx-auto animate-in slide-in-from-bottom-4 duration-500">

      {/* ── Header ── */}
      <div className="flex items-center gap-4 pb-5 border-b border-white/10">
        <div className="relative">
          <div className="bg-gradient-to-br from-blue-500 to-violet-600 p-3 rounded-2xl text-white shadow-lg shadow-blue-500/20">
            <Brain className="h-7 w-7" />
          </div>
          <span className="absolute -bottom-1 -right-1 h-4 w-4 bg-emerald-500 rounded-full border-2 border-[#1E293B]" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Health Copilot <Sparkles className="h-5 w-5 text-amber-500" />
          </h1>
          <p className="text-white/60 text-sm">
            Your AI health companion — context from <strong className="text-white/90">all your reports</strong>, trends, and insights.
          </p>
        </div>
      </div>

      {/* ── Chat area ── */}
      <div className="flex-1 overflow-y-auto py-6 space-y-5">

        {messages.length === 0 ? (
          /* ── Empty state with suggestions ── */
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="bg-white/10 backdrop-blur-xl p-6 rounded-3xl border border-white/10 mb-6">
              <Bot className="h-14 w-14 text-blue-400 mx-auto" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Hi! I'm your Health Copilot</h2>
            <p className="text-white/60 max-w-md mb-8 text-sm leading-relaxed">
              I can answer questions about <strong className="text-white/90">all</strong> your medical reports at once — 
              trends, patterns, and personalised insights. What would you like to know?
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s.text)}
                  className="flex items-center gap-3 text-left p-4 rounded-xl border border-white/10 bg-white/5 backdrop-blur-md hover:border-white/30 hover:bg-white/10 transition-all text-sm text-white/80 shadow-sm hover:shadow group"
                >
                  <div className="text-blue-400 group-hover:scale-110 transition-transform">{s.icon}</div>
                  <span>{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── Messages ── */
          messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="shrink-0 mt-1">
                  <div className="bg-gradient-to-br from-blue-500 to-violet-600 p-2 rounded-xl text-white">
                    <Bot className="h-4 w-4" />
                  </div>
                </div>
              )}

              <div className={`max-w-[80%] rounded-2xl px-5 py-4 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-900/20"
                  : "bg-white/10 backdrop-blur-lg border border-white/10 text-white shadow-sm"
              }`}>
                <div className={msg.role === "user" ? "text-sm text-white" : ""}>
                  {msg.role === "user" ? msg.content : formatMessage(msg.content)}
                </div>
              </div>

              {msg.role === "user" && (
                <div className="shrink-0 mt-1">
                  <div className="bg-white/10 backdrop-blur-md p-2 rounded-xl border border-white/10">
                    <User className="h-4 w-4 text-white/80" />
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {/* Typing indicator */}
        {loading && (
          <div className="flex gap-3 justify-start">
            <div className="shrink-0 mt-1">
              <div className="bg-gradient-to-br from-blue-500 to-violet-600 p-2 rounded-xl text-white">
                <Bot className="h-4 w-4" />
              </div>
            </div>
            <div className="bg-white/10 backdrop-blur-lg border border-white/10 shadow-sm rounded-2xl px-5 py-4 flex items-center gap-3">
              <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
              <div className="flex gap-1">
                <span className="h-2 w-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms"   }} />
                <span className="h-2 w-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="h-2 w-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
              <span className="text-sm text-white/50">Thinking across your reports...</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input bar ── */}
      <div className="border-t border-white/10 pt-4 pb-2">
        <form
          onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
          className="flex items-center gap-3 bg-white/5 backdrop-blur-xl border border-white/15 rounded-2xl p-2 shadow-sm focus-within:ring-2 focus-within:ring-white/20 transition-all"
        >
          <Sparkles className="h-5 w-5 text-amber-300 ml-2 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about your health..."
            className="flex-1 bg-transparent py-2.5 focus:outline-none text-sm text-white placeholder:text-white/40"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 text-white p-2.5 rounded-xl disabled:opacity-40 transition-all shadow hover:shadow-md active:scale-95"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
        <p className="text-center text-[10px] text-white/30 mt-2">
          CareAI Health Copilot uses AI to provide guidance — not medical advice. Always consult a doctor.
        </p>
      </div>
    </div>
  );
}
