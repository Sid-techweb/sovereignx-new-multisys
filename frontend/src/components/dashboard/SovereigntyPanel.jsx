import React, { useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, Globe, Server, Terminal } from 'lucide-react';

export default function SovereigntyPanel() {
  const [summary, setSummary] = useState({
    status: 'NO EXTERNAL APPLICATION CONNECTIONS DETECTED',
    total_connections: 0,
    alerts: 0,
    log: []
  });
  const [wsStatus, setWsStatus] = useState('connecting');

  useEffect(() => {
    // Dynamically resolve websocket protocol and host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Default to localhost:8000 if running on Vite dev server (port 5173)
    const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
    const wsUrl = `${protocol}//${host}/api/sovereignty/ws`;

    let socket;
    let reconnectTimeout;

    function connect() {
      setWsStatus('connecting');
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        setWsStatus('connected');
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.summary) {
            setSummary(data.summary);
          }
        } catch (err) {
          console.error("Error parsing sovereignty update:", err);
        }
      };

      socket.onclose = () => {
        setWsStatus('disconnected');
        // Attempt reconnection after 3 seconds
        reconnectTimeout = setTimeout(connect, 3000);
      };

      socket.onerror = () => {
        setWsStatus('error');
      };
    }

    connect();

    return () => {
      if (socket) socket.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const hasAlerts = summary.alerts > 0;

  return (
    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-4 border-b border-slate-900 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase">Live Network Sovereignty Monitor</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${
            wsStatus === 'connected' ? 'bg-emerald-500 animate-pulse' :
            wsStatus === 'connecting' ? 'bg-amber-500 animate-pulse' : 'bg-rose-500'
          }`} />
          <span className="text-[10px] text-slate-500 uppercase font-mono">{wsStatus}</span>
        </div>
      </div>

      {/* Main Status Area */}
      <div className={`p-4 rounded-xl border flex flex-col items-center justify-center text-center gap-3 transition-all duration-300 ${
        hasAlerts 
          ? 'bg-rose-950/20 border-rose-900/50 text-rose-200' 
          : 'bg-emerald-950/10 border-emerald-900/30 text-emerald-300'
      }`}>
        {hasAlerts ? (
          <ShieldAlert className="w-10 h-10 text-rose-500 animate-bounce" />
        ) : (
          <ShieldCheck className="w-10 h-10 text-emerald-400" />
        )}
        <div className="space-y-1">
          <p className="text-xs uppercase font-mono tracking-wider font-bold">Monitor Status</p>
          <h3 className="text-sm font-bold tracking-tight">{summary.status}</h3>
        </div>
      </div>

      {/* Connection Counters */}
      <div className="grid grid-cols-2 gap-4 my-4">
        <div className="bg-slate-950/40 border border-slate-850 p-3 rounded-lg flex flex-col items-center justify-center">
          <span className="text-xs text-slate-500 font-medium">Total Connections</span>
          <span className="text-xl font-bold text-slate-200 font-mono mt-1">{summary.total_connections}</span>
        </div>
        <div className="bg-slate-950/40 border border-slate-850 p-3 rounded-lg flex flex-col items-center justify-center">
          <span className="text-xs text-slate-500 font-medium">Alerts / Violations</span>
          <span className={`text-xl font-bold font-mono mt-1 ${hasAlerts ? 'text-rose-500' : 'text-slate-400'}`}>
            {summary.alerts}
          </span>
        </div>
      </div>

      {/* Real-time Connection Log */}
      <div className="flex-1 flex flex-col min-h-[160px]">
        <span className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
          <Globe className="w-3.5 h-3.5 text-slate-500" /> Connection Attempt Audit Log
        </span>
        <div className="bg-slate-950/70 border border-slate-855 rounded-lg overflow-hidden flex-1 max-h-[220px] overflow-y-auto">
          {summary.log.length === 0 ? (
            <div className="h-full flex items-center justify-center text-center p-4 text-xs text-slate-600 font-mono">
              Awaiting query execution to intercept traffic...
            </div>
          ) : (
            <table className="w-full text-left border-collapse text-[11px] font-mono">
              <thead>
                <tr className="bg-slate-900 text-slate-500 border-b border-slate-850">
                  <th className="py-2 px-3">Time</th>
                  <th className="py-2 px-3">Method</th>
                  <th className="py-2 px-3">Target / Host</th>
                  <th className="py-2 px-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900/60">
                {summary.log.map((conn, idx) => (
                  <tr key={idx} className="hover:bg-slate-900/30 text-slate-300">
                    <td className="py-2 px-3 text-slate-500">
                      {new Date(conn.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2 px-3 text-sky-400 uppercase font-bold">{conn.method}</td>
                    <td className="py-2 px-3 truncate max-w-[120px]" title={`${conn.host}:${conn.port}`}>
                      {conn.host}:{conn.port}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                        conn.status === 'allowed' 
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-900/20' 
                          : 'bg-rose-500/15 text-rose-400 border border-rose-950/20 animate-pulse'
                      }`}>
                        {conn.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Scope boundary disclaimer */}
      <div className="mt-4 bg-slate-950/40 border border-slate-855/60 p-3 rounded-lg flex gap-2 text-[10px] text-slate-500 font-mono">
        <Terminal className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
        <span>
          <strong>Scope boundary:</strong> This monitor tracks connection attempts at the application level by intercepting requests at the HTTP client library level (httpx/requests). It does not perform low-level kernel or OS socket interception.
        </span>
      </div>
    </div>
  );
}
