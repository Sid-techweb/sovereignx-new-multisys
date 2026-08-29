import React, { useState, useEffect } from 'react';
import AppLayout from './components/layout/AppLayout';
import Overview from './pages/Overview';
import Cases from './pages/Cases';
import Documents from './pages/Documents';
import Investigation from './pages/Investigation';
import KnowledgeBase from './pages/KnowledgeBase';
import Reports from './pages/Reports';
import Agents from './pages/Agents';
import Settings from './pages/Settings';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function App() {
  const [currentPage, setCurrentPage] = useState('overview');
  const [healthStatus, setHealthStatus] = useState('Checking...');
  const [isConnected, setIsConnected] = useState(false);
  const [modelConfig, setModelConfig] = useState({ provider: 'Unknown', model: 'Unknown', status: 'Unknown' });
  const [documents, setDocuments] = useState([]);
  const [cases, setCases] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [isLoadingCases, setIsLoadingCases] = useState(false);

  // Poll backend health and fetch configuration, documents, and cases
  const fetchData = async () => {
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

      // 2. Model Gateway Info (Protected endpoint)
      const modelsRes = await fetch(`${API_BASE}/models`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (modelsRes.ok) {
        const modelsData = await modelsRes.json();
        setModelConfig(modelsData);
      }

      // 3. Documents (Protected endpoint)
      setIsLoadingDocs(true);
      const docsRes = await fetch(`${API_BASE}/documents`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocuments(Array.isArray(docsData) ? docsData : []);
      } else {
        setDocuments([]);
      }

      // 4. Cases (Protected endpoint)
      setIsLoadingCases(true);
      const casesRes = await fetch(`${API_BASE}/cases`, {
        headers: { 'X-API-Key': API_KEY }
      });
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
      setIsLoadingDocs(false);
      setIsLoadingCases(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000); // Poll every 8 seconds
    return () => clearInterval(interval);
  }, []);

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
    >
      {renderPage()}
    </AppLayout>
  );
}
