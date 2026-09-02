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
  FileText, 
  Cpu, 
  X
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
        return 'bg-console-red/10 text-console-red border-console-red/30';
      case 'high':
        return 'bg-console-amberSoft text-console-amber border-console-amber/30';
      case 'medium':
        return 'bg-console-panelSolid text-console-text2 border-console-line';
      case 'low':
        return 'bg-console-greenSoft text-console-green border-console-green/30';
      default:
        return 'bg-console-panelSolid text-console-muted border-console-line';
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Anomaly Cases" 
        description="Asset anomaly cases, investigation status, evidence, and verification history." 
        actions={
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-console-amber text-[#0b1620] hover:brightness-105 rounded-md font-semibold text-xs transition-all shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
          >
            <Plus className="w-4 h-4" />
            CREATE CASE FROM INVESTIGATION
          </button>
        }
      />

      {/* Summary Cards Stat Row */}
      <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] grid grid-cols-1 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-console-lineSoft">
        <div className="flex items-center gap-4 pr-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-console-text">
            <Briefcase className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">TOTAL CASES</div>
            <div className="text-2xl font-bold text-console-text font-mono tabular-nums">{summary.total}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 px-0 md:px-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-amberSoft border border-console-amber/30 flex items-center justify-center text-console-amber">
            <AlertTriangle className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">OPEN</div>
            <div className="text-2xl font-bold text-console-amber font-mono tabular-nums">{summary.open}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 px-0 md:px-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-console-text2">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">UNDER INVESTIGATION</div>
            <div className="text-2xl font-bold text-console-text font-mono tabular-nums">{summary.under_investigation}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 pl-0 md:pl-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-greenSoft border border-console-green/30 flex items-center justify-center text-console-green">
            <CheckCircle className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">RESOLVED</div>
            <div className="text-2xl font-bold text-console-green font-mono tabular-nums">{summary.resolved}</div>
          </div>
        </div>
      </div>

      {/* Case List Table */}
      <div className="bg-console-panel border border-console-line rounded-lg overflow-hidden backdrop-blur-[2px]">
        {loading ? (
          <div className="p-12 text-center text-console-muted font-mono text-xs">
            Loading anomaly cases...
          </div>
        ) : cases.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Briefcase className="w-10 h-10 text-console-muted mx-auto" />
            <h3 className="text-sm font-semibold text-console-text">No anomaly cases recorded</h3>
            <p className="text-xs text-console-muted max-w-sm mx-auto font-mono">
              Run an investigation or click 'Create Case from Investigation' above to record an anomaly case.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead className="bg-console-panelSolid border-b border-console-line text-[10px] font-mono text-console-muted uppercase tracking-[0.14em]">
                <tr>
                  <th className="py-2.5 px-4">CASE ID</th>
                  <th className="py-2.5 px-4">ASSET</th>
                  <th className="py-2.5 px-4">ISSUE / FINDING</th>
                  <th className="py-2.5 px-4">STATUS</th>
                  <th className="py-2.5 px-4">SEVERITY</th>
                  <th className="py-2.5 px-4">EVIDENCE</th>
                  <th className="py-2.5 px-4">CONFIDENCE</th>
                  <th className="py-2.5 px-4">CREATED</th>
                  <th className="py-2.5 px-4 text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-console-lineSoft">
                {cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-white/[.02] transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-console-amber tabular-nums">{c.case_id}</td>
                    <td className="py-3 px-4 font-medium text-console-text">{c.asset}</td>
                    <td className="py-3 px-4 text-console-text2 max-w-xs truncate" title={c.finding}>
                      {c.title || c.finding}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-col gap-1 items-start">
                        <StatusBadge status={c.status} />
                        {c.requires_human_review && (
                          <span className="px-2 py-0.5 rounded text-[9px] font-mono font-bold bg-console-amberSoft text-console-amber border border-console-amber/40 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-console-amber" />
                            NEEDS REVIEW
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border uppercase tracking-wider ${getSeverityBadgeClass(c.severity)}`}>
                        {c.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-console-muted tabular-nums">
                      {c.evidence ? `${c.evidence.length} source(s)` : '0 sources'}
                    </td>
                    <td className={`py-3 px-4 font-mono text-xs font-bold tabular-nums ${c.requires_human_review ? 'text-console-amber' : 'text-console-green'}`}>
                      {(c.confidence * 100).toFixed(2)}%
                    </td>
                    <td className="py-3 px-4 text-xs font-mono text-console-muted tabular-nums">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => setSelectedCase(c)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-white/[.05] hover:bg-white/[.1] text-console-text text-xs rounded border border-console-line font-mono transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
                      >
                        <Eye className="w-3.5 h-3.5 text-console-amber" />
                        VIEW
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
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-console-panelSolid border border-console-line rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl space-y-5 p-6 text-console-text">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-console-line pb-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded bg-console-amberSoft border border-console-amber/30 flex items-center justify-center text-console-amber font-mono font-bold">
                  <Briefcase className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-console-text font-mono flex items-center gap-2">
                    {selectedCase.case_id}
                    <span className="text-xs font-sans font-normal text-console-text2">— {selectedCase.asset}</span>
                  </h3>
                  <p className="text-[11px] text-console-muted font-mono">RECORDED: {new Date(selectedCase.created_at).toLocaleString()}</p>
                </div>
              </div>
              <button 
                onClick={() => setSelectedCase(null)}
                className="text-console-muted hover:text-console-text p-1 rounded hover:bg-white/[.05] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Escalation Warning Box if applicable */}
            {selectedCase.requires_human_review && (
              <div className="bg-console-amberSoft border border-console-amber/30 rounded p-3.5 flex items-start gap-3 text-console-amber font-mono text-xs">
                <AlertTriangle className="w-4 h-4 text-console-amber mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="text-[11px] font-bold uppercase tracking-wider">
                    LOW RETRIEVAL CONFIDENCE — HUMAN REVIEW RECOMMENDED
                  </h4>
                  <p className="text-xs text-console-text2 mt-1 font-sans">
                    {selectedCase.escalation_reason || `Retrieval confidence (${(selectedCase.confidence * 100).toFixed(1)}%) is below safety threshold (70.0%). Recommend manual operator verification before acting on this finding.`}
                  </p>
                </div>
              </div>
            )}

            {/* Operator Controls: Status & Severity Manual Controls */}
            <div className="bg-console-inset border border-console-line rounded p-4 flex flex-wrap items-center justify-between gap-4 font-mono text-xs">
              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-console-muted mb-1">STATUS (MANUAL)</label>
                  <select
                    value={selectedCase.status}
                    onChange={(e) => handleUpdateStatusSeverity(selectedCase.case_id, e.target.value, selectedCase.severity)}
                    className="bg-console-panelSolid border border-console-line text-console-text text-xs rounded px-3 py-1.5 focus:outline-none focus:border-console-amber"
                  >
                    <option value="Open">Open</option>
                    <option value="Under Investigation">Under Investigation</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-console-muted mb-1">SEVERITY (MANUAL)</label>
                  <select
                    value={selectedCase.severity}
                    onChange={(e) => handleUpdateStatusSeverity(selectedCase.case_id, selectedCase.status, e.target.value)}
                    className="bg-console-panelSolid border border-console-line text-console-text text-xs rounded px-3 py-1.5 focus:outline-none focus:border-console-amber"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>
              </div>

              <div>
                <span className="text-[10px] uppercase tracking-wider text-console-muted block mb-1">CONFIDENCE SCORE</span>
                <span className="font-mono text-sm font-bold text-console-green tabular-nums">
                  {(selectedCase.confidence * 100).toFixed(2)}%
                </span>
              </div>
            </div>

            {/* Investigation Query & Grounded Findings */}
            <div className="space-y-4">
              <div>
                <h4 className="text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted mb-1.5">INVESTIGATION QUERY</h4>
                <p className="text-xs font-mono text-console-text bg-console-inset p-3 rounded border border-console-line">
                  {selectedCase.query}
                </p>
              </div>

              <div>
                <h4 className="text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted mb-1.5">GROUNDED FINDING & ANALYSIS</h4>
                <div className="text-xs text-console-text bg-console-inset p-4 rounded border border-console-line leading-relaxed whitespace-pre-wrap font-sans">
                  {selectedCase.finding}
                </div>
              </div>
            </div>

            {/* Evidence & Provenance Traceability Section */}
            <div className="space-y-3">
              <h4 className="text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-console-amber" />
                EVIDENCE PROVENANCE (PHASE 8 CITATION LOGIC)
              </h4>
              {selectedCase.evidence && selectedCase.evidence.length > 0 ? (
                <div className="bg-console-inset border border-console-line rounded overflow-hidden">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-console-panelSolid border-b border-console-line text-console-muted uppercase text-[10px] tracking-wider">
                      <tr>
                        <th className="py-2 px-3">REF</th>
                        <th className="py-2 px-3">DOCUMENT FILENAME</th>
                        <th className="py-2 px-3">PAGE</th>
                        <th className="py-2 px-3">SOURCE CHUNK ID</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-console-lineSoft text-console-text2">
                      {selectedCase.evidence.map((ev) => (
                        <tr key={ev.index || ev.chunk_id}>
                          <td className="py-2 px-3 font-bold text-console-amber">[{ev.index}]</td>
                          <td className="py-2 px-3">{ev.filename}</td>
                          <td className="py-2 px-3">{ev.page !== null ? `Page ${ev.page}` : 'N/A'}</td>
                          <td className="py-2 px-3 text-console-muted truncate max-w-[200px]" title={ev.chunk_id}>
                            {ev.chunk_id}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-console-muted italic font-mono bg-console-inset p-3 rounded border border-console-line">
                  No explicit citation references associated with this case finding.
                </p>
              )}
            </div>

            {/* Deterministic Tool Executions Section */}
            {selectedCase.tool_executions && selectedCase.tool_executions.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted flex items-center gap-2">
                  <Cpu className="w-3.5 h-3.5 text-console-green" />
                  DETERMINISTIC TOOL VERIFICATION RESULTS (PHASE 6)
                </h4>
                <div className="space-y-2">
                  {selectedCase.tool_executions.map((t, idx) => (
                    <div key={idx} className="bg-console-inset border border-console-line rounded p-3 text-xs font-mono space-y-1">
                      <div className="flex items-center justify-between text-console-text">
                        <span className="font-bold text-console-amber">{t.tool_name}</span>
                        <span className="text-console-green uppercase font-semibold">{t.status}</span>
                      </div>
                      <p className="text-console-text2">{t.outputs?.summary}</p>
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
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-console-panelSolid border border-console-line rounded-lg w-full max-w-xl p-6 shadow-2xl space-y-4 text-console-text">
            <div className="flex items-center justify-between border-b border-console-line pb-3">
              <h3 className="text-sm font-bold text-console-text font-mono flex items-center gap-2 uppercase tracking-wider">
                <Plus className="w-4 h-4 text-console-amber" />
                CREATE ANOMALY CASE
              </h3>
              <button onClick={() => setShowCreateModal(false)} className="text-console-muted hover:text-console-text">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateCase} className="space-y-4 text-xs font-mono">
              <div>
                <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">ASSET NAME</label>
                <input
                  type="text"
                  value={newCaseForm.asset}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, asset: e.target.value })}
                  className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-console-text focus:outline-none focus:border-console-amber"
                  required
                />
              </div>

              <div>
                <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">INVESTIGATION QUERY</label>
                <input
                  type="text"
                  value={newCaseForm.query}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, query: e.target.value })}
                  className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-console-text focus:outline-none focus:border-console-amber"
                  required
                />
              </div>

              <div>
                <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">FINDING / GROUNDED ANSWER</label>
                <textarea
                  rows={4}
                  value={newCaseForm.answer}
                  onChange={(e) => setNewCaseForm({ ...newCaseForm, answer: e.target.value })}
                  className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-console-text focus:outline-none focus:border-console-amber font-sans text-xs"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">STATUS</label>
                  <select
                    value={newCaseForm.status}
                    onChange={(e) => setNewCaseForm({ ...newCaseForm, status: e.target.value })}
                    className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-console-text focus:outline-none focus:border-console-amber"
                  >
                    <option value="Open">Open</option>
                    <option value="Under Investigation">Under Investigation</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>

                <div>
                  <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">SEVERITY</label>
                  <select
                    value={newCaseForm.severity}
                    onChange={(e) => setNewCaseForm({ ...newCaseForm, severity: e.target.value })}
                    className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-console-text focus:outline-none focus:border-console-amber"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-console-line">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-1.5 bg-white/[.05] text-console-text rounded border border-console-line hover:bg-white/[.1]"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  disabled={isCreating}
                  className="px-4 py-1.5 bg-console-amber text-[#0b1620] font-semibold rounded hover:brightness-105 shadow"
                >
                  {isCreating ? "SAVING..." : "CREATE CASE"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
