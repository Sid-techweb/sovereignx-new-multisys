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
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px]">
      <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase pb-3 mb-4 border-b border-console-lineSoft flex items-center gap-2">
        {isConnected ? (
          <ShieldCheck className="w-3.5 h-3.5 text-console-green" />
        ) : (
          <ServerCrash className="w-3.5 h-3.5 text-console-red" />
        )}
        <span>SYSTEM HEALTH MONITOR</span>
      </h2>
      
      <div className="space-y-3">
        {systems.map((sys) => (
          <div key={sys.name} className="flex items-center justify-between pb-2 border-b border-console-lineSoft last:border-0 last:pb-0">
            <div>
              <p className="text-xs font-medium text-console-text">{sys.name}</p>
              <p className="text-[10px] text-console-muted font-mono mt-0.5">{sys.detail}</p>
            </div>
            <StatusBadge status={sys.status} />
          </div>
        ))}
      </div>
    </div>
  );
}
