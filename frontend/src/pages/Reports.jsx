import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import { 
  ClipboardList, 
  FileText, 
  Presentation, 
  FileSpreadsheet, 
  Download, 
  Plus, 
  CheckCircle, 
  Clock, 
  X,
  FileCode,
  Layers,
  Sparkles
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [summary, setSummary] = useState({ total: 0, docx: 0, pptx: 0, xlsx: 0 });
  const [loading, setLoading] = useState(true);
  
  // Generate Report Modal State
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('docx');
  const [isGenerating, setIsGenerating] = useState(false);

  // Default sample investigation payload for demonstration
  const samplePayload = {
    query: "What happened to Pump P-204?",
    answer: "Pump P-204 experienced abnormal housing temperatures of 91 C [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02]. The radial vibration reading was elevated at 5.8 mm/s [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02]. The SOP bearing housing limit is 80 C [Source: pump_P204_SOP.pdf | page=1 | chunk_id=377c635a-2a55-4de3-b040-522c4bb00973].",
    confidence: 0.85,
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
    ],
    metadata: {
      model_used: "qwen2.5:7b",
      latency_ms: 142.5
    }
  };

  const fetchReports = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/reports`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (response.ok) {
        const data = await response.json();
        setReports(data.reports || []);
        setSummary(data.summary || { total: 0, docx: 0, pptx: 0, xlsx: 0 });
      }
    } catch (err) {
      console.error("Error fetching reports list:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleGenerateReport = async () => {
    setIsGenerating(true);
    try {
      const endpoint = `/reports/generate-${selectedFormat.toLowerCase()}`;
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify(samplePayload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Report generation failed');
      }

      // Download file directly from stream
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `SovereignX_Report.${selectedFormat.toLowerCase()}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setShowGenerateModal(false);
      fetchReports();
    } catch (err) {
      alert(`Report generation error: ${err.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownloadFile = async (filename) => {
    try {
      const response = await fetch(`${API_BASE}/reports/download/${filename}`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (!response.ok) {
        throw new Error('Download failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Error downloading report: ${err.message}`);
    }
  };

  const getFormatIcon = (fmt) => {
    switch (fmt?.toUpperCase()) {
      case 'DOCX':
        return <FileText className="w-4 h-4 text-sky-400" />;
      case 'PPTX':
        return <Presentation className="w-4 h-4 text-amber-400" />;
      case 'XLSX':
        return <FileSpreadsheet className="w-4 h-4 text-emerald-400" />;
      default:
        return <ClipboardList className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Audit Reports" 
        description="Generated investigation reports, validation records, and operational exports." 
        action={
          <button
            onClick={() => setShowGenerateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium text-sm transition-all shadow-md hover:shadow-sky-500/20"
          >
            <Sparkles className="w-4 h-4" />
            Generate Report
          </button>
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <ClipboardList className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.total}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Total Reports</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.docx}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Word (.DOCX)</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <Presentation className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.pptx}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">PowerPoint (.PPTX)</div>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <FileSpreadsheet className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-100 font-mono">{summary.xlsx}</div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Excel (.XLSX)</div>
          </div>
        </div>
      </div>

      {/* Reports Table */}
      <div className="bg-slate-900/30 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-500 font-mono text-sm">
            Loading generated report records...
          </div>
        ) : reports.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <ClipboardList className="w-12 h-12 text-slate-700 mx-auto" />
            <h3 className="text-base font-semibold text-slate-300">No audit reports have been generated yet.</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Click 'Generate Report' above to export an investigation report in Word, PowerPoint, or Excel format.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950/60 border-b border-slate-800 text-xs font-mono text-slate-400 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 px-4">Report ID</th>
                  <th className="py-3.5 px-4">Investigation / Case</th>
                  <th className="py-3.5 px-4">Format</th>
                  <th className="py-3.5 px-4">Filename</th>
                  <th className="py-3.5 px-4">Generated At</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850 font-sans">
                {reports.map((r) => (
                  <tr key={r.report_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-mono font-bold text-sky-400 flex items-center gap-2">
                      {getFormatIcon(r.format)}
                      {r.report_id}
                    </td>
                    <td className="py-3.5 px-4 text-slate-300 max-w-xs truncate" title={r.query}>
                      {r.query}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs font-bold text-slate-300 uppercase">
                      {r.format}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                      {r.filename}
                    </td>
                    <td className="py-3.5 px-4 text-xs font-mono text-slate-500">
                      {new Date(r.generated_at).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="px-2.5 py-1 rounded-full text-xs font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-800/50">
                        {r.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleDownloadFile(r.filename)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-950/60 hover:bg-sky-900/60 text-sky-400 border border-sky-800/60 text-xs rounded font-medium transition-all"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Generate Report Modal */}
      {showGenerateModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-slate-100 font-mono flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-sky-400" />
                Generate Audit Report
              </h3>
              <button onClick={() => setShowGenerateModal(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Target Investigation Query</label>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 font-mono">
                  {samplePayload.query}
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-2">Select Output Format (Phase 8 Endpoints)</label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    onClick={() => setSelectedFormat('docx')}
                    className={`p-3 rounded-lg border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'docx'
                        ? 'bg-sky-950/80 border-sky-500 text-sky-300 shadow-md'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <FileText className="w-6 h-6 text-sky-400" />
                    <span>Word (.DOCX)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedFormat('pptx')}
                    className={`p-3 rounded-lg border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'pptx'
                        ? 'bg-amber-950/80 border-amber-500 text-amber-300 shadow-md'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <Presentation className="w-6 h-6 text-amber-400" />
                    <span>PowerPoint (.PPTX)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedFormat('xlsx')}
                    className={`p-3 rounded-lg border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'xlsx'
                        ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300 shadow-md'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <FileSpreadsheet className="w-6 h-6 text-emerald-400" />
                    <span>Excel (.XLSX)</span>
                  </button>
                </div>
              </div>

              <div className="bg-slate-950/60 border border-slate-850 p-3 rounded-lg text-slate-400 text-xs font-mono space-y-1">
                <div className="text-slate-300 font-semibold flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  Preserved Provenance Guarantee
                </div>
                <p className="text-[11px] text-slate-500">
                  Reports preserve grounded findings, citations, filenames, page numbers, chunk IDs, and deterministic Phase 6 tool verifications without modification.
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowGenerateModal(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 font-mono"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleGenerateReport}
                  disabled={isGenerating}
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium shadow-md font-mono flex items-center gap-2"
                >
                  {isGenerating ? "Generating..." : `Generate & Download .${selectedFormat.toUpperCase()}`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
