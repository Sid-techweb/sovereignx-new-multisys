import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import { 
  ClipboardList, 
  FileText, 
  Presentation, 
  FileSpreadsheet, 
  Download, 
  CheckCircle, 
  X,
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
        return <FileText className="w-4 h-4 text-console-amber" />;
      case 'PPTX':
        return <Presentation className="w-4 h-4 text-console-amber" />;
      case 'XLSX':
        return <FileSpreadsheet className="w-4 h-4 text-console-green" />;
      default:
        return <ClipboardList className="w-4 h-4 text-console-muted" />;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Audit Reports" 
        description="Generated investigation reports, validation records, and operational exports." 
        actions={
          <button
            onClick={() => setShowGenerateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-console-amber text-[#0b1620] hover:brightness-105 rounded-md font-semibold text-xs transition-all shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber font-mono"
          >
            <Sparkles className="w-4 h-4" />
            GENERATE REPORT
          </button>
        }
      />

      {/* Summary Cards Stat Row */}
      <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] grid grid-cols-1 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-console-lineSoft">
        <div className="flex items-center gap-4 pr-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-console-text">
            <ClipboardList className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">TOTAL REPORTS</div>
            <div className="text-2xl font-bold text-console-text font-mono tabular-nums">{summary.total}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 px-0 md:px-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-console-amber">
            <FileText className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">WORD (.DOCX)</div>
            <div className="text-2xl font-bold text-console-text font-mono tabular-nums">{summary.docx}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 px-0 md:px-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-console-amber">
            <Presentation className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">POWERPOINT (.PPTX)</div>
            <div className="text-2xl font-bold text-console-text font-mono tabular-nums">{summary.pptx}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 pl-0 md:pl-4 pt-2 md:pt-0">
          <div className="w-9 h-9 rounded bg-console-greenSoft border border-console-green/30 flex items-center justify-center text-console-green">
            <FileSpreadsheet className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">EXCEL (.XLSX)</div>
            <div className="text-2xl font-bold text-console-green font-mono tabular-nums">{summary.xlsx}</div>
          </div>
        </div>
      </div>

      {/* Reports Table */}
      <div className="bg-console-panel border border-console-line rounded-lg overflow-hidden backdrop-blur-[2px]">
        {loading ? (
          <div className="p-12 text-center text-console-muted font-mono text-xs">
            Loading generated report records...
          </div>
        ) : reports.length === 0 ? (
          <div className="p-12 text-center space-y-3 font-mono">
            <ClipboardList className="w-10 h-10 text-console-muted mx-auto" />
            <h3 className="text-sm font-semibold text-console-text">No audit reports generated yet.</h3>
            <p className="text-xs text-console-muted max-w-sm mx-auto">
              Click 'Generate Report' above to export an investigation report in Word, PowerPoint, or Excel format.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead className="bg-console-panelSolid border-b border-console-line text-[10px] font-mono text-console-muted uppercase tracking-[0.14em]">
                <tr>
                  <th className="py-2.5 px-4">REPORT ID</th>
                  <th className="py-2.5 px-4">INVESTIGATION / CASE</th>
                  <th className="py-2.5 px-4">FORMAT</th>
                  <th className="py-2.5 px-4">FILENAME</th>
                  <th className="py-2.5 px-4">GENERATED AT</th>
                  <th className="py-2.5 px-4">STATUS</th>
                  <th className="py-2.5 px-4 text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-console-lineSoft">
                {reports.map((r) => (
                  <tr key={r.report_id} className="hover:bg-white/[.02] transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-console-amber flex items-center gap-2 tabular-nums">
                      {getFormatIcon(r.format)}
                      {r.report_id}
                    </td>
                    <td className="py-3 px-4 text-console-text2 max-w-xs truncate" title={r.query}>
                      {r.query}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs font-bold text-console-text uppercase">
                      {r.format}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-console-muted">
                      {r.filename}
                    </td>
                    <td className="py-3 px-4 text-xs font-mono text-console-muted tabular-nums">
                      {new Date(r.generated_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium uppercase tracking-wider bg-console-greenSoft text-console-green border border-console-green/30">
                        {r.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDownloadFile(r.filename)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-white/[.05] hover:bg-white/[.1] text-console-text border border-console-line text-xs rounded font-mono transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
                      >
                        <Download className="w-3.5 h-3.5 text-console-amber" />
                        DOWNLOAD
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
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-console-panelSolid border border-console-line rounded-lg w-full max-w-lg p-6 shadow-2xl space-y-4 text-console-text">
            <div className="flex items-center justify-between border-b border-console-line pb-3">
              <h3 className="text-xs font-bold text-console-text font-mono uppercase tracking-[0.14em] flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-console-amber" />
                GENERATE AUDIT REPORT
              </h3>
              <button onClick={() => setShowGenerateModal(false)} className="text-console-muted hover:text-console-text">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs font-mono">
              <div>
                <label className="block text-console-muted mb-1 uppercase tracking-wider text-[10px]">TARGET INVESTIGATION QUERY</label>
                <div className="bg-console-inset p-3 rounded border border-console-line text-console-text font-mono">
                  {samplePayload.query}
                </div>
              </div>

              <div>
                <label className="block text-console-muted mb-2 uppercase tracking-wider text-[10px]">SELECT OUTPUT FORMAT (PHASE 8 ENDPOINTS)</label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    onClick={() => setSelectedFormat('docx')}
                    className={`p-3 rounded border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'docx'
                        ? 'bg-console-amberSoft border-console-amber text-console-amber font-bold shadow'
                        : 'bg-console-inset border-console-line text-console-muted hover:text-console-text'
                    }`}
                  >
                    <FileText className="w-6 h-6 text-console-amber" />
                    <span>Word (.DOCX)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedFormat('pptx')}
                    className={`p-3 rounded border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'pptx'
                        ? 'bg-console-amberSoft border-console-amber text-console-amber font-bold shadow'
                        : 'bg-console-inset border-console-line text-console-muted hover:text-console-text'
                    }`}
                  >
                    <Presentation className="w-6 h-6 text-console-amber" />
                    <span>PowerPoint (.PPTX)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedFormat('xlsx')}
                    className={`p-3 rounded border flex flex-col items-center gap-2 transition-all ${
                      selectedFormat === 'xlsx'
                        ? 'bg-console-greenSoft border-console-green text-console-green font-bold shadow'
                        : 'bg-console-inset border-console-line text-console-muted hover:text-console-text'
                    }`}
                  >
                    <FileSpreadsheet className="w-6 h-6 text-console-green" />
                    <span>Excel (.XLSX)</span>
                  </button>
                </div>
              </div>

              <div className="bg-console-inset border border-console-line p-3 rounded text-console-muted text-xs font-mono space-y-1">
                <div className="text-console-text font-semibold flex items-center gap-1.5 uppercase text-[10px] tracking-wider">
                  <CheckCircle className="w-3.5 h-3.5 text-console-green" />
                  PRESERVED PROVENANCE GUARANTEE
                </div>
                <p className="text-[10px] text-console-text2">
                  Reports preserve grounded findings, citations, filenames, page numbers, chunk IDs, and deterministic Phase 6 tool verifications.
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-console-line">
                <button
                  type="button"
                  onClick={() => setShowGenerateModal(false)}
                  className="px-4 py-1.5 bg-white/[.05] text-console-text rounded border border-console-line hover:bg-white/[.1]"
                >
                  CANCEL
                </button>
                <button
                  type="button"
                  onClick={handleGenerateReport}
                  disabled={isGenerating}
                  className="px-4 py-1.5 bg-console-amber text-[#0b1620] font-semibold rounded hover:brightness-105 shadow flex items-center gap-1.5"
                >
                  {isGenerating ? "GENERATING..." : `GENERATE & DOWNLOAD .${selectedFormat.toUpperCase()}`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
