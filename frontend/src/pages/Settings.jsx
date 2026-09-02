import React from 'react';
import PageHeader from '../components/common/PageHeader';
import { Shield, Cpu, RefreshCw } from 'lucide-react';
import StatusBadge from '../components/common/StatusBadge';

export default function Settings({ modelConfig, healthStatus }) {
  const provider = modelConfig.provider || 'mock';
  const modelName = modelConfig.model || 'mock-document-analyzer';
  const status = modelConfig.status || 'offline';
  // Live from GET /models (settings.OLLAMA_BASE_URL) -- never a hardcoded
  // display literal; a real deployment's endpoint is whatever the backend
  // is actually configured with, not a fixed placeholder in this file.
  const ollamaBaseUrl = modelConfig.ollama_base_url || 'N/A (mock provider or unavailable)';

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Settings" 
        description="Configure system gateway variables and monitor active environment profiles" 
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Gateway Config Details */}
        <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] space-y-4">
          <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase flex items-center gap-2 border-b border-console-lineSoft pb-3">
            <Cpu className="w-4 h-4 text-console-amber" />
            ACTIVE GATEWAY CONFIGURATION
          </h3>
          
          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">MODEL_PROVIDER</span>
              <span className="text-console-text uppercase font-bold">{provider}</span>
            </div>
            
            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">OLLAMA_BASE_URL</span>
              <span className="text-console-text text-right truncate max-w-[250px] tabular-nums" title={ollamaBaseUrl}>
                {ollamaBaseUrl}
              </span>
            </div>

            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">MODEL_NAME</span>
              <span className="text-console-text font-bold">{modelName}</span>
            </div>

            <div className="flex justify-between">
              <span className="text-console-muted">PROVIDER_STATUS</span>
              <StatusBadge status={status} />
            </div>
          </div>
        </div>

        {/* System Deployment Profile */}
        <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] space-y-4">
          <h3 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase flex items-center gap-2 border-b border-console-lineSoft pb-3">
            <Shield className="w-4 h-4 text-console-green" />
            SOVEREIGNX SYSTEM INFO
          </h3>
          
          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">ENV_PROFILE</span>
              <span className="text-console-text font-bold uppercase">DEMO (AIR-GAPPED)</span>
            </div>

            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">BACKEND_HEALTH</span>
              <span className="text-console-green font-bold uppercase">{healthStatus}</span>
            </div>
            
            <div className="flex justify-between border-b border-console-lineSoft pb-2">
              <span className="text-console-muted">API_SERVER_URL</span>
              <span className="text-console-text tabular-nums">http://127.0.0.1:8000</span>
            </div>

            <div className="flex justify-between">
              <span className="text-console-muted">VERSION</span>
              <span className="text-console-amber font-bold tabular-nums">v1.0.0 (Phase 10 Closed)</span>
            </div>
          </div>
        </div>
      </div>
      
      <div className="bg-console-inset border border-console-line p-3 rounded flex gap-2 text-xs text-console-muted font-mono max-w-3xl">
        <RefreshCw className="w-4 h-4 text-console-muted flex-shrink-0 mt-0.5" />
        <span>To switch the model gateway provider to Ollama or modify settings dynamically, edit the `.env` file in the project root directory and restart the backend server.</span>
      </div>
    </div>
  );
}
