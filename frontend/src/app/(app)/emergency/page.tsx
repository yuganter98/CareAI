"use client";

import { AlertTriangle, ShieldAlert, HeartPulse, ShieldCheck, Loader2 } from "lucide-react";
import { useState } from "react";
import { CareAI } from "@/lib/api";

export default function EmergencyProtocolPage() {
  const [triggering, setTriggering] = useState(false);
  const [status, setStatus] = useState<"IDLE" | "SUCCESS" | "ERROR">("IDLE");

  const handlePanicDrop = async () => {
    setTriggering(true);
    setStatus("IDLE");
    try {
      // Triggers the FastAPI background worker email/SMS subsystem!
      await CareAI.triggerPanicButton();
      setStatus("SUCCESS");
    } catch (e) {
      console.error(e);
      setStatus("ERROR");
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 flex items-center gap-3">
          <ShieldAlert className="h-8 w-8 text-red-600" /> Emergency Protocol
        </h1>
        <p className="text-slate-500 mt-2">
          Manually bypass the AI orchestrator and force a global priority alert to all trusted medical contacts.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 mt-8">
        <div className="rounded-2xl border border-red-200 bg-red-50 p-8 shadow-sm flex flex-col justify-center items-center text-center">
            <div className="bg-red-100 p-4 rounded-full mb-6 relative">
               <AlertTriangle className="h-10 w-10 text-red-600" />
               {triggering && <span className="absolute inset-0 rounded-full border-4 border-red-500 animate-ping opacity-75"></span>}
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Initiate Priority Alert</h2>
            <p className="text-sm text-slate-600 mb-8 max-w-sm">
              Pressing this button securely locks your patient vault and broadcasts your recent critical metrics to emergency responders.
            </p>
            
            <button 
              onClick={handlePanicDrop}
              disabled={triggering || status === "SUCCESS"}
              className={`w-full py-4 rounded-xl font-bold text-white text-lg tracking-wide shadow transition-all
                 ${status === "SUCCESS" ? "bg-emerald-600 pointer-events-none" : "bg-red-600 hover:bg-red-700 hover:shadow-lg active:scale-95 disabled:opacity-75"}
              `}
            >
              {triggering ? (
                <span className="flex items-center justify-center gap-2"><Loader2 className="w-6 h-6 animate-spin" /> Broadcasting...</span>
              ) : status === "SUCCESS" ? (
                <span className="flex items-center justify-center gap-2"><ShieldCheck className="w-6 h-6" /> Protocols Active</span>
              ) : (
                "TRIGGER PANIC BUTTON"
              )}
            </button>
            
            {status === "ERROR" && <p className="text-red-600 mt-4 font-semibold text-sm">Failed to connect to communication gateway.</p>}
        </div>

        <div className="space-y-4">
           <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
             <div className="flex items-center gap-4 border-b border-slate-100 pb-4 mb-4">
               <div className="bg-orange-100 p-2.5 rounded-lg text-orange-600"><HeartPulse className="w-6 h-6" /></div>
               <div>
                  <h3 className="font-bold text-slate-900">Automated Dispatch</h3>
                  <p className="text-xs text-slate-500">Who is alerted?</p>
               </div>
             </div>
             <ul className="space-y-3 text-sm font-medium text-slate-700">
                <li className="flex justify-between items-center"><span className="text-slate-500">Primary ICE Contact</span> <span className="text-slate-900">Dr. Sarah Jenkins</span></li>
                <li className="flex justify-between items-center"><span className="text-slate-500">Family Proxy</span> <span className="text-slate-900">Mark Doe (Brother)</span></li>
                <li className="flex justify-between items-center"><span className="text-slate-500">Method</span> <span className="text-blue-600">SMS / Secure Email</span></li>
             </ul>
           </div>
        </div>
      </div>
    </div>
  );
}
