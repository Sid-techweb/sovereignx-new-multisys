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
  FileCode
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Documents({ documents = [], loading = false, onRefresh }) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [processingId, setProcessingId] = useState(null);
  const [processingError, setProcessingError] = useState(null);
  
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
    setProcessingError(null);

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
    setProcessingError(null);
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
      setProcessingError(err.message || 'Processing failed.');
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
    if (ext === 'csv') return <FileSpreadsheet className="w-3.5 h-3.5 text-console-green" />;
    if (['png', 'jpg', 'jpeg'].includes(ext)) return <FileImage className="w-3.5 h-3.5 text-console-amber" />;
    return <FileText className="w-3.5 h-3.5 text-console-amber" />;
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
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] space-y-4">
            <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-2 border-b border-console-lineSoft">
              DOCUMENT INTAKE PORTAL
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className={`border border-dashed border-console-line hover:border-console-amber rounded-lg p-5 flex flex-col items-center justify-center cursor-pointer transition-colors bg-console-inset ${
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
                  <RefreshCw className="w-7 h-7 text-console-amber animate-spin mb-2" />
                ) : (
                  <Upload className="w-7 h-7 text-console-muted mb-2" />
                )}
                <span className="text-xs font-semibold text-console-text font-sans">
                  {uploading ? 'Uploading File...' : 'Select File to Upload'}
                </span>
                <span className="text-[10px] text-console-muted font-mono mt-1">
                  PDF, CSV, PNG, JPG, JPEG up to 25MB
                </span>
              </label>

              {/* Status Display Area */}
              <div className="bg-console-inset border border-console-line rounded-lg p-4 flex flex-col justify-center space-y-2 font-mono">
                <div className="text-[10px] text-console-muted uppercase tracking-[0.14em] border-b border-console-lineSoft pb-1.5 mb-1">
                  UPLOAD STATUS MONITOR
                </div>
                
                {uploading && (
                  <p className="text-xs text-console-amber font-mono flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Transferring payload to storage...
                  </p>
                )}
                
                {uploadSuccess && (
                  <p className="text-xs text-console-green font-mono flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5" /> Document ingested successfully!
                  </p>
                )}

                {uploadError && (
                  <p className="text-xs text-console-red font-sans flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-console-red" /> {uploadError}
                  </p>
                )}

                {!uploading && !uploadSuccess && !uploadError && (
                  <p className="text-xs text-console-muted font-mono italic">
                    Ready. Standardized UUIDs generated to enforce server path integrity.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Document Table */}
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col space-y-3">
            <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 border-b border-console-lineSoft">
              INGESTED REPOSITORY LIBRARY
            </h3>

            {processingError && (
              <div className="p-3 bg-console-red/10 border border-console-red/30 rounded flex items-center justify-between text-xs text-console-red font-mono">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-console-red flex-shrink-0" />
                  <span>Processing Error: {processingError}</span>
                </div>
                <button onClick={() => setProcessingError(null)} className="text-console-muted hover:text-console-text">×</button>
              </div>
            )}
            
            {loading ? (
              <div className="flex flex-col items-center justify-center py-10">
                <div className="w-5 h-5 border-2 border-console-amber/20 border-t-console-amber rounded-full animate-spin"></div>
                <p className="text-[10px] text-console-muted font-mono mt-2">Loading metadata...</p>
              </div>
            ) : documents.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs font-sans">
                  <thead>
                    <tr className="border-b border-console-line text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted bg-console-panelSolid">
                      <th className="py-2.5 px-3">DOCUMENT</th>
                      <th className="py-2.5 px-3">TYPE</th>
                      <th className="py-2.5 px-3">SIZE</th>
                      <th className="py-2.5 px-3">STATUS</th>
                      <th className="py-2.5 px-3">SOURCE</th>
                      <th className="py-2.5 px-3 text-right">ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-console-lineSoft">
                    {documents.map((doc) => (
                      <tr 
                        key={doc.document_id} 
                        className={`hover:bg-white/[.02] transition-colors duration-150 ${
                          selectedDoc && selectedDoc.document_id === doc.document_id ? 'bg-console-amberSoft/20' : ''
                        }`}
                      >
                        <td className="py-2.5 px-3 font-semibold text-console-text max-w-[200px] truncate" title={doc.filename}>
                          {doc.filename}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-xs uppercase flex items-center gap-1.5 mt-0.5">
                          {getFileIcon(doc.file_type)}
                          <span>{doc.file_type}</span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-xs text-console-muted tabular-nums">
                          {Math.round(doc.file_size / 1024)} KB
                        </td>
                        <td className="py-2.5 px-3">
                          <StatusBadge status={doc.status} />
                        </td>
                        <td className="py-2.5 px-3 font-mono text-xs text-console-muted">
                          {doc.source}
                        </td>
                        <td className="py-2.5 px-3 text-right space-x-2">
                          <button
                            onClick={() => handleProcess(doc.document_id)}
                            disabled={processingId === doc.document_id || ['processed', 'not_implemented', 'processed_with_no_text'].includes(doc.status)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-console-amber text-[#0b1620] hover:brightness-105 disabled:opacity-40 disabled:pointer-events-none transition-all font-mono"
                          >
                            {processingId === doc.document_id ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              'PROCESS'
                            )}
                          </button>
                          
                          <button
                            onClick={() => handleViewDetails(doc.document_id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-white/[.05] hover:bg-white/[.1] text-console-text border border-console-line transition-all font-mono focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
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
            ) : (
              <div className="text-center py-10 space-y-2">
                <Database className="w-8 h-8 text-console-muted mx-auto" />
                <p className="text-xs text-console-muted font-mono italic">No documents ingested. Select files above to populate the registry.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Grid: Document Detail / Evidence Viewer */}
        <div className="space-y-6">
          <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col h-full">
            <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 mb-4 border-b border-console-lineSoft">
              EVIDENCE VIEWER & PROVENANCE
            </h3>

            {selectedDoc ? (
              <div className="space-y-4 flex-1 flex flex-col">
                {/* Meta details */}
                <div className="bg-console-inset border border-console-line p-3.5 rounded space-y-2 font-mono text-[11px]">
                  <div className="flex flex-col gap-1 border-b border-console-lineSoft pb-2">
                    <span className="text-console-muted uppercase tracking-[0.14em] text-[9px] font-bold">DOCUMENT TITLE</span>
                    <span className="text-console-text font-sans font-bold text-xs truncate" title={selectedDoc.filename}>
                      {selectedDoc.filename}
                    </span>
                  </div>
                  
                  <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                    <span className="text-console-muted">DOCUMENT ID</span>
                    <span className="text-console-text2 text-right truncate max-w-[150px] tabular-nums" title={selectedDoc.document_id}>
                      {selectedDoc.document_id}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                    <span className="text-console-muted">PROVENANCE SOURCE</span>
                    <span className="text-console-amber font-bold uppercase">{selectedDoc.source}</span>
                  </div>

                  <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                    <span className="text-console-muted">FILE TYPE / SIZE</span>
                    <span className="text-console-text tabular-nums">
                      {selectedDoc.file_type.toUpperCase()} ({Math.round(selectedDoc.file_size / 1024)} KB)
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                    <span className="text-console-muted">SHA-256 CHECKSUM</span>
                    <span className="text-console-text2 text-right truncate max-w-[130px] tabular-nums" title={selectedDoc.checksum_sha256}>
                      {selectedDoc.checksum_sha256 || 'N/A'}
                    </span>
                  </div>

                  <div className="flex justify-between border-b border-console-lineSoft pb-1.5">
                    <span className="text-console-muted">CASE AFFILIATION</span>
                    <span className="text-console-text font-bold tabular-nums">{selectedDoc.case_id || 'Unassigned'}</span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-console-muted">EXTRACTION STATUS</span>
                    <StatusBadge status={selectedDoc.status} />
                  </div>
                </div>

                {/* Content Panel (Evidence Viewer) */}
                <div className="flex-1 flex flex-col min-h-[300px]">
                  <span className="text-[10px] font-mono tracking-[0.14em] text-console-muted uppercase mb-2 block">
                    EXTRACTED TEXT REPRESENTATION
                  </span>
                  
                  <div className="flex-1 bg-console-inset border border-console-line rounded p-3 overflow-y-auto max-h-[450px]">
                    {loadingContent ? (
                      <div className="flex flex-col items-center justify-center h-full py-10">
                        <RefreshCw className="w-4 h-4 text-console-amber animate-spin" />
                        <span className="text-[10px] text-console-muted font-mono mt-2">Loading content block...</span>
                      </div>
                    ) : contentError ? (
                      <div className="text-console-red text-xs font-mono">{contentError}</div>
                    ) : extractedContent ? (
                      extractedContent.content ? (
                        <pre className="text-xs text-console-text font-mono whitespace-pre-wrap leading-relaxed">
                          {extractedContent.content}
                        </pre>
                      ) : (
                        <div className="text-center py-16 font-mono">
                          {extractedContent.extraction_status === 'not_implemented' ? (
                            <>
                              <FileImage className="w-8 h-8 text-console-muted mx-auto mb-2" />
                              <p className="text-xs text-console-muted italic">Image extraction deferred. OCR integrated in later phase.</p>
                            </>
                          ) : extractedContent.extraction_status === 'processed_with_no_text' ? (
                            <>
                              <FileCode className="w-8 h-8 text-console-muted mx-auto mb-2" />
                              <p className="text-xs text-console-muted italic">PDF file does not contain machine-readable text elements.</p>
                            </>
                          ) : (
                            <>
                              <Database className="w-8 h-8 text-console-muted mx-auto mb-2" />
                              <p className="text-xs text-console-muted italic">
                                Document is parsed but text content is empty. 
                                Click "Process" to attempt extraction if pending.
                              </p>
                            </>
                          )}
                        </div>
                      )
                    ) : (
                      <p className="text-xs text-console-muted font-mono italic">No content loaded. Select a document and click View.</p>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-2 font-mono">
                <FileText className="w-8 h-8 text-console-muted" />
                <p className="text-xs text-console-muted italic max-w-[200px]">Select a document and click "View" to inspect evidence and metadata.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
