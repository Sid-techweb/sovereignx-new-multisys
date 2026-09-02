import React, { useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, Globe, Terminal } from 'lucide-react';

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
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-console-lineSoft">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-console-green" />
          <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">LIVE NETWORK SOVEREIGNTY MONITOR</h2>
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[10px]">
          <span className={`h-1.5 w-1.5 rounded-full ${
            wsStatus === 'connected' ? 'bg-console-green animate-pulse' :
            wsStatus === 'connecting' ? 'bg-console-amber animate-pulse' : 'bg-console-red'
          }`} />
          <span className="text-console-muted uppercase">{wsStatus}</span>
        </div>
      </div>

      {/* Main Status Area */}
      <div className={`p-3 rounded border flex flex-col items-center justify-center text-center gap-2 transition-all duration-300 ${
        hasAlerts 
          ? 'bg-console-red/10 border-console-red/30 text-console-red' 
          : 'bg-console-greenSoft border-console-green/30 text-console-green'
      }`}>
        {hasAlerts ? (
          <ShieldAlert className="w-8 h-8 text-console-red" />
        ) : (
          <ShieldCheck className="w-8 h-8 text-console-green" />
        )}
        <div className="space-y-0.5">
          <p className="text-[10px] uppercase font-mono tracking-[0.14em] text-console-muted">MONITOR STATUS</p>
          <h3 className="text-xs font-mono font-bold tracking-tight">{summary.status}</h3>
        </div>
      </div>

      {/* Connection Counters */}
      <div className="grid grid-cols-2 gap-3 my-3">
        <div className="bg-console-inset border border-console-line p-2.5 rounded flex flex-col items-center justify-center">
          <span className="text-[10px] text-console-muted font-mono uppercase tracking-[0.1em]">TOTAL CONNECTIONS</span>
          <span className="text-lg font-bold text-console-text font-mono tabular-nums mt-0.5">{summary.total_connections}</span>
        </div>
        <div className="bg-console-inset border border-console-line p-2.5 rounded flex flex-col items-center justify-center">
          <span className="text-[10px] text-console-muted font-mono uppercase tracking-[0.1em]">ALERTS / VIOLATIONS</span>
          <span className={`text-lg font-bold font-mono tabular-nums mt-0.5 ${hasAlerts ? 'text-console-red' : 'text-console-text2'}`}>
            {summary.alerts}
          </span>
        </div>
      </div>

      {/* Real-time Connection Log */}
      <div className="flex-1 flex flex-col min-h-[150px]">
        <span className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase mb-2 flex items-center gap-1.5">
          <Globe className="w-3.5 h-3.5 text-console-muted" /> CONNECTION ATTEMPT AUDIT LOG
        </span>
        <div className="bg-console-inset border border-console-line rounded overflow-hidden flex-1 max-h-[200px] overflow-y-auto">
          {summary.log.length === 0 ? (
            <div className="h-full flex items-center justify-center text-center p-4 text-[11px] text-console-muted font-mono">
              Awaiting query execution to intercept traffic...
            </div>
          ) : (
            <table className="w-full text-left border-collapse text-[11px] font-mono">
              <thead>
                <tr className="bg-console-panelSolid text-console-muted border-b border-console-line">
                  <th className="py-1.5 px-3 uppercase tracking-wider text-[10px]">TIME</th>
                  <th className="py-1.5 px-3 uppercase tracking-wider text-[10px]">METHOD</th>
                  <th className="py-1.5 px-3 uppercase tracking-wider text-[10px]">TARGET / HOST</th>
                  <th className="py-1.5 px-3 text-right uppercase tracking-wider text-[10px]">STATUS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-console-lineSoft">
                {summary.log.map((conn, idx) => (
                  <tr key={idx} className="hover:bg-white/[.02] text-console-text">
                    <td className="py-1.5 px-3 text-console-muted tabular-nums">
                      {new Date(conn.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-1.5 px-3 text-console-amber uppercase font-bold">{conn.method}</td>
                    <td className="py-1.5 px-3 truncate max-w-[120px]" title={`${conn.host}:${conn.port}`}>
                      {conn.host}:{conn.port}
                    </td>
                    <td className="py-1.5 px-3 text-right">
                      <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                        conn.status === 'allowed' 
                          ? 'bg-console-greenSoft text-console-green border border-console-green/30' 
                          : 'bg-console-red/10 text-console-red border border-console-red/30'
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
      <div className="mt-3 bg-console-inset border border-console-line p-2.5 rounded flex gap-2 text-[10px] text-console-muted font-mono">
        <Terminal className="w-3.5 h-3.5 text-console-muted flex-shrink-0 mt-0.5" />
        <span>
          <strong className="text-console-text2">SCOPE BOUNDARY:</strong> Intercepts requests at client library level (httpx/requests). Local deterministic.
        </span>
      </div>
    </div>
  );
}
