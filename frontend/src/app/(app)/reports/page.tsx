"use client";

import { Upload, Loader2, Trash2, FileText, Calendar, ArrowRight } from "lucide-react";
import { UploadForm } from "@/components/reports/UploadForm";
import { useState, useEffect } from "react";
import { CareAI } from "@/lib/api";
import Link from "next/link";

export default function ReportsPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchReports = () => {
    CareAI.getMyReports()
      .then(res => { setReports(res || []); setLoading(false); })
      .catch(err => { console.error(err); setLoading(false); });
  };

  useEffect(() => { fetchReports(); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Permanently delete this report and all its AI analysis data?")) return;
    setDeleting(id);
    try {
      await CareAI.deleteReport(id);
      setReports(prev => prev.filter(r => r.id !== id));
    } catch (e) {
      alert("Failed to delete report.");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Medical Reports</h1>
          <p className="text-slate-500 mt-1">Analyze and manage your clinical documents securely.</p>
        </div>
      </div>
      
      <div className="py-6 border-b border-t border-slate-200/60 bg-slate-50/30 rounded-2xl mb-8 flex items-center justify-center">
        <UploadForm />
      </div>

      <div className="flex flex-col mt-8">
         <h2 className="text-xl font-bold tracking-tight text-slate-900 mb-6">
           Secured Document Vault
           {!loading && reports.length > 0 && (
             <span className="ml-3 text-sm font-normal text-slate-400 bg-slate-100 px-2.5 py-1 rounded-full">{reports.length} documents</span>
           )}
         </h2>
         {loading ? (
           <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white p-12 text-center shadow-sm flex flex-col items-center justify-center">
              <Loader2 className="h-10 w-10 text-blue-600 animate-spin" />
              <h3 className="font-semibold text-lg text-slate-900 mt-4">Syncing Encrypted Vault...</h3>
           </div>
         ) : reports.length === 0 ? (
           <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white p-12 text-center shadow-sm">
             <div className="bg-slate-100 p-4 rounded-full inline-block mb-4">
                <Upload className="h-8 w-8 text-slate-400" />
             </div>
             <h3 className="font-semibold text-lg text-slate-900">Your vault is empty</h3>
             <p className="text-slate-500 mt-1 max-w-sm mx-auto">Drop your first PDF or image above to trigger the Multi-Agent orchestrator pipeline.</p>
           </div>
         ) : (
           <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {reports.map((report) => (
                <div key={report.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col h-full group">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="bg-slate-100 p-2.5 rounded-lg text-slate-500 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-900">Report {report.id.substring(0,6)}</h3>
                        <div className="flex items-center text-xs text-slate-500 mt-0.5">
                          <Calendar className="h-3 w-3 mr-1" />
                          {new Date(report.uploaded_at || Date.now()).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(report.id)}
                      disabled={deleting === report.id}
                      className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                      title="Delete report"
                    >
                      {deleting === report.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </button>
                  </div>
                  <div className="mb-6 flex-grow">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider border text-amber-600 bg-amber-50 border-amber-200">MEDIUM RISK</span>
                    <p className="text-sm text-slate-600 mt-2 leading-relaxed">Analyzed by CareAI multi-agent orchestrator.</p>
                  </div>
                  <Link 
                    href={`/reports/${report.id}`}
                    className="w-full flex items-center justify-center gap-2 py-2 mt-auto text-sm font-medium text-blue-600 bg-blue-50/50 hover:bg-blue-50 rounded-lg transition-colors border border-transparent hover:border-blue-100"
                  >
                    View Report Analysis <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              ))}
           </div>
         )}
      </div>
    </div>
  );
}
