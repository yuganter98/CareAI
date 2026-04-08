/**
 * useAgentStream — Real-time WebSocket hook for agent execution observability.
 *
 * Architecture:
 *   1. Seeds state from REST: GET /agents/logs/{report_id}
 *   2. Opens WebSocket: ws://localhost:8000/ws/agents/{report_id}
 *   3. Merges incoming events into a deduplicated agent state map
 *   4. On disconnect → exponential backoff reconnect (max 3 attempts)
 *   5. After max retries → falls back to REST polling every 3s
 *
 * Returns: { agents, connected, loading }
 *   - agents: Map<agentName, { status, duration_ms, message, timestamp }>
 *   - connected: "ws" | "polling" | "disconnected"
 *   - loading: initial fetch in progress
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { CareAI } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AgentState {
  agent_name: string;
  status: "started" | "completed" | "failed";
  message: string | null;
  duration_ms: number | null;
  timestamp: string;
}

type ConnectionStatus = "ws" | "polling" | "disconnected";

interface UseAgentStreamReturn {
  /** Ordered list of agents with their latest status. */
  agents: AgentState[];
  /** Current connection mode. */
  connected: ConnectionStatus;
  /** True while first REST fetch is in flight. */
  loading: boolean;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const WS_BASE       = "ws://localhost:8000";
const MAX_RETRIES   = 3;
const BASE_DELAY_MS = 1000;   // 1s → 2s → 4s
const POLL_INTERVAL = 3000;

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAgentStream(reportId: string): UseAgentStreamReturn {
  // Agent state is kept as an ordered Map so the timeline stays stable
  const [agentMap, setAgentMap] = useState<Map<string, AgentState>>(new Map());
  const [connected, setConnected] = useState<ConnectionStatus>("disconnected");
  const [loading, setLoading] = useState(true);

  const wsRef      = useRef<WebSocket | null>(null);
  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef   = useRef(0);
  const cancelRef  = useRef(false);

  // ── Merge a batch of log entries into the agent map ──
  const mergeEntries = useCallback((entries: AgentState[]) => {
    setAgentMap(prev => {
      const next = new Map(prev);
      for (const entry of entries) {
        const existing = next.get(entry.agent_name);
        // Only update if this event is newer OR carries a "heavier" status
        if (!existing || statusWeight(entry.status) >= statusWeight(existing.status)) {
          next.set(entry.agent_name, entry);
        }
      }
      return next;
    });
  }, []);

  // ── REST seed (always runs first) ──
  const fetchLogs = useCallback(() => {
    return CareAI.getAgentLogs(reportId)
      .then((res: any[]) => {
        if (cancelRef.current) return;
        const entries: AgentState[] = res.map(r => ({
          agent_name:  r.agent_name,
          status:      r.status,
          message:     r.message ?? null,
          duration_ms: r.duration_ms ?? null,
          timestamp:   r.timestamp,
        }));
        mergeEntries(entries);
        setLoading(false);
      })
      .catch(() => { if (!cancelRef.current) setLoading(false); });
  }, [reportId, mergeEntries]);

  // ── Start polling fallback ──
  const startPolling = useCallback(() => {
    if (pollRef.current || cancelRef.current) return;
    setConnected("polling");
    pollRef.current = setInterval(() => {
      if (cancelRef.current) return;
      fetchLogs();
    }, POLL_INTERVAL);
  }, [fetchLogs]);

  // ── Stop polling ──
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // ── WebSocket connect with exponential backoff ──
  const connectWS = useCallback(() => {
    if (cancelRef.current) return;

    const url = `${WS_BASE}/ws/agents/${reportId}`;
    let socket: WebSocket;

    try {
      socket = new WebSocket(url);
    } catch {
      startPolling();
      return;
    }

    wsRef.current = socket;

    socket.onopen = () => {
      if (cancelRef.current) { socket.close(); return; }
      retryRef.current = 0;      // reset backoff on success
      stopPolling();              // kill any active poller
      setConnected("ws");
    };

    socket.onmessage = (event) => {
      if (cancelRef.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "agent_event") {
          mergeEntries([{
            agent_name:  data.agent,
            status:      data.status,
            message:     data.message ?? null,
            duration_ms: data.duration_ms ?? null,
            timestamp:   data.timestamp,
          }]);
        }
      } catch { /* malformed frame — skip */ }
    };

    socket.onclose = () => {
      if (cancelRef.current) return;
      setConnected("disconnected");
      scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose fires after onerror — reconnect is handled there
      socket.close();
    };
  }, [reportId, mergeEntries, startPolling, stopPolling]);

  // ── Reconnect with exponential backoff ──
  const scheduleReconnect = useCallback(() => {
    if (cancelRef.current) return;

    if (retryRef.current >= MAX_RETRIES) {
      // Exhausted retries — fall back to REST polling permanently
      startPolling();
      return;
    }

    const delay = BASE_DELAY_MS * Math.pow(2, retryRef.current);
    retryRef.current += 1;

    setTimeout(() => {
      if (!cancelRef.current) connectWS();
    }, delay);
  }, [connectWS, startPolling]);

  // ── Lifecycle ──
  useEffect(() => {
    cancelRef.current = false;
    retryRef.current  = 0;

    // 1. Seed from REST
    fetchLogs();

    // 2. Open WebSocket
    connectWS();

    return () => {
      cancelRef.current = true;
      wsRef.current?.close();
      stopPolling();
    };
  }, [reportId, fetchLogs, connectWS, stopPolling]);

  // ── Derived ordered array ──
  const agents = Array.from(agentMap.values());

  return { agents, connected, loading };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statusWeight(s: string): number {
  switch (s) {
    case "started":   return 1;
    case "completed": return 2;
    case "failed":    return 2;  // terminal — same weight as completed
    default:          return 0;
  }
}
