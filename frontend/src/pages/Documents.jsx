import React, { useState } from 'react';
import PageHeader from '../components/common/PageHeader';
import StatusBadge from '../components/common/StatusBadge';
import { 
  FileText, 
  Upload, 
  RefreshCw, 
  Eye, 
  CheckCircle, 
  AlertTriangle, 
  FileSpreadsheet, 
  FileImage,
  Database,
  Calendar,
  Layers,
  FileCode
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Documents({ documents = [], loading = false, onRefresh }) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [processingId, setProcessingId] = useState(null);
  
  // Detail Viewer State
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [extractedContent, setExtractedContent] = useState(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState(null);

  const allowedExtensions = ['.pdf', '.csv', '.png', '.jpg', '.jpeg'];
  const maxUploadSizeBytes = 25 * 1024 * 1024; // 25MB

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);

    // Client-side validations
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.includes(ext)) {
      setUploadError(`Unsupported file extension. Allowed: ${allowedExtensions.join(', ')}`);
      setUploading(false);
      return;
    }

    if (file.size > maxUploadSizeBytes) {
      setUploadError('File exceeds the maximum upload limit of 25MB.');
      setUploading(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/documents/upload`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY },
        body: formData
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Upload failed. Invalid format or server issue.');
      }

      setUploadSuccess(true);
      if (onRefresh) onRefresh();
    } catch (err) {
      setUploadError(err.message || 'An error occurred during file upload.');
    } finally {
      setUploading(false);
    }
  };

  const handleProcess = async (docId) => {
    setProcessingId(docId);
    try {
      const response = await fetch(`${API_BASE}/documents/${docId}/process`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY }
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Processing failed.');
      }

      if (onRefresh) onRefresh();
      
      // If we are currently viewing the processed document, reload its details
      if (selectedDoc && selectedDoc.document_id === docId) {
        handleViewDetails(docId);
      }
    } catch (err) {
      alert(`Processing error: ${err.message}`);
    } finally {
      setProcessingId(null);
    }
  };

  const handleViewDetails = async (docId) => {
    setLoadingContent(true);
    setContentError(null);
    setExtractedContent(null);
    
    // Find metadata first
    const meta = documents.find(d => d.document_id === docId);
    setSelectedDoc(meta);

    try {
      const response = await fetch(`${API_BASE}/documents/${docId}/content`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (!response.ok) {
        throw new Error('Failed to load extracted document details.');
      }
      const data = await response.json();
      setExtractedContent(data);
    } catch (err) {
      setContentError(err.message || 'Error loading content.');
    } finally {
      setLoadingContent(false);
    }
  };

  const getFileIcon = (fileType) => {
    const ext = fileType.toLowerCase();
    if (ext === 'csv') return <FileSpreadsheet className="w-4 h-4 text-emerald-400" />;
    if (['png', 'jpg', 'jpeg'].includes(ext)) return <FileImage className="w-4 h-4 text-amber-400" />;
    return <FileText className="w-4 h-4 text-sky-400" />;
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Documents" 
        description="Standard Operating Procedures (SOPs) and Inspection Logs Library"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Grid: Upload & Document Table */}
        <div className="lg:col-span-2 space-y-6">
          
          {/* Upload Interface */}
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Document Intake Portal
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className={`border-2 border-dashed border-slate-800 hover:border-sky-500/50 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer transition-colors ${
                uploading ? 'pointer-events-none opacity-50' : ''
              }`}>
                <input 
                  type="file" 
                  className="hidden" 
                  onChange={handleFileUpload} 
                  accept=".pdf,.csv,.png,.jpg,.jpeg"
                  disabled={uploading}
                />
                {uploading ? (
                  <RefreshCw className="w-8 h-8 text-sky-400 animate-spin mb-2" />
                ) : (
                  <Upload className="w-8 h-8 text-slate-500 mb-2" />
                )}
                <span className="text-xs font-semibold text-slate-300">
                  {uploading ? 'Uploading File...' : 'Select File to Upload'}
                </span>
                <span className="text-[10px] text-slate-500 font-mono mt-1">
                  PDF, CSV, PNG, JPG, JPEG up to 25MB
                </span>
              </label>

              {/* Status Display Area */}
              <div className="bg-slate-950/40 border border-slate-850/60 rounded-xl p-4 flex flex-col justify-center space-y-2">
                <div className="text-xs font-mono text-slate-500 uppercase tracking-widest border-b border-slate-900 pb-1.5 mb-1.5">
                  Upload Status Monitor
                </div>
                
                {uploading && (
                  <p className="text-xs text-sky-400 font-mono flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Transferring payload to storage...
                  </p>
                )}
                
                {uploadSuccess && (
                  <p className="text-xs text-emerald-400 font-mono flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5" /> Document ingested successfully!
                  </p>
                )}

                {uploadError && (
                  <p className="text-xs text-rose-400 font-sans flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> {uploadError}
                  </p>
                )}

                {!uploading && !uploadSuccess && !uploadError && (
                  <p className="text-xs text-slate-500 font-sans italic">
                    Ready. Standardized UUIDs will be generated to enforce server path integrity.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Document Table */}
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 border-b border-slate-900 pb-3">
              Ingested Repository Library
            </h3>
            
            {loading ? (
              <div className="flex flex-col items-center justify-center py-10">
                <div className="w-6 h-6 border-2 border-sky-500/20 border-t-sky-500 rounded-full animate-spin"></div>
                <p className="text-[10px] text-slate-500 font-mono mt-2">Loading metadata...</p>
              </div>
            ) : documents.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs font-mono uppercase text-slate-500">
                      <th className="py-2.5 px-3">Document</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Size</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Source</th>
                      <th className="py-2.5 px-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-900 text-sm">
                    {documents.map((doc) => (
                      <tr 
                        key={doc.document_id} 
                        className={`hover:bg-slate-900/10 transition-colors duration-150 ${
                          selectedDoc && selectedDoc.document_id === doc.document_id ? 'bg-sky-500/[0.02]' : ''
                        }`}
                      >
                        <td className="py-3 px-3 font-semibold text-slate-200 max-w-[200px] truncate" title={doc.filename}>
                          {doc.filename}
                        </td>
                        <td className="py-3 px-3 font-mono text-xs uppercase flex items-center gap-1.5 mt-0.5">
                          {getFileIcon(doc.file_type)}
                          <span>{doc.file_type}</span>
                        </td>
                        <td className="py-3 px-3 font-mono text-xs text-slate-400">
                          {Math.round(doc.file_size / 1024)} KB
                        </td>
                        <td className="py-3 px-3">
                          <StatusBadge status={doc.status} />
                        </td>
                        <td className="py-3 px-3 font-mono text-xs text-slate-500">
                          {doc.source}
                        </td>
                        <td className="py-3 px-3 space-x-2">
                          <button
                            onClick={() => handleProcess(doc.document_id)}
                            disabled={processingId === doc.document_id || ['processed', 'not_implemented', 'processed_with_no_text'].includes(doc.status)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 disabled:text-slate-600 transition-colors"
                          >
                            {processingId === doc.document_id ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              'Process'
                            )}
                          </button>
                          
                          <button
                            onClick={() => handleViewDetails(doc.document_id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-10 space-y-2">
                <Database className="w-8 h-8 text-slate-700 mx-auto" />
                <p className="text-xs text-slate-500 italic">No documents ingested. Select files above to populate the registry.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Grid: Document Detail / Evidence Viewer */}
        <div className="space-y-6">
          <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col h-full">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 border-b border-slate-900 pb-3">
              Evidence Viewer & Provenance
            </h3>

            {selectedDoc ? (
              <div className="space-y-5 flex-1 flex flex-col">
                {/* Meta details */}
                <div className="bg-slate-950/40 border border-slate-850 p-4 rounded-xl space-y-3 font-mono text-[11px]">
                  <div className="flex flex-col gap-1 border-b border-slate-900 pb-2">
                    <span className="text-slate-500 uppercase tracking-widest text-[9px] font-bold">Document Title</span>
                    <span className="text-slate-200 font-sans font-bold text-xs truncate" title={selectedDoc.filename}>
                      {selectedDoc.filename}
                    </span>
                  </div>
                  
                  <div className="flex justify-between border-b border-slate-900 pb-2">
                    <span className="text-slate-500">DOCUMENT ID</span>
                    <span className="text-slate-400 text-right truncate max-w-[150px]" title={selectedDoc.document_id}>
                      {selectedDoc.document_id}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-slate-900 pb-2">
                    <span className="text-slate-500">PROVENANCE SOURCE</span>
                    <span className="text-sky-400 font-bold uppercase">{selectedDoc.source}</span>
                  </div>

                  <div className="flex justify-between border-b border-slate-900 pb-2">
                    <span className="text-slate-500">FILE TYPE / SIZE</span>
                    <span className="text-slate-300">
                      {selectedDoc.file_type.toUpperCase()} ({Math.round(selectedDoc.file_size / 1024)} KB)
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-slate-900 pb-2">
                    <span className="text-slate-500">SHA-256 CHECKSUM</span>
                    <span className="text-slate-400 text-right truncate max-w-[130px]" title={selectedDoc.checksum_sha256}>
                      {selectedDoc.checksum_sha256 || 'N/A'}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-slate-900 pb-2">
                    <span className="text-slate-500">CASE AFFILIATION</span>
                    <span className="text-slate-300 font-bold">{selectedDoc.case_id || 'Unassigned'}</span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-slate-500">EXTRACTION STATUS</span>
                    <StatusBadge status={selectedDoc.status} />
                  </div>
                </div>

                {/* Content Panel (Evidence Viewer) */}
                <div className="flex-1 flex flex-col min-h-[300px]">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono mb-2 block">
                    Extracted Text Representation
                  </span>
                  
                  <div className="flex-1 bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 overflow-y-auto max-h-[450px]">
                    {loadingContent ? (
                      <div className="flex flex-col items-center justify-center h-full py-10">
                        <RefreshCw className="w-5 h-5 text-sky-400 animate-spin" />
                        <span className="text-[10px] text-slate-500 font-mono mt-2">Loading content block...</span>
                      </div>
                    ) : contentError ? (
                      <div className="text-rose-400 text-xs font-mono">{contentError}</div>
                    ) : extractedContent ? (
                      extractedContent.content ? (
                        <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
                          {extractedContent.content}
                        </pre>
                      ) : (
                        <div className="text-center py-20">
                          {extractedContent.extraction_status === 'not_implemented' ? (
                            <>
                              <FileImage className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                              <p className="text-xs text-slate-500 font-sans italic">Image extraction is deferred. OCR will be integrated in a later phase.</p>
                            </>
                          ) : extractedContent.extraction_status === 'processed_with_no_text' ? (
                            <>
                              <FileCode className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                              <p className="text-xs text-slate-500 font-sans italic">PDF file does not contain machine-readable text elements.</p>
                            </>
                          ) : (
                            <>
                              <Database className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                              <p className="text-xs text-slate-500 font-sans italic">
                                Document is parsed but text content is empty. 
                                Click "Process" to attempt extraction if status is pending.
                              </p>
                            </>
                          )}
                        </div>
                      )
                    ) : (
                      <p className="text-xs text-slate-600 font-mono italic">No content loaded. Process document or select view.</p>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2">
                <FileText className="w-10 h-10 text-slate-800" />
                <p className="text-xs text-slate-500 italic max-w-[200px]">Select a document and click "View" to inspect evidence and metadata.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
