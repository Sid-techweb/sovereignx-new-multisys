import React from 'react';
import PageHeader from '../components/common/PageHeader';
import { Settings as SettingsIcon, Shield, Cpu, RefreshCw } from 'lucide-react';
import StatusBadge from '../components/common/StatusBadge';

export default function Settings({ modelConfig, healthStatus }) {
  const provider = modelConfig.provider || 'mock';
  const modelName = modelConfig.model || 'mock-document-analyzer';
  const status = modelConfig.status || 'offline';

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Settings" 
        description="Configure system gateway variables and monitor active environment profiles" 
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Gateway Config Details */}
        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
          <h3 className="text-sm font-semibold tracking-wider text-slate-400 uppercase flex items-center gap-2 border-b border-slate-900 pb-3">
            <Cpu className="w-4 h-4 text-sky-400" />
            Active Gateway Configuration
          </h3>
          
          <div className="space-y-4 font-mono text-sm">
            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">MODEL_PROVIDER</span>
              <span className="text-slate-300 capitalize font-bold">{provider}</span>
            </div>
            
            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">OLLAMA_BASE_URL</span>
              <span className="text-slate-300 text-right truncate max-w-[250px]" title="http://localhost:11434">
                http://localhost:11434
              </span>
            </div>

            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">MODEL_NAME</span>
              <span className="text-slate-300">{modelName}</span>
            </div>

            <div className="flex justify-between">
              <span className="text-slate-500">PROVIDER_STATUS</span>
              <StatusBadge status={status} />
            </div>
          </div>
        </div>

        {/* System Deployment Profile */}
        <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
          <h3 className="text-sm font-semibold tracking-wider text-slate-400 uppercase flex items-center gap-2 border-b border-slate-900 pb-3">
            <Shield className="w-4 h-4 text-sky-400" />
            SovereignX System Info
          </h3>
          
          <div className="space-y-4 font-mono text-sm">
            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">ENV_PROFILE</span>
              <span className="text-slate-300 font-bold">development</span>
            </div>

            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">BACKEND_HEATH</span>
              <span className="text-slate-300 font-bold uppercase">{healthStatus}</span>
            </div>
            
            <div className="flex justify-between border-b border-slate-900 pb-2">
              <span className="text-slate-500">API_SERVER_URL</span>
              <span className="text-slate-300">http://localhost:8000</span>
            </div>

            <div className="flex justify-between">
              <span className="text-slate-500">VERSION</span>
              <span className="text-slate-300 font-bold">0.1.0-alpha (Phase 2A/2B)</span>
            </div>
          </div>
        </div>
      </div>
      
      <div className="bg-slate-950/40 border border-slate-855/60 p-4 rounded-xl flex gap-2 text-xs text-slate-500 font-mono max-w-3xl">
        <RefreshCw className="w-4 h-4 text-slate-600 flex-shrink-0" />
        <span>To switch the model gateway provider to Ollama or modify settings dynamically, edit the `.env` file in the project root directory and restart the backend server.</span>
      </div>
    </div>
  );
}
