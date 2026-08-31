import React from 'react';
import { Plus, MessageSquare, RefreshCw } from 'lucide-react';

const DAY_MS = 24 * 60 * 60 * 1000;

function groupConversations(conversations) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups = { Today: [], Yesterday: [], 'Previous 7 Days': [], Older: [] };

  for (const c of conversations) {
    const updated = new Date(c.updated_at).getTime();
    const daysAgo = Math.floor((startOfToday - updated) / DAY_MS);
    if (isNaN(updated)) {
      groups.Older.push(c);
    } else if (daysAgo <= 0) {
      groups.Today.push(c);
    } else if (daysAgo === 1) {
      groups.Yesterday.push(c);
    } else if (daysAgo <= 7) {
      groups['Previous 7 Days'].push(c);
    } else {
      groups.Older.push(c);
    }
  }
  return groups;
}

export default function ChatHistoryPanel({
  conversations,
  loading,
  activeConversationId,
  onSelect,
  onNewChat,
  collapsed,
}) {
  const groups = groupConversations(conversations);

  if (collapsed) return null;

  return (
    <div className="w-64 flex-shrink-0 border-r border-slate-800 bg-slate-950/40 flex flex-col h-full">
      <div className="p-3 border-b border-slate-800">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-semibold text-slate-300 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {loading && conversations.length === 0 && (
          <div className="flex items-center gap-2 text-slate-600 text-xs font-mono px-2 py-3">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading history...
          </div>
        )}

        {!loading && conversations.length === 0 && (
          <div className="text-center text-slate-600 text-xs px-3 py-6">
            No previous conversations yet.
          </div>
        )}

        {Object.entries(groups).map(([label, items]) =>
          items.length === 0 ? null : (
            <div key={label} className="mb-3">
              <div className="px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider text-slate-600">
                {label}
              </div>
              <div className="space-y-0.5">
                {items.map((c) => {
                  const isActive = c.conversation_id === activeConversationId;
                  return (
                    <button
                      key={c.conversation_id}
                      onClick={() => onSelect(c.conversation_id)}
                      title={c.title || 'Untitled conversation'}
                      className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left text-xs transition-colors ${
                        isActive
                          ? 'bg-sky-500/10 text-sky-300 border border-sky-500/20'
                          : 'hover:bg-slate-800/70 text-slate-400 border border-transparent'
                      }`}
                    >
                      <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-sky-400' : 'text-slate-600'}`} />
                      <span className="truncate">{c.title || 'New conversation'}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}
