import React from 'react';
import { ShieldCheck, ServerCrash } from 'lucide-react';
import StatusBadge from '../common/StatusBadge';

export default function SystemStatus({ modelConfig, isConnected }) {
  const provider = modelConfig.provider || 'mock';
  const providerLabel = provider.toLowerCase() === 'mock' 
    ? 'Mock Provider' 
    : `Ollama (${modelConfig.model || 'Unknown'})`;

  const systems = [
    {
      name: 'Model Gateway',
      status: isConnected ? 'Operational' : 'Offline',
      detail: isConnected ? `${providerLabel} active` : 'Cannot connect to backend server'
    },
    {
      name: 'Knowledge Base',
      status: 'Ready',
      detail: 'Semantic search indices loaded'
    },
    {
      name: 'Document Pipeline',
      status: 'Ready',
      detail: 'OCR parser and directory listener running'
    },
    {
      name: 'Agent Runtime',
      status: 'Ready',
      detail: 'Workflow coordinator initialized'
    }
  ];

  return (
    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg">
      <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase mb-4 flex items-center gap-2">
        {isConnected ? (
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
        ) : (
          <ServerCrash className="w-4 h-4 text-rose-400" />
        )}
        System Health Monitor
      </h2>
      
      <div className="space-y-4">
        {systems.map((sys) => (
          <div key={sys.name} className="flex items-center justify-between border-b border-slate-900/60 pb-3 last:border-0 last:pb-0">
            <div>
              <p className="text-sm font-medium text-slate-200">{sys.name}</p>
              <p className="text-xs text-slate-500 font-mono mt-0.5">{sys.detail}</p>
            </div>
            <StatusBadge status={sys.status} />
          </div>
        ))}
      </div>
    </div>
  );
}
