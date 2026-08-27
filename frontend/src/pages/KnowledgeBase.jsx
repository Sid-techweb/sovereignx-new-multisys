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
  CheckCircle, 
  AlertTriangle,
  FolderOpen,
  Info,
  ExternalLink
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';

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
      const statsRes = await fetch(`${API_BASE}/knowledge-base`);
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      } else {
        setStats(prev => ({ ...prev, index_status: 'offline' }));
      }

      // 2. Fetch all documents
      const docsRes = await fetch(`${API_BASE}/documents`);
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
    try {
      const response = await fetch(`${API_BASE}/knowledge-base/index/${docId}`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Indexing failed.');
      }

      alert('Document indexed successfully!');
      fetchData(); // Refresh stats and list
    } catch (err) {
      alert(`Indexing error: ${err.message}`);
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
        headers: { 'Content-Type': 'application/json' },
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

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Knowledge Base" 
        description="Search asset schematics, equipment guidelines, and historic SOP references locally" 
      />

      {/* RAG Status Block */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 bg-sky-500/10 rounded-lg text-sky-400">
            <FolderOpen className="w-5 h-5" />
          </div>
          <div className="font-mono">
            <div className="text-[10px] text-slate-500 uppercase tracking-widest">Indexed Documents</div>
            <div className="text-xl font-bold text-slate-200">
              {loadingStats ? '...' : stats.documents_indexed}
            </div>
          </div>
        </div>

        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">
            <Layers className="w-5 h-5" />
          </div>
          <div className="font-mono">
            <div className="text-[10px] text-slate-500 uppercase tracking-widest">Indexed Chunks</div>
            <div className="text-xl font-bold text-slate-200">
              {loadingStats ? '...' : stats.chunks_indexed}
            </div>
          </div>
        </div>

        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 bg-amber-500/10 rounded-lg text-amber-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div className="font-mono">
            <div className="text-[10px] text-slate-500 uppercase tracking-widest">Embedding Model</div>
            <div className="text-sm font-bold text-slate-200 truncate max-w-[150px]" title={stats.embedding_model}>
              {stats.embedding_model.split('/').pop()}
            </div>
          </div>
        </div>

        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 bg-purple-500/10 rounded-lg text-purple-400">
            <Database className="w-5 h-5" />
          </div>
          <div className="font-mono">
            <div className="text-[10px] text-slate-500 uppercase tracking-widest">Vector Database</div>
            <div className="text-xs font-bold text-slate-300">
              {stats.vector_store}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Repository Registry Indexer */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 border-b border-slate-900 pb-3">
              Indexing Coordinator
            </h3>
            
            {loadingDocs ? (
              <div className="flex flex-col items-center justify-center py-10">
                <div className="w-6 h-6 border-2 border-sky-500/20 border-t-sky-500 rounded-full animate-spin"></div>
                <p className="text-[10px] text-slate-500 font-mono mt-2">Loading documents...</p>
              </div>
            ) : docs.length > 0 ? (
              <div className="space-y-3.5 max-h-[500px] overflow-y-auto pr-1">
                {docs.map((doc) => {
                  const isProcessable = ['processed', 'processed_with_no_text'].includes(doc.status);
                  
                  return (
                    <div 
                      key={doc.document_id} 
                      className="bg-slate-950/40 border border-slate-850 p-3 rounded-lg flex flex-col gap-2 font-mono text-[11px]"
                    >
                      <div className="flex justify-between items-start">
                        <span className="text-slate-200 font-sans font-bold truncate max-w-[160px]" title={doc.filename}>
                          {doc.filename}
                        </span>
                        <span className="text-[9px] text-slate-500 uppercase">{doc.file_type}</span>
                      </div>
                      
                      <div className="flex justify-between items-center text-[10px]">
                        <span className="text-slate-500">Extraction Status</span>
                        <StatusBadge status={doc.status} />
                      </div>

                      <div className="flex justify-between items-center mt-1 border-t border-slate-900/80 pt-2">
                        <span className="text-slate-500 text-[10px]">Case ID: {doc.case_id || 'Unassigned'}</span>
                        
                        <button
                          onClick={() => handleIndexDocument(doc.document_id)}
                          disabled={indexingId === doc.document_id || !isProcessable}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold rounded bg-sky-600 hover:bg-sky-500 disabled:bg-slate-850 disabled:text-slate-600 transition-colors text-slate-200"
                        >
                          {indexingId === doc.document_id ? (
                            <Clock className="w-2.5 h-2.5 animate-spin" />
                          ) : (
                            <Play className="w-2.5 h-2.5" />
                          )}
                          Index Chunks
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 space-y-2">
                <FileText className="w-8 h-8 text-slate-700 mx-auto" />
                <p className="text-xs text-slate-500 italic">No files available to index. Visit the Documents intake page first.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Search Console & Retrieved Evidence list */}
        <div className="lg:col-span-2 space-y-6">
          {/* Search Console Input */}
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 border-b border-slate-900 pb-3">
              Semantic Query Console
            </h3>

            <form onSubmit={handleSearch} className="space-y-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 w-4 h-4 text-slate-500" />
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search organization knowledge (e.g. Pump P-204 SOP limits)..."
                    className="w-full bg-slate-950/70 border border-slate-850 focus:border-sky-500 rounded-lg py-2.5 pl-9 pr-4 text-sm text-slate-200 placeholder-slate-500 font-sans outline-none transition-colors"
                  />
                </div>
                
                <div className="w-24">
                  <select
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                    className="w-full bg-slate-950/70 border border-slate-850 focus:border-sky-500 rounded-lg py-2.5 px-3 text-sm text-slate-400 font-mono outline-none"
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
                  className="px-5 py-2.5 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 disabled:text-slate-600 font-semibold text-sm rounded-lg transition-colors flex items-center gap-1.5"
                >
                  {searching ? 'Searching...' : 'Search'}
                </button>
              </div>
            </form>
          </div>

          {/* Results Area */}
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg min-h-[300px] flex flex-col">
            <div className="flex justify-between items-center mb-4 border-b border-slate-900 pb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Retrieved Evidence Records
              </h3>
              
              {(!searchResults || (searchResults.results && searchResults.results.length > 0)) && (
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 bg-slate-950/40 px-2 py-1 rounded border border-slate-850">
                  <Info className="w-3.5 h-3.5 text-slate-400" />
                  <span>GROUNDED PASSAGES • NO LLM HALLUCINATIONS</span>
                </div>
              )}
            </div>

            {searching ? (
              <div className="flex-1 flex flex-col items-center justify-center py-20">
                <div className="w-8 h-8 border-2 border-sky-500/20 border-t-sky-500 rounded-full animate-spin"></div>
                <p className="text-xs text-slate-500 font-mono mt-3">Computing query vector on local CPU model...</p>
              </div>
            ) : searchError ? (
              <div className="bg-rose-950/20 border border-rose-900/60 rounded-xl p-4 flex gap-3 text-rose-400 text-xs font-mono">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <div>
                  <div className="font-bold">Error In Retrieval</div>
                  <div className="mt-1">{searchError}</div>
                </div>
              </div>
            ) : searchResults ? (
              searchResults.results.length > 0 ? (
                <div className="space-y-4">
                  <div className="text-[10px] font-mono text-slate-500 mb-1">
                    Found {searchResults.results.length} relevant evidence chunks matching query: "{searchResults.query}"
                  </div>
                  
                  {searchResults.results.map((res, index) => (
                    <div 
                      key={res.chunk_id} 
                      className="bg-slate-950/50 border border-slate-850 rounded-xl p-4 space-y-3 shadow"
                    >
                      {/* Meta header */}
                      <div className="flex justify-between items-center text-[10px] font-mono text-slate-500 border-b border-slate-900/60 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-400 uppercase">Evidence #{index + 1}</span>
                          <span className="text-slate-600">|</span>
                          <span className="text-sky-400 font-bold truncate max-w-[180px]" title={res.filename}>
                            {res.filename}
                          </span>
                          <span className="text-slate-600">|</span>
                          <span>Page: {res.metadata.page_number || 'N/A'}</span>
                          <span className="text-slate-600">|</span>
                          <span>Chunk: {res.metadata.chunk_index}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span>Relevance:</span>
                          <span className="text-emerald-400 font-bold font-sans text-xs">{(res.score * 100).toFixed(1)}%</span>
                        </div>
                      </div>

                      {/* Text chunk content */}
                      <div className="text-xs text-slate-300 font-mono leading-relaxed bg-slate-950/70 p-3 rounded-lg border border-slate-900 whitespace-pre-wrap">
                        {res.content}
                      </div>

                      {/* Provenance Footer */}
                      <div className="flex justify-between items-center text-[9px] font-mono text-slate-600 pt-1">
                        <span>SOURCE: {res.source.toUpperCase()}</span>
                        <span>DOCUMENT ID: {res.document_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2">
                  <Database className="w-8 h-8 text-slate-700 mx-auto" />
                  <p className="text-xs text-slate-500 italic">
                    {searchResults.below_threshold
                      ? "No sufficiently relevant evidence found in the knowledge base for this query."
                      : "No matching evidence found. Ensure documents are processed and indexed."}
                  </p>
                </div>
              )
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2">
                <Search className="w-10 h-10 text-slate-800" />
                <p className="text-xs text-slate-500 italic max-w-sm">Enter a search query in the semantic query console above to retrieve grounded organizational evidence.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
