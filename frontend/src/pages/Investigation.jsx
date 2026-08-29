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
      }
      const data = await response.json();
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
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
            <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 mb-4 border-b border-console-lineSoft">
              MODEL GATEWAY TESTING INTERFACE
            </h2>
            <form onSubmit={handleAnalyze} className="space-y-4">
              <div>
                <label className="block text-[10px] font-mono text-console-muted uppercase tracking-[0.14em] mb-2">
                  INPUT PROMPT / INSPECTION FINDINGS
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full h-44 bg-console-inset border border-console-line rounded-md p-3 text-xs font-mono text-console-text focus:outline-none focus:border-console-amber resize-none leading-relaxed"
                  placeholder="Enter findings description here..."
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isLoading || !isConnected}
                  className="flex items-center gap-2 px-4 py-2 bg-console-amber text-[#0b1620] hover:brightness-105 disabled:opacity-40 font-semibold rounded-md shadow text-xs transition-all font-mono focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
                >
                  {isLoading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ANALYZING...
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      ANALYZE
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Response Panel */}
          {(analysisResult || error || isLoading) && (
            <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px]">
              <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 mb-4 border-b border-console-lineSoft">
                ANALYSIS RESPONSE
              </h3>

              {isLoading && (
                <div className="flex flex-col items-center justify-center py-10 space-y-2">
                  <div className="w-6 h-6 border-2 border-console-amber/20 border-t-console-amber rounded-full animate-spin"></div>
                  <p className="text-xs text-console-muted font-mono">Consulting Model Gateway...</p>
                </div>
              )}

              {error && (
                <div className="bg-console-red/10 border border-console-red/30 rounded p-3 flex gap-3 text-console-red text-xs font-mono">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold uppercase tracking-wider text-[10px]">ANALYSIS FAILED</p>
                    <p className="text-console-text2 mt-1 font-sans">{error}</p>
                  </div>
                </div>
              )}

              {analysisResult && !isLoading && (
                <div className="space-y-4">
                  {/* Phase 10 Confidence-Gated Escalation Banner */}
                  {analysisResult.requires_human_review && (
                    <div className="bg-console-amberSoft border border-console-amber/40 rounded p-3.5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-console-amber font-mono text-xs">
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="w-4 h-4 text-console-amber mt-0.5 flex-shrink-0" />
                        <div>
                          <h4 className="text-[11px] font-bold uppercase tracking-wider">
                            LOW RETRIEVAL CONFIDENCE — HUMAN REVIEW RECOMMENDED
                          </h4>
                          <p className="text-xs text-console-text2 mt-1 font-sans">
                            {analysisResult.escalation_reason}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleCreateCase(true)}
                        disabled={createCaseStatus === 'creating'}
                        className="px-3 py-1.5 bg-console-amber text-[#0b1620] hover:brightness-105 font-bold text-xs rounded shadow transition-all flex-shrink-0 font-mono"
                      >
                        {createCaseStatus === 'creating' ? 'CREATING...' : 'CREATE ESCALATED CASE FILE'}
                      </button>
                    </div>
                  )}

                  {createCaseStatus && createCaseStatus !== 'creating' && (
                    <div className="bg-console-greenSoft border border-console-green/30 text-console-green px-3 py-2 rounded text-xs font-mono">
                      {createCaseStatus}
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-console-inset p-3.5 border border-console-line rounded">
                      <p className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">FINDING</p>
                      <p className="text-xs text-console-text mt-1 font-medium">{analysisResult.finding}</p>
                    </div>

                    <div className="bg-console-inset p-3.5 border border-console-line rounded">
                      <p className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">SOP REFERENCE</p>
                      <p className="text-xs text-console-amber mt-1 font-mono font-bold">{analysisResult.sop_reference}</p>
                    </div>

                    <div className="bg-console-inset p-3.5 border border-console-line rounded font-mono">
                      <p className="text-[10px] text-console-muted uppercase tracking-[0.14em]">CONFIDENCE METRIC</p>
                      <div className="flex items-center gap-3 mt-2">
                        <div className="w-full bg-console-panelSolid h-1.5 rounded overflow-hidden">
                          <div 
                            className={`${analysisResult.requires_human_review ? 'bg-console-amber' : 'bg-console-green'} h-full rounded transition-all duration-300`} 
                            style={{ width: `${analysisResult.confidence * 100}%` }}
                          />
                        </div>
                        <span className={`text-xs font-bold tabular-nums ${analysisResult.requires_human_review ? 'text-console-amber' : 'text-console-green'}`}>
                          {(analysisResult.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    <div className="bg-console-inset p-3.5 border border-console-line rounded font-mono">
                      <p className="text-[10px] text-console-muted uppercase tracking-[0.14em]">VERIFICATION STATUS</p>
                      <div className="flex items-center gap-2 text-xs font-medium mt-2">
                        {analysisResult.requires_human_review ? (
                          <span className="text-console-amber flex items-center gap-1.5 font-bold">
                            <AlertTriangle className="w-4 h-4 text-console-amber" /> ESCALATION: HUMAN REVIEW REQ
                          </span>
                        ) : (
                          <span className="text-console-green flex items-center gap-1.5 font-bold">
                            <CheckCircle className="w-4 h-4 text-console-green" /> READY FOR AUDIT REVIEW
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="bg-console-inset p-3.5 border border-console-line rounded">
                    <p className="text-[10px] text-console-muted font-mono uppercase tracking-[0.14em]">RECOMMENDED ACTION</p>
                    <p className="text-xs text-console-text mt-1 font-medium">{analysisResult.recommended_action}</p>
                  </div>

                  <div className="border-t border-console-lineSoft pt-3 flex justify-between items-center text-[10px] text-console-muted font-mono">
                    <span>GATEWAY PROVIDER: {modelConfig.provider.toUpperCase()}</span>
                    <span>MODEL: {modelConfig.model.toUpperCase()}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sidebar Info/Instruction Card */}
        <div className="space-y-6">
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] space-y-3 font-mono">
            <h3 className="text-[11px] tracking-[0.14em] text-console-muted uppercase pb-2 border-b border-console-lineSoft">GATEWAY CONTEXT</h3>
            <div className="text-xs space-y-2">
              <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                <span className="text-console-muted uppercase text-[10px]">PROVIDER:</span>
                <span className="text-console-text font-bold uppercase">{modelConfig.provider}</span>
              </div>
              <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                <span className="text-console-muted uppercase text-[10px]">MODEL NAME:</span>
                <span className="text-console-text font-bold">{modelConfig.model || 'mock'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-console-muted uppercase text-[10px]">STATUS:</span>
                <span className={`font-bold uppercase ${modelConfig.status === 'available' ? 'text-console-green' : 'text-console-amber'}`}>
                  {modelConfig.status}
                </span>
              </div>
            </div>
            <p className="text-xs text-console-text2 font-sans leading-relaxed pt-2 border-t border-console-lineSoft">
              This terminal queries the active model gateway. When set to <code className="bg-console-inset px-1 py-0.5 rounded text-console-amber font-mono">mock</code>, response is populated with deterministic Phase 1 outputs.
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

  const getScoreBandColor = (scorePercent) => {
    if (scorePercent >= 80) return 'text-console-green';
    if (scorePercent >= 60) return 'text-console-amber';
    return 'text-console-muted';
  };

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] space-y-3 font-mono">
      <h3 className="text-[11px] tracking-[0.14em] text-console-muted uppercase pb-2 border-b border-console-lineSoft">
        LOCAL RAG EVIDENCE SEARCH
      </h3>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Query local KB..."
          className="flex-1 bg-console-inset border border-console-line focus:border-console-amber rounded px-2.5 py-1 text-xs text-console-text outline-none placeholder-console-muted font-sans"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-3 py-1 bg-console-amber hover:brightness-105 disabled:opacity-40 rounded text-xs font-bold text-[#0b1620] transition-colors"
        >
          FIND
        </button>
      </form>

      {loading && (
        <div className="text-[10px] text-console-muted font-mono animate-pulse">
          Retrieving relevance chunks...
        </div>
      )}

      {error && (
        <div className="text-[10px] text-console-red font-mono">
          Error: {error}
        </div>
      )}

      {searched && results.length === 0 && (
        <div className="text-[10px] text-console-muted font-mono italic">
          {belowThreshold 
            ? "No sufficiently relevant evidence found in the knowledge base for this query."
            : "No matching evidence found. Ensure documents are processed and indexed."}
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
          <div className="text-[9px] font-mono text-console-muted uppercase tracking-widest border-b border-console-lineSoft pb-1">
            RETRIEVED EVIDENCE CHUNKS
          </div>
          {results.map((res) => {
            const scorePercent = Number((res.score * 100).toFixed(0));
            const scoreColor = getScoreBandColor(scorePercent);
            return (
              <div key={res.chunk_id} className="bg-console-inset border border-console-line p-2.5 rounded text-[10px] font-mono space-y-1.5">
                <div className="flex justify-between text-[9px] text-console-muted border-b border-console-lineSoft pb-1">
                  <span className="text-console-amber truncate max-w-[120px]" title={res.filename}>{res.filename}</span>
                  <span className={`font-bold tabular-nums ${scoreColor}`}>{scorePercent}% MATCH</span>
                </div>
                <p className="text-console-text2 line-clamp-3 leading-relaxed font-sans text-xs">{res.content}</p>
                <button
                  type="button"
                  onClick={() => onPastePrompt(res.content)}
                  className="w-full py-1 bg-white/[.05] hover:bg-white/[.1] border border-console-line text-[9px] font-bold text-console-text rounded transition-colors font-mono"
                >
                  PASTE AS PROMPT CONTEXT
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
