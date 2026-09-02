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
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/[.05] hover:bg-white/[.1] text-console-text text-xs font-mono rounded border border-console-line transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-console-amber"
          >
            <RefreshCw className="w-3.5 h-3.5 text-console-amber" />
            SYNC SYSTEM
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Configuration Panel */}
        <div className="lg:col-span-5 bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col h-full font-mono">
          <div className="flex items-center justify-between border-b border-console-lineSoft pb-3 mb-4">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-console-amber" />
              <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">
                TOOL RUNNER INTERFACE
              </h2>
            </div>
            <span className="text-[10px] text-console-muted uppercase">LOCAL · DETERMINISTIC</span>
          </div>

          {isLoadingTools ? (
            <div className="flex flex-col items-center justify-center py-20 text-console-muted">
              <RefreshCw className="w-6 h-6 animate-spin text-console-amber mb-2" />
              <p className="text-xs">Loading tools registry...</p>
            </div>
          ) : (
            <form onSubmit={handleExecute} className="space-y-4 flex-1 flex flex-col justify-between">
              <div className="space-y-4">
                {/* Selector */}
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-console-muted mb-1.5 font-mono">
                    SELECT TOOL FUNCTION
                  </label>
                  <select
                    value={selectedToolName}
                    onChange={handleToolChange}
                    className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-xs text-console-text focus:outline-none focus:border-console-amber font-mono"
                  >
                    {tools.map(t => (
                      <option key={t.name} value={t.name}>{t.name}</option>
                    ))}
                  </select>
                  {selectedTool && (
                    <p className="text-xs text-console-text2 mt-2 bg-console-inset p-2.5 rounded border border-console-line font-sans leading-relaxed">
                      {selectedTool.description}
                    </p>
                  )}
                </div>

                {/* Parameters Forms */}
                {selectedTool && (
                  <div className="space-y-3 border-t border-console-lineSoft pt-3">
                    <h3 className="text-[10px] uppercase tracking-[0.14em] text-console-muted font-mono">
                      INPUT ARGUMENTS
                    </h3>
                    
                    {Object.entries(selectedTool.parameters).map(([name, param]) => (
                      <div key={name} className="space-y-1">
                        <div className="flex justify-between items-baseline">
                          <label className="block text-xs font-semibold text-console-text font-sans">
                            {name}
                            {param.required && <span className="text-console-amber ml-0.5">*</span>}
                          </label>
                          <span className="text-[9px] font-mono text-console-muted uppercase bg-console-panelSolid px-1.5 py-0.5 rounded border border-console-lineSoft">
                            {param.type}
                          </span>
                        </div>

                        {param.options ? (
                          <select
                            value={argumentsData[name] || ''}
                            onChange={(e) => handleInputChange(name, e.target.value)}
                            className="w-full bg-console-inset border border-console-line rounded px-3 py-1.5 text-xs text-console-text focus:outline-none focus:border-console-amber font-mono"
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
                            className="w-full bg-console-inset border border-console-line rounded px-3 py-2 text-xs text-console-text focus:outline-none focus:border-console-amber font-mono h-20 resize-none leading-normal"
                          />
                        ) : (
                          <input
                            type={param.type === 'float' || param.type === 'int' ? 'number' : 'text'}
                            step="any"
                            value={argumentsData[name] !== undefined ? argumentsData[name] : ''}
                            onChange={(e) => handleInputChange(name, e.target.value)}
                            className="w-full bg-console-inset border border-console-line rounded px-3 py-1.5 text-xs text-console-text focus:outline-none focus:border-console-amber font-mono"
                          />
                        )}
                        <p className="text-[10px] text-console-muted font-sans italic">
                          {param.description}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="border-t border-console-lineSoft pt-3 mt-4">
                <button
                  type="submit"
                  disabled={isExecuting || !selectedTool}
                  className="w-full flex items-center justify-center gap-2 py-2 bg-console-amber text-[#0b1620] hover:brightness-105 disabled:opacity-40 text-xs font-semibold rounded shadow transition-all font-mono"
                >
                  {isExecuting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      EXECUTING...
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" />
                      RUN TOOL FUNCTION
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Results Panel */}
        <div className="lg:col-span-7 bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] flex flex-col justify-between h-full font-mono">
          <div className="flex items-center justify-between border-b border-console-lineSoft pb-3 mb-4">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-console-amber" />
              <h2 className="text-[11px] tracking-[0.14em] text-console-muted uppercase">
                EVALUATION OUTPUT
              </h2>
            </div>
            {executionResult && (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase tracking-wider ${
                executionResult.status === 'success' ? 'bg-console-greenSoft text-console-green border border-console-green/30' : 'bg-console-red/10 text-console-red border border-console-red/30'
              }`}>
                {executionResult.status}
              </span>
            )}
          </div>

          <div className="flex-1 flex flex-col justify-center min-h-[300px]">
            {!executionResult && !isExecuting && (
              <div className="text-center py-20">
                <Activity className="w-10 h-10 text-console-muted mx-auto mb-3" />
                <h3 className="text-xs font-bold text-console-text uppercase tracking-wider">No Execution Yet</h3>
                <p className="text-xs text-console-muted max-w-xs mx-auto mt-1 leading-normal font-sans">
                  Select a registered tool function from the runner menu, configure parameters, and execute to see sandboxed results.
                </p>
              </div>
            )}

            {isExecuting && (
              <div className="text-center py-20">
                <RefreshCw className="w-6 h-6 text-console-amber animate-spin mx-auto mb-3" />
                <h3 className="text-xs font-bold text-console-text uppercase tracking-wider">Running computation...</h3>
                <p className="text-xs text-console-muted mt-1 font-sans">
                  Verifying constraints and registering operational log entry.
                </p>
              </div>
            )}

            {executionResult && (
              <div className="space-y-4 h-full flex flex-col justify-between">
                {executionResult.status === 'success' ? (
                  <div className="space-y-3">
                    {/* Summary Statement */}
                    {executionResult.outputs.summary && (
                      <div className="flex gap-2.5 items-start bg-console-inset border border-console-line rounded p-3">
                        <CheckCircle2 className="w-4 h-4 text-console-green shrink-0 mt-0.5" />
                        <div className="text-xs text-console-text leading-relaxed font-mono">
                          {executionResult.outputs.summary}
                        </div>
                      </div>
                    )}

                    {/* Specific Tool Visual Renderings */}
                    {executionResult.tool_name === 'compare_reading_against_sop_limit' && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className={`border rounded p-3 text-center ${
                          executionResult.outputs.is_exceeded ? 'bg-console-amberSoft border-console-amber/40' : 'bg-console-inset border-console-line'
                        }`}>
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">SOP STATUS</span>
                          <span className={`text-xs font-bold block mt-1 ${
                            executionResult.outputs.is_exceeded ? 'text-console-amber' : 'text-console-green'
                          }`}>
                            {executionResult.outputs.is_exceeded ? '■ EXCEEDS' : '■ WITHIN LIMIT'}
                          </span>
                        </div>
                        <div className="bg-console-inset border border-console-line rounded p-3 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">ABSOLUTE DELTA</span>
                          <span className="text-xs font-bold text-console-text block mt-1 tabular-nums">
                            {executionResult.outputs.difference}
                          </span>
                        </div>
                        <div className="bg-console-inset border border-console-line rounded p-3 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">DEVIATION %</span>
                          <span className="text-xs font-bold text-console-text block mt-1 tabular-nums">
                            {executionResult.outputs.percentage_exceeded}%
                          </span>
                        </div>
                      </div>
                    )}

                    {executionResult.tool_name === 'compute_variance_across_readings' && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-console-inset border border-console-line rounded p-2.5 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">SAMPLE SIZE</span>
                          <span className="text-xs font-bold text-console-text block mt-0.5 tabular-nums">{executionResult.outputs.count}</span>
                        </div>
                        <div className="bg-console-inset border border-console-line rounded p-2.5 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">MEAN AVERAGE</span>
                          <span className="text-xs font-bold text-console-text block mt-0.5 tabular-nums">{executionResult.outputs.mean}</span>
                        </div>
                        <div className="bg-console-inset border border-console-line rounded p-2.5 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">VARIANCE</span>
                          <span className="text-xs font-bold text-console-text block mt-0.5 tabular-nums">{executionResult.outputs.variance}</span>
                        </div>
                        <div className="bg-console-inset border border-console-line rounded p-2.5 text-center">
                          <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">STD DEV (σ)</span>
                          <span className="text-xs font-bold text-console-text block mt-0.5 tabular-nums">{executionResult.outputs.std_dev}</span>
                        </div>
                      </div>
                    )}

                    {executionResult.tool_name === 'convert_units' && (
                      <div className="bg-console-inset border border-console-line rounded p-3.5 text-center max-w-sm mx-auto">
                        <span className="block text-[9px] text-console-muted font-bold uppercase tracking-wider">CONVERSION OUTCOME</span>
                        <div className="text-xl font-bold text-console-amber mt-1.5 tabular-nums">
                          {executionResult.outputs.converted_value}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex gap-2.5 items-start bg-console-red/10 border border-console-red/30 rounded p-3 text-console-red">
                    <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <div className="text-xs text-console-red leading-normal font-mono">
                      <strong className="uppercase">Tool execution failed:</strong>
                      <p className="mt-1 font-sans text-console-text2">{executionResult.error}</p>
                    </div>
                  </div>
                )}

                {/* Micro Metrics Badges */}
                <div className="flex flex-wrap gap-3 text-[10px] font-mono text-console-muted bg-console-inset p-2 rounded border border-console-line mt-3">
                  <div className="flex items-center gap-1">
                    <Cpu className="w-3 h-3 text-console-muted" />
                    <span>DURATION:</span>
                    <span className="text-console-text font-bold tabular-nums">{executionResult.duration_ms} ms</span>
                  </div>
                  <span className="text-console-line">|</span>
                  <div className="flex items-center gap-1">
                    <Layers className="w-3 h-3 text-console-muted" />
                    <span>LOG ID:</span>
                    <span className="text-console-text2 select-all tabular-nums">{executionResult.execution_log_id}</span>
                  </div>
                </div>

                {/* Collapsible raw json */}
                <div className="mt-2 border-t border-console-lineSoft pt-2">
                  <button
                    onClick={() => setRawJsonVisible(!rawJsonVisible)}
                    className="flex items-center gap-1 text-[10px] uppercase font-bold tracking-wider text-console-muted hover:text-console-text font-mono transition-colors"
                  >
                    {rawJsonVisible ? <ChevronUp className="w-3.5 h-3.5 text-console-amber" /> : <ChevronDown className="w-3.5 h-3.5 text-console-amber" />}
                    RAW OUTPUT PAYLOAD
                  </button>
                  {rawJsonVisible && (
                    <pre className="mt-2 text-[11px] font-mono bg-console-panelSolid border border-console-line rounded p-3 overflow-x-auto text-console-text2 max-h-48 leading-relaxed">
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
      <div className="bg-console-panel border border-console-line rounded-lg p-4 backdrop-blur-[2px] font-mono">
        <div className="flex items-center justify-between border-b border-console-lineSoft pb-3 mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-console-amber" />
            <h2 className="text-[11px] font-mono tracking-[0.14em] text-console-muted uppercase">
              TOOL AUDIT LOGS HISTORY
            </h2>
          </div>
          <button 
            onClick={fetchLogs}
            disabled={isLoadingLogs}
            className="flex items-center gap-1 text-xs text-console-amber hover:brightness-110 font-medium transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingLogs ? 'animate-spin' : ''}`} />
            REFRESH LOGS
          </button>
        </div>

        {isLoadingLogs && executionLogs.length === 0 ? (
          <div className="text-center py-10 text-console-muted">
            <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-console-amber" />
            <p className="text-xs">Fetching execution logs...</p>
          </div>
        ) : executionLogs.length === 0 ? (
          <div className="text-center py-10 text-console-muted">
            <Activity className="w-8 h-8 mx-auto mb-2 text-console-muted" />
            <p className="text-xs">No tool executions logged yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-console-line text-[10px] font-bold font-mono text-console-muted uppercase tracking-[0.14em] bg-console-panelSolid">
                  <th className="py-2.5 px-3">TIME</th>
                  <th className="py-2.5 px-3">TOOL NAME</th>
                  <th className="py-2.5 px-3">STATUS</th>
                  <th className="py-2.5 px-3">DURATION</th>
                  <th className="py-2.5 px-3">ARGUMENTS SAMPLE</th>
                  <th className="py-2.5 px-3 text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-console-lineSoft text-xs">
                {executionLogs.map(log => (
                  <React.Fragment key={log.id}>
                    <tr className="hover:bg-white/[.02] text-console-text transition-colors">
                      <td className="py-2.5 px-3 font-mono text-console-muted tabular-nums">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="py-2.5 px-3 font-mono font-semibold text-console-text">
                        {log.tool_name}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded font-mono uppercase tracking-wider ${
                          log.status === 'success' ? 'bg-console-greenSoft text-console-green border border-console-green/30' : 'bg-console-red/10 text-console-red border border-console-red/30'
                        }`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-console-muted tabular-nums">
                        {log.duration_ms} ms
                      </td>
                      <td className="py-2.5 px-3 font-mono text-console-muted truncate max-w-xs">
                        {JSON.stringify(log.inputs)}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => toggleExpandLog(log.id)}
                          className="text-[10px] font-mono text-console-amber hover:brightness-110 font-bold"
                        >
                          {expandedLogId === log.id ? 'COLLAPSE' : 'INSPECT'}
                        </button>
                      </td>
                    </tr>
                    {expandedLogId === log.id && (
                      <tr>
                        <td colSpan="6" className="bg-console-inset p-4 border-t border-b border-console-line font-mono">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <h4 className="text-[10px] font-bold text-console-muted uppercase tracking-[0.14em] mb-2">INPUT ARGUMENTS</h4>
                              <pre className="text-[11px] font-mono bg-console-panelSolid border border-console-line rounded p-2.5 overflow-x-auto text-console-text2 select-all max-h-32">
                                {JSON.stringify(log.inputs, null, 2)}
                              </pre>
                            </div>
                            <div>
                              <h4 className="text-[10px] font-bold text-console-muted uppercase tracking-[0.14em] mb-2">
                                {log.status === 'success' ? 'OUTPUTS' : 'ERROR DETAILS'}
                              </h4>
                              {log.status === 'success' ? (
                                <pre className="text-[11px] font-mono bg-console-panelSolid border border-console-line rounded p-2.5 overflow-x-auto text-console-text2 select-all max-h-32">
                                  {JSON.stringify(log.outputs, null, 2)}
                                </pre>
                              ) : (
                                <div className="text-[11px] font-mono bg-console-red/10 border border-console-red/30 text-console-red rounded p-2.5 leading-relaxed">
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
