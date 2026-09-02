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
    <div className="w-64 flex-shrink-0 border-r border-console-line bg-console-inset flex flex-col h-full">
      <div className="p-3 border-b border-console-line">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 bg-white/[.05] hover:bg-white/[.1] border border-console-line rounded text-xs font-mono font-semibold text-console-text transition-all"
        >
          <Plus className="w-3.5 h-3.5" /> New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {loading && conversations.length === 0 && (
          <div className="flex items-center gap-2 text-console-muted text-xs font-mono px-2 py-3">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading history...
          </div>
        )}

        {!loading && conversations.length === 0 && (
          <div className="text-center text-console-muted text-xs px-3 py-6 font-sans">
            No previous conversations yet.
          </div>
        )}

        {Object.entries(groups).map(([label, items]) =>
          items.length === 0 ? null : (
            <div key={label} className="mb-3">
              <div className="px-2.5 py-1 text-[10px] font-mono uppercase tracking-[0.14em] text-console-muted">
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
                      className={`w-full flex items-center gap-2 px-2.5 py-2 rounded text-left text-xs font-sans transition-all ${
                        isActive
                          ? 'bg-console-amberSoft text-console-amber border border-console-amber/30'
                          : 'hover:bg-white/[.04] text-console-text2 border border-transparent'
                      }`}
                    >
                      <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-console-amber' : 'text-console-muted'}`} />
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
