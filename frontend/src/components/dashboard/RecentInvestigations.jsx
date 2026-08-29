import React from 'react';
import StatusBadge from '../common/StatusBadge';
import { ClipboardList } from 'lucide-react';

export default function RecentInvestigations({ cases = [], loading = false }) {
  // Sort by updated_at / created_at descending if present
  const recentCases = [...cases].sort((a, b) => {
    const tA = new Date(a.updated_at || a.created_at || 0).getTime();
    const tB = new Date(b.updated_at || b.created_at || 0).getTime();
    return tB - tA;
  }).slice(0, 5);

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
      <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-console-lineSoft">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-3.5 h-3.5 text-console-amber" />
          <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">RECENT INVESTIGATIONS</h2>
        </div>
        <span className="text-[10px] font-mono tracking-[0.14em] text-console-muted uppercase">LIVE CASES LEDGER</span>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-10">
          <div className="w-5 h-5 border-2 border-console-amber/20 border-t-console-amber rounded-full animate-spin"></div>
          <p className="text-[10px] text-console-muted font-mono mt-2">Loading cases...</p>
        </div>
      ) : recentCases.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse font-sans text-xs">
            <thead>
              <tr className="border-b border-console-line text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted bg-console-panelSolid">
                <th className="py-2 px-3">CASE ID</th>
                <th className="py-2 px-3">ASSET / TITLE</th>
                <th className="py-2 px-3">SUMMARY / DIAGNOSTICS</th>
                <th className="py-2 px-3">SEVERITY</th>
                <th className="py-2 px-3">STATUS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-console-lineSoft">
              {recentCases.map((inv) => (
                <tr key={inv.case_id} className="hover:bg-white/[.02] transition-colors duration-150">
                  <td className="py-2.5 px-3 font-mono font-bold text-console-text2 tabular-nums">
                    {inv.case_number || inv.case_id}
                  </td>
                  <td className="py-2.5 px-3 font-medium text-console-text">{inv.title || 'N/A'}</td>
                  <td className="py-2.5 px-3 text-console-text2 max-w-[280px] truncate" title={inv.summary}>
                    {inv.summary || 'No diagnostic summary provided.'}
                  </td>
                  <td className="py-2.5 px-3">
                    <StatusBadge status={inv.severity || 'UNKNOWN'} />
                  </td>
                  <td className="py-2.5 px-3">
                    <StatusBadge status={inv.status || 'OPEN'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-10 space-y-2">
          <ClipboardList className="w-8 h-8 text-console-muted mx-auto" />
          <p className="text-xs text-console-muted font-mono italic">No recent investigations recorded yet.</p>
        </div>
      )}
    </div>
  );
}
