import React from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout({ children, currentPage, onPageChange, healthStatus, isConnected, modelConfig }) {
  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Persistent Sidebar */}
      <Sidebar currentPage={currentPage} onPageChange={onPageChange} />

      {/* Main Layout Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <Topbar 
          healthStatus={healthStatus} 
          isConnected={isConnected} 
          modelConfig={modelConfig} 
        />

        {/* Scrollable Main Content */}
        <main className="flex-1 overflow-y-auto p-6 bg-slate-950/20">
          <div className="max-w-7xl mx-auto w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
