import { FileText, Calendar, ArrowRight, AlertCircle } from "lucide-react";
import Link from "next/link";

interface ReportCardProps {
  id: string;
  reportName: string;
  date: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH";
  summary: string;
}

export function ReportCard({ id, reportName, date, riskLevel, summary }: ReportCardProps) {
  const riskColor = 
    riskLevel === "HIGH" ? "text-red-600 bg-red-50 border-red-200" :
    riskLevel === "MEDIUM" ? "text-amber-600 bg-amber-50 border-amber-200" :
    "text-emerald-600 bg-emerald-50 border-emerald-200";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col h-full group">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="bg-slate-100 p-2.5 rounded-lg text-slate-500 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 truncate max-w-[150px]">{reportName}</h3>
            <div className="flex items-center text-xs text-slate-500 mt-0.5">
              <Calendar className="h-3 w-3 mr-1" />
              {date}
            </div>
          </div>
        </div>
        <div className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider border flex items-center gap-1 ${riskColor}`}>
          {riskLevel === "HIGH" && <AlertCircle className="h-3 w-3" />}
          {riskLevel} RISK
        </div>
      </div>
      
      <p className="text-sm text-slate-600 line-clamp-3 mb-6 flex-grow leading-relaxed">
        {summary}
      </p>

      <Link 
        href={`/reports/${id}`} 
        className="w-full flex items-center justify-center gap-2 py-2 mt-auto text-sm font-medium text-blue-600 bg-blue-50/50 hover:bg-blue-50 rounded-lg transition-colors border border-transparent hover:border-blue-100"
      >
        View Report Analysis
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}
