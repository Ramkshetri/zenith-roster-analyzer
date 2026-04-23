"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5001";

const SAMPLE_STAFF = `[
  { "id": "s1", "name": "Anna Martinez",  "role": "Manager",      "max_hours": 40 },
  { "id": "s2", "name": "David Chen",     "role": "Manager",      "max_hours": 35 },
  { "id": "s3", "name": "Priya Sharma",   "role": "Receptionist", "max_hours": 32 },
  { "id": "s4", "name": "Tom O'Brien",    "role": "Receptionist", "max_hours": 30 },
  { "id": "s5", "name": "Sofia Romano",   "role": "Housekeeper",  "max_hours": 38 }
]`;

const SAMPLE_SHIFTS = `[
  { "id": "mon-am", "day": "Mon", "start": "07:00", "end": "15:00",
    "required_roles": { "Manager": 1, "Receptionist": 1, "Housekeeper": 1 } },
  { "id": "mon-pm", "day": "Mon", "start": "15:00", "end": "23:00",
    "required_roles": { "Manager": 1, "Receptionist": 1 } },
  { "id": "tue-am", "day": "Tue", "start": "07:00", "end": "15:00",
    "required_roles": { "Manager": 1, "Receptionist": 1, "Housekeeper": 1 } },
  { "id": "tue-pm", "day": "Tue", "start": "15:00", "end": "23:00",
    "required_roles": { "Manager": 1, "Receptionist": 1 } },
  { "id": "wed-am", "day": "Wed", "start": "07:00", "end": "15:00",
    "required_roles": { "Manager": 1, "Receptionist": 1, "Housekeeper": 1 } }
]`;

const DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Home() {
  const [staffText, setStaffText] = useState(SAMPLE_STAFF);
  const [shiftsText, setShiftsText] = useState(SAMPLE_SHIFTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [roster, setRoster] = useState(null);

  async function handleGenerate() {
    setError(null);
    setRoster(null);

    let staff, shifts;
    try {
      staff = JSON.parse(staffText);
      shifts = JSON.parse(shiftsText);
    } catch (e) {
      setError(`Invalid JSON in inputs: ${e.message}`);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/generate-roster`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ staff, shifts }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || `Backend returned HTTP ${res.status}`);
      }
      setRoster(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Group roster shifts by day for cleaner display
  const shiftsByDay = {};
  if (roster?.roster) {
    for (const shift of roster.roster) {
      (shiftsByDay[shift.day] ||= []).push(shift);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <h1 className="text-xl font-bold">Zenith Roster Analyzer</h1>
          <p className="text-sm text-slate-600">
            AI-powered staff rostering &amp; compliance checks for hospitality operations
          </p>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* INPUT PANEL */}
        <section className="space-y-4">
          <div>
            <label className="block text-sm font-semibold mb-1">Staff (JSON)</label>
            <textarea
              value={staffText}
              onChange={(e) => setStaffText(e.target.value)}
              rows={12}
              className="w-full font-mono text-xs p-3 rounded-md border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">Shifts (JSON)</label>
            <textarea
              value={shiftsText}
              onChange={(e) => setShiftsText(e.target.value)}
              rows={14}
              className="w-full font-mono text-xs p-3 rounded-md border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white font-semibold py-3 rounded-md transition"
          >
            {loading ? "Generating roster…" : "Generate Roster"}
          </button>

          {error && (
            <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-800 text-sm">
              <strong>Error:</strong> {error}
            </div>
          )}
        </section>

        {/* OUTPUT PANEL */}
        <section className="space-y-4">
          {!roster && !loading && (
            <div className="p-6 rounded-md border-2 border-dashed border-slate-300 text-slate-500 text-center">
              The generated roster will appear here.
            </div>
          )}

          {loading && (
            <div className="p-6 rounded-md bg-white border border-slate-200 text-slate-600 text-center">
              Claude is thinking… (typically 3–8 seconds)
            </div>
          )}

          {roster && (
            <>
              {/* Roster grouped by day */}
              <div className="bg-white border border-slate-200 rounded-md p-4">
                <h2 className="font-semibold mb-3">Weekly Roster</h2>
                <div className="space-y-3">
                  {DAY_ORDER.filter((d) => shiftsByDay[d]).map((day) => (
                    <div key={day}>
                      <h3 className="text-sm font-bold text-indigo-700">{day}</h3>
                      <div className="space-y-1 mt-1">
                        {shiftsByDay[day].map((shift) => (
                          <div
                            key={shift.shift_id}
                            className="text-sm border-l-2 border-indigo-200 pl-3"
                          >
                            <div className="text-slate-600">
                              {shift.start}–{shift.end}{" "}
                              <span className="text-xs text-slate-400">({shift.shift_id})</span>
                            </div>
                            <div className="ml-2">
                              {shift.assignments?.length ? (
                                shift.assignments.map((a) => (
                                  <div key={a.staff_id}>
                                    • {a.name}{" "}
                                    <span className="text-xs text-slate-500">({a.role})</span>
                                  </div>
                                ))
                              ) : (
                                <div className="text-red-600 text-xs">No one assigned</div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Staff hours summary */}
              {roster.staff_summary?.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-md p-4">
                  <h2 className="font-semibold mb-2">Staff Hours</h2>
                  <div className="space-y-1 text-sm">
                    {roster.staff_summary.map((s) => {
                      const pct = Math.min(100, (s.scheduled_hours / s.max_hours) * 100);
                      return (
                        <div key={s.staff_id}>
                          <div className="flex justify-between text-xs">
                            <span>{s.name}</span>
                            <span className="text-slate-500">
                              {s.scheduled_hours}h / {s.max_hours}h
                            </span>
                          </div>
                          <div className="h-2 bg-slate-100 rounded">
                            <div
                              className={`h-2 rounded ${
                                pct >= 100 ? "bg-red-500" : pct >= 85 ? "bg-amber-500" : "bg-emerald-500"
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Uncovered slots */}
              {roster.uncovered_slots?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-md p-4">
                  <h2 className="font-semibold text-red-800 mb-2">Uncovered Slots</h2>
                  <ul className="text-sm text-red-800 space-y-1">
                    {roster.uncovered_slots.map((u, i) => (
                      <li key={i}>
                        <strong>{u.shift_id}</strong> — missing {u.missing_count} {u.role}: {u.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Manager gaps */}
              {roster.manager_gaps?.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-4">
                  <h2 className="font-semibold text-amber-900 mb-2">Manager-on-Duty Gaps</h2>
                  <ul className="text-sm text-amber-900 space-y-1">
                    {roster.manager_gaps.map((g, i) => (
                      <li key={i}>
                        {g.day} {g.start}–{g.end}: {g.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Warnings */}
              {roster.warnings?.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-4">
                  <h2 className="font-semibold text-amber-900 mb-2">Warnings</h2>
                  <ul className="text-sm text-amber-900 space-y-1 list-disc list-inside">
                    {roster.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}