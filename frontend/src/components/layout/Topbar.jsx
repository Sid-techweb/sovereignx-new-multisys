import React from 'react';
import { Cpu, Wifi, WifiOff } from 'lucide-react';

export default function Topbar({ healthStatus, isConnected, modelConfig }) {
  const provider = modelConfig.provider || 'N/A';
  const model = modelConfig.model || 'N/A';

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/40 backdrop-blur px-6 flex items-center justify-between flex-shrink-0">
      {/* Page Title Context or Breadcrumb could go here */}
      <div className="flex items-center gap-4">
        <span className="text-xs text-slate-500 font-mono tracking-widest uppercase">Console v1.0.0</span>
      </div>

      {/* Status items */}
      <div className="flex items-center gap-6">
        {/* Model Gateway Status */}
        <div className="flex items-center gap-2 bg-slate-950/40 border border-slate-800 px-3 py-1 rounded-lg">
          <Cpu className="w-3.5 h-3.5 text-sky-400" />
          <span className="text-xs font-mono text-slate-400">Gateway:</span>
          <span className="text-xs font-mono text-slate-300 font-bold capitalize">
            {provider} {provider.toLowerCase() === 'mock' ? '• Operational' : `(${model})`}
          </span>
        </div>

        {/* Server Connection Status */}
        <div className="flex items-center gap-2">
          {isConnected ? (
            <div className="flex items-center gap-1.5 text-emerald-400">
              <Wifi className="w-4.5 h-4.5" />
              <span className="text-xs font-mono">SYS ONLINE</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-rose-400">
              <WifiOff className="w-4.5 h-4.5" />
              <span className="text-xs font-mono">SYS OFFLINE</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
