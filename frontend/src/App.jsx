import React, { useState, useEffect } from 'react';
import AppLayout from './components/layout/AppLayout';
import Overview from './pages/Overview';
import Chat from './pages/Chat';
import Cases from './pages/Cases';
import Documents from './pages/Documents';
import Investigation from './pages/Investigation';
import KnowledgeBase from './pages/KnowledgeBase';
import Reports from './pages/Reports';
import Agents from './pages/Agents';
import Settings from './pages/Settings';
import Login from './pages/Login';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';
const ACTIVE_CONVERSATION_STORAGE_KEY = 'sovereignx_active_conversation_id';
const CHAT_CONVERSATION_PATH = /^\/chat\/([0-9a-fA-F-]{36})\/?$/;

function parseInitialLocation() {
  const path = window.location.pathname;
  const match = path.match(CHAT_CONVERSATION_PATH);
  if (match) return { page: 'chat', conversationId: match[1] };
  if (path === '/chat' || path === '/chat/') return { page: 'chat', conversationId: null };
  return { page: 'overview', conversationId: undefined };
}

export default function App() {
  const initialLocation = parseInitialLocation();
  const [currentPage, setCurrentPage] = useState(initialLocation.page);
  const [activeConversationId, setActiveConversationIdState] = useState(() => {
    if (initialLocation.conversationId !== undefined) return initialLocation.conversationId;
    try {
      return localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  // Theme & Auth State
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('sovereignx_theme') || 'dark';
    } catch {
      return 'dark';
    }
  });
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    try {
      localStorage.setItem('sovereignx_theme', nextTheme);
    } catch {}
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Check auth session on startup
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('sovereignx_token');
      try {
        const headers = token ? { 'Authorization': `Bearer ${token}` } : { 'X-API-Key': API_KEY };
        const res = await fetch(`${API_BASE}/auth/me`, { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated) {
            setCurrentUser({ username: data.username, email: data.email });
          }
        }
      } catch (e) {
        console.warn('Auth check failed:', e);
      } finally {
        setAuthChecked(true);
      }
    };
    checkAuth();
  }, []);

  const handleLoginSuccess = (user, token) => {
    setCurrentUser(user);
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
    } catch {}
    localStorage.removeItem('sovereignx_token');
    setCurrentUser(null);
  };

  const setActiveConversationId = (id) => {
    setActiveConversationIdState(id);
    try {
      if (id) localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, id);
      else localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY);
    } catch {}
  };

  useEffect(() => {
    if (currentPage === 'chat') {
      const path = activeConversationId ? `/chat/${activeConversationId}` : '/chat';
      if (window.location.pathname !== path) {
        window.history.pushState({ page: 'chat', conversationId: activeConversationId }, '', path);
      }
    } else if (window.location.pathname.startsWith('/chat')) {
      window.history.pushState({}, '', '/');
    }
  }, [currentPage, activeConversationId]);

  useEffect(() => {
    const onPopState = () => {
      const parsed = parseInitialLocation();
      setCurrentPage(parsed.page);
      if (parsed.page === 'chat') {
        setActiveConversationIdState(parsed.conversationId || null);
      }
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const [healthStatus, setHealthStatus] = useState('Checking...');
  const [isConnected, setIsConnected] = useState(false);
  const [modelConfig, setModelConfig] = useState({ provider: 'Unknown', model: 'Unknown', status: 'Unknown' });
  const [documents, setDocuments] = useState([]);
  const [cases, setCases] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [isLoadingCases, setIsLoadingCases] = useState(false);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('sovereignx_token');
    return token ? { 'Authorization': `Bearer ${token}` } : { 'X-API-Key': API_KEY };
  };

  // Poll backend health and fetch configuration, documents, and cases
  // Helper equality comparison for documents state to eliminate unnecessary re-renders/flicker
  const areDocsEqual = (prev, next) => {
    if (!Array.isArray(prev) || !Array.isArray(next)) return false;
    if (prev.length !== next.length) return false;
    for (let i = 0; i < prev.length; i++) {
      const p = prev[i], n = next[i];
      if (!p || !n) return false;
      if ((p.document_id || p.id) !== (n.document_id || n.id)) return false;
      if (p.status !== n.status) return false;
      if (p.chunks_count !== n.chunks_count) return false;
      if (p.failed_at_batch !== n.failed_at_batch) return false;
      if (p.chunks_succeeded !== n.chunks_succeeded) return false;
      if (p.error_message !== n.error_message) return false;
    }
    return true;
  };

  const fetchData = async (isInitial = false) => {
    try {
      // 1. Health Check (Public endpoint)
      const healthRes = await fetch(`${API_BASE}/health`);
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        setHealthStatus(healthData.status === 'ok' ? 'Connected' : 'Degraded');
        setIsConnected(true);
      } else {
        setHealthStatus('Disconnected');
        setIsConnected(false);
      }

      const headers = getAuthHeaders();

      // 2. Model Gateway Info (Protected endpoint)
      const modelsRes = await fetch(`${API_BASE}/models`, { headers });
      if (modelsRes.ok) {
        const modelsData = await modelsRes.json();
        setModelConfig(modelsData);
      }

      // 3. Documents (Protected endpoint)
      if (isInitial) setIsLoadingDocs(true);
      const docsRes = await fetch(`${API_BASE}/documents`, { headers });
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        const nextDocs = Array.isArray(docsData) ? docsData : [];
        setDocuments(prevDocs => areDocsEqual(prevDocs, nextDocs) ? prevDocs : nextDocs);
      } else {
        setDocuments([]);
      }

      // 4. Cases (Protected endpoint)
      if (isInitial) setIsLoadingCases(true);
      const casesRes = await fetch(`${API_BASE}/cases`, { headers });
      if (casesRes.ok) {
        const casesData = await casesRes.json();
        setCases(Array.isArray(casesData) ? casesData : []);
      } else {
        setCases([]);
      }
    } catch (err) {
      setHealthStatus('Disconnected');
      setIsConnected(false);
      setModelConfig({ provider: 'N/A', model: 'N/A', status: 'Offline' });
      setDocuments([]);
      setCases([]);
    } finally {
      if (isInitial) {
        setIsLoadingDocs(false);
        setIsLoadingCases(false);
      }
    }
  };

  useEffect(() => {
    if (currentUser) {
      fetchData(true);
      const interval = setInterval(() => {
        fetchData(false);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [currentUser]);

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center font-mono text-xs text-blue-400">
        Initializing SovereignX Authentication...
      </div>
    );
  }

  if (!currentUser) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  const safeCases = Array.isArray(cases) ? cases : [];
  const safeDocuments = Array.isArray(documents) ? documents : [];

  const openCasesCount = safeCases.filter(
    c => c && (c.status || '').toLowerCase() !== 'closed' && (c.status || '').toLowerCase() !== 'resolved'
  ).length;

  const renderPage = () => {
    switch (currentPage) {
      case 'overview':
        return (
          <Overview 
            modelConfig={modelConfig} 
            isConnected={isConnected} 
            documentsCount={safeDocuments.length} 
            cases={safeCases}
            loadingCases={isLoadingCases}
          />
        );
      case 'chat':
        return (
          <Chat
            modelConfig={modelConfig}
            isConnected={isConnected}
            activeConversationId={activeConversationId}
            setActiveConversationId={setActiveConversationId}
          />
        );
      case 'cases':
        return <Cases />;
      case 'documents':
        return <Documents documents={safeDocuments} loading={isLoadingDocs} onRefresh={fetchData} />;
      case 'investigation':
        return <Investigation modelConfig={modelConfig} isConnected={isConnected} />;
      case 'knowledge-base':
        return <KnowledgeBase />;
      case 'reports':
        return <Reports />;
      case 'agents':
        return <Agents />;
      case 'settings':
        return <Settings modelConfig={modelConfig} healthStatus={healthStatus} />;
      default:
        return (
          <Overview 
            modelConfig={modelConfig} 
            isConnected={isConnected} 
            documentsCount={safeDocuments.length} 
            cases={safeCases}
            loadingCases={isLoadingCases}
          />
        );
    }
  };

  return (
    <AppLayout
      currentPage={currentPage}
      onPageChange={setCurrentPage}
      healthStatus={healthStatus}
      isConnected={isConnected}
      modelConfig={modelConfig}
      openCasesCount={openCasesCount}
      theme={theme}
      onToggleTheme={toggleTheme}
      currentUser={currentUser}
      onLogout={handleLogout}
    >
      {renderPage()}
    </AppLayout>
  );
}
