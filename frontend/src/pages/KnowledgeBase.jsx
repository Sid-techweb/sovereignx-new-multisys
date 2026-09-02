import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import StatusBadge from '../components/common/StatusBadge';
import { 
  Database, 
  Search, 
  Layers, 
  Cpu, 
  Clock, 
  FileText, 
  Play, 
  AlertTriangle,
  CheckCircle,
  FolderOpen,
  Info
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function KnowledgeBase() {
  const [stats, setStats] = useState({
    documents_indexed: 0,
    chunks_indexed: 0,
    embedding_model: 'BAAI/bge-m3',
    vector_store: 'postgresql+pgvector',
    index_status: 'unknown'
  });
  const [loadingStats, setLoadingStats] = useState(true);

  // Documents listing state
  const [docs, setDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [indexingId, setIndexingId] = useState(null);
  const [indexMessage, setIndexMessage] = useState(null);
  const [indexError, setIndexError] = useState(null);

  // Search state
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [searchError, setSearchError] = useState(null);

  // Load stats and documents
  const fetchData = async () => {
    setLoadingStats(true);
    setLoadingDocs(true);
    try {
      // 1. Fetch RAG stats
      const statsRes = await fetch(`${API_BASE}/knowledge-base`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      } else {
        setStats(prev => ({ ...prev, index_status: 'offline' }));
      }

      // 2. Fetch all documents
      const docsRes = await fetch(`${API_BASE}/documents`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocs(docsData);
      }
    } catch (err) {
      console.error("Error fetching knowledge base data:", err);
      setStats(prev => ({ ...prev, index_status: 'offline' }));
    } finally {
      setLoadingStats(false);
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleIndexDocument = async (docId) => {
    setIndexingId(docId);
    setIndexMessage(null);
    setIndexError(null);
    try {
      const response = await fetch(`${API_BASE}/knowledge-base/index/${docId}`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY }
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Indexing failed.');
      }

      setIndexMessage('Document indexed successfully!');
      fetchData(); // Refresh stats and list
    } catch (err) {
      setIndexError(err.message || 'Indexing failed.');
    } finally {
      setIndexingId(null);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setSearching(true);
    setSearchError(null);
    setSearchResults(null);

    try {
      const response = await fetch(`${API_BASE}/knowledge-base/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({ query, top_k: Number(topK) })
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Search request failed.');
      }

      const data = await response.json();
      setSearchResults(data);
    } catch (err) {
      setSearchError(err.message || 'An error occurred during retrieval.');
    } finally {
      setSearching(false);
    }
  };

  const getScoreBandColor = (scorePercent) => {
    if (scorePercent >= 80) return 'text-console-green';
    if (scorePercent >= 60) return 'text-console-amber';
    return 'text-console-muted';
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Knowledge Base" 
        description="Search asset schematics, equipment guidelines, and historic SOP references locally" 
      />

      {/* RAG Status Block Stat Row */}
      <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] grid grid-cols-1 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-console-lineSoft font-mono">
        <div className="flex items-center gap-3 pr-4 pt-2 md:pt-0">
          <div className="p-2 bg-console-panelSolid rounded text-console-amber border border-console-line">
            <FolderOpen className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted uppercase tracking-[0.14em]">INDEXED DOCUMENTS</div>
            <div className="text-xl font-bold text-console-text tabular-nums">
              {loadingStats ? '...' : stats.documents_indexed}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 px-0 md:px-4 pt-2 md:pt-0">
          <div className="p-2 bg-console-greenSoft rounded text-console-green border border-console-green/30">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted uppercase tracking-[0.14em]">INDEXED CHUNKS</div>
            <div className="text-xl font-bold text-console-text tabular-nums">
              {loadingStats ? '...' : stats.chunks_indexed}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 px-0 md:px-4 pt-2 md:pt-0">
          <div className="p-2 bg-console-panelSolid rounded text-console-amber border border-console-line">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted uppercase tracking-[0.14em]">EMBEDDING MODEL</div>
            <div className="text-xs font-bold text-console-text truncate max-w-[150px]" title={stats.embedding_model}>
              {stats.embedding_model.split('/').pop()}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 pl-0 md:pl-4 pt-2 md:pt-0">
          <div className="p-2 bg-console-panelSolid rounded text-console-text2 border border-console-line">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] text-console-muted uppercase tracking-[0.14em]">VECTOR DATABASE</div>
            <div className="text-xs font-bold text-console-text">
              {stats.vector_store}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Repository Registry Indexer */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col space-y-3">
            <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 border-b border-console-lineSoft">
              INDEXING COORDINATOR
            </h3>

            {indexMessage && (
              <div className="p-2.5 bg-console-green/10 border border-console-green/30 rounded flex items-center justify-between text-xs text-console-green font-mono">
                <div className="flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5 text-console-green flex-shrink-0" />
                  <span>{indexMessage}</span>
                </div>
                <button onClick={() => setIndexMessage(null)} className="text-console-muted hover:text-console-text">×</button>
              </div>
            )}

            {indexError && (
              <div className="p-2.5 bg-console-red/10 border border-console-red/30 rounded flex items-center justify-between text-xs text-console-red font-mono">
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-console-red flex-shrink-0" />
                  <span>{indexError}</span>
                </div>
                <button onClick={() => setIndexError(null)} className="text-console-muted hover:text-console-text">×</button>
              </div>
            )}
            
            {loadingDocs ? (
              <div className="flex flex-col items-center justify-center py-10">
                <div className="w-5 h-5 border-2 border-console-amber/20 border-t-console-amber rounded-full animate-spin"></div>
                <p className="text-[10px] text-console-muted font-mono mt-2">Loading documents...</p>
              </div>
            ) : docs.length > 0 ? (
              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                {docs.map((doc) => {
                  const isProcessable = ['processed', 'processed_with_no_text'].includes(doc.status);
                  
                  return (
                    <div 
                      key={doc.document_id} 
                      className="bg-console-inset border border-console-line p-3 rounded flex flex-col gap-2 font-mono text-[11px]"
                    >
                      <div className="flex justify-between items-start">
                        <span className="text-console-text font-sans font-bold truncate max-w-[160px]" title={doc.filename}>
                          {doc.filename}
                        </span>
                        <span className="text-[9px] text-console-muted uppercase">{doc.file_type}</span>
                      </div>
                      
                      <div className="flex justify-between items-center text-[10px]">
                        <span className="text-console-muted uppercase">EXTRACTION STATUS</span>
                        <StatusBadge status={doc.status} />
                      </div>

                      <div className="flex justify-between items-center mt-1 border-t border-console-lineSoft pt-2">
                        <span className="text-console-muted text-[10px] tabular-nums">Case ID: {doc.case_id || 'Unassigned'}</span>
                        
                        <button
                          onClick={() => handleIndexDocument(doc.document_id)}
                          disabled={indexingId === doc.document_id || !isProcessable}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold rounded bg-console-amber text-[#0b1620] hover:brightness-105 disabled:opacity-40 disabled:pointer-events-none transition-all"
                        >
                          {indexingId === doc.document_id ? (
                            <Clock className="w-2.5 h-2.5 animate-spin" />
                          ) : (
                            <Play className="w-2.5 h-2.5" />
                          )}
                          INDEX CHUNKS
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 space-y-2">
                <FileText className="w-8 h-8 text-console-muted mx-auto" />
                <p className="text-xs text-console-muted font-mono italic">No files available to index. Visit the Documents intake page first.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Search Console & Retrieved Evidence list */}
        <div className="lg:col-span-2 space-y-6">
          {/* Search Console Input */}
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px]">
            <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 mb-4 border-b border-console-lineSoft">
              SEMANTIC QUERY CONSOLE
            </h3>

            <form onSubmit={handleSearch} className="space-y-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 w-4 h-4 text-console-muted" />
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search organization knowledge (e.g. Pump P-204 SOP limits)..."
                    className="w-full bg-console-inset border border-console-line focus:border-console-amber rounded-md py-2 pl-9 pr-4 text-xs text-console-text placeholder-console-muted font-sans outline-none transition-colors"
                  />
                </div>
                
                <div className="w-24">
                  <select
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                    className="w-full bg-console-inset border border-console-line focus:border-console-amber rounded-md py-2 px-2 text-xs text-console-text font-mono outline-none"
                  >
                    <option value={3}>Top 3</option>
                    <option value={5}>Top 5</option>
                    <option value={10}>Top 10</option>
                    <option value={20}>Top 20</option>
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={searching || !query.trim()}
                  className="px-4 py-2 bg-console-amber text-[#0b1620] hover:brightness-105 disabled:opacity-40 font-semibold text-xs rounded-md transition-all flex items-center gap-1.5 font-mono focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
                >
                  {searching ? 'SEARCHING...' : 'SEARCH'}
                </button>
              </div>
            </form>
          </div>

          {/* Results Area */}
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] min-h-[300px] flex flex-col">
            <div className="flex justify-between items-center mb-4 pb-3 border-b border-console-lineSoft">
              <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">
                RETRIEVED EVIDENCE RECORDS
              </h3>
              
              {(!searchResults || (searchResults.results && searchResults.results.length > 0)) && (
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-console-muted bg-console-inset px-2 py-1 rounded border border-console-line">
                  <Info className="w-3.5 h-3.5 text-console-muted" />
                  <span>GROUNDED PASSAGES · DOCUMENT-BACKED</span>
                </div>
              )}
            </div>

            {searching ? (
              <div className="flex-1 flex flex-col items-center justify-center py-20">
                <div className="w-6 h-6 border-2 border-console-amber/20 border-t-console-amber rounded-full animate-spin"></div>
                <p className="text-xs text-console-muted font-mono mt-3">Computing query vector on local CPU model...</p>
              </div>
            ) : searchError ? (
              <div className="bg-console-red/10 border border-console-red/30 rounded p-4 flex gap-3 text-console-red text-xs font-mono">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <div>
                  <div className="font-bold">Error In Retrieval</div>
                  <div className="mt-1">{searchError}</div>
                </div>
              </div>
            ) : searchResults ? (
              searchResults.results.length > 0 ? (
                <div className="space-y-3">
                  <div className="text-[10px] font-mono text-console-muted mb-1 uppercase">
                    Found {searchResults.results.length} evidence chunks matching query: "{searchResults.query}"
                  </div>
                  
                  {searchResults.results.map((res, index) => {
                    const scorePercent = Number((res.score * 100).toFixed(1));
                    const scoreColor = getScoreBandColor(scorePercent);
                    return (
                      <div 
                        key={res.chunk_id} 
                        className="bg-console-inset border border-console-line rounded p-3.5 space-y-2 shadow-sm"
                      >
                        {/* Meta header */}
                        <div className="flex justify-between items-center text-[10px] font-mono text-console-muted border-b border-console-lineSoft pb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-console-text2 uppercase">EVIDENCE #{index + 1}</span>
                            <span className="text-console-line">/</span>
                            <span className="text-console-amber font-bold truncate max-w-[180px]" title={res.filename}>
                              {res.filename}
                            </span>
                            <span className="text-console-line">/</span>
                            <span>PAGE: {res.metadata.page_number || 'N/A'}</span>
                            <span className="text-console-line">/</span>
                            <span>CHUNK: {res.metadata.chunk_index}</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span>RELEVANCE:</span>
                            <span className={`font-mono font-bold text-xs tabular-nums ${scoreColor}`}>{scorePercent}%</span>
                          </div>
                        </div>

                        {/* Text chunk content */}
                        <div className="text-xs text-console-text font-mono leading-relaxed bg-console-panelSolid p-3 rounded border border-console-lineSoft whitespace-pre-wrap">
                          {res.content}
                        </div>

                        {/* Provenance Footer */}
                        <div className="flex justify-between items-center text-[9px] font-mono text-console-muted pt-1">
                          <span>SOURCE: {res.source.toUpperCase()}</span>
                          <span className="tabular-nums">DOCUMENT ID: {res.document_id}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2 font-mono">
                  <Database className="w-8 h-8 text-console-muted mx-auto" />
                  <p className="text-xs text-console-muted italic">
                    {searchResults.below_threshold
                      ? "No sufficiently relevant evidence found in the knowledge base for this query."
                      : "No matching evidence found. Ensure documents are processed and indexed."}
                  </p>
                </div>
              )
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2 font-mono">
                <Search className="w-8 h-8 text-console-muted" />
                <p className="text-xs text-console-muted italic max-w-sm">Enter a search query in the semantic query console above to retrieve grounded organizational evidence.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
