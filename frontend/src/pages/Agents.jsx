import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import { 
  Play, 
  RefreshCw, 
  CheckCircle2, 
  XCircle, 
  FileText, 
  Terminal, 
  ChevronDown, 
  ChevronUp, 
  Activity,
  Percent,
  TrendingUp,
  Cpu,
  Layers
} from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'sovereignx-demo-key-2026';

export default function Agents() {
  const [tools, setTools] = useState([]);
  const [selectedToolName, setSelectedToolName] = useState('');
  const [argumentsData, setArgumentsData] = useState({});
  const [executionResult, setExecutionResult] = useState(null);
  const [executionLogs, setExecutionLogs] = useState([]);
  
  const [isLoadingTools, setIsLoadingTools] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [rawJsonVisible, setRawJsonVisible] = useState(false);

  // Get currently selected tool details
  const selectedTool = tools.find(t => t.name === selectedToolName) || null;

  const fetchTools = async () => {
    setIsLoadingTools(true);
    try {
      const response = await fetch(`${API_BASE}/tools`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (response.ok) {
        const data = await response.json();
        setTools(data);
        if (data.length > 0) {
          setSelectedToolName(data[0].name);
          initializeArgs(data[0]);
        }
      }
    } catch (err) {
      console.error('Error fetching tools:', err);
    } finally {
      setIsLoadingTools(false);
    }
  };

  const fetchLogs = async () => {
    setIsLoadingLogs(true);
    try {
      const response = await fetch(`${API_BASE}/tools/logs?limit=30`, {
        headers: { 'X-API-Key': API_KEY }
      });
      if (response.ok) {
        const data = await response.json();
        setExecutionLogs(data);
      }
    } catch (err) {
      console.error('Error fetching logs:', err);
    } finally {
      setIsLoadingLogs(false);
    }
  };

  const initializeArgs = (tool) => {
    const initialArgs = {};
    Object.entries(tool.parameters).forEach(([name, param]) => {
      initialArgs[name] = param.default !== null ? param.default : (param.options ? param.options[0] : '');
    });
    setArgumentsData(initialArgs);
    setExecutionResult(null);
  };

  useEffect(() => {
    fetchTools();
    fetchLogs();
  }, []);

  const handleToolChange = (e) => {
    const name = e.target.value;
    setSelectedToolName(name);
    const tool = tools.find(t => t.name === name);
    if (tool) {
      initializeArgs(tool);
    }
  };

  const handleInputChange = (paramName, value) => {
    setArgumentsData(prev => ({
      ...prev,
      [paramName]: value
    }));
  };

  const handleExecute = async (e) => {
    e.preventDefault();
    if (!selectedTool) return;

    setIsExecuting(true);
    setExecutionResult(null);

    // Process arguments based on their schema types
    const processedArgs = {};
    try {
      Object.entries(selectedTool.parameters).forEach(([name, param]) => {
        const rawVal = argumentsData[name];
        
        if (param.type === 'float' || param.type === 'int') {
          if (rawVal === '' || rawVal === undefined) {
            if (param.required) {
              throw new Error(`Field '${name}' is required.`);
            }
            processedArgs[name] = param.default;
          } else {
            const num = Number(rawVal);
            if (isNaN(num)) {
              throw new Error(`Field '${name}' must be a valid number.`);
            }
            processedArgs[name] = num;
          }
        } else if (param.type === 'list[float]') {
          if (!rawVal || rawVal.trim() === '') {
            if (param.required) {
              throw new Error(`Field '${name}' is required.`);
            }
            processedArgs[name] = [];
          } else {
            const arr = rawVal.split(',').map(item => {
              const num = Number(item.trim());
              if (isNaN(num)) {
                throw new Error(`Array field '${name}' contains invalid number: '${item}'`);
              }
              return num;
            });
            processedArgs[name] = arr;
          }
        } else {
          // str or others
          processedArgs[name] = rawVal;
        }
      });

      const response = await fetch(`${API_BASE}/tools/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify({
          tool_name: selectedTool.name,
          arguments: processedArgs
        })
      });

      const data = await response.json();
      setExecutionResult(data);
      fetchLogs(); // Refresh logs after execution
    } catch (err) {
      setExecutionResult({
        tool_name: selectedTool.name,
        status: 'failed',
        error: err.message,
        outputs: {},
        execution_log_id: 'local-validation-error',
        duration_ms: 0
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const formatTimestamp = (isoString) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) {
      return isoString;
    }
  };

  const toggleExpandLog = (id) => {
    setExpandedLogId(expandedLogId === id ? null : id);
  };

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Local Tools & Execution Sandbox" 
        description="Air-gapped computational utilities for local evaluation, statistical thresholds, and metric transformations" 
        actions={
          <button 
            onClick={() => { fetchTools(); fetchLogs(); }}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold rounded-lg border border-slate-800 transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Sync System
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Configuration Panel */}
        <div className="lg:col-span-5 bg-slate-900/30 border border-slate-800/80 rounded-xl p-5 shadow-lg flex flex-col h-full">
          <div className="flex items-center gap-2 border-b border-slate-800/60 pb-3 mb-4">
            <Cpu className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Tool Runner Interface
            </h2>
          </div>

          {isLoadingTools ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <RefreshCw className="w-8 h-8 animate-spin text-slate-600 mb-2" />
              <p className="text-xs">Loading tools registry...</p>
            </div>
          ) : (
            <form onSubmit={handleExecute} className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                {/* Selector */}
                <div>
                  <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5 font-mono">
                    Select Tool Function
                  </label>
                  <select
                    value={selectedToolName}
                    onChange={handleToolChange}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 font-medium"
                  >
                    {tools.map(t => (
                      <option key={t.name} value={t.name}>{t.name}</option>
                    ))}
                  </select>
                  {selectedTool && (
                    <p className="text-xs text-slate-400 mt-2 bg-slate-950/40 p-2.5 rounded border border-slate-850/60 font-sans leading-relaxed">
                      {selectedTool.description}
                    </p>
                  )}
                </div>

                {/* Parameters Forms */}
                {selectedTool && (
                  <div className="space-y-3.5 border-t border-slate-800/40 pt-4">
                    <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono">
                      Input Arguments
                    </h3>
                    
                    {Object.entries(selectedTool.parameters).map(([name, param]) => (
                      <div key={name} className="space-y-1">
                        <div className="flex justify-between items-baseline">
                          <label className="block text-xs font-semibold text-slate-300">
                            {name}
                            {param.required && <span className="text-red-500 ml-0.5">*</span>}
                          </label>
                          <span className="text-[9px] font-mono text-slate-600 uppercase bg-slate-950 px-1.5 py-0.5 rounded">
                            {param.type}
                          </span>
                        </div>

                        {param.options ? (
                          <select
                            value={argumentsData[name] || ''}
                            onChange={(e) => handleInputChange(name, e.target.value)}
                            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 font-mono"
                          >
                            {param.options.map(opt => (
                              <option key={opt} value={opt}>{opt}</option>
                            ))}
                          </select>
                        ) : param.type === 'list[float]' ? (
                          <textarea
                            value={argumentsData[name] || ''}
                            onChange={(e) => handleInputChange(name, e.target.value)}
                            placeholder="e.g. 74.0, 78.5, 81.2, 91.0, 85.0"
                            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 font-mono h-20 resize-none leading-normal"
                          />
                        ) : (
                          <input
                            type={param.type === 'float' || param.type === 'int' ? 'number' : 'text'}
                            step="any"
                            value={argumentsData[name] !== undefined ? argumentsData[name] : ''}
                            onChange={(e) => handleInputChange(name, e.target.value)}
                            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 font-mono"
                          />
                        )}
                        <p className="text-[10px] text-slate-500 font-sans italic">
                          {param.description}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="border-t border-slate-800/40 pt-4 mt-6">
                <button
                  type="submit"
                  disabled={isExecuting || !selectedTool}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-850 disabled:text-slate-600 text-white text-sm font-semibold rounded-lg shadow-lg hover:shadow-sky-900/10 transition-all font-sans"
                >
                  {isExecuting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Executing...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Run Tool Function
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Results Panel */}
        <div className="lg:col-span-7 bg-slate-900/30 border border-slate-800/80 rounded-xl p-5 shadow-lg flex flex-col justify-between h-full">
          <div className="flex items-center justify-between border-b border-slate-800/60 pb-3 mb-4">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-sky-400" />
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Evaluation Output
              </h2>
            </div>
            {executionResult && (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                executionResult.status === 'success' ? 'bg-emerald-950 text-emerald-400 border border-emerald-900' : 'bg-red-950 text-red-400 border border-red-900'
              }`}>
                {executionResult.status.toUpperCase()}
              </span>
            )}
          </div>

          <div className="flex-1 flex flex-col justify-center min-h-[300px]">
            {!executionResult && !isExecuting && (
              <div className="text-center py-20">
                <Activity className="w-12 h-12 text-slate-700 mx-auto mb-4 animate-pulse" />
                <h3 className="text-sm font-semibold text-slate-400">No Execution Yet</h3>
                <p className="text-xs text-slate-500 max-w-xs mx-auto mt-1 leading-normal font-sans">
                  Select a registered tool function from the runner menu, configure parameters, and execute to see sandboxed results.
                </p>
              </div>
            )}

            {isExecuting && (
              <div className="text-center py-20">
                <RefreshCw className="w-8 h-8 text-sky-500 animate-spin mx-auto mb-4" />
                <h3 className="text-sm font-semibold text-slate-300 font-mono">Running computation...</h3>
                <p className="text-xs text-slate-500 mt-1 font-sans">
                  Verifying constraints and registering operational log entry.
                </p>
              </div>
            )}

            {executionResult && (
              <div className="space-y-4 h-full flex flex-col justify-between">
                {executionResult.status === 'success' ? (
                  <div className="space-y-4">
                    {/* Summary Statement */}
                    {executionResult.outputs.summary && (
                      <div className="flex gap-2.5 items-start bg-slate-950/80 border border-slate-800 rounded-lg p-3.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        <div className="text-xs text-slate-200 leading-relaxed font-mono">
                          {executionResult.outputs.summary}
                        </div>
                      </div>
                    )}

                    {/* Specific Tool Visual Renderings */}
                    {executionResult.tool_name === 'compare_reading_against_sop_limit' && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className={`border rounded-lg p-3 text-center ${
                          executionResult.outputs.is_exceeded ? 'bg-red-950/20 border-red-900/60' : 'bg-slate-950/50 border-slate-800'
                        }`}>
                          <span className="block text-[10px] text-slate-500 font-bold uppercase tracking-wider font-mono">SOP Status</span>
                          <span className={`text-sm font-bold block mt-1 ${
                            executionResult.outputs.is_exceeded ? 'text-red-400' : 'text-emerald-400'
                          }`}>
                            {executionResult.outputs.is_exceeded ? 'EXCEEDANCE DETECTED' : 'NORMAL RANGE'}
                          </span>
                        </div>
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-3 text-center">
                          <span className="block text-[10px] text-slate-500 font-bold uppercase tracking-wider font-mono">Absolute Delta</span>
                          <span className="text-sm font-bold text-slate-200 block mt-1 font-mono">
                            {executionResult.outputs.difference}
                          </span>
                        </div>
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-3 text-center">
                          <span className="block text-[10px] text-slate-500 font-bold uppercase tracking-wider font-mono">Deviation %</span>
                          <span className="text-sm font-bold text-slate-200 block mt-1 font-mono">
                            {executionResult.outputs.percentage_exceeded}%
                          </span>
                        </div>
                      </div>
                    )}

                    {executionResult.tool_name === 'compute_variance_across_readings' && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-2.5 text-center">
                          <span className="block text-[9px] text-slate-500 font-bold uppercase tracking-wider font-mono">Sample Size</span>
                          <span className="text-xs font-bold text-slate-200 block mt-0.5 font-mono">{executionResult.outputs.count}</span>
                        </div>
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-2.5 text-center">
                          <span className="block text-[9px] text-slate-500 font-bold uppercase tracking-wider font-mono">Mean Average</span>
                          <span className="text-xs font-bold text-slate-200 block mt-0.5 font-mono">{executionResult.outputs.mean}</span>
                        </div>
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-2.5 text-center">
                          <span className="block text-[9px] text-slate-500 font-bold uppercase tracking-wider font-mono">Variance</span>
                          <span className="text-xs font-bold text-slate-200 block mt-0.5 font-mono">{executionResult.outputs.variance}</span>
                        </div>
                        <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-2.5 text-center">
                          <span className="block text-[9px] text-slate-500 font-bold uppercase tracking-wider font-mono">Std Dev (σ)</span>
                          <span className="text-xs font-bold text-slate-200 block mt-0.5 font-mono">{executionResult.outputs.std_dev}</span>
                        </div>
                      </div>
                    )}

                    {executionResult.tool_name === 'convert_units' && (
                      <div className="bg-slate-950/50 border border-slate-800 rounded-lg p-4 text-center max-w-sm mx-auto">
                        <span className="block text-[10px] text-slate-500 font-bold uppercase tracking-wider font-mono">Conversion Outcome</span>
                        <div className="text-2xl font-bold text-sky-400 mt-2 font-mono">
                          {executionResult.outputs.converted_value}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex gap-2.5 items-start bg-red-950/20 border border-red-900 rounded-lg p-3.5">
                    <XCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                    <div className="text-xs text-red-400 leading-normal font-mono">
                      <strong>Tool execution failed:</strong>
                      <p className="mt-1 font-sans text-slate-300">{executionResult.error}</p>
                    </div>
                  </div>
                )}

                {/* Micro Metrics Badges */}
                <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-500 bg-slate-950/30 p-2 rounded-lg border border-slate-850 mt-4">
                  <div className="flex items-center gap-1">
                    <Cpu className="w-3 h-3 text-slate-600" />
                    <span>Duration:</span>
                    <span className="text-slate-300 font-bold">{executionResult.duration_ms} ms</span>
                  </div>
                  <span className="text-slate-700">|</span>
                  <div className="flex items-center gap-1">
                    <Layers className="w-3 h-3 text-slate-600" />
                    <span>Log ID:</span>
                    <span className="text-slate-400 select-all">{executionResult.execution_log_id}</span>
                  </div>
                </div>

                {/* Collapsible raw json */}
                <div className="mt-2 border-t border-slate-800/40 pt-3">
                  <button
                    onClick={() => setRawJsonVisible(!rawJsonVisible)}
                    className="flex items-center gap-1 text-[10px] uppercase font-bold tracking-wider text-slate-500 hover:text-slate-400 font-mono transition-colors"
                  >
                    {rawJsonVisible ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    Raw Output Payload
                  </button>
                  {rawJsonVisible && (
                    <pre className="mt-2 text-[11px] font-mono bg-slate-950/90 border border-slate-850 rounded-lg p-3 overflow-x-auto text-slate-400 max-h-48 leading-relaxed">
                      {JSON.stringify(executionResult, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Execution Logs Table */}
      <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5 shadow-lg">
        <div className="flex items-center justify-between border-b border-slate-800/60 pb-3 mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Tool Audit Logs History
            </h2>
          </div>
          <button 
            onClick={fetchLogs}
            disabled={isLoadingLogs}
            className="flex items-center gap-1 text-xs text-sky-500 hover:text-sky-400 font-medium transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingLogs ? 'animate-spin' : ''}`} />
            Refresh Logs
          </button>
        </div>

        {isLoadingLogs && executionLogs.length === 0 ? (
          <div className="text-center py-10 text-slate-600">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
            <p className="text-xs">Fetching execution logs...</p>
          </div>
        ) : executionLogs.length === 0 ? (
          <div className="text-center py-10 text-slate-600">
            <Activity className="w-8 h-8 mx-auto mb-2 text-slate-700" />
            <p className="text-xs">No tool executions logged yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800/80 text-[10px] font-bold font-mono text-slate-500 uppercase tracking-wider">
                  <th className="py-2.5 px-3">Time</th>
                  <th className="py-2.5 px-3">Tool Name</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Duration</th>
                  <th className="py-2.5 px-3">Arguments Sample</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850/40 text-xs">
                {executionLogs.map(log => (
                  <React.Fragment key={log.id}>
                    <tr className="hover:bg-slate-950/20 text-slate-300 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-slate-400">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="py-2.5 px-3 font-mono font-semibold text-slate-200">
                        {log.tool_name}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${
                          log.status === 'success' ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-900/40' : 'bg-red-950/40 text-red-400 border border-red-900/40'
                        }`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-400">
                        {log.duration_ms} ms
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-500 truncate max-w-xs">
                        {JSON.stringify(log.inputs)}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => toggleExpandLog(log.id)}
                          className="text-[10px] font-mono text-sky-500 hover:text-sky-400 hover:underline font-bold"
                        >
                          {expandedLogId === log.id ? 'Collapse' : 'Inspect'}
                        </button>
                      </td>
                    </tr>
                    {expandedLogId === log.id && (
                      <tr>
                        <td colSpan="6" className="bg-slate-950/60 p-4 border-t border-b border-slate-850/60">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono mb-2">Input Arguments</h4>
                              <pre className="text-[11px] font-mono bg-slate-950 border border-slate-900 rounded p-2.5 overflow-x-auto text-slate-400 select-all max-h-32">
                                {JSON.stringify(log.inputs, null, 2)}
                              </pre>
                            </div>
                            <div>
                              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono mb-2">
                                {log.status === 'success' ? 'Outputs' : 'Error details'}
                              </h4>
                              {log.status === 'success' ? (
                                <pre className="text-[11px] font-mono bg-slate-950 border border-slate-900 rounded p-2.5 overflow-x-auto text-slate-400 select-all max-h-32">
                                  {JSON.stringify(log.outputs, null, 2)}
                                </pre>
                              ) : (
                                <div className="text-[11px] font-mono bg-red-950/10 border border-red-950/60 text-red-400 rounded p-2.5 leading-relaxed">
                                  {log.error}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
