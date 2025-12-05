import { useState, useEffect } from 'react';
import { Search, Loader, CheckCircle, XCircle, AlertCircle, Trash2, Play, Clock, ChevronDown, ChevronUp, Globe, Zap, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function Discovery() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Form state
  const [keywords, setKeywords] = useState([]);
  const [keywordInput, setKeywordInput] = useState('');
  const [searchEngines, setSearchEngines] = useState(['google']);
  const [region, setRegion] = useState('US');
  const [maxResults, setMaxResults] = useState(100);
  const [depth, setDepth] = useState('fast');
  const [proxyMode, setProxyMode] = useState('none');

  // Advanced Query Generation Options
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxQueries, setMaxQueries] = useState(400);
  const [negativeKeywords, setNegativeKeywords] = useState([]);
  const [negativeKeywordInput, setNegativeKeywordInput] = useState('');
  const [geoRegions, setGeoRegions] = useState([]);
  const [geoRegionInput, setGeoRegionInput] = useState('');
  const [geoTlds, setGeoTlds] = useState([]);
  const [geoTldInput, setGeoTldInput] = useState('');

  // Job state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [pollingJobId, setPollingJobId] = useState(null);
  const [expandedJobId, setExpandedJobId] = useState(null);
  const [showRevetModal, setShowRevetModal] = useState(false);
  const [revetData, setRevetData] = useState(null);

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, navigate]);

  // Load recent jobs on mount
  useEffect(() => {
    loadRecentJobs();
    const interval = setInterval(loadRecentJobs, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  // Poll for specific job updates
  useEffect(() => {
    if (pollingJobId) {
      const interval = setInterval(() => pollJobStatus(pollingJobId), 2000);
      return () => clearInterval(interval);
    }
  }, [pollingJobId]);

  const loadRecentJobs = async () => {
    try {
      const response = await api.discovery.listJobs({ skip: 0, limit: 10 });
      setRecentJobs(response.data.jobs || []);
    } catch (err) {
      console.error('Failed to load recent jobs:', err);
    }
  };

  const pollJobStatus = async (jobId) => {
    try {
      const response = await api.jobs.get(jobId);
      const job = response.data;

      // Update job in recent jobs list
      setRecentJobs(prev =>
        prev.map(j => j.id === jobId ? job : j)
      );

      // Stop polling if job is complete
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        setPollingJobId(null);
        setLoading(false);
      }
    } catch (err) {
      console.error('Failed to poll job status:', err);
    }
  };

  const handleAddKeyword = () => {
    const trimmed = keywordInput.trim();
    if (trimmed && !keywords.includes(trimmed)) {
      setKeywords([...keywords, trimmed]);
      setKeywordInput('');
    }
  };

  const handleRemoveKeyword = (keyword) => {
    setKeywords(keywords.filter(k => k !== keyword));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddKeyword();
    }
  };

  const handleAddNegativeKeyword = () => {
    const trimmed = negativeKeywordInput.trim();
    if (trimmed && !negativeKeywords.includes(trimmed)) {
      setNegativeKeywords([...negativeKeywords, trimmed]);
      setNegativeKeywordInput('');
    }
  };

  const handleRemoveNegativeKeyword = (keyword) => {
    setNegativeKeywords(negativeKeywords.filter(k => k !== keyword));
  };

  const handleAddGeoRegion = () => {
    const trimmed = geoRegionInput.trim();
    if (trimmed && !geoRegions.includes(trimmed)) {
      setGeoRegions([...geoRegions, trimmed]);
      setGeoRegionInput('');
    }
  };

  const handleRemoveGeoRegion = (region) => {
    setGeoRegions(geoRegions.filter(r => r !== region));
  };

  const handleAddGeoTld = () => {
    const trimmed = geoTldInput.trim();
    if (trimmed && !geoTlds.includes(trimmed)) {
      setGeoTlds([...geoTlds, trimmed]);
      setGeoTldInput('');
    }
  };

  const handleRemoveGeoTld = (tld) => {
    setGeoTlds(geoTlds.filter(t => t !== tld));
  };

  const handleEngineToggle = (engine) => {
    if (searchEngines.includes(engine)) {
      if (searchEngines.length > 1) {
        setSearchEngines(searchEngines.filter(e => e !== engine));
      }
    } else {
      setSearchEngines([...searchEngines, engine]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (keywords.length === 0) {
      setError('Please add at least one keyword');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const requestData = {
        keywords,
        search_engines: searchEngines,
        region,
        max_results: maxResults,
        depth,
        proxy_mode: proxyMode,
      };

      // Add advanced query generation options if provided
      if (maxQueries !== 400) requestData.max_queries = maxQueries;
      if (negativeKeywords.length > 0) requestData.negative_keywords = negativeKeywords;
      if (geoRegions.length > 0) requestData.geo_regions = geoRegions;
      if (geoTlds.length > 0) requestData.geo_tlds = geoTlds;

      const response = await api.discovery.start(requestData);

      const jobId = response.data.job_id;
      setPollingJobId(jobId);

      // Reload jobs to show the new one
      await loadRecentJobs();

    } catch (error) {
      console.error('Discovery failed:', error);
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      setError('Failed to start discovery: ' + errorMsg);
      setLoading(false);
    }
  };

  const handleCancelJob = async (jobId) => {
    try {
      await api.jobs.cancel(jobId);
      await loadRecentJobs();
    } catch (err) {
      console.error('Failed to cancel job:', err);
      setError('Failed to cancel job: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteJob = async (jobId) => {
    try {
      await api.jobs.delete(jobId);
      setRecentJobs(prev => prev.filter(j => j.id !== jobId));
    } catch (err) {
      console.error('Failed to delete job:', err);
      setError('Failed to delete job: ' + (err.response?.data?.detail || err.message));
    }
  };

  const openRevetModal = (jobId, rejectedDomains) => {
    if (rejectedDomains.length === 0) {
      setError('No rejected domains to re-vet');
      return;
    }
    setRevetData({ jobId, rejectedDomains });
    setShowRevetModal(true);
  };

  const handleRevetDomains = async () => {
    if (!revetData) return;

    const { jobId, rejectedDomains } = revetData;

    try {
      setLoading(true);
      setShowRevetModal(false);
      const domains = rejectedDomains.map(d => d.domain);

      const response = await api.discovery.revet({
        domains: domains,
        job_id: jobId,
        min_ecommerce_keywords: 1,
        min_relevance_score: 0.2
      });

      const newJobId = response.data.job_id;
      setPollingJobId(newJobId);
      setError(null);

      // Reload jobs to show the new one
      await loadRecentJobs();

      setLoading(false);
      setRevetData(null);

    } catch (err) {
      console.error('Failed to start re-vetting:', err);
      setError('Failed to start re-vetting: ' + (err.response?.data?.detail || err.message));
      setLoading(false);
      setRevetData(null);
    }
  };


  const getStatusIcon = (status) => {
    switch (status) {
      case 'queued':
        return <Clock className="w-5 h-5 text-yellow-500" />;
      case 'running':
        return <Loader className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />;
      case 'cancelled':
        return <XCircle className="w-5 h-5 text-gray-500" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-500" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'queued':
        return 'bg-yellow-100 text-yellow-800';
      case 'running':
        return 'bg-blue-100 text-blue-800';
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'cancelled':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const toggleJobDetails = (jobId) => {
    setExpandedJobId(expandedJobId === jobId ? null : jobId);
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'N/A';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
  };

  const renderJobDetails = (job) => {
    if (expandedJobId !== job.id) return null;

    const result = job.result || {};
    const config = job.config || {};
    const execSummary = result.execution_summary || {};
    const queryExecutions = result.query_executions || [];

    return (
      <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200 space-y-4">
        {/* Summary Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="text-xs text-gray-500 mb-1">Total Results</div>
            <div className="text-2xl font-bold text-gray-900">{result.total_results || 0}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="text-xs text-gray-500 mb-1">Unique Domains</div>
            <div className="text-2xl font-bold text-blue-600">{result.unique_domains || 0}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="text-xs text-gray-500 mb-1">Approved</div>
            <div className="text-2xl font-bold text-green-600">{result.approved_domains || 0}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="text-xs text-gray-500 mb-1">Saved</div>
            <div className="text-2xl font-bold text-purple-600">{result.saved_domains || 0}</div>
          </div>
        </div>

        {/* Execution Details */}
        <div className="bg-white p-3 rounded-lg border border-gray-200">
          <h4 className="text-sm font-semibold text-gray-900 mb-2">Execution Details</h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div>
              <span className="text-gray-500">Region:</span>
              <span className="ml-2 font-medium">{result.region || config.region || 'N/A'}</span>
            </div>
            <div>
              <span className="text-gray-500">Duration:</span>
              <span className="ml-2 font-medium">{formatDuration(execSummary.total_duration_seconds)}</span>
            </div>
            <div>
              <span className="text-gray-500">Base Keywords:</span>
              <span className="ml-2 font-medium">{execSummary.base_keywords_count || config.keywords?.length || 0}</span>
            </div>
            <div>
              <span className="text-gray-500">Expanded Queries:</span>
              <span className="ml-2 font-medium text-blue-600 font-bold">{execSummary.expanded_queries_count || execSummary.total_queries || 0}</span>
            </div>
            <div>
              <span className="text-gray-500">Queries Executed:</span>
              <span className="ml-2 font-medium">{execSummary.total_queries || 0}</span>
            </div>
            <div>
              <span className="text-gray-500">Engines:</span>
              <span className="ml-2 font-medium">{result.search_engines?.join(', ') || 'N/A'}</span>
            </div>
            <div>
              <span className="text-gray-500">Started:</span>
              <span className="ml-2 font-medium">
                {execSummary.started_at ? new Date(execSummary.started_at + 'Z').toLocaleTimeString() : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Completed:</span>
              <span className="ml-2 font-medium">
                {execSummary.completed_at ? new Date(execSummary.completed_at + 'Z').toLocaleTimeString() : 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* Query Breakdown */}
        {queryExecutions.length > 0 && (
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-900 mb-3">Query Breakdown</h4>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {queryExecutions.map((query, idx) => (
                <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded border border-gray-100">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Globe className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <span className="text-sm font-medium text-gray-900 truncate">{query.query}</span>
                      <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                        {query.engine}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 ml-4">
                    <div className="text-right">
                      <div className="text-sm font-semibold text-gray-900">{query.results_count}</div>
                      <div className="text-xs text-gray-500">results</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-gray-900">{formatDuration(query.duration_seconds)}</div>
                      <div className="text-xs text-gray-500">duration</div>
                    </div>
                    {query.success ? (
                      <CheckCircle className="w-5 h-5 text-green-500" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-500" title={query.error} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Vetting Stats */}
        {result.vetted > 0 && (
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-900 mb-2">Vetting Results</h4>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <span className="text-gray-500">Vetted:</span>
                <span className="ml-2 font-medium">{result.vetted || 0}</span>
              </div>
              <div>
                <span className="text-gray-500">Approved:</span>
                <span className="ml-2 font-medium text-green-600">{result.approved_domains || 0}</span>
              </div>
              <div>
                <span className="text-gray-500">Rejected:</span>
                <span className="ml-2 font-medium text-red-600">{result.rejected_domains || 0}</span>
              </div>
            </div>
          </div>
        )}

        {/* Detailed Vetting List */}
        {result.vetting_details && result.vetting_details.length > 0 && (
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-gray-900">All Vetted Domains</h4>

              {/* Action buttons */}
              <div className="flex gap-2">
                {result.vetting_details.filter(v => v.status === 'rejected').length > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      const rejected = result.vetting_details.filter(v => v.status === 'rejected');
                      openRevetModal(job.id, rejected);
                    }}
                    className="flex items-center gap-1 px-3 py-1.5 bg-orange-600 text-white text-xs font-medium rounded hover:bg-orange-700 transition-colors"
                    title="Re-vet all rejected domains"
                    disabled={loading}
                  >
                    <RefreshCw className="w-3 h-3" />
                    Re-vet Rejected ({result.vetting_details.filter(v => v.status === 'rejected').length})
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {/* Approved Domains First */}
              {result.vetting_details
                .filter(v => v.status === 'approved')
                .map((vet, idx) => (
                  <div key={`approved-${idx}`} className="flex items-start justify-between p-3 bg-green-50 rounded border border-green-200">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <CheckCircle className="w-4 h-4 text-green-600 flex-shrink-0" />
                        <a
                          href={`https://${vet.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-gray-900 hover:text-blue-600 truncate"
                        >
                          {vet.domain}
                        </a>
                        <span className="px-2 py-0.5 bg-green-600 text-white text-xs rounded-full">
                          APPROVED
                        </span>
                      </div>
                      <div className="text-xs text-green-700 mb-1">{vet.reason}</div>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <span className="text-green-600">
                          Relevance: {(vet.relevance_score * 100).toFixed(0)}%
                        </span>
                        {vet.ecommerce_keywords && vet.ecommerce_keywords.length > 0 && (
                          <span className="text-green-600">
                            E-commerce: {vet.ecommerce_keywords.join(', ')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

              {/* Rejected Domains */}
              {result.vetting_details
                .filter(v => v.status === 'rejected')
                .map((vet, idx) => (
                  <div key={`rejected-${idx}`} className="flex items-start justify-between p-3 bg-red-50 rounded border border-red-200">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <XCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                        <a
                          href={`https://${vet.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-gray-900 hover:text-blue-600 truncate"
                        >
                          {vet.domain}
                        </a>
                        <span className="px-2 py-0.5 bg-red-600 text-white text-xs rounded-full">
                          REJECTED
                        </span>
                      </div>
                      <div className="text-xs text-red-700 font-medium mb-1">
                        {vet.reason}
                      </div>
                      <div className="flex flex-wrap gap-2 text-xs">
                        {vet.relevance_score !== undefined && (
                          <span className="text-red-600">
                            Relevance: {(vet.relevance_score * 100).toFixed(0)}%
                          </span>
                        )}
                        {vet.ecommerce_keywords && vet.ecommerce_keywords.length > 0 && (
                          <span className="text-red-600">
                            E-commerce keywords: {vet.ecommerce_keywords.length}
                          </span>
                        )}
                        {!vet.has_ecommerce && (
                          <span className="text-red-600">
                            ❌ No e-commerce
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Company Discovery</h1>
        <p className="mt-1 text-sm text-gray-500">
          Search for B2B companies using multiple search engines and keywords
        </p>
      </div>

      {/* Search Form */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Keywords */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Search Keywords
            </label>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder='e.g., "B2B SaaS companies California"'
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={loading}
              />
              <button
                type="button"
                onClick={handleAddKeyword}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                disabled={loading || !keywordInput.trim()}
              >
                Add
              </button>
            </div>
            {keywords.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {keywords.map((keyword) => (
                  <span
                    key={keyword}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm"
                  >
                    {keyword}
                    <button
                      type="button"
                      onClick={() => handleRemoveKeyword(keyword)}
                      className="hover:text-blue-900"
                      disabled={loading}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Search Engines */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Search Engines
            </label>
            <div className="flex gap-3">
              {['google', 'bing'].map((engine) => (
                <label key={engine} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={searchEngines.includes(engine)}
                    onChange={() => handleEngineToggle(engine)}
                    className="rounded text-blue-600 focus:ring-2 focus:ring-blue-500"
                    disabled={loading}
                  />
                  <span className="text-sm text-gray-700 capitalize">{engine}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Region */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Region
              </label>
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={loading}
              >
                <option value="US">United States</option>
                <option value="UK">United Kingdom</option>
                <option value="CA">Canada</option>
                <option value="AU">Australia</option>
              </select>
            </div>

            {/* Depth */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Search Depth
              </label>
              <select
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={loading}
              >
                <option value="fast">Fast (~50 results)</option>
                <option value="standard">Standard (~100 results)</option>
                <option value="deep">Deep (~200+ results)</option>
              </select>
            </div>

            {/* Max Results */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Max Results
              </label>
              <input
                type="number"
                value={maxResults}
                onChange={(e) => setMaxResults(parseInt(e.target.value))}
                min="10"
                max="1000"
                step="10"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={loading}
              />
            </div>
          </div>

          {/* Advanced Query Generation Settings */}
          <div className="border-t border-gray-200 pt-4">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900 mb-3"
            >
              {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Advanced Query Generation
              <span className="text-xs text-gray-500">(optional)</span>
            </button>

            {showAdvanced && (
              <div className="space-y-4 bg-gray-50 rounded-lg p-4 border border-gray-200">
                {/* Max Queries */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Max Queries
                    <span className="ml-2 text-xs text-gray-500">AI will generate up to this many search queries</span>
                  </label>
                  <input
                    type="number"
                    value={maxQueries}
                    onChange={(e) => setMaxQueries(parseInt(e.target.value))}
                    min="50"
                    max="1000"
                    step="50"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    disabled={loading}
                  />
                </div>

                {/* Negative Keywords */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Negative Keywords
                    <span className="ml-2 text-xs text-gray-500">Exclude sites (e.g., amazon, ebay)</span>
                  </label>
                  <div className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={negativeKeywordInput}
                      onChange={(e) => setNegativeKeywordInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddNegativeKeyword())}
                      placeholder="e.g., amazon"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={handleAddNegativeKeyword}
                      className="px-3 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 text-sm"
                      disabled={loading || !negativeKeywordInput.trim()}
                    >
                      Add
                    </button>
                  </div>
                  {negativeKeywords.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {negativeKeywords.map((keyword) => (
                        <span
                          key={keyword}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 text-red-800 rounded text-xs"
                        >
                          -{keyword}
                          <button
                            type="button"
                            onClick={() => handleRemoveNegativeKeyword(keyword)}
                            className="hover:text-red-900"
                            disabled={loading}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Geo Regions */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Geographic Regions
                    <span className="ml-2 text-xs text-gray-500">Target specific regions (e.g., us, uk, ca)</span>
                  </label>
                  <div className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={geoRegionInput}
                      onChange={(e) => setGeoRegionInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddGeoRegion())}
                      placeholder="e.g., us"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={handleAddGeoRegion}
                      className="px-3 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 text-sm"
                      disabled={loading || !geoRegionInput.trim()}
                    >
                      Add
                    </button>
                  </div>
                  {geoRegions.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {geoRegions.map((region) => (
                        <span
                          key={region}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-800 rounded text-xs"
                        >
                          {region}
                          <button
                            type="button"
                            onClick={() => handleRemoveGeoRegion(region)}
                            className="hover:text-green-900"
                            disabled={loading}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Geo TLDs */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Geographic TLDs
                    <span className="ml-2 text-xs text-gray-500">Target specific TLDs (e.g., .co.uk, .de)</span>
                  </label>
                  <div className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={geoTldInput}
                      onChange={(e) => setGeoTldInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddGeoTld())}
                      placeholder="e.g., .co.uk"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={handleAddGeoTld}
                      className="px-3 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 text-sm"
                      disabled={loading || !geoTldInput.trim()}
                    >
                      Add
                    </button>
                  </div>
                  {geoTlds.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {geoTlds.map((tld) => (
                        <span
                          key={tld}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs"
                        >
                          {tld}
                          <button
                            type="button"
                            onClick={() => handleRemoveGeoTld(tld)}
                            className="hover:text-purple-900"
                            disabled={loading}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="text-xs text-gray-600 bg-blue-50 rounded p-3 border border-blue-100">
                  <strong>💡 Tip:</strong> These settings use AI to generate hundreds of targeted search queries from your keywords.
                  Negative keywords help filter out unwanted sites like marketplaces. Geographic targeting focuses on specific regions/TLDs.
                </div>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || keywords.length === 0}
            className="w-full flex items-center justify-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <>
                <Loader className="w-5 h-5 mr-2 animate-spin" />
                Starting Discovery...
              </>
            ) : (
              <>
                <Search className="w-5 h-5 mr-2" />
                Start Discovery
              </>
            )}
          </button>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-start">
            <XCircle className="w-5 h-5 text-red-600 mr-3 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">Error</p>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Recent Jobs */}
      {recentJobs.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Discovery Jobs
          </h3>
          <div className="space-y-3">
            {recentJobs.map((job) => (
              <div key={job.id}>
                <div
                  className={`flex items-center justify-between p-4 border ${
                    expandedJobId === job.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
                  } rounded-lg transition-colors cursor-pointer`}
                  onClick={() => toggleJobDetails(job.id)}
                >
                  <div className="flex items-center space-x-4 flex-1">
                    {getStatusIcon(job.status)}

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {job.config?.keywords?.join(', ') || 'Discovery Job'}
                        </p>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(job.status)}`}>
                          {job.status}
                        </span>
                      </div>

                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                        <span>{new Date(job.created_at).toLocaleString()}</span>
                        {job.status === 'running' && job.progress > 0 && (
                          <span className="text-blue-600 font-medium">{job.progress}% complete</span>
                        )}
                        {job.status === 'completed' && job.result && (
                          <>
                            <span className="text-green-600 font-medium">
                              {job.result.saved_domains || 0} saved
                            </span>
                            {job.result.execution_summary?.total_duration_seconds && (
                              <span className="text-gray-500">
                                • {formatDuration(job.result.execution_summary.total_duration_seconds)}
                              </span>
                            )}
                          </>
                        )}
                        {job.error && (
                          <span className="text-red-600 font-medium">
                            Error: {job.error}
                          </span>
                        )}
                      </div>

                      {/* Progress Bar */}
                      {job.status === 'running' && (
                        <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${job.progress || 0}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 ml-4">
                    {job.status === 'running' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCancelJob(job.id);
                        }}
                        className="px-3 py-1 text-sm text-red-600 hover:bg-red-50 rounded transition-colors"
                        title="Cancel job"
                      >
                        Cancel
                      </button>
                    )}
                    {['completed', 'failed', 'cancelled'].includes(job.status) && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteJob(job.id);
                        }}
                        className="text-gray-400 hover:text-red-600 transition-colors"
                        title="Delete job"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {job.status === 'completed' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleJobDetails(job.id);
                        }}
                        className="text-blue-600 hover:text-blue-700 transition-colors"
                        title={expandedJobId === job.id ? "Hide details" : "Show details"}
                      >
                        {expandedJobId === job.id ? (
                          <ChevronUp className="w-5 h-5" />
                        ) : (
                          <ChevronDown className="w-5 h-5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
                {renderJobDetails(job)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Help Text */}
      <div className="bg-blue-50 rounded-lg border border-blue-200 p-6">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Tips for Better Results</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Be specific with your search keywords (industry, location, company size)</li>
          <li>• Use multiple keywords for better coverage</li>
          <li>• Include keywords like "ecommerce", "online store", "B2B", "SaaS", etc.</li>
          <li>• Jobs run in the background - you can navigate away and come back</li>
          <li>• Google typically provides the best results for B2B discovery</li>
        </ul>
      </div>

      {/* Re-vet Confirmation Modal */}
      {showRevetModal && revetData && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-orange-600 to-orange-700 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <RefreshCw className="w-6 h-6 text-white" />
                  <h3 className="text-xl font-bold text-white">Re-vet Rejected Domains</h3>
                </div>
                <button
                  onClick={() => setShowRevetModal(false)}
                  className="text-white hover:text-orange-100 transition-colors"
                >
                  <XCircle className="w-6 h-6" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
              <div className="mb-4">
                <p className="text-gray-700 mb-2">
                  You're about to re-vet <span className="font-bold text-orange-600">{revetData.rejectedDomains.length}</span> rejected domains.
                </p>
                <p className="text-sm text-gray-600 mb-4">
                  This will retry fetching and vetting these domains. Domains that were rejected due to temporary fetch errors may pass this time.
                </p>
              </div>

              {/* Domain List Preview */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 mb-4">
                <h4 className="text-sm font-semibold text-gray-900 mb-2">
                  Domains to re-vet ({revetData.rejectedDomains.length}):
                </h4>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {revetData.rejectedDomains.slice(0, 10).map((d, idx) => (
                    <div key={idx} className="text-sm text-gray-700 flex items-center gap-2">
                      <XCircle className="w-3 h-3 text-red-500 flex-shrink-0" />
                      <span className="font-medium">{d.domain}</span>
                      <span className="text-xs text-gray-500 truncate">
                        {d.reason?.substring(0, 50)}{d.reason?.length > 50 ? '...' : ''}
                      </span>
                    </div>
                  ))}
                  {revetData.rejectedDomains.length > 10 && (
                    <div className="text-sm text-gray-500 italic pt-2">
                      ... and {revetData.rejectedDomains.length - 10} more domains
                    </div>
                  )}
                </div>
              </div>

              {/* Info Box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-900">
                    <p className="font-semibold mb-1">What happens next:</p>
                    <ul className="list-disc list-inside space-y-1 text-blue-800">
                      <li>A background job will be created</li>
                      <li>Each domain will be fetched and re-vetted</li>
                      <li>Approved domains will be saved as companies</li>
                      <li>You can track progress in the job list</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="bg-gray-50 px-6 py-4 flex items-center justify-end gap-3 border-t border-gray-200">
              <button
                onClick={() => setShowRevetModal(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleRevetDomains}
                disabled={loading}
                className="px-6 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors font-medium flex items-center gap-2 disabled:bg-gray-400"
              >
                {loading ? (
                  <>
                    <Loader className="w-4 h-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    Start Re-vetting
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
