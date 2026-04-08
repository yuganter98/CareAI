"use client";

import { useState } from "react";
import { UploadCloud, File, X, Loader2, CheckCircle2 } from "lucide-react";
import { CareAI } from "@/lib/api";
import { useRouter } from "next/navigation";

export function UploadForm() {
  const router = useRouter();
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [done, setDone] = useState(false);

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    try {
      const reportMeta = await CareAI.uploadReport(file);
      await CareAI.processMultiAgentAI(reportMeta.id);
      setDone(true);
      // Auto-navigate to the freshly analyzed report's RAG console
      setTimeout(() => router.push(`/reports/${reportMeta.id}`), 1200);
    } catch(e: any) {
      console.error(e);
      alert("AI Pipeline failure: " + e.message);
      setIsUploading(false);
    }
  };

  if (done) {
    return (
      <div className="w-full max-w-xl mx-auto border border-emerald-200 bg-emerald-50 rounded-xl p-10 flex flex-col items-center text-center animate-in zoom-in-95 duration-300 shadow-sm">
        <CheckCircle2 className="h-12 w-12 text-emerald-600 mb-4" />
        <h3 className="text-lg font-bold text-slate-900">Analysis Complete!</h3>
        <p className="text-sm text-slate-500 mt-1">Navigating you to the AI Report Console...</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-xl mx-auto shadow-sm">
      {!file ? (
        <label 
          className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${
            isDragging ? "border-blue-500 bg-blue-50/80 scale-[1.02]" : "border-slate-300 hover:border-blue-400 hover:bg-slate-50"
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              setFile(e.dataTransfer.files[0]);
            }
          }}
        >
          <div className="bg-blue-100 p-4 rounded-full mb-5 transition-transform hover:scale-110">
            <UploadCloud className="h-8 w-8 text-blue-600" />
          </div>
          <h3 className="text-xl font-semibold text-slate-900 mb-1">Upload Medical Extract</h3>
          <p className="text-sm text-slate-500 max-w-xs mb-6">
            Drag & drop your PDF or Image lab results directly safely into the encrypted AI pool.
          </p>
          <div className="bg-white border shadow-sm px-5 py-2.5 rounded-lg font-medium text-slate-700 pointer-events-none">
            Browse Protected Files
          </div>
          <input 
              type="file" 
              className="hidden" 
              accept=".pdf,image/png,image/jpeg"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) setFile(e.target.files[0]);
              }}
          />
        </label>
      ) : (
        <div className="border border-slate-200 rounded-xl p-5 bg-white shadow-md animate-in zoom-in-95 duration-200">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-4">
              <div className="bg-slate-100 p-3.5 rounded-lg text-slate-600 border border-slate-200">
                <File className="h-6 w-6 text-slate-500" />
              </div>
              <div className="overflow-hidden">
                <p className="font-semibold text-slate-900 truncate max-w-[250px]">{file.name}</p>
                <p className="text-xs font-mono text-slate-500 mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            </div>
            {!isUploading && (
              <button onClick={() => setFile(null)} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
          <button 
            onClick={handleUpload}
            disabled={isUploading}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-all flex items-center justify-center gap-2 disabled:opacity-80 shadow hover:shadow-md active:scale-[0.98]"
          >
            {isUploading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Processing via Multi-Agent Orchestrator...
              </>
            ) : "Dispatch to CareAI Analyzer"}
          </button>
        </div>
      )}
    </div>
  );
}
