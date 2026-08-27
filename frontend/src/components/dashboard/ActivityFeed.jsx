import React from 'react';
import { Bot, Terminal, ShieldAlert } from 'lucide-react';

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
    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
      <div className="flex items-center gap-2 mb-5 border-b border-slate-900 pb-3">
        <Bot className="w-4 h-4 text-sky-400" />
        <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase">Agent Activity Feed</h2>
      </div>

      <div className="relative border-l border-slate-850 ml-3.5 pl-5 space-y-6">
        {activities.map((act, index) => (
          <div key={index} className="relative group">
            {/* Dot marker */}
            <span className={`absolute -left-[27px] top-1.5 h-3.5 w-3.5 rounded-full border-2 bg-slate-950 transition-colors duration-150 ${
              act.type === 'agent' ? 'border-sky-400' :
              act.type === 'gateway' ? 'border-emerald-400' : 'border-slate-700'
            }`} />
            
            <div className="flex flex-col">
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-bold text-slate-200">{act.agent}</span>
                <span className="text-[10px] text-slate-500 font-mono">{act.time}</span>
              </div>
              <p className="text-xs text-sky-400 font-mono mt-0.5 font-bold uppercase">{act.action}</p>
              <p className="text-xs text-slate-500 font-sans mt-1 leading-relaxed">
                {act.detail}
              </p>
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-4 bg-slate-950/40 border border-slate-855/60 p-3 rounded-lg flex gap-2 text-[10px] text-slate-500 font-mono">
        <Terminal className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
        <span>NOTE: All agent events on this dashboard are simulated demonstration timelines. Actual backend actions will run in a later phase.</span>
      </div>
    </div>
  );
}
