import React from 'react';

export default function StatusBadge({ status }) {
  if (!status) return null;
  const normalized = status.toLowerCase().trim();
  
  let colorClasses = 'bg-console-panelSolid border-console-lineSoft text-console-muted';
  let customStyle = {};

  if (normalized === 'critical' || normalized === 'failed' || normalized === 'offline') {
    colorClasses = 'bg-console-red/15 border-console-red/40 text-console-red font-bold';
    customStyle = { backgroundColor: 'rgba(226, 96, 76, 0.15)', borderColor: 'rgba(226, 96, 76, 0.4)', color: '#e2604c' };
  } else if (normalized === 'warning' || normalized === 'high' || normalized === 'degraded' || normalized === 'pending' || normalized === 'pending review' || normalized === 'exceeds' || normalized === 'needs review') {
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
