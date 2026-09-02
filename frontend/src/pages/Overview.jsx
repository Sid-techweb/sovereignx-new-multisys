import React from 'react';
import PageHeader from '../components/common/PageHeader';
import MetricCard from '../components/dashboard/MetricCard';
import SystemStatus from '../components/dashboard/SystemStatus';
import SovereigntyPanel from '../components/dashboard/SovereigntyPanel';
import RecentInvestigations from '../components/dashboard/RecentInvestigations';
import ActivityFeed from '../components/dashboard/ActivityFeed';
import { 
  Activity, 
  Briefcase, 
  FileText, 
  AlertTriangle 
} from 'lucide-react';

export default function Overview({ modelConfig, isConnected, documentsCount = 0, cases = [], loadingCases = false }) {
  const activeInvestigationsCount = cases.filter(
    c => (c.status || '').toLowerCase().includes('active') || (c.status || '').toLowerCase().includes('investigation')
  ).length;

  const openCasesCount = cases.filter(
    c => (c.status || '').toLowerCase() !== 'closed' && (c.status || '').toLowerCase() !== 'resolved'
  ).length;

  const criticalFindingsCount = cases.filter(
    c => (c.severity || '').toLowerCase() === 'critical' || (c.severity || '').toLowerCase() === 'high'
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Overview" 
        description="Industrial Intelligence Command Center" 
      />

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard 
          title="Active Investigations" 
          value={String(activeInvestigationsCount)} 
          icon={Activity} 
          description="Ongoing sensor telemetry scans"
          status={activeInvestigationsCount > 0 ? "active" : "muted"}
        />
        <MetricCard 
          title="Open Cases" 
          value={String(openCasesCount)} 
          icon={Briefcase} 
          description="Awaiting manual operations sign-off"
          status={openCasesCount > 0 ? "warning" : "muted"}
        />
        <MetricCard 
          title="Documents Processed" 
          value={String(documentsCount)} 
          icon={FileText} 
          description="SOP manuals and inspection reports"
          status={documentsCount > 0 ? "active" : "muted"}
        />
        <MetricCard 
          title="Critical Findings" 
          value={String(criticalFindingsCount)} 
          icon={AlertTriangle} 
          description="High severity threshold exceedances"
          status={criticalFindingsCount > 0 ? "critical" : "muted"}
        />
      </div>

      {/* Main Grid: Data & Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Recent Investigations Table */}
        <div className="lg:col-span-2 space-y-6">
          <RecentInvestigations cases={cases} loading={loadingCases} />
        </div>

        {/* Right Column: System Status, Sovereignty Panel & Activity Feed */}
        <div className="space-y-6">
          <SystemStatus 
            modelConfig={modelConfig} 
            isConnected={isConnected} 
          />
          <SovereigntyPanel />
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
