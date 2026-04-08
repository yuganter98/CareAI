"use client";
import { Plus, Trash2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { CareAI } from "@/lib/api";

export default function MedicationsPage() {
  const [meds, setMeds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newMed, setNewMed] = useState({ medicine_name: "", dosage: "", time: "" });
  const [adding, setAdding] = useState(false);

  const fetchMeds = () => {
    CareAI.getMedications()
      .then(res => {
         setMeds(res?.medications || []);
         setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchMeds();
  }, []);

  const handleAdd = async () => {
    if (!newMed.medicine_name || !newMed.time) return;
    setAdding(true);
    try {
      await CareAI.addMedication({
        ...newMed,
        start_date: new Date().toISOString()
      });
      setShowForm(false);
      setNewMed({ medicine_name: "", dosage: "", time: "" });
      fetchMeds();
    } catch(err: any) {
      alert("API Error: " + err.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Prescriptions</h1>
          <p className="text-slate-500 mt-1">Manage your active medications and automated background API reminders.</p>
        </div>
        <button 
           onClick={() => setShowForm(!showForm)}
           className="flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-blue-700 transition shadow-sm hover:shadow"
        >
          <Plus className={`h-4 w-4 transition-transform ${showForm ? "rotate-45" : ""}`} />
          {showForm ? "Cancel" : "Add Medication"}
        </button>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden mt-8 min-h-[300px] flex flex-col">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50/80 text-slate-600 font-semibold border-b">
            <tr>
              <th className="px-6 py-4 tracking-wide uppercase text-xs">Medicine</th>
              <th className="px-6 py-4 tracking-wide uppercase text-xs">Dosage</th>
              <th className="px-6 py-4 tracking-wide uppercase text-xs">Time scheduled</th>
              <th className="px-6 py-4 text-right tracking-wide uppercase text-xs">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
               <tr><td colSpan={4} className="p-16 text-center"><Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600" /></td></tr>
            ) : (
              <>
              {showForm && (
                <tr className="bg-blue-50/50">
                  <td className="px-6 py-4">
                     <input type="text" placeholder="e.g. Lisinopril" value={newMed.medicine_name} onChange={e => setNewMed({...newMed, medicine_name: e.target.value})} className="border rounded-md px-3 py-1.5 w-full text-sm" />
                  </td>
                  <td className="px-6 py-4">
                     <input type="text" placeholder="e.g. 10mg" value={newMed.dosage} onChange={e => setNewMed({...newMed, dosage: e.target.value})} className="border rounded-md px-3 py-1.5 w-full text-sm font-mono" />
                  </td>
                  <td className="px-6 py-4">
                     <input type="text" placeholder="e.g. 08:00 AM" value={newMed.time} onChange={e => setNewMed({...newMed, time: e.target.value})} className="border rounded-md px-3 py-1.5 w-full text-sm font-bold text-blue-600" />
                  </td>
                  <td className="px-6 py-4 text-right">
                     <button onClick={handleAdd} disabled={adding} className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs px-4 py-1.5 rounded disabled:opacity-50">
                        {adding ? "Saving..." : "Save"}
                     </button>
                  </td>
                </tr>
              )}
              {meds.length === 0 && !showForm ? (
                 <tr><td colSpan={4} className="p-16 text-center text-slate-500 font-medium text-base">You haven't appended any prescriptions to your CareAI profile yet.</td></tr>
              ) : (
              meds.map((med, idx) => (
                <tr key={idx} className="transition hover:bg-slate-50/50">
                  <td className="px-6 py-4 font-semibold text-slate-900">{med.medicine_name}</td>
                  <td className="px-6 py-4 text-slate-600 bg-slate-50 rounded-md font-mono text-xs w-min inline-block mt-3 ml-6 border">{med.dosage}</td>
                  <td className="px-6 py-4 text-blue-600 font-bold">{med.time}</td>
                  <td className="px-6 py-4 text-right">
                    <button className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
            </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
