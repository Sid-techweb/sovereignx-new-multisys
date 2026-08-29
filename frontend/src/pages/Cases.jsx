import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import StatusBadge from '../components/common/StatusBadge';
import { 
  Briefcase, 
  Eye, 
  Plus, 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  ShieldAlert, 
  FileText, 
  Cpu, 
  Search,
  X,
  ExternalLink,
  ChevronRight
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Cases() {
  const [cases, setCases] = useState([]);
  const [summary, setSummary] = useState({ total: 0, open: 0, under_investigation: 0, resolved: 0 });
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);
  
  // Create Case Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCaseForm, setNewCaseForm] = useState({
    query: "What happened to Pump P-204?",
    answer: "Pump P-204 experienced abnormal housing temperatures of 91 C [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02]. The radial vibration reading was elevated at 5.8 mm/s [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02]. The SOP bearing housing limit is 80 C [Source: pump_P204_SOP.pdf | page=1 | chunk_id=377c635a-2a55-4de3-b040-522c4bb00973].",
    asset: "Pump P-204",
    status: "Under Investigation",
    severity: "High",
    confidence: 0.85
  });
  const [isCreating, setIsCreating] = useState(false);

  const fetchCases = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/cases`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (response.ok) {
        const data = await response.json();
        setCases(data.cases || []);
        setSummary(data.summary || { total: 0, open: 0, under_investigation: 0, resolved: 0 });
      }
    } catch (err) {
      console.error("Error fetching cases:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, []);

  const handleCreateCase = async (e) => {
    e.preventDefault();
    if (!newCaseForm.query.trim() || !newCaseForm.answer.trim()) return;

    setIsCreating(true);
    try {
      const response = await fetch(`${API_BASE}/cases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({
          query: newCaseForm.query,
          answer: newCaseForm.answer,
          asset: newCaseForm.asset,
          status: newCaseForm.status,
          severity: newCaseForm.severity,
          confidence: Number(newCaseForm.confidence),
          retrieved_chunks: [
            {
              chunk_id: "c2c4c44f-4bbb-420d-898d-449ed40a9f02",
              filename: "pump_P204_sensor_data.csv",
              source: "user_upload",
              content: "temperature_c: 91\nvibration_mm_s: 5.8",
              metadata: { page_number: 1 }
            },
            {
              chunk_id: "377c635a-2a55-4de3-b040-522c4bb00973",
              filename: "pump_P204_SOP.pdf",
              source: "user_upload",
              content: "bearing housing limit is 80 C",
              metadata: { page_number: 1 }
            }
          ],
          tool_executions: [
            {
              tool_name: "compare_reading_against_sop_limit",
              arguments: { reading_value: 91.0, limit_value: 80.0, comparison_type: "greater_than", unit: "C" },
              outputs: { is_exceeded: true, summary: "Exceedance detected: Reading (91.0 C) is greater than SOP limit (80.0 C) by 11.0 C (13.75%)." },
              status: "success"
            },
            {
              tool_name: "compare_reading_against_sop_limit",
              arguments: { reading_value: 5.8, limit_value: 4.0, comparison_type: "greater_than", unit: "mm/s" },
              outputs: { is_exceeded: true, summary: "Exceedance detected: Reading (5.8 mm/s) is greater than SOP limit (4.0 mm/s) by 1.8 mm/s (45.0%)." },
              status: "success"
            }
          ]
        })
      });

      if (response.ok) {
        setShowCreateModal(false);
        fetchCases();
      } else {
        const errData = await response.json();
        alert(`Failed to create case: ${errData.detail || 'Server error'}`);
      }
    } catch (err) {
      alert(`Error creating case: ${err.message}`);
    } finally {
      setIsCreating(false);
    }
  };

  const handleUpdateStatusSeverity = async (caseId, newStatus, newSeverity) => {
    try {
      const response = await fetch(`${API_BASE}/cases/${caseId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({
          status: newStatus,
          severity: newSeverity
        })
      });

      if (response.ok) {
        const updated = await response.json();
        setSelectedCase(updated);
        fetchCases();
      }
    } catch (err) {
      console.error("Error updating case:", err);
    }
  };

  const getSeverityBadgeClass = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'bg-rose-950/80 text-rose-400 border-rose-800/60';
      case 'high':
        return 'bg-amber-950/80 text-amber-400 border-amber-800/60';
      case 'medium':
        return 'bg-sky-950/80 text-sky-400 border-sky-800/60';
      case 'low':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60';
      default:
        return 'bg-slate-900 text-slate-400 border-slate-800';
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status?.toLowerCase()) {
      case 'resolved':
        return 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50';
      case 'under investigation':
        return 'bg-sky-950/60 text-sky-400 border-sky-800/50';
      case 'open':
        return 'bg-amber-950/60 text-amber-400 border-amber-800/50';
      default:
        return 'bg-slate-900 text-slate-400 border-slate-800';
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Anomaly Cases" 
        description="Asset anomaly cases, investigation status, evidence, and verification history." 
        action={
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium text-sm transition-all shadow-md hover:shadow-sky-500/20"
          >
            <Plus className="w-4 h-4" />
            Create Case from Investigation
          </button>
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <Briefcase className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.total}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Total Cases</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.open}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Open</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.under_investigation}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Under Investigation</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.resolved}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Resolved</div>
          </div>
        </div>
      </div>

      {/* Case List Table */}
      <div className="bg-slate-900/30 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-500 font-mono text-sm">
            Loading anomaly cases...
          </div>
        ) : cases.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Briefcase className="w-12 h-12 text-slate-700 mx-auto" />
            <h3 className="text-base font-semibold text-slate-300">No anomaly cases yet</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Run an investigation or click 'Create Case from Investigation' above to record an anomaly case.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950/60 border-b border-slate-800 text-xs font-mono text-slate-400 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 px-4">Case ID</th>
                  <th className="py-3.5 px-4">Asset</th>
                  <th className="py-3.5 px-4">Issue / Finding</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4">Severity</th>
                  <th className="py-3.5 px-4">Evidence</th>
                  <th className="py-3.5 px-4">Confidence</th>
                  <th className="py-3.5 px-4">Created</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850 font-sans">
                {cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-mono font-bold text-sky-400">{c.case_id}</td>
                    <td className="py-3.5 px-4 font-medium text-slate-200">{c.asset}</td>
                    <td className="py-3.5 px-4 text-slate-300 max-w-xs truncate" title={c.finding}>
                      {c.title || c.finding}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-col gap-1 items-start">
                        <span className={`px-2.5 py-1 rounded-full text-xs font-mono border ${getStatusBadgeClass(c.status)}`}>
                          {c.status}
                        </span>
                        {c.requires_human_review && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-amber-400" />
                            NEEDS REVIEW
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-mono font-medium border ${getSeverityBadgeClass(c.severity)}`}>
                        {c.severity}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                      {c.evidence ? `${c.evidence.length} source(s)` : '0 sources'}
                    </td>
                    <td className={`py-3.5 px-4 font-mono text-xs font-bold ${c.requires_human_review ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {(c.confidence * 100).toFixed(2)}%
                    </td>
                    <td className="py-3.5 px-4 text-xs font-mono text-slate-500">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => setSelectedCase(c)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded font-medium transition-all border border-slate-700"
                      >
                        <Eye className="w-3.5 h-3.5 text-sky-400" />
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Case Detail Modal */}
      {selectedCase && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl space-y-6 p-6">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 font-mono font-bold">
                  <Briefcase className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-100 font-mono flex items-center gap-2">
                    {selectedCase.case_id}
                    <span className="text-sm font-sans font-normal text-slate-400">— {selectedCase.asset}</span>
                  </h3>
                  <p className="text-xs text-slate-400">Recorded: {new Date(selectedCase.created_at).toLocaleString()}</p>
                </div>
              </div>
              <button 
                onClick={() => setSelectedCase(null)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Escalation Warning Box if applicable */}
            {selectedCase.requires_human_review && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3.5 flex items-start gap-3 text-amber-300">
                <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="text-xs font-bold font-mono uppercase tracking-wider">
                    ⚠️ Low Retrieval Confidence — Human Review Recommended
                  </h4>
                  <p className="text-xs text-amber-200/80 mt-1 font-sans">
                    {selectedCase.escalation_reason || `Retrieval confidence (${(selectedCase.confidence * 100).toFixed(1)}%) is below safety threshold (70.0%). Recommend manual operator verification before acting on this finding.`}
                  </p>
                </div>
              </div>
            )}

            {/* Operator Controls: Status & Severity Manual Controls */}
            <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-xs font-mono uppercase text-slate-500 mb-1">Status (Manual)</label>
                  <select
                    value={selectedCase.status}
                    onChange={(e) => handleUpdateStatusSeverity(selectedCase.case_id, e.target.value, selectedCase.severity)}
                    className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 font-mono focus:outline-none focus:border-sky-500"
                  >
                    <option value="Open">Open</option>
                    <option value="Under Investigation">Under Investigation</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase text-slate-500 mb-1">Severity (Manual)</label>
                  <select
                    value={selectedCase.severity}
                    onChange={(e) => handleUpdateStatusSeverity(selectedCase.case_id, selectedCase.status, e.target.value)}
                    className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 font-mono focus:outline-none focus:border-sky-500"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>
              </div>

              <div>
                <span className="text-xs font-mono text-slate-500 uppercase block mb-1">Confidence Score</span>
                <span className="font-mono text-sm font-bold text-emerald-400">
                  {(selectedCase.confidence * 100).toFixed(2)}%
                </span>
              </div>
            </div>

            {/* Investigation Query & Grounded Findings */}
            <div className="space-y-4">
              <div>
                <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-1.5">Investigation Query</h4>
                <p className="text-sm font-medium text-slate-200 bg-slate-950/40 p-3 rounded-lg border border-slate-850 font-mono">
                  {selectedCase.query}
                </p>
              </div>

              <div>
                <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-1.5">Grounded Finding & Analysis</h4>
                <div className="text-sm text-slate-300 bg-slate-950/40 p-4 rounded-lg border border-slate-850 leading-relaxed whitespace-pre-wrap font-sans">
                  {selectedCase.finding}
                </div>
              </div>
            </div>

            {/* Evidence & Provenance Traceability Section */}
            <div className="space-y-3">
              <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-2">
                <FileText className="w-4 h-4 text-sky-400" />
                Evidence Provenance (Phase 8 Citation Logic)
              </h4>
              {selectedCase.evidence && selectedCase.evidence.length > 0 ? (
                <div className="bg-slate-950/50 border border-slate-850 rounded-lg overflow-hidden">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 uppercase">
                      <tr>
                        <th className="py-2.5 px-3">Ref</th>
                        <th className="py-2.5 px-3">Document Filename</th>
                        <th className="py-2.5 px-3">Page</th>
                        <th className="py-2.5 px-3">Source Chunk ID</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-850 text-slate-300">
                      {selectedCase.evidence.map((ev) => (
                        <tr key={ev.index || ev.chunk_id}>
                          <td className="py-2 px-3 font-bold text-sky-400">[{ev.index}]</td>
                          <td className="py-2 px-3">{ev.filename}</td>
                          <td className="py-2 px-3">{ev.page !== null ? `Page ${ev.page}` : 'N/A'}</td>
                          <td className="py-2 px-3 text-slate-400 truncate max-w-[200px]" title={ev.chunk_id}>
                            {ev.chunk_id}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic font-mono bg-slate-950/40 p-3 rounded-lg">
                  No explicit citation references associated with this case finding.
                </p>
              )}
            </div>

            {/* Deterministic Tool Executions Section */}
            {selectedCase.tool_executions && selectedCase.tool_executions.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-emerald-400" />
                  Deterministic Tool Verification Results (Phase 6)
                </h4>
                <div className="space-y-2">
                  {selectedCase.tool_executions.map((t, idx) => (
                    <div key={idx} className="bg-slate-950/50 border border-slate-850 rounded-lg p-3 text-xs font-mono space-y-1">
                      <div className="flex items-center justify-between text-slate-300">
                        <span className="font-bold text-sky-400">{t.tool_name}</span>
                        <span className="text-emerald-400 uppercase font-semibold">{t.status}</span>
                      </div>
                      <p className="text-slate-400">{t.outputs?.summary}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Case Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-xl p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-slate-100 font-mono flex items-center gap-2">
                <Plus className="w-4 h-4 text-sky-400" />
                Create Anomaly Case
              </h3>
              <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateCase} className="space-y-4 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Asset Name</label>
                <input
                  type="text"
                  value={newCaseForm.asset}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, asset: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Investigation Query</label>
                <input
                  type="text"
                  value={newCaseForm.query}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, query: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Finding / Grounded Answer</label>
                <textarea
                  rows={4}
                  value={newCaseForm.answer}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, answer: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 font-sans"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-slate-400 mb-1">Status</label>
                  <select
                    value={newCaseForm.status}
                    onChange={(e) => setNewCaseForm({ ...newCaseForm, status: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                  >
                    <option value="Open">Open</option>
                    <option value="Under Investigation">Under Investigation</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Severity</label>
                  <select
                    value={newCaseForm.severity}
                    onChange={(e) => setNewCaseForm({ ...newCaseForm, severity: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating}
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium shadow-md"
                >
                  {isCreating ? "Saving..." : "Create Case"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
