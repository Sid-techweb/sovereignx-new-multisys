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

const API_BASE = 'http://127.0.0.1:8000';
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
  // The active chat conversation is lifted up here (rather than living inside
  // <Chat/>) specifically so it survives Chat being unmounted when the user
  // navigates to another dashboard and back -- see Chat.jsx for the message
  // history, which is always re-fetched from Postgres, never cached here.
  const [activeConversationId, setActiveConversationIdState] = useState(() => {
    if (initialLocation.conversationId !== undefined) return initialLocation.conversationId;
    try {
      return localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  const setActiveConversationId = (id) => {
    setActiveConversationIdState(id);
    try {
      if (id) localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, id);
      else localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY);
    } catch {
      // localStorage unavailable (private browsing, etc.) -- conversation
      // still works for this tab via the lifted state above.
    }
  };

  // Keep the URL addressable for the chat page (/chat or /chat/{id}) without
  // pulling in a router: push on change, reset to / when leaving chat since
  // no other page in this app is URL-addressable yet.
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
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  // Poll backend health and fetch configuration/documents
  const fetchData = async () => {
    try {
      // 1. Health Check
      const healthRes = await fetch(`${API_BASE}/health`);
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        setHealthStatus(healthData.status === 'ok' ? 'Connected' : 'Degraded');
        setIsConnected(true);
      } else {
        setHealthStatus('Disconnected');
        setIsConnected(false);
      }

      // 2. Model Gateway Info
      const modelsRes = await fetch(`${API_BASE}/models`);
      if (modelsRes.ok) {
        const modelsData = await modelsRes.json();
        setModelConfig(modelsData);
      }

      // 3. Documents
      setIsLoadingDocs(true);
      const docsRes = await fetch(`${API_BASE}/documents`);
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocuments(docsData);
      }
    } catch (err) {
      setHealthStatus('Disconnected');
      setIsConnected(false);
      setModelConfig({ provider: 'N/A', model: 'N/A', status: 'Offline' });
      setDocuments([]);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000); // Poll every 8 seconds
    return () => clearInterval(interval);
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case 'overview':
        return (
          <Overview 
            modelConfig={modelConfig} 
            isConnected={isConnected} 
            documentsCount={documents.length} 
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
        return <Documents documents={documents} loading={isLoadingDocs} onRefresh={fetchData} />;
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
            documentsCount={documents.length} 
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
    >
      {renderPage()}
    </AppLayout>
  );
}
