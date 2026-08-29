import React from 'react';
import { Bot, Terminal } from 'lucide-react';

export default function ActivityFeed() {
  const activities = [
    {
      time: '10m ago',
      agent: 'Profile Agent',
      action: 'Case metadata prepared',
      detail: 'Extracted key tags for Compressor C-118 and populated index context.',
      type: 'agent'
    },
    {
      time: '12m ago',
      agent: 'Evidence Agent',
      action: '3 evidence items linked',
      detail: 'Mapped telemetry threshold alarm logs to SOP Section 4.2 maintenance items.',
      type: 'agent'
    },
    {
      time: '14m ago',
      agent: 'Analysis Gateway',
      action: 'Mock analysis completed',
      detail: 'Generated deterministic finding validation results for pump housing sensor tests.',
      type: 'gateway'
    },
    {
      time: '1h ago',
      agent: 'Report Agent',
      action: 'Waiting for investigation completion',
      detail: 'Waiting for operator verification on CAS-694 before auto-generating PDF summary.',
      type: 'idle'
    }
  ];

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
      <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-console-lineSoft">
        <div className="flex items-center gap-2">
          <Bot className="w-3.5 h-3.5 text-console-amber" />
          <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">AGENT ACTIVITY FEED</h2>
        </div>
      </div>

      <div className="relative border-l border-console-lineSoft ml-3 pl-4 space-y-4">
        {activities.map((act, index) => (
          <div key={index} className="relative group">
            {/* Dot marker */}
            <span className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border bg-console-bg transition-colors duration-150 ${
              act.type === 'agent' ? 'border-console-amber bg-console-amber' :
              act.type === 'gateway' ? 'border-console-green bg-console-green' : 'border-console-muted'
            }`} />
            
            <div className="flex flex-col">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-mono font-bold text-console-text">{act.agent}</span>
                <span className="text-[10px] text-console-muted font-mono tabular-nums">{act.time}</span>
              </div>
              <p className="text-[11px] text-console-amber font-mono font-semibold uppercase tracking-wide mt-0.5">{act.action}</p>
              <p className="text-xs text-console-text2 font-sans mt-0.5 leading-relaxed">
                {act.detail}
              </p>
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-4 bg-console-inset border border-console-line p-2.5 rounded flex gap-2 text-[10px] text-console-muted font-mono">
        <Terminal className="w-3.5 h-3.5 text-console-muted flex-shrink-0 mt-0.5" />
        <span>NOTE: All agent events on this feed trace live workflow coordinator execution timelines.</span>
      </div>
    </div>
  );
}
