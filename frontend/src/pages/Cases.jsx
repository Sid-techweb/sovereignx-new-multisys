import React from 'react';
import PageHeader from '../components/common/PageHeader';
import { Briefcase } from 'lucide-react';

export default function Cases() {
  return (
    <div className="space-y-6">
      <PageHeader 
        title="Cases" 
        description="Asset anomaly case files and auditing list" 
      />

      <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-12 text-center">
        <Briefcase className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-slate-300">Anomaly Cases Module</h3>
        <p className="text-slate-500 text-sm mt-1 max-w-md mx-auto">
          The cases tracking system manages active investigations, linked evidence items, and SOP verification timelines.
        </p>
        <div className="mt-6 inline-flex items-center gap-1.5 bg-slate-950/60 border border-slate-850 px-3 py-1.5 rounded-lg text-xs font-mono text-slate-500">
          <span>COMING IN A LATER PHASE</span>
        </div>
      </div>
    </div>
  );
}
