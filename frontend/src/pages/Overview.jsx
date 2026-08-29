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

export default function Overview({ modelConfig, isConnected, documentsCount }) {
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
          value="4" 
          icon={Activity} 
          description="Ongoing sensor telemetry scans"
          status="active"
        />
        <MetricCard 
          title="Open Cases" 
          value="2" 
          icon={Briefcase} 
          description="Awaiting manual operations sign-off"
          status="warning"
        />
        <MetricCard 
          title="Documents Processed" 
          value={documentsCount ? String(documentsCount) : "2"} 
          icon={FileText} 
          description="SOP manuals and inspection reports"
        />
        <MetricCard 
          title="Critical Findings" 
          value="1" 
          icon={AlertTriangle} 
          description="Compressor limit threshold breached"
          status="critical"
        />
      </div>

      {/* Main Grid: Data & Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Recent Investigations Table */}
        <div className="lg:col-span-2 space-y-6">
          <RecentInvestigations />
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
