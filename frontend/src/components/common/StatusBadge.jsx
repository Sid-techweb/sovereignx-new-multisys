import React from 'react';

export default function StatusBadge({ status }) {
  const normalized = status.toLowerCase();
  
  let styles = 'bg-slate-900 border-slate-800 text-slate-400';
  
  if (normalized === 'critical' || normalized === 'failed' || normalized === 'offline') {
    styles = 'bg-rose-500/10 border-rose-500/20 text-rose-400';
  } else if (normalized === 'warning' || normalized === 'degraded' || normalized === 'pending') {
    styles = 'bg-amber-500/10 border-amber-500/20 text-amber-400';
  } else if (normalized === 'resolved' || normalized === 'completed' || normalized === 'active' || normalized === 'operational' || normalized === 'ok') {
    styles = 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';
  } else if (normalized === 'ready' || normalized === 'available' || normalized === 'running') {
    styles = 'bg-sky-500/10 border-sky-500/20 text-sky-400';
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-mono font-medium ${styles}`}>
      {status}
    </span>
  );
}
