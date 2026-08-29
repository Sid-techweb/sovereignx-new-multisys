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
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  // Poll backend health and fetch configuration/documents
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
