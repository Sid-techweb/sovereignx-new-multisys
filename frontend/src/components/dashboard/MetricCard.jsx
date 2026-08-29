import React from 'react';

export default function MetricCard({ title, value, icon: Icon, description, trend, status }) {
  let valueColor = 'text-console-text';
  let badgeStyle = 'bg-console-panelSolid border-console-line text-console-text2';

  if (status === 'critical') {
    valueColor = 'text-console-red';
    badgeStyle = 'bg-console-red/10 border-console-red/30 text-console-red';
  } else if (status === 'warning') {
    valueColor = 'text-console-amber';
    badgeStyle = 'bg-console-amberSoft border-console-amber/30 text-console-amber';
  } else if (status === 'active') {
    valueColor = 'text-console-text';
    badgeStyle = 'bg-console-greenSoft border-console-green/30 text-console-green';
  }

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex items-start justify-between">
      <div className="space-y-1.5">
        <span className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase block">{title}</span>
        <div className="flex items-baseline gap-2">
          <span className={`text-2xl font-mono font-bold tracking-tight tabular-nums ${valueColor}`}>{value}</span>
          {trend && (
            <span className="text-xs font-mono text-console-green tabular-nums">{trend}</span>
          )}
        </div>
        {description && (
          <p className="text-xs text-console-text2">{description}</p>
        )}
      </div>
      
      {Icon && (
        <div className={`p-2 rounded border ${badgeStyle}`}>
          <Icon className="w-4 h-4" />
        </div>
      )}
    </div>
  );
}
