import React from 'react';
import PageHeader from '../components/common/PageHeader';
import { ClipboardList } from 'lucide-react';

export default function Reports() {
  return (
    <div className="space-y-6">
      <PageHeader 
        title="Reports" 
        description="Audit reports, validation compliance, and operations exports summaries" 
      />

      <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-12 text-center">
        <ClipboardList className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-slate-300">Audit Reports Module</h3>
        <p className="text-slate-500 text-sm mt-1 max-w-md mx-auto">
          Generate formal PDF audit summaries containing telemetry graphs, matched SOP references, and operator recommendation sign-offs.
        </p>
        <div className="mt-6 inline-flex items-center gap-1.5 bg-slate-950/60 border border-slate-850 px-3 py-1.5 rounded-lg text-xs font-mono text-slate-500">
          <span>COMING IN A LATER PHASE</span>
        </div>
      </div>
    </div>
  );
}
