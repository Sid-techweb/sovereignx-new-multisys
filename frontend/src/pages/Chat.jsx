import React, { useState, useRef, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import ChatHistoryPanel from '../components/chat/ChatHistoryPanel';
import {
  Send, RefreshCw, AlertTriangle, Paperclip, X, Plus,
  MessageSquare, FileText, Image as ImageIcon, Wrench, Sparkles, PanelLeftClose, PanelLeft
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';

const ROUTE_LABELS = {
  GENERAL_CHAT: { label: 'General', icon: Sparkles, color: 'text-sky-400' },
  DOCUMENT_RAG: { label: 'Document', icon: FileText, color: 'text-emerald-400' },
  MULTIMODAL: { label: 'Image', icon: ImageIcon, color: 'text-amber-400' },
  EXISTING_TOOL_FLOW: { label: 'Tool', icon: Wrench, color: 'text-violet-400' },
};

export default function Chat({ modelConfig, isConnected, activeConversationId, setActiveConversationId }) {
  const [messages, setMessages] = useState([]);
  // In-flight assistant reply being streamed in, or null when nothing is streaming.
  // Kept separate from `messages` so a turn is appended to history exactly
  // once, fully formed, when the stream completes -- never duplicated and
  // never persisted/rendered as many partial entries.
  const [streamingMessage, setStreamingMessage] = useState(null);
  const [input, setInput] = useState('');
  const [attachedDoc, setAttachedDoc] = useState(null); // { document_id, filename, file_type }
  const [attaching, setAttaching] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  // Loading a previous conversation's history is a cheap DB read, distinct
  // from "sending"/generating a new response -- kept as separate state so
  // the UI never shows "Generating response..." while merely reopening an
  // old chat.
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [conversations, setConversations] = useState([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);

  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);
  // Set right before we locally create a new conversation and immediately
  // adopt its id, so the history-hydration effect below doesn't re-fetch
  // (and clobber) the turn we're already building in local state.
  const skipNextHydrationRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage, sending]);

  const fetchConversations = async () => {
    setLoadingConversations(true);
    try {
      const res = await fetch(`${API_BASE}/chat/conversations`);
      if (res.ok) {
        setConversations(await res.json());
      }
    } catch {
      // Non-fatal: history panel just stays as-is. The active conversation
      // (if any) still works via the endpoints below.
    } finally {
      setLoadingConversations(false);
    }
  };

  useEffect(() => {
    fetchConversations();
    // Only on mount -- afterwards the list is refreshed explicitly (new
    // conversation created, turn completed), not on a timer/poll, so it
    // never competes with in-flight generation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reload message history from Postgres whenever the active conversation
  // changes -- covers: initial mount with a restored id (nav-back/refresh),
  // and the user picking a different conversation from the history panel.
  useEffect(() => {
    if (skipNextHydrationRef.current) {
      skipNextHydrationRef.current = false;
      return;
    }
    if (!activeConversationId) {
      setMessages([]);
      setStreamingMessage(null);
      setLoadingHistory(false);
      return;
    }

    let cancelled = false;
    setLoadingHistory(true);
    setError(null);
    setStreamingMessage(null);

    fetch(`${API_BASE}/chat/conversations/${activeConversationId}/messages`)
      .then(async (res) => {
        if (res.status === 404) throw new Error('__NOT_FOUND__');
        if (!res.ok) throw new Error('__UNAVAILABLE__');
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setMessages(
          data.map((m) => ({
            role: m.role,
            content: m.content,
            route: m.route || undefined,
            sources: m.sources || [],
            document_id: m.document_id,
          }))
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setMessages([]);
        if (err.message === '__NOT_FOUND__') {
          setError('That conversation no longer exists. Starting a new one.');
          setActiveConversationId(null);
        } else {
          setError('Could not load that conversation. Check that the SovereignX backend is running.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeConversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  const startNewChat = () => {
    setActiveConversationId(null);
    setMessages([]);
    setStreamingMessage(null);
    setAttachedDoc(null);
    setError(null);
    setInput('');
  };

  const selectConversation = (id) => {
    if (id === activeConversationId) return;
    setActiveConversationId(id);
  };

  const handleAttach = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';

    setAttaching(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const uploadRes = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', body: formData });
      if (!uploadRes.ok) {
        const errData = await uploadRes.json().catch(() => ({}));
        throw new Error(errData.detail || 'Upload failed.');
      }
      const doc = await uploadRes.json();

      const processRes = await fetch(`${API_BASE}/documents/${doc.document_id}/process`, { method: 'POST' });
      if (!processRes.ok) {
        const errData = await processRes.json().catch(() => ({}));
        throw new Error(errData.detail || 'Document processing failed.');
      }

      setAttachedDoc({ document_id: doc.document_id, filename: doc.filename, file_type: doc.file_type });
    } catch (err) {
      setError(err.message || 'Failed to attach file.');
    } finally {
      setAttaching(false);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    const message = input.trim();
    if (!message || sending) return;

    setError(null);
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: message, document_id: attachedDoc?.document_id || null }]);
    setSending(true);
    setStreamingMessage(null);

    const attachment = attachedDoc;
    setAttachedDoc(null);

    let convoId = activeConversationId;
    let createdNewConversation = false;
    try {
      if (!convoId) {
        const createRes = await fetch(`${API_BASE}/chat/conversations`, { method: 'POST' });
        if (!createRes.ok) throw new Error('Could not start a new conversation.');
        const created = await createRes.json();
        convoId = created.conversation_id;
        createdNewConversation = true;
        skipNextHydrationRef.current = true;
        setActiveConversationId(convoId);
      }
    } catch (err) {
      setError('Cannot reach the SovereignX backend. Check that it is running.');
      setSending(false);
      return;
    }

    if (createdNewConversation) fetchConversations();

    try {
      const res = await fetch(`${API_BASE}/chat/conversations/${convoId}/messages/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, document_id: attachment?.document_id || null }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Request failed with status ${res.status}`);
      }
      if (!res.body) {
        throw new Error('Streaming is not supported by this browser response.');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const handleEvent = (event) => {
        if (event.type === 'start') {
          setStreamingMessage({
            content: '',
            route: event.route,
            sources: event.retrieved_chunks || [],
            ragDegraded: event.rag_degraded_reason,
          });
        } else if (event.type === 'token') {
          setStreamingMessage(prev => ({
            ...(prev || { route: null, sources: [] }),
            content: (prev?.content || '') + event.content,
          }));
        } else if (event.type === 'done') {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: event.answer,
            route: event.route,
            sources: event.retrieved_chunks || [],
            timings: event.timings_ms,
            ragDegraded: event.rag_degraded_reason,
          }]);
          setStreamingMessage(null);
          // Refresh the list now (not on every token) so the title
          // (assigned from the first user message) and updated_at
          // reordering show up without polling.
          fetchConversations();
        } else if (event.type === 'error') {
          if (event.partial_content) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: event.partial_content,
              incomplete: true,
            }]);
          }
          setStreamingMessage(null);
          setError(event.message || 'Something went wrong while generating a response.');
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.trim()) handleEvent(JSON.parse(line));
        }
      }
      if (buffer.trim()) handleEvent(JSON.parse(buffer));
    } catch (err) {
      setStreamingMessage(prev => {
        // A network/parse failure mid-stream: preserve whatever text had
        // already arrived rather than silently discarding it.
        if (prev && prev.content) {
          setMessages(m => [...m, { role: 'assistant', content: prev.content, incomplete: true }]);
        }
        return null;
      });
      setError(err.message || 'Network error while contacting the backend.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <PageHeader
        title="Chat"
        description="Ask anything. Local model knowledge by default, with document/image grounding used automatically when relevant."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setHistoryCollapsed(v => !v)}
              title={historyCollapsed ? 'Show history' : 'Hide history'}
              className="flex items-center justify-center w-8 h-8 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-400 transition-colors"
            >
              {historyCollapsed ? <PanelLeft className="w-3.5 h-3.5" /> : <PanelLeftClose className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={startNewChat}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-semibold text-slate-300 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> New Chat
            </button>
          </div>
        }
      />

      <div className="flex-1 min-h-0 bg-slate-900/30 border border-slate-800 rounded-xl flex overflow-hidden shadow-lg">
        <ChatHistoryPanel
          conversations={conversations}
          loading={loadingConversations}
          activeConversationId={activeConversationId}
          onSelect={selectConversation}
          onNewChat={startNewChat}
          collapsed={historyCollapsed}
        />

        <div className="flex-1 min-w-0 flex flex-col">
          {/* Message list */}
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
            {loadingHistory && (
              <div className="flex items-center gap-2 text-slate-500 text-xs font-mono pl-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading conversation...
              </div>
            )}

            {!loadingHistory && messages.length === 0 && !streamingMessage && (
              <div className="h-full flex flex-col items-center justify-center text-center space-y-3 py-16">
                <MessageSquare className="w-10 h-10 text-slate-800" />
                <p className="text-sm text-slate-500 max-w-sm">
                  Start a new conversation. Ask a general question, or attach a PDF/image to ground the answer in it.
                </p>
              </div>
            )}

            {!loadingHistory && messages.map((msg, idx) => (
              <MessageBubble key={idx} msg={msg} />
            ))}

            {/* Once tokens start arriving, this replaces the "Generating..." indicator. */}
            {streamingMessage && streamingMessage.content && (
              <MessageBubble msg={{ role: 'assistant', ...streamingMessage }} isStreaming />
            )}

            {sending && !(streamingMessage && streamingMessage.content) && (
              <div className="flex items-center gap-2 text-slate-500 text-xs font-mono pl-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Generating response...
              </div>
            )}

            {error && (
              <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-3 flex gap-2.5 text-rose-400 text-sm">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Composer */}
          <div className="border-t border-slate-800 p-4 bg-slate-950/30">
            {attachedDoc && (
              <div className="mb-2 inline-flex items-center gap-2 bg-slate-800/80 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300">
                <Paperclip className="w-3.5 h-3.5 text-sky-400" />
                <span className="max-w-[220px] truncate">{attachedDoc.filename}</span>
                <button type="button" onClick={() => setAttachedDoc(null)} className="text-slate-500 hover:text-slate-300">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            <form onSubmit={handleSend} className="flex items-end gap-2.5">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.csv,.png,.jpg,.jpeg"
                onChange={handleAttach}
                disabled={attaching}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={attaching || sending}
                title="Attach a PDF, CSV, or image (optional)"
                className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 text-slate-400 transition-colors"
              >
                {attaching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
              </button>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend(e);
                  }
                }}
                placeholder="Ask anything -- no document required..."
                rows={1}
                className="flex-1 resize-none bg-slate-950/80 border border-slate-800 rounded-lg px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 max-h-32"
              />
              <button
                type="submit"
                disabled={sending || !input.trim() || !isConnected}
                className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-slate-850 disabled:text-slate-600 text-white transition-colors"
              >
                {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </form>
            <p className="text-[10px] text-slate-600 font-mono mt-2">
              Provider: {modelConfig?.provider || 'unknown'} · Model: {modelConfig?.model || 'unknown'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg, isStreaming = false }) {
  const isUser = msg.role === 'user';
  const routeMeta = msg.route ? ROUTE_LABELS[msg.route] : null;
  const RouteIcon = routeMeta?.icon;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
        isUser
          ? 'bg-sky-600/90 text-white'
          : 'bg-slate-800/70 border border-slate-800 text-slate-200'
      }`}>
        {msg.content}
        {isStreaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-sky-400 align-middle animate-pulse" />}

        {msg.incomplete && (
          <div className="mt-1.5 text-[10px] font-mono text-amber-400/80">Response was interrupted.</div>
        )}

        {!isUser && !isStreaming && (routeMeta || (msg.sources && msg.sources.length > 0) || msg.timings) && (
          <div className="mt-2 pt-2 border-t border-slate-700/60 flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-500">
            {routeMeta && (
              <span className={`inline-flex items-center gap-1 ${routeMeta.color}`}>
                {RouteIcon && <RouteIcon className="w-3 h-3" />} {routeMeta.label}
              </span>
            )}
            {msg.timings?.ttft_ms != null && <span>TTFT: {Math.round(msg.timings.ttft_ms)}ms</span>}
            {msg.timings?.total_ms != null && <span>Total: {Math.round(msg.timings.total_ms)}ms</span>}
            {msg.sources && msg.sources.length > 0 && (
              <span className="truncate max-w-[260px]">
                Sources: {msg.sources.map(s => s.filename).filter((v, i, a) => a.indexOf(v) === i).join(', ')}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
