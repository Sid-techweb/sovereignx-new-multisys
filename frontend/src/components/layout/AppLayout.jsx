import React from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout({ children, currentPage, onPageChange, healthStatus, isConnected, modelConfig }) {
  return (
    <div className="app-bg flex h-screen overflow-hidden font-sans text-console-text">
      {/* Persistent Sidebar */}
      <Sidebar currentPage={currentPage} onPageChange={onPageChange} />

      {/* Main Layout Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10 bg-transparent">
        {/* Topbar */}
        <Topbar 
          currentPage={currentPage}
          healthStatus={healthStatus} 
          isConnected={isConnected} 
          modelConfig={modelConfig} 
        />

        {/* Scrollable Main Content */}
        <main className="flex-1 overflow-y-auto p-6 bg-transparent">
          <div className="max-w-7xl mx-auto w-full space-y-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
