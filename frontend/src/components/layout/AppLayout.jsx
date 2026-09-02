import React from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout({ 
  children, 
  currentPage, 
  onPageChange, 
  healthStatus, 
  isConnected, 
  modelConfig, 
  openCasesCount,
  theme,
  onToggleTheme,
  currentUser,
  onLogout
}) {
  return (
    <div className="app-bg flex h-screen overflow-hidden font-sans text-console-text">
      {/* Persistent Sidebar */}
      <Sidebar currentPage={currentPage} onPageChange={onPageChange} openCasesCount={openCasesCount} />

      {/* Main Layout Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10 bg-transparent">
        {/* Topbar */}
        <Topbar 
          currentPage={currentPage}
          healthStatus={healthStatus} 
          isConnected={isConnected} 
          modelConfig={modelConfig} 
          theme={theme}
          onToggleTheme={onToggleTheme}
          currentUser={currentUser}
          onLogout={onLogout}
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
