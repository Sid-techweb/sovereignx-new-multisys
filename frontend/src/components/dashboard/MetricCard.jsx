import React from 'react';

export default function MetricCard({ title, value, icon: Icon, description, trend, status }) {
  let borderStyle = 'border-slate-800 bg-slate-900/30';
  let titleColor = 'text-slate-400';
  let valueColor = 'text-slate-100';

  if (status === 'critical') {
    borderStyle = 'border-rose-500/25 bg-rose-500/[0.02]';
  } else if (status === 'warning') {
    borderStyle = 'border-amber-500/25 bg-amber-500/[0.02]';
  } else if (status === 'active') {
    borderStyle = 'border-sky-500/25 bg-sky-500/[0.02]';
  }

  return (
    <div className={`border rounded-xl p-5 shadow-lg flex items-start justify-between ${borderStyle}`}>
      <div className="space-y-2">
        <span className={`text-xs font-semibold uppercase tracking-wider ${titleColor}`}>{title}</span>
        <div className="flex items-baseline gap-2">
          <span className={`text-2xl font-bold font-mono tracking-tight ${valueColor}`}>{value}</span>
          {trend && (
            <span className="text-xs font-mono text-emerald-400">{trend}</span>
          )}
        </div>
        {description && (
          <p className="text-xs text-slate-500 font-sans">{description}</p>
        )}
      </div>
      
      {Icon && (
        <div className={`p-2.5 rounded-lg border ${
          status === 'critical' ? 'bg-rose-500/10 border-rose-500/20 text-rose-400' :
          status === 'warning' ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' :
          status === 'active' ? 'bg-sky-500/10 border-sky-500/20 text-sky-400' :
          'bg-slate-800 border-slate-700 text-slate-400'
        }`}>
          <Icon className="w-5 h-5" />
        </div>
      )}
    </div>
  );
}
