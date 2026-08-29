import React, { useState } from 'react';
import PageHeader from '../components/common/PageHeader';
import { Send, RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Investigation({ modelConfig, isConnected }) {
  const [prompt, setPrompt] = useState(
    "Inspection Report:\nPump P-204 bearing housing temperature = 91°C.\n\nSOP:\nMaximum permitted temperature = 80°C.\n\nEquipment data:\nVibration is elevated."
  );
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAnalyze = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);

    try {
      const response = await fetch(`${API_BASE}/agents/investigate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({ query: prompt })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned status ${response.status}`);
      }      const data = await response.json();
      const formattedResult = {
        raw_data: data,
        query: data.query,
        answer: data.answer,
        retrieved_chunks: data.retrieved_chunks,
        tool_executions: data.tool_executions,
        finding: data.answer,
        sop_reference: data.retrieved_chunks
          ? data.retrieved_chunks
              .map(c => c.filename)
              .filter((v, i, a) => a.indexOf(v) === i)
              .join(', ')
          : 'N/A',
        confidence: data.confidence,
        requires_human_review: data.requires_human_review || (data.confidence < 0.7000),
        escalation_reason: data.escalation_reason || `Retrieval confidence (${(data.confidence * 100).toFixed(1)}%) is below safety threshold (70.0%) — recommend manual verification before acting on this finding.`,
        recommended_action: data.tool_executions && data.tool_executions.length > 0 
          ? data.tool_executions.map(t => t.outputs?.summary).filter(Boolean).join('\n')
          : 'Review RAG evidence citations above.'
      };
      setAnalysisResult(formattedResult);
    } catch (err) {
      setError(err.message || 'An error occurred during analysis');
    } finally {
      setIsLoading(false);
    }
  };

  const [createCaseStatus, setCreateCaseStatus] = useState(null);

  const handleCreateCase = async (isEscalated = false) => {
    if (!analysisResult) return;
    setCreateCaseStatus('creating');
    try {
      const res = await fetch(`${API_BASE}/cases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({
          query: analysisResult.query,
          answer: analysisResult.answer,
          confidence: analysisResult.confidence,
          requires_human_review: isEscalated || analysisResult.requires_human_review,
          escalation_reason: analysisResult.escalation_reason,
          retrieved_chunks: analysisResult.retrieved_chunks || [],
          tool_executions: analysisResult.tool_executions || []
        })
      });
      if (!res.ok) throw new Error('Failed to create case');
      const caseData = await res.json();
      setCreateCaseStatus(`Case ${caseData.case_id} created successfully!`);
      setTimeout(() => setCreateCaseStatus(null), 5000);
    } catch (err) {
      setCreateCaseStatus(`Error creating case: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Investigation" 
        description="Interact with the configured Model Gateway to validate asset anomalies" 
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Input Panel */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-6 shadow-lg flex flex-col">
            <h2 className="text-sm font-bold tracking-wider text-slate-400 uppercase mb-4">
              Model Gateway Testing Interface
            </h2>
            <form onSubmit={handleAnalyze} className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 font-mono">
                  Input Prompt / Inspection Findings
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full h-48 bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 text-sm font-mono text-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 resize-none leading-relaxed"
                  placeholder="Enter findings description here..."
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isLoading || !isConnected}
                  className="flex items-center gap-2 px-5 py-2.5 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-855 disabled:text-slate-600 font-medium rounded-lg shadow-lg text-sm text-white transition-all"
                >
                  {isLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Send className="w-4 h-4" />
                      Analyze
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Response Panel */}
          {(analysisResult || error || isLoading) && (
            <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-6 shadow-lg animate-fadeIn">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">
                Analysis Response
              </h3>

              {isLoading && (
                <div className="flex flex-col items-center justify-center py-10 space-y-3">
                  <div className="w-8 h-8 border-4 border-sky-500/20 border-t-sky-500 rounded-full animate-spin"></div>
                  <p className="text-xs text-slate-400 font-mono">Consulting Model Gateway...</p>
                </div>
              )}

              {error && (
                <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-4 flex gap-3 text-rose-400 text-sm">
                  <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                  <div>
                    <p className="font-semibold font-mono text-xs uppercase tracking-wider">Analysis Failed</p>
                    <p className="text-slate-400 mt-1 font-sans text-xs">{error}</p>
                  </div>
                </div>
              )}

              {analysisResult && !isLoading && (
                <div className="space-y-4">
                  {/* Phase 10 Confidence-Gated Escalation Banner */}
                  {analysisResult.requires_human_review && (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 animate-fadeIn">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-amber-300">
                            ⚠️ Low Retrieval Confidence — Human Review Recommended
                          </h4>
                          <p className="text-xs text-amber-200/80 mt-1 font-sans">
                            {analysisResult.escalation_reason}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleCreateCase(true)}
                        disabled={createCaseStatus === 'creating'}
                        className="px-3.5 py-2 bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs rounded-lg shadow transition-colors flex-shrink-0 font-mono"
                      >
                        {createCaseStatus === 'creating' ? 'Creating...' : 'Create Escalated Case File'}
                      </button>
                    </div>
                  )}

                  {createCaseStatus && createCaseStatus !== 'creating' && (
                    <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-4 py-2.5 rounded-lg text-xs font-mono">
                      {createCaseStatus}
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-slate-950/60 p-4 border border-slate-855 rounded-lg">
                      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Finding</p>
                      <p className="text-sm text-slate-200 mt-1.5 font-medium">{analysisResult.finding}</p>
                    </div>

                    <div className="bg-slate-950/60 p-4 border border-slate-855 rounded-lg">
                      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">SOP Reference</p>
                      <p className="text-sm text-sky-400 mt-1.5 font-mono font-bold">{analysisResult.sop_reference}</p>
                    </div>

                    <div className="bg-slate-950/60 p-4 border border-slate-855 rounded-lg">
                      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Confidence Metric</p>
                      <div className="flex items-center gap-3 mt-2">
                        <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                          <div 
                            className={`${analysisResult.requires_human_review ? 'bg-amber-500' : 'bg-sky-500'} h-full rounded-full transition-all duration-300`} 
                            style={{ width: `${analysisResult.confidence * 100}%` }}
                          />
                        </div>
                        <span className={`text-xs font-bold font-mono ${analysisResult.requires_human_review ? 'text-amber-400' : 'text-sky-400'}`}>
                          {(analysisResult.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    <div className="bg-slate-950/60 p-4 border border-slate-855 rounded-lg">
                      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Verification Status</p>
                      <div className="flex items-center gap-2 text-xs font-medium mt-2 font-mono">
                        {analysisResult.requires_human_review ? (
                          <span className="text-amber-400 flex items-center gap-1.5 font-bold">
                            <AlertTriangle className="w-4 h-4" /> ESCALATION: HUMAN REVIEW REQ
                          </span>
                        ) : (
                          <span className="text-emerald-400 flex items-center gap-1.5 font-bold">
                            <CheckCircle className="w-4 h-4" /> READY FOR AUDIT REVIEW
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-950/60 p-4 border border-slate-850 rounded-lg">
                    <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Recommended Action</p>
                    <p className="text-sm text-slate-200 mt-1.5 font-medium">{analysisResult.recommended_action}</p>
                  </div>

                  <div className="border-t border-slate-800/80 pt-4 flex justify-between items-center text-[10px] text-slate-500 font-mono">
                    <span>Gateway Provider: {modelConfig.provider}</span>
                    <span>Model: {modelConfig.model}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sidebar Info/Instruction Card */}
        <div className="space-y-6">
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Gateway Context</h3>
            <div className="text-xs space-y-3 font-mono">
              <div className="flex justify-between border-b border-slate-850 pb-2">
                <span className="text-slate-500">Provider:</span>
                <span className="text-slate-300 font-bold uppercase">{modelConfig.provider}</span>
              </div>
              <div className="flex justify-between border-b border-slate-850 pb-2">
                <span className="text-slate-500">Model Name:</span>
                <span className="text-slate-300 font-bold">{modelConfig.model || 'mock'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Status:</span>
                <span className={`font-bold ${modelConfig.status === 'available' ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {modelConfig.status}
                </span>
              </div>
            </div>
            <p className="text-xs text-slate-500 font-sans leading-relaxed pt-2 border-t border-slate-850">
              This terminal queries the active model gateway. When the provider is set to <code className="bg-slate-950 px-1 py-0.5 rounded text-sky-400">mock</code>, the response is instantaneously populated with deterministic, verified Phase 1 outputs.
            </p>
          </div>

          {/* Local RAG Retrieval Card */}
          <InvestigationRagCard 
            onPastePrompt={(text) => setPrompt(prev => prev ? `${prev}\n\nEvidence Context:\n${text}` : `Evidence Context:\n${text}`)} 
          />
        </div>

      </div>
    </div>
  );
}

function InvestigationRagCard({ onPastePrompt }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [belowThreshold, setBelowThreshold] = useState(false);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResults([]);
    setBelowThreshold(false);
    setSearched(false);

    try {
      const res = await fetch(`${API_BASE}/knowledge-base/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5 })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Retrieval failed.');
      }

      const data = await res.json();
      setResults(data.results);
      setBelowThreshold(data.below_threshold || false);
      setSearched(true);
    } catch (err) {
      setError(err.message || 'Retrieval error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
        Local RAG Evidence Search
      </h3>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Query local KB..."
          className="flex-1 bg-slate-950/70 border border-slate-850 focus:border-sky-500 rounded px-2.5 py-1.5 text-xs text-slate-350 outline-none placeholder-slate-650"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-855 disabled:text-slate-600 rounded text-xs font-bold text-slate-200 transition-colors"
        >
          Find
        </button>
      </form>

      {loading && (
        <div className="text-[10px] text-slate-500 font-mono animate-pulse">
          Retrieving relevance chunks...
        </div>
      )}

      {error && (
        <div className="text-[10px] text-rose-400 font-mono">
          Error: {error}
        </div>
      )}

      {searched && results.length === 0 && (
        <div className="text-[10px] text-slate-500 font-mono italic">
          {belowThreshold 
            ? "No sufficiently relevant evidence found in the knowledge base for this query."
            : "No matching evidence found. Ensure documents are processed and indexed."}
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
          <div className="text-[9px] font-mono text-slate-500 uppercase tracking-widest border-b border-slate-900 pb-1.5">
            Retrieved Evidence Chunks
          </div>
          {results.map((res) => (
            <div key={res.chunk_id} className="bg-slate-950/50 border border-slate-850 p-2.5 rounded text-[10px] font-mono space-y-2">
              <div className="flex justify-between text-[9px] text-slate-500 border-b border-slate-900 pb-1">
                <span className="text-sky-400 truncate max-w-[120px]" title={res.filename}>{res.filename}</span>
                <span className="text-emerald-400 font-bold">{(res.score * 100).toFixed(0)}% Match</span>
              </div>
              <p className="text-slate-300 line-clamp-3 leading-relaxed">{res.content}</p>
              <button
                type="button"
                onClick={() => onPastePrompt(res.content)}
                className="w-full py-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[9px] font-bold text-slate-400 hover:text-slate-300 rounded transition-colors"
              >
                Paste as Prompt Context
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

