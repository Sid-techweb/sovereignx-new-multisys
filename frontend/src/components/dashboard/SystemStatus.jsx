import React, { useState, useEffect } from 'react';
import { ShieldCheck, ServerCrash } from 'lucide-react';
import StatusBadge from '../common/StatusBadge';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function SystemStatus({ modelConfig, isConnected }) {
  const [kbStatus, setKbStatus] = useState('Checking...');
  const [kbDetail, setKbDetail] = useState('Querying vector index...');

  useEffect(() => {
    const fetchKbStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/knowledge-base`, {
          headers: { 'X-API-Key': API_KEY }
        });
        if (res.ok) {
          const data = await res.json();
          setKbStatus('Operational');
          setKbDetail(`${data.documents_indexed || 0} docs / ${data.chunks_indexed || 0} chunks indexed`);
        } else {
          setKbStatus('Offline');
          setKbDetail('Index unavailable');
        }
      } catch (err) {
        setKbStatus('Offline');
        setKbDetail('Failed to reach RAG server');
      }
    };
    fetchKbStatus();
  }, [isConnected]);

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
      status: isConnected ? kbStatus : 'Offline',
      detail: isConnected ? kbDetail : 'Backend server disconnected'
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
