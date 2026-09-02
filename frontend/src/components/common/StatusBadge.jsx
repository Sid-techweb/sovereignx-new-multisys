import React from 'react';
import { RefreshCw, CheckCircle, AlertTriangle, Clock } from 'lucide-react';

export default function StatusBadge({ status }) {
  if (!status) return null;
  const normalized = status.toLowerCase().trim();
  
  if (normalized === 'indexing') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase bg-amber-500/15 border-amber-500/40 text-amber-500 font-bold">
        <RefreshCw className="w-3 h-3 animate-spin text-amber-500" />
        <span>INDEXING...</span>
      </span>
    );
  }

  if (normalized === 'indexed' || normalized === 'processed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase bg-emerald-500/15 border-emerald-500/40 text-emerald-500 font-bold">
        <CheckCircle className="w-3 h-3 text-emerald-500" />
        <span>INDEXED</span>
      </span>
    );
  }

  if (normalized === 'failed_partial') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase bg-red-500/20 border-red-500/50 text-red-400 font-bold">
        <AlertTriangle className="w-3 h-3 text-red-400" />
        <span>FAILED (PARTIAL)</span>
      </span>
    );
  }

  if (normalized === 'failed' || normalized === 'critical' || normalized === 'offline') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase bg-red-500/15 border-red-500/40 text-red-500 font-bold">
        <AlertTriangle className="w-3 h-3 text-red-500" />
        <span>FAILED</span>
      </span>
    );
  }

  if (normalized === 'uploaded' || normalized === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase bg-blue-500/15 border-blue-500/40 text-blue-400 font-bold">
        <Clock className="w-3 h-3 text-blue-400 animate-pulse" />
        <span>UPLOADED</span>
      </span>
    );
  }

  let colorClasses = 'bg-console-panelSolid border-console-lineSoft text-console-muted';
  let customStyle = {};

  if (normalized === 'warning' || normalized === 'high' || normalized === 'degraded' || normalized === 'pending review' || normalized === 'exceeds' || normalized === 'needs review') {
    colorClasses = 'bg-console-amberSoft border-console-amber/40 text-console-amber font-bold';
    customStyle = { backgroundColor: 'rgba(239, 143, 43, 0.15)', borderColor: 'rgba(239, 143, 43, 0.4)', color: '#ef8f2b' };
  } else if (normalized === 'active' || normalized === 'operational' || normalized === 'ready' || normalized === 'connected' || normalized === 'within limit' || normalized === 'ok' || normalized === 'running' || normalized === 'available') {
    colorClasses = 'bg-console-greenSoft border-console-green/40 text-console-green font-bold';
    customStyle = { backgroundColor: 'rgba(78, 199, 127, 0.15)', borderColor: 'rgba(78, 199, 127, 0.4)', color: '#4ec77f' };
  } else if (normalized === 'resolved' || normalized === 'completed') {
    colorClasses = 'bg-console-panelSolid border-console-lineSoft text-console-muted font-medium';
    customStyle = { backgroundColor: '#0d1a26', borderColor: 'rgba(146, 178, 208, 0.12)', color: '#6b8095' };
  }

  return (
    <span 
      style={customStyle}
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-mono tracking-wider uppercase ${colorClasses}`}
    >
      {status}
    </span>
  );
}
