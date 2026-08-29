import { useState, useEffect, useRef } from "react";
import { chat, sendPermission, approve, getSettings, getGoogleStatus, type ChatResp } from "../api/client";
import type { ChatReq } from "../api/client";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../stores/auth";
import { useQueryClient } from "@tanstack/react-query";
import { FormFieldBuilder, type FieldConfig } from "../components/FormFieldBuilder";

function getDefaultFields(): FieldConfig[] {
  return [
    { id: crypto.randomUUID(), title: "Full Name", type: "text", required: true },
    { id: crypto.randomUUID(), title: "Email", type: "text", required: true },
    { id: crypto.randomUUID(), title: "Year", type: "multiple_choice", required: true, options: ["1st", "2nd", "3rd", "4th"] },
    { id: crypto.randomUUID(), title: "Expectations", type: "paragraph", required: false },
  ];
}

// Strip internal `id` before sending to backend (not part of ChatReq fields type)
function fieldsForBackend(fields: FieldConfig[]) {
  return fields.map(({ id, ...rest }) => rest);
}

export default function NewEvent() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { club } = useAuth();
  const isAdmin = club?.role === "admin";
  const [message, setMessage] = useState(`${club?.name || "FOSS MEC"} wants to conduct a java workshop for 50 students next Monday`);
  const [fields, setFields] = useState<FieldConfig[]>(() => getDefaultFields());
  const [date, setDate] = useState(() => new Date(Date.now() + 86400000 * 2).toISOString().slice(0,10)); // default +2 days
  const [start, setStart] = useState("15:30");
  const [end, setEnd] = useState("16:30");
  const [speaker, setSpeaker] = useState("Mr. Deepak Padmanabhan (Alumni of MEC)");
  const [purpose, setPurpose] = useState("Students will gain insights from his academic and professional journey");
  const [needOnfoot, setNeedOnfoot] = useState(true);
  const [resp, setResp] = useState<ChatResp | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingSend, setLoadingSend] = useState(false);
  const [loadingApprove, setLoadingApprove] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [editEmail, setEditEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [chairperson, setChairperson] = useState("");
  const [staffInCharge, setStaffInCharge] = useState("");
  const [principalEmail, setPrincipalEmail] = useState("");
  const [settingsReady, setSettingsReady] = useState<boolean | null>(null);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [driveConnected, setDriveConnected] = useState<boolean | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Load org settings to prefill chairperson/staff — only if not placeholder
  useEffect(()=>{
    if(!club?.name) return;
    const isPlaceholder = (v:string, _f?:string)=> !v || !v.trim() || v.includes("example.com") || v.trim()==="Govt. Model Engineering College" || v.trim()==="Thrikkakara";
    getSettings(club.name).then(s=>{
      if(s.chairperson && !isPlaceholder(s.chairperson)) setChairperson(s.chairperson);
      if(s.staff_in_charge && !isPlaceholder(s.staff_in_charge)) setStaffInCharge(s.staff_in_charge);
      if(s.faculty_email && !isPlaceholder(s.faculty_email)) setPrincipalEmail(s.faculty_email);
    }).catch(()=>{});
    // Check completeness + Drive
    getGoogleStatus(club.name).then(g=>{
      setSettingsReady(g.configured);
      setMissingFields(g.missing_fields || []);
      setDriveConnected(g.connected);
    }).catch(()=>{ setSettingsReady(false); setMissingFields(["all"]); });
  },[club?.name]);

  const resetForm = ()=>{
    setMessage(`${club?.name || "FOSS MEC"} wants to conduct a workshop for 50 students`);
    setFields(getDefaultFields());
    setDate(new Date(Date.now() + 86400000 * 2).toISOString().slice(0,10)); setStart("15:30"); setEnd("16:30");
    setSpeaker("Mr. Deepak Padmanabhan (Alumni of MEC)");
    setPurpose("Students will gain insights from his academic and professional journey");
    setNeedOnfoot(true);
    setResp(null); setEditEmail(""); setShowConfirm(false); setError(null); setSuccess(null);
  };
  const doChat = async()=>{
    if(loadingChat) return;
    if(settingsReady===false){ setError(`Settings incomplete — please complete Settings first. Missing: ${missingFields.join(", ")}. Go to Settings → fill all fields.`); return; }
    if(driveConnected===false){ setError(`Google Drive not connected for ${club?.name}. Go to Settings → Connect Google Drive and approve permissions, then retry.`); return; }
    if(!message.trim()){ setError("Please enter a natural language request."); return; }
    if(message.trim().length < 10){ setError("Request too short — add more detail (e.g. org, topic, headcount)."); return; }
    if(!date){ setError("Please pick a date — date picker is required to prevent double-bookings."); return; }
    if(!start.trim() || !end.trim()){ setError("Start and end time are required."); return; }
    setLoadingChat(true); setError(null); setSuccess(null);
    try{
      const payload: ChatReq = { message: message.trim(), date, fields: fieldsForBackend(fields), start_time: start.trim() || undefined, end_time: end.trim() || undefined, speaker: speaker.trim() || undefined, purpose: purpose.trim() || undefined, need_onfoot: needOnfoot, chairperson: chairperson.trim() || undefined, staff_in_charge: staffInCharge.trim() || undefined };
      const r = await chat(payload);
      setResp(r);
      setEditEmail(r.permission_letter || r.email_draft || "");
      if(!r.permission_letter && !r.email_draft) setError("Agent returned no letter — try editing and sending anyway or reset.");
      else setSuccess("Draft ready — review and send to principal.");
      await qc.invalidateQueries({queryKey:["events"]});
    }catch(e: any){ const d = e?.response?.data?.detail; let msg: string; if (typeof d === "object" && d?.error) { msg = d.error + (d.conflicts?.length ? ` Conflicts: ${JSON.stringify(d.conflicts.slice(0,2))}` : "") + (d.alternatives?.length ? ` Try: ${d.alternatives.map((a:any)=>a.room).join(", ")}` : "") + (d.suggestion ? ` — ${d.suggestion}` : ""); } else { msg = (typeof d === "string" ? d : e?.message) || "Failed"; } setError(msg); }
    setLoadingChat(false);
  };
  const doSend = async()=>{
    if(!resp?.event_id || loadingSend) return;
    if(!editEmail.trim()){ setError("Permission letter cannot be empty."); return; }
    setLoadingSend(true); setError(null);
    try{
      await sendPermission(resp.event_id, { edited_email: editEmail || undefined });
      setSuccess("Sent to principal with PDFs!");
      setShowConfirm(false);
      setResp(prev => prev ? { ...prev, permission_email_sent: true } : prev);
      await qc.invalidateQueries({queryKey:["events"]});
    }catch(e: unknown){ const msg = (e as {response?:{data?:{detail?:string}}; message?:string})?.response?.data?.detail || (e as Error)?.message || "Failed"; setError(msg); }
    setLoadingSend(false);
  };
  const doApprove = async()=>{
    if(!resp?.event_id || loadingApprove || !isAdmin) return;
    setLoadingApprove(true); setError(null);
    try{
      const r = await approve(resp.event_id, true);
      setSuccess("Approved → Form: "+(r.event?.form_link||r.message));
      await qc.invalidateQueries({queryKey:["events"]});
      nav(`/events/${resp.event_id}`);
    }catch(e: unknown){ const msg = (e as {response?:{data?:{detail?:string}}; message?:string})?.response?.data?.detail||(e as Error)?.message||"Failed"; setError(msg); }
    setLoadingApprove(false);
  };

  useEffect(()=>{
    if(!showConfirm) return;
    const onKey = (e: KeyboardEvent)=>{ if(e.key==="Escape") setShowConfirm(false); };
    window.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return ()=> window.removeEventListener("keydown", onKey);
  }, [showConfirm]);

  return (
    <div className="min-h-screen bg-charcoal">
      <header className="border-b border-white/10 bg-charcoal/80 backdrop-blur sticky top-0">
        <div className="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="font-space font-bold text-white">New Event — 1-Chat Heart</h1>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={resetForm} disabled={loadingChat || loadingSend}>Reset</Button>
            <Button variant="ghost" onClick={()=>nav("/dashboard")}>← Dashboard</Button>
          </div>
        </div>
      </header>
      <div className="max-w-6xl mx-auto px-6 py-6">
        {settingsReady===false && (
          <div className="mb-4 rounded-xl bg-amber-500/10 border border-amber-500/20 p-4 flex gap-3">
            <div className="text-amber-400 text-sm">⚠️ Settings incomplete — you cannot create events yet.</div>
            <div className="text-xs text-amber-200/80">Missing: {missingFields.join(", ") || "all fields"}. <button onClick={()=>nav("/settings")} className="underline text-amber-200">Go to Settings → fill all fields</button> (institution, principal email, chairperson, staff, recipients). This blocks /chat until saved.</div>
          </div>
        )}
        {driveConnected===false && settingsReady && (
          <div className="mb-4 rounded-xl bg-oxide/10 border border-oxide/20 p-3 flex gap-2 items-center text-sm text-zinc-300">
            <span>Central Drive not connected — Forms/Sheets will be mock. Contact admin.</span>
            <button onClick={()=>nav("/settings")} className="ml-auto text-oxide underline text-xs">Connect Drive in Settings</button>
            <span className="text-xs text-zinc-500">(TEST_CLUB doesn't need this)</span>
          </div>
        )}
        <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <Card>
            <label htmlFor="nl-message" className="text-sm text-zinc-300">Natural language request</label>
            <textarea id="nl-message" aria-label="Natural language request" value={message} onChange={e=>{setMessage(e.target.value); if(error) setError(null);}} rows={3} className="w-full mt-2 rounded-xl bg-white/5 border border-white/10 p-3 text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-oxide" placeholder="e.g. FOSS MEC wants java workshop for 50 next Monday" />
            <div className="text-xs text-zinc-500 mt-1">{message.trim().length} chars</div>
          </Card>
          <Card>
            <FormFieldBuilder
              initialFields={fields}
              onChange={setFields}
              disabled={loadingChat}
            />
          </Card>
          <Card>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="event-date" className="text-xs text-zinc-400">Date *</label>
                <input id="event-date" type="date" aria-label="Event date" value={date} onChange={e=>setDate(e.target.value)} className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
                <p className="text-[11px] text-zinc-500 mt-1">Future events are kept — past bookings auto-cleared daily at 02:00.</p>
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label htmlFor="start-time" className="text-xs text-zinc-400">Start *</label>
                  <input id="start-time" aria-label="Start time" type="time" value={start} onChange={e=>setStart(e.target.value)} className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
                </div>
                <div className="flex-1">
                  <label htmlFor="end-time" className="text-xs text-zinc-400">End *</label>
                  <input id="end-time" aria-label="End time" type="time" value={end} onChange={e=>setEnd(e.target.value)} className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
                </div>
              </div>
              <div className="col-span-2">
                <label htmlFor="speaker" className="text-xs text-zinc-400">Speaker</label>
                <input id="speaker" aria-label="Speaker" placeholder="Speaker" value={speaker} onChange={e=>setSpeaker(e.target.value)} className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
              </div>
              <div className="col-span-2">
                <label htmlFor="purpose" className="text-xs text-zinc-400">Purpose</label>
                <textarea id="purpose" aria-label="Purpose" placeholder="Purpose" value={purpose} onChange={e=>setPurpose(e.target.value)} rows={2} className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 p-3 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
              </div>
              <label className="col-span-2 flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={needOnfoot} onChange={e=>setNeedOnfoot(e.target.checked)} /> Need on-foot publicity letter?</label>
              <div className="col-span-2 grid grid-cols-2 gap-3 mt-1">
                <div>
                  <label className="text-xs text-zinc-400">Chairperson (from Settings)</label>
                  <input value={chairperson} onChange={e=>setChairperson(e.target.value)} placeholder="auto from Settings" className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
                </div>
                <div>
                  <label className="text-xs text-zinc-400">Staff In Charge</label>
                  <input value={staffInCharge} onChange={e=>setStaffInCharge(e.target.value)} placeholder="auto from Settings" className="w-full mt-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-oxide" />
                </div>
              </div>
              <p className="col-span-2 text-xs text-zinc-500">Leave blank to use Settings defaults. Edit in <button type="button" onClick={()=>nav("/settings")} className="underline text-sage">Settings</button> to persist.</p>
            </div>
          </Card>
          {error && <div role="alert" className="rounded-xl border border-red-900/30 bg-red-950/20 p-3 text-sm text-red-300">{error}</div>}
          {success && <div role="status" className="rounded-xl border border-sage/20 bg-sage/10 p-3 text-sm text-sage">{success}</div>}
          <Button onClick={doChat} disabled={loadingChat || !message.trim() || settingsReady===false || driveConnected===false} className="w-full" title={settingsReady===false ? "Complete Settings first" : driveConnected===false ? "Connect Drive first" : undefined}>{loadingChat ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Thinking...</> : settingsReady===false ? "Blocked — Complete Settings First" : driveConnected===false ? "Blocked — Connect Drive First" : "Create → Show Draft Letter"}</Button>
          {settingsReady===false && <p className="text-xs text-amber-300 text-center">Go to <button onClick={()=>nav("/settings")} className="underline">Settings</button> to unlock.</p>}
          {driveConnected===false && settingsReady && <p className="text-xs text-amber-300 text-center">Drive not connected — <button onClick={()=>nav("/settings")} className="underline">Connect in Settings</button> to create real Forms/Sheets.</p>}
        </div>

        <div className="space-y-4">
          {!resp ? <Card><p className="text-sm text-zinc-500">Draft preview will appear here after Create. You can edit the permission letter then Send to Principal (PDFs attached).</p></Card> : (
            <>
              <Card>
                <h3 className="font-medium text-white">Agent response</h3>
                <pre className="whitespace-pre-wrap text-sm text-zinc-300 mt-2 bg-white/5 p-3 rounded-xl max-h-40 overflow-auto">{resp.response}</pre>
                <div className="text-xs text-zinc-500 mt-2">Status: {String(resp.status).replaceAll("_"," ")} • ID: {resp.event_id || "—"}</div>
              </Card>
              <Card>
                <label htmlFor="perm-letter" className="font-medium text-white">Permission letter — edit before send</label>
                <textarea id="perm-letter" aria-label="Permission letter" value={editEmail} onChange={e=>setEditEmail(e.target.value)} rows={14} className="w-full mt-2 rounded-xl bg-white/5 border border-white/10 p-3 text-xs text-zinc-200 font-mono focus:outline-none focus:ring-2 focus:ring-oxide" />
                <div className="flex gap-2 mt-3">
                  {resp.permission_email_sent ? <div role="status" className="flex-1 rounded-xl border border-sage/30 bg-sage/10 px-4 py-2 text-center text-sm text-sage">Sent to principal</div> : <Button onClick={()=>setShowConfirm(true)} disabled={loadingSend || loadingApprove || !editEmail.trim()} className="flex-1">Send to Principal (with PDFs)</Button>}
                  {isAdmin && <Button variant="outline" onClick={doApprove} disabled={loadingApprove || loadingSend}>{loadingApprove ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Approving...</> : "Approve (Admin)"}</Button>}
                </div>
                {!isAdmin && <p className="text-xs text-zinc-500 mt-2">After sending, principal approves via Admin dashboard — you’ll be notified when live.</p>}
                {resp.event_id && <Button variant="ghost" onClick={resetForm} className="w-full mt-2 text-xs">Start Fresh — New Event</Button>}
                <p className="text-xs text-zinc-500 mt-2">Send attaches Permission PDF + On-foot PDF (if needed). Shows confirmation first.</p>
              </Card>
              {showConfirm && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur flex items-center justify-center p-4 z-50" onClick={()=>!loadingSend && setShowConfirm(false)}>
                  <Card ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Confirm send to Principal" className="max-w-lg w-full outline-none" onClick={e=>e.stopPropagation()}>
                    <h3 className="font-bold text-white">Confirm send to Principal?</h3>
                    <p className="text-sm text-zinc-400 mt-2">This will email <span className="text-white">{principalEmail || "principal (from Settings)"}</span> with:</p>
                    <ul className="text-xs text-zinc-300 list-disc ml-5 mt-2">
                      <li>Permission Letter PDF</li>
                      {resp?.onfoot_letter && <li>On-foot Publicity PDF</li>}
                    </ul>
                    <p className="text-xs text-zinc-500 mt-2">You can still edit the text above before confirming.</p>
                    <div className="flex gap-2 mt-4">
                      <Button onClick={doSend} disabled={loadingSend} className="flex-1">{loadingSend ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Sending...</> : "Confirm Send"}</Button>
                      <Button variant="outline" onClick={()=>setShowConfirm(false)} disabled={loadingSend} className="flex-1">Cancel / Edit</Button>
                    </div>
                  </Card>
                </div>
              )}
              {resp.announcement_draft && <Card><h3 className="text-sm font-medium text-white">Announcement preview</h3><pre className="whitespace-pre-wrap text-xs text-zinc-400 mt-2">{resp.announcement_draft}</pre></Card>}
            </>
          )}
        </div>
      </div>
    </div>
  </div>
  );
}
