"use client";

import { useState, useEffect } from "react";
import { User, Phone, MapPin, Droplet, ShieldAlert, Loader2, Save, Bell } from "lucide-react";
import { CareAI } from "@/lib/api";

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"IDLE" | "SUCCESS" | "ERROR">("IDLE");
  
  const [profile, setProfile] = useState({
    name: "",
    email: "",
    whatsapp_number: "",
    address: "",
    blood_type: "",
    emergency_contact_name: "",
    emergency_contact_phone: "",
    notify_sms: "true",
    notify_email: "true",
    notify_report_ready: "true",
    notify_high_risk: "true"
  });

  useEffect(() => {
    CareAI.getProfile()
      .then(res => {
         // Merge existing data with empty strings to avoid React controlled input warnings
         setProfile({
           name: res.name || "",
           email: res.email || "",
           whatsapp_number: res.whatsapp_number || "",
           address: res.address || "",
           blood_type: res.blood_type || "",
           emergency_contact_name: res.emergency_contact_name || "",
           emergency_contact_phone: res.emergency_contact_phone || "",
           notify_sms: res.notify_sms ?? "true",
           notify_email: res.notify_email ?? "true",
           notify_report_ready: res.notify_report_ready ?? "true",
           notify_high_risk: res.notify_high_risk ?? "true"
         });
         setLoading(false);
      })
      .catch(err => {
         console.error(err);
         setLoading(false);
      });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatus("IDLE");
    try {
      await CareAI.updateProfile({
        whatsapp_number: profile.whatsapp_number,
        address: profile.address,
        blood_type: profile.blood_type,
        emergency_contact_name: profile.emergency_contact_name,
        emergency_contact_phone: profile.emergency_contact_phone,
        notify_sms: profile.notify_sms,
        notify_email: profile.notify_email,
        notify_report_ready: profile.notify_report_ready,
        notify_high_risk: profile.notify_high_risk
      });
      setStatus("SUCCESS");
      setTimeout(() => setStatus("IDLE"), 3000);
    } catch (err) {
       console.error(err);
       setStatus("ERROR");
    } finally {
       setSaving(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setProfile({ ...profile, [e.target.name]: e.target.value });
  };

  if (loading) {
     return <div className="flex h-[50vh] items-center justify-center"><Loader2 className="h-10 w-10 animate-spin text-blue-600" /></div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in slide-in-from-bottom-4 duration-500 pb-12">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 flex items-center gap-3">
          <User className="h-8 w-8 text-blue-600" /> Patient Profile
        </h1>
        <p className="text-slate-500 mt-2">
          Manage your personal healthcare information, telemetry settings, and panic dispatch configurations.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-8">
        
        {/* Core Identity */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
             <h2 className="font-semibold text-slate-800 text-lg flex items-center gap-2"><User className="h-5 w-5 text-slate-500"/> Core Identity</h2>
          </div>
          <div className="p-6 grid gap-6 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Full Name</label>
              <input type="text" disabled value={profile.name} className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-slate-500 cursor-not-allowed" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Registered Email</label>
              <input type="email" disabled value={profile.email} className="w-full bg-slate-100 border-none rounded-xl px-4 py-3 text-slate-500 cursor-not-allowed" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2 flex items-center gap-2"><Phone className="h-4 w-4"/> WhatsApp Number</label>
              <input type="tel" name="whatsapp_number" value={profile.whatsapp_number} onChange={handleChange} placeholder="+1 555-0192" className="w-full border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2 flex items-center gap-2"><MapPin className="h-4 w-4"/> Home Address</label>
              <input type="text" name="address" value={profile.address} onChange={handleChange} placeholder="123 CareAI Avenue, SF" className="w-full border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2 flex items-center gap-2 text-red-600"><Droplet className="h-4 w-4"/> Blood Type</label>
              <input type="text" name="blood_type" value={profile.blood_type} onChange={handleChange} placeholder="O+, A-, etc." className="w-full border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase" />
            </div>
          </div>
        </div>

        {/* Emergency Dispatch Config */}
        <div className="rounded-2xl border border-red-200 bg-white shadow-sm overflow-hidden">
          <div className="bg-red-50 px-6 py-4 border-b border-red-200">
             <h2 className="font-semibold text-red-800 text-lg flex items-center gap-2"><ShieldAlert className="h-5 w-5"/> Emergency Panic Dispatch</h2>
          </div>
          <div className="p-6 grid gap-6 md:grid-cols-2">
            <div className="md:col-span-2">
              <p className="text-sm text-slate-500 mb-4 bg-slate-50 p-4 rounded-xl border border-slate-100">
                This contact will be immediately notified via SMS and securely un-locked into your medical vault if you trigger the system's Panic Button.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Primary Contact Name</label>
              <input type="text" name="emergency_contact_name" value={profile.emergency_contact_name} onChange={handleChange} placeholder="John Doe" className="w-full border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Contact Phone / WhatsApp</label>
              <input type="tel" name="emergency_contact_phone" value={profile.emergency_contact_phone} onChange={handleChange} placeholder="+1 999-0000" className="w-full border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
          </div>
        </div>

        {/* Notification Preferences */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
             <h2 className="font-semibold text-slate-800 text-lg flex items-center gap-2"><Bell className="h-5 w-5 text-slate-500"/> Notification Preferences</h2>
          </div>
          <div className="p-6 space-y-4">
            {([
              { key: "notify_sms", label: "SMS Alerts", desc: "Receive text messages for critical events" },
              { key: "notify_email", label: "Email Alerts", desc: "Get email summaries of your reports" },
              { key: "notify_report_ready", label: "Report Ready", desc: "Notify when AI analysis finishes" },
              { key: "notify_high_risk", label: "High Risk Alerts", desc: "Immediate alert for concerning findings" },
            ] as {key: keyof typeof profile, label: string, desc: string}[]).map(pref => (
              <div key={pref.key} className="flex items-center justify-between py-3 border-b border-slate-50 last:border-0">
                <div>
                  <p className="font-medium text-slate-800 text-sm">{pref.label}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{pref.desc}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setProfile(p => ({...p, [pref.key]: p[pref.key] === "true" ? "false" : "true"}))}
                  className={`relative w-12 h-6 rounded-full transition-colors duration-200 focus:outline-none ${
                    profile[pref.key] === "true" ? "bg-blue-600" : "bg-slate-200"
                  }`}
                >
                  <span className={`absolute top-0.5 left-0.5 h-5 w-5 bg-white rounded-full shadow-md transition-transform duration-200 ${
                    profile[pref.key] === "true" ? "translate-x-6" : "translate-x-0"
                  }`} />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-4 pt-4">
          {status === "SUCCESS" && <span className="text-emerald-600 font-medium">Profile completely synced.</span>}
          {status === "ERROR" && <span className="text-red-600 font-medium">Failed to save profile.</span>}
          <button 
             type="submit" 
             disabled={saving}
             className="bg-blue-600 text-white font-bold tracking-wide px-8 py-3.5 rounded-xl hover:bg-blue-700 flex items-center gap-2 shadow disabled:opacity-50 transition-all hover:shadow-lg active:scale-95"
          >
             {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
             SAVE CHANGES
          </button>
        </div>

      </form>
    </div>
  );
}
