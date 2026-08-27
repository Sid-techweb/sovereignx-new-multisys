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
    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
      <div className="flex items-center gap-2 mb-4 border-b border-slate-900 pb-3">
        <ClipboardList className="w-4 h-4 text-sky-400" />
        <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase">Recent Investigations</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-xs font-mono uppercase text-slate-500">
              <th className="py-2.5 px-3">Case ID</th>
              <th className="py-2.5 px-3">Asset</th>
              <th className="py-2.5 px-3">Issue / Diagnostics</th>
              <th className="py-2.5 px-3">Severity</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-900 text-sm">
            {investigations.map((inv) => (
              <tr key={inv.id} className="hover:bg-slate-900/20 transition-colors duration-150">
                <td className="py-3 px-3 font-mono font-bold text-slate-400">{inv.id}</td>
                <td className="py-3 px-3 font-medium text-slate-200">{inv.asset}</td>
                <td className="py-3 px-3 text-slate-400 max-w-[280px] truncate" title={inv.issue}>
                  {inv.issue}
                </td>
                <td className="py-3 px-3">
                  <StatusBadge status={inv.severity} />
                </td>
                <td className="py-3 px-3">
                  <StatusBadge status={inv.status} />
                </td>
                <td className="py-3 px-3 text-xs text-slate-500 font-mono">{inv.updated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
