import React from 'react';
import { 
  Shield, 
  LayoutDashboard, 
  Briefcase, 
  FileText, 
  Activity, 
  Database, 
  ClipboardList, 
  Bot, 
  Settings 
} from 'lucide-react';

export default function Sidebar({ currentPage, onPageChange }) {
  const menuItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'cases', label: 'Cases', icon: Briefcase },
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'investigation', label: 'Investigation', icon: Activity },
    { id: 'knowledge-base', label: 'Knowledge Base', icon: Database },
    { id: 'reports', label: 'Reports', icon: ClipboardList },
    { id: 'agents', label: 'Agent Activity', icon: Bot },
  ];

  return (
    <aside className="w-60 bg-console-inset border-r border-console-line flex flex-col h-full text-console-text2 flex-shrink-0 z-20">
      {/* Brand Logo */}
      <div className="h-14 flex items-center gap-3 px-5 border-b border-console-line">
        <Shield className="w-5 h-5 text-console-amber flex-shrink-0" />
        <div>
          <span className="text-xs font-mono font-bold tracking-[0.14em] text-console-text uppercase block leading-none">SOVEREIGNX</span>
          <span className="text-[10px] text-console-muted font-mono tracking-[0.1em] uppercase">INDUSTRIAL AI OPS</span>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted font-bold px-3 mb-2">
            WORKSPACE
          </div>
          <div className="space-y-1">
            {menuItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentPage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onPageChange(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded text-xs transition-all duration-150 text-left font-sans ${
                    isActive 
                      ? 'bg-console-amber text-[#0b1620] font-bold border border-console-amber shadow-md' 
                      : 'text-console-text2 hover:bg-white/[.04] hover:text-console-text border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-[#0b1620]' : 'text-console-muted'}`} />
                    <span>{item.label}</span>
                  </div>
                  {item.id === 'cases' && (
                    <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
                      isActive ? 'bg-[#0b1620]/20 text-[#0b1620]' : 'bg-console-amberSoft text-console-amber border border-console-amber/30'
                    }`}>
                      2
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Settings at Bottom */}
      <div className="p-3 border-t border-console-line">
        <button
          onClick={() => onPageChange('settings')}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded text-xs transition-all duration-150 text-left font-sans ${
            currentPage === 'settings' 
              ? 'bg-console-amber text-[#0b1620] font-bold border border-console-amber shadow-md' 
              : 'text-console-text2 hover:bg-white/[.04] hover:text-console-text border border-transparent'
          }`}
        >
          <Settings className={`w-4 h-4 flex-shrink-0 ${currentPage === 'settings' ? 'text-[#0b1620]' : 'text-console-muted'}`} />
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}
