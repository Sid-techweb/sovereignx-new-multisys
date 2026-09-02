import React, { useState, useEffect } from 'react';
import { Bot, Terminal, RefreshCw } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function ActivityFeed() {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchLogs = async () => {
    try {
      const response = await fetch(`${API_BASE}/tools/logs?limit=10`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (response.ok) {
        const data = await response.json();
        setActivities(Array.isArray(data) ? data : []);
      } else {
        setActivities([]);
      }
    } catch (err) {
      setActivities([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 10000);
    return () => clearInterval(interval);
  }, []);

  const formatTimeAgo = (isoString) => {
    if (!isoString) return 'Just now';
    const date = new Date(isoString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
      <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-console-lineSoft">
        <div className="flex items-center gap-2">
          <Bot className="w-3.5 h-3.5 text-console-amber" />
          <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">TOOL EXECUTION AUDIT LOG</h2>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-8">
          <RefreshCw className="w-4 h-4 text-console-amber animate-spin" />
          <span className="text-[10px] text-console-muted font-mono mt-2">Loading audit feed...</span>
        </div>
      ) : activities.length > 0 ? (
        <div className="relative border-l border-console-lineSoft ml-3 pl-4 space-y-4 max-h-[350px] overflow-y-auto">
          {activities.map((act) => {
            const isSuccess = act.status === 'success';
            return (
              <div key={act.id} className="relative group font-mono">
                {/* Dot marker */}
                <span className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border bg-console-bg transition-colors duration-150 ${
                  isSuccess ? 'border-console-green bg-console-green' : 'border-console-red bg-console-red'
                }`} />
                
                <div className="flex flex-col">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs font-bold text-console-text">{act.tool_name}</span>
                    <span className="text-[10px] text-console-muted tabular-nums">{formatTimeAgo(act.timestamp)}</span>
                  </div>
                  <p className={`text-[10px] font-semibold uppercase tracking-wide mt-0.5 ${
                    isSuccess ? 'text-console-green' : 'text-console-red'
                  }`}>
                    {act.status} ({act.duration_ms}ms)
                  </p>
                  <p className="text-[11px] text-console-text2 font-sans mt-0.5 leading-relaxed truncate" title={JSON.stringify(act.inputs)}>
                    Inputs: {JSON.stringify(act.inputs)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8 space-y-1">
          <Terminal className="w-6 h-6 text-console-muted mx-auto" />
          <p className="text-xs text-console-muted font-mono italic">No recent tool execution activity logged yet.</p>
        </div>
      )}
      
      <div className="mt-4 bg-console-inset border border-console-line p-2.5 rounded flex gap-2 text-[10px] text-console-muted font-mono">
        <Terminal className="w-3.5 h-3.5 text-console-muted flex-shrink-0 mt-0.5" />
        <span>NOTE: All tool executions on this feed trace live workflow coordinator execution timelines.</span>
      </div>
    </div>
  );
}
