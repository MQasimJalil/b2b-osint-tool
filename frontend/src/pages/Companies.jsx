import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Building2,
  Mail,
  Phone,
  Linkedin,
  ExternalLink,
  Loader,
  Plus,
  Globe,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  Trash2
} from 'lucide-react';
import { api } from '../api/client';
import { getBaseDomain } from '../utils/dateUtils';

export default function Companies() {
  const [companies, setCompanies] = useState([]);
  const [totalCompanies, setTotalCompanies] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize] = useState(20);
  const [selectedCompanies, setSelectedCompanies] = useState(new Set());
  const [crawlingCompanies, setCrawlingCompanies] = useState(new Set());
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newDomain, setNewDomain] = useState('');
  const [addingCompany, setAddingCompany] = useState(false);
  const [showCrawledOnly, setShowCrawledOnly] = useState(false); // New state for filter
  const pollingIntervalRef = useRef(null);
  const pollingStartTimeRef = useRef(null);
  const isPollingRef = useRef(false);
  const MAX_POLLING_DURATION = 10 * 60 * 1000; // 10 minutes max polling

  const loadCompanies = useCallback(async (isPolling = false) => {
    try {
      // Only show loading spinner if not polling (i.e., manual load)
      if (!isPolling) {
        setLoading(true);
      }
      const params = {
        skip: page * pageSize,
        limit: pageSize,
        crawled_status_filter: showCrawledOnly ? 'crawled_only' : 'all', // Add filter param
      };

      if (searchTerm.trim()) {
        params.search = searchTerm.trim();
      }

      // Use standard endpoint which returns {companies, total, skip, limit}
      const response = await api.companies.list(params);
      const responseData = response.data || {};
      const companiesData = responseData.companies || [];
      const total = responseData.total || 0;

      setCompanies(companiesData);
      setTotalCompanies(total);

      // Update crawlingCompanies set based on status
      const newCrawlingSet = new Set();
      companiesData.forEach(company => {
        if (company.crawl_status === 'crawling' || company.crawl_status === 'queued') {
          newCrawlingSet.add(company.id);
        }
      });

      // Only update if the set actually changed (prevent infinite loop)
      setCrawlingCompanies(prev => {
        // Check if sets are equal
        if (prev.size !== newCrawlingSet.size) {
          return newCrawlingSet;
        }
        // Check if all elements in prev are in newCrawlingSet
        for (let id of prev) {
          if (!newCrawlingSet.has(id)) {
            return newCrawlingSet;
          }
        }
        // Check if all elements in newCrawlingSet are in prev
        for (let id of newCrawlingSet) {
          if (!prev.has(id)) {
            return newCrawlingSet;
          }
        }
        return prev; // No change, keep previous set to avoid re-render
      });
    } catch (error) {
      console.error('Failed to load companies:', error);
    } finally {
      // Only hide loading spinner if we showed it (i.e., not during polling)
      if (!isPolling) {
        setLoading(false);
      }
    }
  }, [page, pageSize, searchTerm, showCrawledOnly]); // Add showCrawledOnly to dependencies

  // Load companies when page or search term changes
  useEffect(() => {
    loadCompanies();
  }, [loadCompanies]);

  // Manage polling based on crawlingCompanies
  useEffect(() => {
    // Clear any existing interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    // Only start polling if there are crawling companies
    if (crawlingCompanies.size > 0) {
      // Record when polling started
      if (!pollingStartTimeRef.current) {
        pollingStartTimeRef.current = Date.now();
      }

      pollingIntervalRef.current = setInterval(() => {
        // Check if polling has exceeded maximum duration
        if (Date.now() - pollingStartTimeRef.current > MAX_POLLING_DURATION) {
          console.warn('Polling timeout reached. Stopping polling for stale crawl statuses.');
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
          pollingStartTimeRef.current = null;
          // Force clear crawling companies to stop polling
          setCrawlingCompanies(new Set());
          return;
        }
        loadCompanies(true); // Pass true to indicate this is a polling update
      }, 3000); // Poll every 3 seconds
    } else {
      // Reset polling start time when no companies are crawling
      pollingStartTimeRef.current = null;
    }

    // Cleanup on unmount or when dependencies change
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [crawlingCompanies, loadCompanies, MAX_POLLING_DURATION]);

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
    setPage(0); // Reset to first page
  };

  const handleFilterChange = () => {
    setShowCrawledOnly(prev => !prev);
    setPage(0); // Reset to first page when filter changes
  };

  const toggleSelectCompany = (companyId, e) => {
    e.preventDefault();
    e.stopPropagation();
    const newSelected = new Set(selectedCompanies);
    if (newSelected.has(companyId)) {
      newSelected.delete(companyId);
    } else {
      newSelected.add(companyId);
    }
    setSelectedCompanies(newSelected);
  };

  const selectAll = (e) => {
    e.preventDefault();
    if (selectedCompanies.size === companies.length) {
      setSelectedCompanies(new Set());
    } else {
      setSelectedCompanies(new Set(companies.map(c => c.id)));
    }
  };

  const handleCrawlCompany = async (companyId, e) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      await api.companies.crawl(companyId);
      // Add to crawling set - polling will handle updates
      setCrawlingCompanies(prev => new Set([...prev, companyId]));
      // Don't reload immediately - let the polling mechanism handle it
    } catch (error) {
      console.error('Failed to start crawl:', error);
      alert('Failed to start crawl: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCrawlSelected = async () => {
    if (selectedCompanies.size === 0) {
      alert('Please select at least one company to crawl');
      return;
    }

    try {
      const companyIds = Array.from(selectedCompanies);
      await api.companies.crawlBatch(companyIds);
      // Add to crawling set - polling will handle updates
      setCrawlingCompanies(prev => new Set([...prev, ...companyIds]));
      setSelectedCompanies(new Set()); // Clear selection
      // Don't reload immediately - let the polling mechanism handle it
    } catch (error) {
      console.error('Failed to start batch crawl:', error);
      alert('Failed to start batch crawl: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getCrawlStatusBadge = (company) => {
    const status = company.crawl_status || 'not_crawled';

    switch (status) {
      case 'not_crawled':
        return (
          <div className="flex items-center text-xs text-gray-500">
            <Clock className="w-3 h-3 mr-1" />
            Not Crawled
          </div>
        );
      case 'queued':
        return (
          <div className="flex items-center text-xs text-blue-600">
            <Clock className="w-3 h-3 mr-1 animate-pulse" />
            Queued
          </div>
        );
      case 'crawling':
        return (
          <div className="flex items-center text-xs text-blue-600">
            <Loader className="w-3 h-3 mr-1 animate-spin" />
            Crawling in progress...
          </div>
        );
      case 'completed':
        return (
          <div className="flex items-center text-xs text-green-600">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            {company.crawled_pages || 0} pages
          </div>
        );
      case 'failed':
        return (
          <div className="flex items-center text-xs text-red-600">
            <XCircle className="w-3 h-3 mr-1" />
            Failed
          </div>
        );
      default:
        return null;
    }
  };

  const getCrawlButton = (company) => {
    const status = company.crawl_status || 'not_crawled';

    if (status === 'crawling' || status === 'queued') {
      return (
        <button
          disabled
          className="flex items-center px-3 py-1 text-xs bg-gray-100 text-gray-400 rounded cursor-not-allowed"
        >
          <Loader className="w-3 h-3 mr-1 animate-spin" />
          {status === 'queued' ? 'Queued' : 'Crawling'}
        </button>
      );
    }

    if (status === 'completed') {
      return (
        <button
          onClick={(e) => handleCrawlCompany(company.id, e)}
          className="flex items-center px-3 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100 transition-colors"
        >
          <Globe className="w-3 h-3 mr-1" />
          Re-crawl
        </button>
      );
    }

    return (
      <button
        onClick={(e) => handleCrawlCompany(company.id, e)}
        className="flex items-center px-3 py-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded hover:bg-blue-100 transition-colors"
      >
        <Globe className="w-3 h-3 mr-1" />
        Crawl
      </button>
    );
  };

  const getVettingBadge = (company) => {
    if (!company.vetting_status) return null;

    switch (company.vetting_status) {
      case 'approved':
        return (
          <div className="flex items-center px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
            ✓ Vetted {company.vetting_score ? `(${(company.vetting_score * 100).toFixed(0)}%)` : ''}
          </div>
        );
      case 'rejected':
        return (
          <div className="flex items-center px-2 py-1 bg-red-100 text-red-800 rounded-full text-xs font-medium">
            ✗ Rejected
          </div>
        );
      default:
        return null;
    }
  };

  // Add company handler
  const handleAddCompany = async (e) => {
    e.preventDefault();
    if (!newDomain.trim()) return;

    setAddingCompany(true);
    try {
      await api.companies.create({ domain: newDomain.trim() });
      setShowAddDialog(false);
      setNewDomain('');
      await loadCompanies(); // Reload companies list
      alert('Company added successfully!');
    } catch (error) {
      console.error('Error adding company:', error);
      alert(error.response?.data?.detail || 'Failed to add company');
    } finally {
      setAddingCompany(false);
    }
  };

  // Delete company handler
  const handleDeleteCompany = async (domain, e) => {
    e.preventDefault();
    e.stopPropagation();

    if (!confirm(`Are you sure you want to delete ${domain}? This will remove all associated data including products and crawled pages.`)) {
      return;
    }

    try {
      await api.companies.delete(domain);
      await loadCompanies(); // Reload companies list
      alert('Company deleted successfully!');
    } catch (error) {
      console.error('Error deleting company:', error);
      alert(error.response?.data?.detail || 'Failed to delete company');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Companies</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage and explore your company database
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowAddDialog(true)}
            className="flex items-center px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-colors"
          >
            <Plus className="w-5 h-5 mr-2" />
            Add Company
          </button>
          <Link
            to="/discovery"
            className="flex items-center px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-5 h-5 mr-2" />
            Discover More
          </Link>
        </div>
      </div>

      {/* Search Bar & Batch Actions */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search companies by name, domain, or description..."
            value={searchTerm}
            onChange={handleSearchChange}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* Filter for Crawled Companies */}
        <div className="flex items-center justify-end">
          <label className="flex items-center cursor-pointer">
            <div className="relative">
              <input
                type="checkbox"
                className="sr-only"
                checked={showCrawledOnly}
                onChange={handleFilterChange}
              />
              <div
                className={`block w-10 h-6 rounded-full ${
                  showCrawledOnly ? 'bg-blue-600' : 'bg-gray-200'
                }`}
              ></div>
              <div
                className={`dot absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${
                  showCrawledOnly ? 'translate-x-full' : 'translate-x-0'
                }`}
              ></div>
            </div>
            <div className="ml-3 text-sm font-medium text-gray-900">
              Show Crawled Companies Only
            </div>
          </label>
        </div>

        {/* Batch Actions */}
        {companies.length > 0 && (
          <div className="flex items-center justify-between pt-4 border-t border-gray-200">
            <div className="flex items-center gap-3">
              <button
                onClick={selectAll}
                className="text-sm text-blue-600 hover:text-blue-700 font-medium"
              >
                {selectedCompanies.size === companies.length ? 'Deselect All' : 'Select All'}
              </button>
              {selectedCompanies.size > 0 && (
                <span className="text-sm text-gray-500">
                  {selectedCompanies.size} selected
                </span>
              )}
            </div>
            {selectedCompanies.size > 0 && (
              <button
                onClick={handleCrawlSelected}
                className="flex items-center px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Globe className="w-4 h-4 mr-2" />
                Crawl Selected ({selectedCompanies.size})
              </button>
            )}
          </div>
        )}
      </div>

      {/* Companies Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader className="w-8 h-8 text-blue-600 animate-spin" />
        </div>
      ) : companies.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Building2 className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No companies found</h3>
          <p className="text-sm text-gray-500 mb-6">
            {searchTerm ? 'Try adjusting your search terms' : 'Start by discovering companies'}
          </p>
          <Link
            to="/discovery"
            className="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Search className="w-5 h-5 mr-2" />
            Discover Companies
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {companies.map((company) => (
            <div
              key={company.id}
              className={`bg-white rounded-lg border ${
                selectedCompanies.has(company.id) ? 'border-blue-500 ring-2 ring-blue-200' : 'border-gray-200'
              } p-6 hover:shadow-lg transition-all relative`}
            >
              {/* Selection Checkbox */}
              <div className="absolute top-4 left-4">
                <input
                  type="checkbox"
                  checked={selectedCompanies.has(company.id)}
                  onChange={(e) => toggleSelectCompany(company.id, e)}
                  className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 cursor-pointer"
                />
              </div>

              {/* Delete Button */}
              <div className="absolute top-4 right-4">
                <button
                  onClick={(e) => handleDeleteCompany(company.domain, e)}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="Delete company"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <Link
                to={`/companies/${getBaseDomain(company.domain)}`}
                className="block ml-8 mr-8"
              >
                {/* Company Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">
                      {company.company_name || company.domain}
                    </h3>
                    <div className="flex items-center text-sm text-gray-500">
                      <ExternalLink className="w-4 h-4 mr-1" />
                      {company.domain}
                    </div>
                  </div>
                  {getVettingBadge(company)}
                </div>

                {/* Description */}
                {company.description && (
                  <p className="text-sm text-gray-600 mb-4 line-clamp-2">
                    {company.description}
                  </p>
                )}

                {/* SMYKM Notes */}
                {company.smykm_notes && company.smykm_notes.length > 0 && (
                  <div className="mb-4 p-3 bg-blue-50 border-l-4 border-blue-400 rounded">
                    <p className="text-xs font-semibold text-blue-700 mb-2 flex items-center">
                      <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" />
                      </svg>
                      Key Insights
                    </p>
                    <div className="space-y-1">
                      {(Array.isArray(company.smykm_notes) ? company.smykm_notes : [company.smykm_notes])
                        .slice(0, 2)
                        .map((note, idx) => (
                          <p key={idx} className="text-sm text-blue-900 leading-snug">
                            • {note}
                          </p>
                        ))}
                      {Array.isArray(company.smykm_notes) && company.smykm_notes.length > 2 && (
                        <p className="text-xs text-blue-600 mt-1">
                          +{company.smykm_notes.length - 2} more insights
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Crawl Status & Action */}
                <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                  {getCrawlStatusBadge(company)}
                  {getCrawlButton(company)}
                </div>

                {/* Timestamps */}
                <div className="mt-3 text-xs text-gray-400 space-y-1">
                  {company.crawled_at && (
                    <div>Crawled: {new Date(company.crawled_at).toLocaleDateString()}</div>
                  )}
                  {company.extracted_at && (
                    <div>Extracted: {new Date(company.extracted_at).toLocaleDateString()}</div>
                  )}
                  {company.embedded_at && (
                    <div>Embedded: {new Date(company.embedded_at).toLocaleDateString()}</div>
                  )}
                </div>
              </Link>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {companies.length > 0 && (
        <div className="flex items-center justify-between bg-white rounded-lg border border-gray-200 p-4">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <div className="flex flex-col items-center gap-1">
            <span className="text-sm text-gray-600">
              Page {page + 1} of {Math.ceil(totalCompanies / pageSize)}
            </span>
            <span className="text-xs text-gray-500">
              Showing {Math.min(page * pageSize + 1, totalCompanies)}-{Math.min((page + 1) * pageSize, totalCompanies)} of {totalCompanies} companies
            </span>
          </div>
          <button
            onClick={() => setPage(page + 1)}
            disabled={companies.length < pageSize || (page + 1) * pageSize >= totalCompanies}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}

      {/* Add Company Dialog */}
      {showAddDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Add Company Manually</h2>
            <form onSubmit={handleAddCompany}>
              <div className="space-y-4">
                <div>
                  <label htmlFor="domain" className="block text-sm font-medium text-gray-700 mb-1">
                    Company Domain
                  </label>
                  <input
                    type="text"
                    id="domain"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    placeholder="example.com"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                    autoFocus
                    required
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Enter the domain without http:// or www.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button
                  type="submit"
                  disabled={addingCompany}
                  className="flex-1 px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {addingCompany ? (
                    <span className="flex items-center justify-center">
                      <Loader className="w-4 h-4 mr-2 animate-spin" />
                      Adding...
                    </span>
                  ) : (
                    'Add Company'
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddDialog(false);
                    setNewDomain('');
                  }}
                  disabled={addingCompany}
                  className="flex-1 px-4 py-2 bg-gray-200 text-gray-700 font-medium rounded-lg hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
