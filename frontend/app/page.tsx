"use client";

import { useState, useEffect, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001";
const ROLES = ["Manager", "Receptionist", "Housekeeper", "F&B"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_COLORS = {
  Mon: "from-indigo-500 to-indigo-600",
  Tue: "from-violet-500 to-violet-600",
  Wed: "from-fuchsia-500 to-fuchsia-600",
  Thu: "from-rose-500 to-rose-600",
  Fri: "from-amber-500 to-amber-600",
  Sat: "from-emerald-500 to-emerald-600",
  Sun: "from-sky-500 to-sky-600",
};
const ROLE_COLORS = {
  Manager: "bg-indigo-100 text-indigo-700",
  Receptionist: "bg-emerald-100 text-emerald-700",
  Housekeeper: "bg-amber-100 text-amber-700",
  "F&B": "bg-rose-100 text-rose-700",
};

async function api(path, opts = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export default function Home() {
  const [state, setState] = useState({ staff: [], shifts: [], assignments: [], applications: [] });
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("admin");
  const [currentUserId, setCurrentUserId] = useState("");

  const [newStaffName, setNewStaffName] = useState("");
  const [newStaffRole, setNewStaffRole] = useState("Manager");
  const [newStaffHours, setNewStaffHours] = useState(40);
  const [newShiftDay, setNewShiftDay] = useState("Mon");
  const [newShiftStart, setNewShiftStart] = useState("09:00");
  const [newShiftEnd, setNewShiftEnd] = useState("17:00");
  const [newShiftRoles, setNewShiftRoles] = useState({ Manager: 1, Receptionist: 1, Housekeeper: 0, "F&B": 0 });

  const [generating, setGenerating] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatBottomRef = useRef(null);

  async function refresh() {
    try { setState(await api("/api/state")); }
    catch (e) { setError(`Failed to load state: ${e.message}`); }
  }
  useEffect(() => { refresh(); }, []);
  useEffect(() => { chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages, chatLoading]);

  async function addStaff() {
    const name = newStaffName.trim();
    if (!name) return setError("Please enter a staff name.");
    try {
      await api("/api/staff", { method: "POST", body: JSON.stringify({
        id: `s${Date.now()}`, name, role: newStaffRole, max_hours: Number(newStaffHours)
      })});
      setNewStaffName(""); setError(null); refresh();
    } catch (e) { setError(e.message); }
  }
  async function removeStaff(id) {
    try { await api(`/api/staff/${id}`, { method: "DELETE" }); refresh(); }
    catch (e) { setError(e.message); }
  }
  async function addShift() {
    const cleaned = {};
    for (const [r, n] of Object.entries(newShiftRoles)) if (n > 0) cleaned[r] = n;
    if (Object.keys(cleaned).length === 0) return setError("Shift requires at least one role.");
    if (newShiftStart >= newShiftEnd) return setError("End must be after start.");
    try {
      await api("/api/shifts", { method: "POST", body: JSON.stringify({
        id: `sh-${Date.now()}`, day: newShiftDay, start: newShiftStart, end: newShiftEnd, required_roles: cleaned
      })});
      setError(null); refresh();
    } catch (e) { setError(e.message); }
  }
  async function removeShift(id) {
    try { await api(`/api/shifts/${id}`, { method: "DELETE" }); refresh(); }
    catch (e) { setError(e.message); }
  }
  async function handleGenerate() {
    if (state.staff.length === 0) return setError("Add at least one staff member.");
    if (state.shifts.length === 0) return setError("Add at least one shift.");
    setGenerating(true); setError(null);
    try {
      await api("/api/generate-roster", { method: "POST", body: JSON.stringify({
        staff: state.staff, shifts: state.shifts
      })});
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setGenerating(false); }
  }
  async function applyForShift(shiftId) {
    if (!currentUserId) return setError("Pick who you are first.");
    try {
      await api("/api/applications", { method: "POST", body: JSON.stringify({
        shift_id: shiftId, staff_id: currentUserId
      })});
      refresh();
    } catch (e) { setError(e.message); }
  }
  async function decideApplication(appId, status) {
    try {
      await api(`/api/applications/${appId}`, { method: "PATCH", body: JSON.stringify({ status }) });
      refresh();
    } catch (e) { setError(e.message); }
  }

  // Multi-turn memory: send the entire conversation history so Claude
  // can resolve follow-ups like "monday" → "remove Ben from monday".
  // We strip any malformed tool_use blocks (missing id) defensively so
  // a stale message can't poison the next request.
  async function sendChat() {
    const text = chatInput.trim();
    if (!text) return;
    const optimistic = [...chatMessages, { role: "user", content: text }];
    const safeHistory = optimistic.filter(m => {
      if (!Array.isArray(m.content)) return true;
      return m.content.every(b => b.type !== "tool_use" || !!b.id);
    });
    setChatMessages(optimistic);
    setChatInput("");
    setChatLoading(true);
    try {
      const result = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ messages: safeHistory }),  // send full history
      });
      const r = result.reply;

      // Preferred: replace local history with the backend's canonical
      // message list — it has the tool_use ids Anthropic requires for
      // multi-turn conversations.
      if (r && Array.isArray(r.messages)) {
        setChatMessages(r.messages);
      } else {
        // Fallback for plain-string replies
        const content = typeof r === "string" ? r : (r?.reply || JSON.stringify(r));
        setChatMessages([...optimistic, { role: "assistant", content }]);
      }
      await refresh();
    } catch (e) {
      setChatMessages(prev => [...prev, { role: "assistant", content: `⚠ ${e.message}` }]);
    }
    finally { setChatLoading(false); }
  }

  // Derived data
  const assignmentsByShift = {};
  for (const a of state.assignments) (assignmentsByShift[a.shift_id] ||= []).push(a);
  function openingsFor(shift, role) {
    const need = shift.required_roles[role] || 0;
    const have = (assignmentsByShift[shift.id] || []).filter(a => a.role === role).length;
    return Math.max(0, need - have);
  }
  const currentUser = state.staff.find(s => s.id === currentUserId);
  const myApplications = state.applications.filter(a => a.staff_id === currentUserId);
  const myPendingShiftIds = new Set(myApplications.filter(a => a.status === "pending").map(a => a.shift_id));
  const myAssignedShiftIds = new Set(state.assignments.filter(a => a.staff_id === currentUserId).map(a => a.shift_id));
  const applicableShifts = currentUser ? state.shifts.filter(sh =>
    openingsFor(sh, currentUser.role) > 0
    && !myAssignedShiftIds.has(sh.id)
    && !myPendingShiftIds.has(sh.id)
  ) : [];
  const myAssignments = state.assignments.filter(a => a.staff_id === currentUserId);
  const pendingApplications = state.applications.filter(a => a.status === "pending");

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50 text-slate-900">
      {/* HEADER */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold shadow-md">Z</div>
            <div>
              <h1 className="text-base font-bold tracking-tight">Zenith Roster Analyzer</h1>
              <p className="text-xs text-slate-500">AI-powered rostering &amp; compliance for hospitality</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {mode === "staff" && (
              <select value={currentUserId} onChange={(e) => setCurrentUserId(e.target.value)}
                className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg bg-white shadow-sm">
                <option value="">— pick who you are —</option>
                {state.staff.map(s => <option key={s.id} value={s.id}>{s.name} ({s.role})</option>)}
              </select>
            )}
            <div className="flex bg-slate-100 rounded-lg p-1 shadow-inner">
              <button onClick={() => setMode("admin")}
                className={`px-3 py-1 text-sm font-medium rounded-md transition ${mode === "admin" ? "bg-white shadow text-indigo-700" : "text-slate-600 hover:text-slate-900"}`}>
                Admin
              </button>
              <button onClick={() => setMode("staff")}
                className={`px-3 py-1 text-sm font-medium rounded-md transition ${mode === "staff" ? "bg-white shadow text-indigo-700" : "text-slate-600 hover:text-slate-900"}`}>
                Staff
              </button>
            </div>
          </div>
        </div>
      </header>

      {error && (
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm flex justify-between items-start shadow-sm">
            <div className="break-all"><strong>Error:</strong> {error}</div>
            <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800 font-bold ml-3 text-lg leading-none">×</button>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {mode === "admin" ? (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* LEFT: Setup */}
              <section className="space-y-4">
                {/* Staff manager */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-semibold text-slate-900">Staff</h2>
                    <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">{state.staff.length}</span>
                  </div>
                  <div className="space-y-1 mb-4">
                    {state.staff.map(s => (
                      <div key={s.id} className="flex justify-between items-center text-sm py-1.5 px-2 hover:bg-slate-50 rounded-md group">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{s.name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${ROLE_COLORS[s.role] || "bg-slate-100 text-slate-600"}`}>{s.role}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-500">{s.max_hours}h/wk</span>
                          <button onClick={() => removeStaff(s.id)}
                            className="text-slate-300 group-hover:text-red-500 hover:text-red-700 text-lg leading-none transition">×</button>
                        </div>
                      </div>
                    ))}
                    {state.staff.length === 0 && <p className="text-xs text-slate-400 italic px-2">No staff yet.</p>}
                  </div>
                  <div className="border-t border-slate-100 pt-3 flex flex-wrap gap-2">
                    <input type="text" value={newStaffName} onChange={e => setNewStaffName(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && addStaff()} placeholder="Name"
                      className="flex-1 min-w-[120px] px-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400" />
                    <select value={newStaffRole} onChange={e => setNewStaffRole(e.target.value)}
                      className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg bg-white">
                      {ROLES.map(r => <option key={r}>{r}</option>)}
                    </select>
                    <input type="number" value={newStaffHours} onChange={e => setNewStaffHours(Number(e.target.value))}
                      min="1" max="80" className="w-16 px-2 py-1.5 text-sm border border-slate-300 rounded-lg" />
                    <button onClick={addStaff}
                      className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition">
                      + Add
                    </button>
                  </div>
                </div>

                {/* Shift manager */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-semibold text-slate-900">Shifts</h2>
                    <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">{state.shifts.length}</span>
                  </div>
                  <div className="space-y-1 mb-4">
                    {state.shifts.map(s => (
                      <div key={s.id} className="flex justify-between items-center text-sm py-1.5 px-2 hover:bg-slate-50 rounded-md group">
                        <div className="flex-1 flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold px-2 py-0.5 bg-slate-100 text-slate-700 rounded">{s.day}</span>
                          <span className="text-slate-700">{s.start}–{s.end}</span>
                          <span className="text-xs text-slate-500">
                            {Object.entries(s.required_roles).map(([r, n]) => `${n} ${r}`).join(" · ")}
                          </span>
                        </div>
                        <button onClick={() => removeShift(s.id)}
                          className="text-slate-300 group-hover:text-red-500 hover:text-red-700 text-lg leading-none transition">×</button>
                      </div>
                    ))}
                    {state.shifts.length === 0 && <p className="text-xs text-slate-400 italic px-2">No shifts yet.</p>}
                  </div>
                  <div className="border-t border-slate-100 pt-3 space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <select value={newShiftDay} onChange={e => setNewShiftDay(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg bg-white">
                        {DAYS.map(d => <option key={d}>{d}</option>)}
                      </select>
                      <input type="time" value={newShiftStart} onChange={e => setNewShiftStart(e.target.value)}
                        className="px-2 py-1.5 text-sm border border-slate-300 rounded-lg" />
                      <span className="text-sm self-center text-slate-500">to</span>
                      <input type="time" value={newShiftEnd} onChange={e => setNewShiftEnd(e.target.value)}
                        className="px-2 py-1.5 text-sm border border-slate-300 rounded-lg" />
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {ROLES.map(r => (
                        <label key={r} className="flex items-center gap-1.5 text-xs">
                          <span className="text-slate-600">{r}</span>
                          <input type="number" min="0" max="10" value={newShiftRoles[r] ?? 0}
                            onChange={e => setNewShiftRoles({ ...newShiftRoles, [r]: Number(e.target.value) })}
                            className="w-12 px-1.5 py-0.5 border border-slate-300 rounded text-center" />
                        </label>
                      ))}
                    </div>
                    <button onClick={addShift}
                      className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition">
                      + Add Shift
                    </button>
                  </div>
                </div>

                <button onClick={handleGenerate} disabled={generating}
                  className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:from-slate-400 disabled:to-slate-400 text-white font-semibold py-3 rounded-xl shadow-md hover:shadow-lg transition flex items-center justify-center gap-2">
                  {generating ? (
                    <>
                      <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Generating roster…
                    </>
                  ) : "✨ Generate Roster with AI"}
                </button>
              </section>

              {/* RIGHT: Output */}
              <section className="space-y-4">
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <h2 className="font-semibold mb-4 text-slate-900">Weekly Roster</h2>
                  {state.assignments.length === 0 ? (
                    <div className="text-center py-8 text-slate-400">
                      <div className="text-3xl mb-2">📅</div>
                      <p className="text-sm">No assignments yet.</p>
                      <p className="text-xs mt-1">Click "Generate Roster" or use the AI Command Center.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {DAYS.filter(d => state.shifts.some(s => s.day === d)).map(day => (
                        <div key={day} className="rounded-lg overflow-hidden border border-slate-200">
                          <div className={`bg-gradient-to-r ${DAY_COLORS[day]} px-3 py-1.5 text-white text-sm font-semibold`}>
                            {day}
                          </div>
                          <div className="divide-y divide-slate-100">
                            {state.shifts.filter(s => s.day === day).map(shift => {
                              const assigned = assignmentsByShift[shift.id] || [];
                              return (
                                <div key={shift.id} className="px-3 py-2">
                                  <div className="text-xs text-slate-500 mb-1">{shift.start}–{shift.end}</div>
                                  {assigned.length === 0 ? (
                                    <div className="text-amber-600 text-xs italic">— unassigned —</div>
                                  ) : (
                                    <div className="flex flex-wrap gap-1.5">
                                      {assigned.map(a => (
                                        <span key={a.staff_id}
                                          className={`text-xs px-2 py-1 rounded-md ${ROLE_COLORS[a.role] || "bg-slate-100 text-slate-700"}`}>
                                          {a.staff_name} <span className="opacity-60">· {a.role}</span>
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="font-semibold text-slate-900">Pending Applications</h2>
                    <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">{pendingApplications.length}</span>
                  </div>
                  {pendingApplications.length === 0 ? (
                    <p className="text-xs text-slate-400 italic">No pending applications.</p>
                  ) : (
                    <div className="space-y-2">
                      {pendingApplications.map(a => (
                        <div key={a.id} className="text-sm flex items-center justify-between py-2 px-3 bg-amber-50 border border-amber-100 rounded-lg">
                          <div>
                            <strong className="text-slate-900">{a.staff_name}</strong>
                            <span className="text-xs text-slate-500 ml-1">({a.staff_role})</span>
                            <span className="mx-1 text-slate-400">→</span>
                            <strong className="text-slate-700">{a.day} {a.start}–{a.end}</strong>
                          </div>
                          <div className="flex gap-1">
                            <button onClick={() => decideApplication(a.id, "approved")}
                              className="px-3 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-md shadow-sm transition">Approve</button>
                            <button onClick={() => decideApplication(a.id, "rejected")}
                              className="px-3 py-1 text-xs bg-slate-300 hover:bg-slate-400 text-slate-800 rounded-md transition">Reject</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            </div>

            {/* CHATBOT */}
            <section className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-indigo-50 to-violet-50">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold">AI</div>
                  <h2 className="font-semibold text-slate-900">AI Command Center</h2>
                </div>
                <button onClick={() => setChatMessages([])}
                  className="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 hover:bg-white rounded transition">Clear</button>
              </div>

              <div className="h-80 overflow-y-auto p-4 bg-slate-50 space-y-3">
                {chatMessages.length === 0 && (
                  <div className="text-center pt-8 text-slate-400 text-sm">
                    <p className="mb-2">💬 Ask me anything about the roster.</p>
                    <div className="flex flex-wrap justify-center gap-1.5 text-xs">
                      {["Who's working Monday?", "Take Anna off Monday morning", "Approve all pending applications"].map(s => (
                        <button key={s} onClick={() => setChatInput(s)}
                          className="px-2 py-1 bg-white border border-slate-200 rounded-full hover:border-indigo-300 hover:text-indigo-700 transition">
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {chatMessages.map((m, i) => {
                  if (m.role === "user" && Array.isArray(m.content)) return null;
                  if (m.role === "user") {
                    return (
                      <div key={i} className="flex justify-end">
                        <div className="bg-gradient-to-br from-indigo-600 to-violet-600 text-white px-3.5 py-2 rounded-2xl rounded-br-sm max-w-md text-sm shadow-sm">
                          {m.content}
                        </div>
                      </div>
                    );
                  }
                  const blocks = Array.isArray(m.content) ? m.content : [{ type: "text", text: m.content }];
                  return (
                    <div key={i} className="flex justify-start gap-2">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">AI</div>
                      <div className="bg-white border border-slate-200 px-3.5 py-2 rounded-2xl rounded-bl-sm max-w-md text-sm space-y-1.5 shadow-sm">
                        {blocks.map((b, j) => {
                          if (b.type === "text") return <div key={j} className="whitespace-pre-wrap">{b.text}</div>;
                          if (b.type === "tool_use") {
                            const prettyName = String(b.name || "")
                              .replace(/_/g, " ")
                              .replace(/\b\w/g, c => c.toUpperCase());
                            const entries = b.input && typeof b.input === "object"
                              ? Object.entries(b.input)
                              : [];
                            return (
                              <div key={j} className="text-xs bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-lg px-2.5 py-1.5 flex items-center gap-2 flex-wrap">
                                <span className="inline-flex items-center gap-1 font-semibold text-amber-800">
                                  <span className="text-amber-500">⚡</span>
                                  {prettyName}
                                </span>
                                {entries.length > 0 && (
                                  <>
                                    <span className="text-amber-300">·</span>
                                    <div className="flex flex-wrap gap-1">
                                      {entries.map(([k, v]) => (
                                        <span key={k} className="inline-flex items-center gap-1 bg-white border border-amber-200 rounded-full px-2 py-0.5 text-amber-900">
                                          <span className="text-amber-600">{k}</span>
                                          <span className="font-medium">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                                        </span>
                                      ))}
                                    </div>
                                  </>
                                )}
                              </div>
                            );
                          }
                          return null;
                        })}
                      </div>
                    </div>
                  );
                })}
                {chatLoading && (
                  <div className="flex justify-start gap-2">
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold">AI</div>
                    <div className="bg-white border border-slate-200 px-3.5 py-2.5 rounded-2xl rounded-bl-sm shadow-sm">
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>

              <div className="border-t border-slate-100 p-3 flex gap-2 bg-white">
                <input type="text" value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !chatLoading && sendChat()}
                  placeholder="Ask the AI to inspect or change the roster…"
                  className="flex-1 px-3.5 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400" />
                <button onClick={sendChat} disabled={chatLoading || !chatInput.trim()}
                  className="px-4 py-2 text-sm bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:from-slate-300 disabled:to-slate-300 text-white rounded-lg shadow-sm transition font-medium">
                  Send
                </button>
              </div>
            </section>
          </>
        ) : (
          /* ===== STAFF MODE ===== */
          !currentUserId ? (
            <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-500 shadow-sm">
              <div className="text-4xl mb-3">👋</div>
              <p>Pick who you are from the dropdown above to see your schedule and available shifts.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-semibold">Available Shifts</h2>
                  <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full">{applicableShifts.length}</span>
                </div>
                <p className="text-xs text-slate-500 mb-3">Open slots matching your role ({currentUser.role}). Click Apply to bid.</p>
                {applicableShifts.length === 0 ? (
                  <p className="text-xs text-slate-400 italic">No open shifts for your role right now.</p>
                ) : (
                  <div className="space-y-2">
                    {applicableShifts.map(sh => (
                      <div key={sh.id} className="flex justify-between items-center py-2.5 px-3 border border-slate-200 rounded-lg text-sm hover:border-indigo-300 hover:shadow-sm transition">
                        <div>
                          <div className="font-medium">{sh.day} {sh.start}–{sh.end}</div>
                          <div className="text-xs text-slate-500">openings: {openingsFor(sh, currentUser.role)} {currentUser.role}</div>
                        </div>
                        <button onClick={() => applyForShift(sh.id)}
                          className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition">Apply</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <h2 className="font-semibold mb-3">My Confirmed Shifts ({myAssignments.length})</h2>
                  {myAssignments.length === 0 ? (
                    <p className="text-xs text-slate-400 italic">Nothing scheduled.</p>
                  ) : (
                    <ul className="text-sm space-y-1.5">
                      {myAssignments.map(a => (
                        <li key={a.id} className="flex items-center gap-2">
                          <span className="w-2 h-2 bg-emerald-500 rounded-full" />
                          {a.day} {a.start}–{a.end} <span className="text-xs text-slate-500">({a.role})</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                  <h2 className="font-semibold mb-3">My Applications ({myApplications.length})</h2>
                  {myApplications.length === 0 ? (
                    <p className="text-xs text-slate-400 italic">No applications.</p>
                  ) : (
                    <ul className="text-sm space-y-1.5">
                      {myApplications.map(a => (
                        <li key={a.id} className="flex justify-between items-center">
                          <span>{a.day} {a.start}–{a.end}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            a.status === "approved" ? "bg-emerald-100 text-emerald-800" :
                            a.status === "rejected" ? "bg-slate-200 text-slate-700" :
                            "bg-amber-100 text-amber-800"
                          }`}>{a.status}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )
        )}
      </div>
    </main>
  );
}