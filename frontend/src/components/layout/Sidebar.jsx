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
  Settings,
  MessageSquare
} from 'lucide-react';

export default function Sidebar({ currentPage, onPageChange }) {
  const menuItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'cases', label: 'Cases', icon: Briefcase },
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'investigation', label: 'Investigation', icon: Activity },
    { id: 'knowledge-base', label: 'Knowledge Base', icon: Database },
    { id: 'reports', label: 'Reports', icon: ClipboardList },
    { id: 'agents', label: 'Agent Activity', icon: Bot },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-full text-slate-300">
      {/* Brand Logo */}
      <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-800 bg-slate-950/20">
        <Shield className="w-6 h-6 text-sky-500 flex-shrink-0" />
        <div>
          <span className="text-sm font-bold tracking-wider text-slate-100 uppercase block leading-none">SovereignX</span>
          <span className="text-[10px] text-slate-500 font-mono tracking-tighter">Industrial AI Ops</span>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              className={`w-full flex items-center gap-3.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 text-left ${
                isActive 
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' 
                  : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-sky-400' : 'text-slate-500'}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Settings at Bottom */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/20">
        <button
          onClick={() => onPageChange('settings')}
          className={`w-full flex items-center gap-3.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 text-left ${
            currentPage === 'settings' 
              ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' 
              : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-transparent'
          }`}
        >
          <Settings className={`w-4 h-4 ${currentPage === 'settings' ? 'text-sky-400' : 'text-slate-500'}`} />
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}
