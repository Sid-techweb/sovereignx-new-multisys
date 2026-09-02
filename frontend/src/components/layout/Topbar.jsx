import React from 'react';
import { Sun, Moon, LogOut, User } from 'lucide-react';

export default function Topbar({ 
  currentPage = 'overview', 
  healthStatus, 
  isConnected, 
  modelConfig,
  theme = 'dark',
  onToggleTheme,
  currentUser,
  onLogout
}) {
  const provider = (modelConfig?.provider || 'OLLAMA').toUpperCase();
  const model = (modelConfig?.model || 'QWEN2.5:7B').toUpperCase();
  const formattedPageName = currentPage.replace(/-/g, ' ').toUpperCase();

  return (
    <header className="h-14 border-b border-console-line bg-console-inset px-6 flex items-center justify-between flex-shrink-0 z-10 font-mono">
      {/* Breadcrumb in mono uppercase */}
      <div className="flex items-center gap-2 text-[11px] tracking-[0.14em] text-console-text2">
        <span className="text-console-muted">CONSOLE v1.0.0</span>
        <span className="text-console-muted">/</span>
        <span className="text-console-text font-medium">{formattedPageName}</span>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-3 text-[11px] tracking-[0.14em]">
        {/* Model Gateway Status Pill */}
        <div className="hidden sm:flex items-center gap-2 bg-console-panelSolid border border-console-line px-3 py-1 rounded">
          <span className="text-console-muted">GATEWAY</span>
          <span className="text-console-text font-bold">{provider} · {model}</span>
        </div>

        {/* Server Connection Status */}
        <div className="flex items-center gap-2 bg-console-panelSolid border border-console-line px-3 py-1 rounded">
          {isConnected ? (
            <div className="flex items-center gap-2 text-console-green font-medium">
              <span className="w-2 h-2 rounded-full bg-console-green animate-pulse inline-block" />
              <span>ONLINE</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-console-red font-medium">
              <span className="w-2 h-2 rounded-full bg-console-red inline-block" />
              <span>OFFLINE</span>
            </div>
          )}
        </div>

        {/* Theme Toggle Button */}
        <button
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          className="flex items-center justify-center p-1.5 rounded bg-console-panelSolid border border-console-line text-console-text hover:border-console-amber transition-colors"
        >
          {theme === 'dark' ? (
            <Sun className="w-4 h-4 text-console-amber" />
          ) : (
            <Moon className="w-4 h-4 text-blue-600" />
          )}
        </button>

        {/* User Badge & Logout */}
        {currentUser && (
          <div className="flex items-center gap-2 bg-console-panelSolid border border-console-line px-2.5 py-1 rounded">
            <User className="w-3.5 h-3.5 text-console-amber" />
            <span className="text-console-text font-bold max-w-[100px] truncate">{currentUser.username}</span>
            <button
              onClick={onLogout}
              title="Log Out"
              className="ml-1 text-console-muted hover:text-console-red transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
