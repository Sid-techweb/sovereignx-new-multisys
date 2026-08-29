import React from 'react';
import StatusBadge from '../common/StatusBadge';
import { ClipboardList } from 'lucide-react';

export default function RecentInvestigations() {
  const investigations = [
    {
      id: 'CAS-701',
      asset: 'Compressor C-118',
      issue: 'Discharge pressure exceeds limit (14.2 bar vs 12.5 bar limit)',
      severity: 'Critical',
      status: 'Active',
      updated: '10m ago'
    },
    {
      id: 'CAS-694',
      asset: 'Pump P-204',
      issue: 'Bearing housing overheating (91°C vs 80°C threshold)',
      severity: 'Warning',
      status: 'Active',
      updated: '1h ago'
    },
    {
      id: 'CAS-688',
      asset: 'Heat Exchanger HX-31',
      issue: 'Tube bundle thermal degradation detected',
      severity: 'Warning',
      status: 'Pending Review',
      updated: '4h ago'
    },
    {
      id: 'CAS-652',
      asset: 'Boiler B-101',
      issue: 'Fuel valve flow rate deviation',
      severity: 'Resolved',
      status: 'Completed',
      updated: 'Yesterday'
    }
  ];

  return (
    <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col">
      <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-console-lineSoft">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-3.5 h-3.5 text-console-amber" />
          <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">RECENT INVESTIGATIONS</h2>
        </div>
        <span className="text-[10px] font-mono tracking-[0.14em] text-console-muted uppercase">LOCAL · DETERMINISTIC</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse font-sans text-xs">
          <thead>
            <tr className="border-b border-console-line text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted bg-console-panelSolid">
              <th className="py-2 px-3">CASE ID</th>
              <th className="py-2 px-3">ASSET</th>
              <th className="py-2 px-3">ISSUE / DIAGNOSTICS</th>
              <th className="py-2 px-3">SEVERITY</th>
              <th className="py-2 px-3">STATUS</th>
              <th className="py-2 px-3">UPDATED</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-console-lineSoft">
            {investigations.map((inv) => (
              <tr key={inv.id} className="hover:bg-white/[.02] transition-colors duration-150">
                <td className="py-2.5 px-3 font-mono font-bold text-console-text2 tabular-nums">{inv.id}</td>
                <td className="py-2.5 px-3 font-medium text-console-text">{inv.asset}</td>
                <td className="py-2.5 px-3 text-console-text2 max-w-[280px] truncate" title={inv.issue}>
                  {inv.issue}
                </td>
                <td className="py-2.5 px-3">
                  <StatusBadge status={inv.severity} />
                </td>
                <td className="py-2.5 px-3">
                  <StatusBadge status={inv.status} />
                </td>
                <td className="py-2.5 px-3 text-[11px] text-console-muted font-mono tabular-nums">{inv.updated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
