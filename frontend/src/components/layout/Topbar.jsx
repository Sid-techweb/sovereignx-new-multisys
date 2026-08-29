import React from 'react';

export default function Topbar({ currentPage = 'overview', healthStatus, isConnected, modelConfig }) {
  const provider = (modelConfig?.provider || 'OLLAMA').toUpperCase();
  const model = (modelConfig?.model || 'QWEN2.5:7B').toUpperCase();

  const formattedPageName = currentPage.replace(/-/g, ' ').toUpperCase();

  return (
    <header className="h-14 border-b border-console-line bg-console-inset px-6 flex items-center justify-between flex-shrink-0 z-10 font-mono">
      {/* Breadcrumb in mono uppercase */}
      <div className="flex items-center gap-2 text-[11px] tracking-[0.14em] text-console-text2">
        <span className="text-console-muted">CONSOLE v1.0.0</span>
        <span className="text-console-muted">/</span>
        <span className="text-console-text font-medium">{formattedPageName}</span>
      </div>

      {/* Status items */}
      <div className="flex items-center gap-4 text-[11px] tracking-[0.14em]">
        {/* Model Gateway Status Pill */}
        <div className="flex items-center gap-2 bg-console-panelSolid border border-console-line px-3 py-1 rounded">
          <span className="text-console-muted">GATEWAY</span>
          <span className="text-console-text font-bold">{provider} · {model}</span>
        </div>

        {/* Server Connection Status */}
        <div className="flex items-center gap-2 bg-console-panelSolid border border-console-line px-3 py-1 rounded">
          {isConnected ? (
            <div className="flex items-center gap-2 text-console-green font-medium">
              <span className="w-2 h-2 rounded-full bg-console-green animate-pulse inline-block" />
              <span>SYS ONLINE</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-console-red font-medium">
              <span className="w-2 h-2 rounded-full bg-console-red inline-block" />
              <span>SYS OFFLINE</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
