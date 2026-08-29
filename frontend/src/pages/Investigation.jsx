import React, { useState } from 'react';
import PageHeader from '../components/common/PageHeader';
import { Send, RefreshCw, AlertTriangle, CheckCircle, Sparkles, ChevronRight, FileText, Activity } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Investigation({ modelConfig, isConnected }) {
  const [prompt, setPrompt] = useState(
    "Inspection Report:\nPump P-204 bearing housing temperature = 91°C.\n\nSOP:\nMaximum permitted temperature = 80°C.\n\nEquipment data:\nVibration is elevated."
  );
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createCaseStatus, setCreateCaseStatus] = useState(null);

  const handleAnalyze = async (e) => {
    if (e) e.preventDefault();
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

  const handleNewTurn = () => {
    setPrompt('');
    setAnalysisResult(null);
    setError(null);
    setCreateCaseStatus(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Investigation" 
        description="Ask questions about your industrial knowledge base and receive grounded answers from SovereignX." 
        actions={
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleNewTurn}
              className="px-3.5 py-1.5 bg-white/[.05] hover:bg-white/[.1] text-console-text text-xs font-mono font-semibold rounded border border-console-line transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
            >
              New turn
            </button>
            <a
              href="/reports"
              className="px-3.5 py-1.5 bg-console-amber hover:brightness-105 text-[#0b1620] text-xs font-mono font-bold rounded shadow transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
            >
              Generate report
            </a>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Main Conversation Panel */}
        <div className="lg:col-span-2 flex flex-col space-y-4">
          <div className="bg-console-panel border border-console-line rounded-lg p-5 backdrop-blur-[2px] min-h-[520px] flex flex-col justify-between">
            
            {/* Conversation Flow Area */}
            <div className="flex-1 flex flex-col">
              
              {/* Empty State */}
              {!analysisResult && !isLoading && !error && (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-8 space-y-4 my-auto">
                  <div className="w-12 h-12 rounded-full bg-console-amberSoft border border-console-amber/30 flex items-center justify-center text-console-amber">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-xs font-mono font-bold uppercase tracking-[0.14em] text-console-text">
                      ASK SOVEREIGNX
                    </h3>
                    <p className="text-xs text-console-muted max-w-md mx-auto mt-1.5 font-sans leading-relaxed">
                      Ask questions about equipment, inspections, SOPs, reports, and other indexed industrial documents.
                    </p>
                  </div>
                  
                  {/* Pre-fill suggestion chips */}
                  <div className="flex flex-wrap gap-2 justify-center max-w-lg pt-3 font-mono text-[11px]">
                    {[
                      "What happened to Pump P-204?",
                      "What is the SOP bearing temperature limit?",
                      "Summarize radial vibration limits"
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => setPrompt(suggestion)}
                        className="px-3 py-1.5 bg-console-inset hover:bg-white/[.05] border border-console-line rounded text-console-text2 hover:text-console-text transition-colors text-left"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Active Conversation Flow */}
              {(analysisResult || isLoading || error) && (
                <div className="space-y-6 flex-1 overflow-y-auto pb-4">
                  
                  {/* User Query Message */}
                  <div className="flex gap-3 items-start bg-console-inset border border-console-line rounded-lg p-4 font-sans">
                    <div className="w-7 h-7 rounded bg-console-panelSolid border border-console-line flex items-center justify-center text-[10px] font-mono font-bold text-console-muted shrink-0 mt-0.5">
                      YOU
                    </div>
                    <div className="text-xs font-mono text-console-text leading-relaxed whitespace-pre-wrap">
                      {analysisResult?.query || prompt}
                    </div>
                  </div>

                  {/* Loading State */}
                  {isLoading && (
                    <div className="flex gap-3 items-start bg-console-panelSolid/60 border border-console-lineSoft rounded-lg p-4">
                      <div className="w-7 h-7 rounded bg-console-amberSoft border border-console-amber/30 flex items-center justify-center text-console-amber text-[10px] font-mono font-bold shrink-0 mt-0.5 animate-pulse">
                        SX
                      </div>
                      <div className="flex items-center gap-2 text-xs font-mono text-console-muted py-1">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-console-amber" />
                        <span>Consulting Model Gateway and retrieving evidence...</span>
                      </div>
                    </div>
                  )}

                  {/* Error State */}
                  {error && (
                    <div className="bg-console-red/10 border border-console-red/30 rounded-lg p-4 flex gap-3 text-console-red text-xs font-mono">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-bold uppercase tracking-wider text-[10px]">ANALYSIS FAILED</p>
                        <p className="text-console-text2 mt-1 font-sans">{error}</p>
                      </div>
                    </div>
                  )}

                  {/* Assistant Response Card */}
                  {analysisResult && !isLoading && (
                    <div className="flex gap-3 items-start bg-console-panelSolid/80 border border-console-line rounded-lg p-5 font-sans space-y-4">
                      <div className="w-7 h-7 rounded bg-console-amber text-[#0b1620] flex items-center justify-center text-[10px] font-mono font-bold shrink-0 mt-0.5">
                        SX
                      </div>
                      
                      <div className="flex-1 space-y-4">
                        {/* Header Metadata Pill */}
                        <div className="flex items-center justify-between border-b border-console-lineSoft pb-2.5 font-mono text-[10px]">
                          <span className="text-console-muted font-bold tracking-widest uppercase">SOVEREIGNX ASSISTANT</span>
                          
                          {/* Confidence Score Pill */}
                          <div className="flex items-center gap-2">
                            <span className={`px-2.5 py-0.5 rounded border font-mono font-bold tabular-nums text-[10px] uppercase tracking-wider ${
                              analysisResult.confidence >= 0.8 
                                ? 'bg-console-greenSoft text-console-green border-console-green/30' 
                                : analysisResult.confidence >= 0.6 
                                  ? 'bg-console-amberSoft text-console-amber border-console-amber/30' 
                                  : 'bg-console-panelSolid text-console-muted border-console-lineSoft'
                            }`}>
                              {(analysisResult.confidence * 100).toFixed(1)}% GROUNDED
                            </span>
                          </div>
                        </div>

                        {/* Conversational Assistant Response Text */}
                        <div className="text-[15px] leading-[1.65] text-console-text font-normal space-y-3 font-sans">
                          {analysisResult.answer}
                        </div>

                        {/* Cited Evidence Chips */}
                        {analysisResult.retrieved_chunks && analysisResult.retrieved_chunks.length > 0 && (
                          <div className="pt-3 border-t border-console-lineSoft space-y-2">
                            <span className="text-[10px] font-mono uppercase tracking-widest text-console-muted block">EVIDENCE CITATIONS:</span>
                            <div className="flex flex-wrap gap-2">
                              {analysisResult.retrieved_chunks.map((chunk, idx) => (
                                <span 
                                  key={idx} 
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-console-amberSoft border border-console-amber/30 text-console-amber font-mono text-[11px] font-bold"
                                >
                                  [{chunk.filename}{chunk.page ? ` · p.${chunk.page}` : ''}]
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Human Review Escalation Banner & Secondary Action */}
                        {analysisResult.requires_human_review && (
                          <div className="bg-console-amberSoft border border-console-amber/40 rounded p-3.5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-console-amber font-mono text-xs">
                            <div className="flex items-start gap-2.5">
                              <AlertTriangle className="w-4 h-4 text-console-amber mt-0.5 shrink-0" />
                              <div>
                                <h4 className="text-[11px] font-bold uppercase tracking-wider">HUMAN REVIEW RECOMMENDED</h4>
                                <p className="text-xs text-console-text2 mt-0.5 font-sans">{analysisResult.escalation_reason}</p>
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleCreateCase(true)}
                              disabled={createCaseStatus === 'creating'}
                              className="px-3.5 py-1.5 bg-console-amber text-[#0b1620] hover:brightness-105 font-bold text-xs rounded shadow transition-all shrink-0 font-mono"
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

                        {/* Secondary Collapsible Reasoning Trail */}
                        <ReasoningTrailDisclosure 
                          toolExecutions={analysisResult.tool_executions} 
                          modelConfig={modelConfig} 
                        />
                      </div>
                    </div>
                  )}

                </div>
              )}
            </div>

            {/* Pinned Assistant Composer */}
            <div className="border-t border-console-lineSoft pt-3 mt-4">
              <form onSubmit={handleAnalyze} className="relative flex items-center bg-console-inset border border-console-line rounded-lg p-2 focus-within:border-console-amber transition-all">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleAnalyze(e);
                    }
                  }}
                  placeholder="Ask about your industrial knowledge base..."
                  className="w-full bg-transparent text-xs text-console-text placeholder-console-muted font-sans outline-none resize-none h-12 p-2 leading-relaxed"
                />
                <button
                  type="submit"
                  disabled={isLoading || !isConnected || !prompt.trim()}
                  className="ml-2 px-4 py-2 bg-console-amber hover:brightness-105 disabled:opacity-40 text-[#0b1620] font-mono font-bold text-xs rounded transition-all shrink-0 flex items-center gap-1.5"
                >
                  {isLoading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  <span>SEND</span>
                </button>
              </form>
            </div>

          </div>
        </div>

        {/* Right Rail: Evidence & RAG Retrieval */}
        <div className="space-y-6">
          <InvestigationRagCard 
            onPastePrompt={(text) => setPrompt(prev => prev ? `${prev}\n\nEvidence Context:\n${text}` : `Evidence Context:\n${text}`)} 
          />
        </div>

      </div>
    </div>
  );
}

function ReasoningTrailDisclosure({ toolExecutions, modelConfig }) {
  const [isOpen, setIsOpen] = useState(false);
  const traceSteps = ["ANALYSIS_AGENT", "RETRIEVAL_RAG", "REPORT_GEN"];

  return (
    <div className="border-t border-console-lineSoft pt-3 font-mono text-[10px]">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-console-muted hover:text-console-text transition-colors uppercase tracking-widest font-bold"
      >
        <span>{isOpen ? '▼ HIDE REASONING TRAIL' : '▶ SHOW REASONING TRAIL'}</span>
        <span className="text-console-muted">({traceSteps.join(' › ')})</span>
      </button>
      
      {isOpen && (
        <div className="mt-2.5 p-3 bg-console-inset border border-console-line rounded space-y-2 text-console-text2 font-mono">
          <div className="flex justify-between text-[9px] text-console-muted border-b border-console-lineSoft pb-1">
            <span>GATEWAY: {modelConfig?.provider?.toUpperCase() || 'OLLAMA'}</span>
            <span>MODEL: {modelConfig?.model?.toUpperCase() || 'QWEN2.5:7B'}</span>
          </div>
          {toolExecutions && toolExecutions.length > 0 ? (
            <div className="space-y-1">
              <span className="text-console-muted block">DETERMINISTIC TOOL EXECUTIONS:</span>
              {toolExecutions.map((tool, idx) => (
                <div key={idx} className="text-console-amber bg-console-panelSolid p-1.5 rounded border border-console-lineSoft">
                  <span className="font-bold">{tool.tool_name}</span>: {tool.outputs?.summary || JSON.stringify(tool.outputs)}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-console-muted italic">No deterministic tool executions required for this query.</div>
          )}
        </div>
      )}
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
      <div className="flex items-center gap-2 pb-2 border-b border-console-lineSoft">
        <FileText className="w-3.5 h-3.5 text-console-amber" />
        <h3 className="text-[11px] tracking-[0.14em] text-console-muted uppercase">
          EVIDENCE LEDGER
        </h3>
      </div>
      
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search evidence..."
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
          Retrieving evidence chunks...
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
        <div className="space-y-2.5 max-h-[360px] overflow-y-auto pr-1">
          <div className="text-[9px] font-mono text-console-muted uppercase tracking-widest border-b border-console-lineSoft pb-1">
            RETRIEVED EVIDENCE CHUNKS
          </div>
          {results.map((res, idx) => {
            const scorePercent = Number((res.score * 100).toFixed(0));
            const scoreColor = getScoreBandColor(scorePercent);
            return (
              <div 
                key={res.chunk_id} 
                className={`bg-console-inset border border-console-line p-2.5 rounded text-[10px] font-mono space-y-1.5 ${
                  idx === 0 ? 'border-l-2 border-l-console-amber' : ''
                }`}
              >
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
