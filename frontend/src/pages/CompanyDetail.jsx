import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  Mail,
  Phone,
  Linkedin,
  ExternalLink,
  Loader,
  MessageSquare,
  Package,
  History,
  Send,
  Plus,
  CheckCircle,
  XCircle,
  RefreshCw,
  X,
  Star,
  ShoppingCart,
  FileText,
  Database,
  Loader2,
  Sparkles,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api/client';
import { formatDate } from '../utils/dateUtils';
import { ToastContainer, useToast } from '../components/ui/Toast';
import { ConfirmationModal } from '../components/ui/Modal';

export default function CompanyDetail() {
  const { domain } = useParams();
  const { toasts, success, error, info, removeToast } = useToast();
  
  const [company, setCompany] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [products, setProducts] = useState([]);
  const [enrichmentHistory, setEnrichmentHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [aiQuery, setAiQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [showAllInsights, setShowAllInsights] = useState(false);
  
  // Context & Memory State
  const [summary, setSummary] = useState('');
  const [processedCount, setProcessedCount] = useState(0); // Count of messages already summarized
  const [suggestions, setSuggestions] = useState([]);

  const messagesEndRef = useRef(null);

  // Action states
  const [actionLoading, setActionLoading] = useState({
    recrawl: false,
    extract: false,
    embed: false
  });
  
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    type: null, // 'recrawl', 'extract', 'embed'
    title: '',
    message: ''
  });

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, aiLoading]);

  // Polling for crawl status
  useEffect(() => {
    let intervalId;
    
    if (company?.crawl_status === 'crawling' || company?.crawl_status === 'queued') {
      intervalId = setInterval(async () => {
        try {
          const res = await api.companies.getCrawlStatus(company.id);
          const status = res.data.crawl_status;
          
          if (status !== company.crawl_status) {
            setCompany(prev => ({ ...prev, crawl_status: status }));
            if (status === 'completed') {
              success('Crawl completed successfully!', 'Process Finished');
              loadCompanyData(); // Reload all data
            } else if (status === 'failed') {
              error('Crawl failed. Please try again.', 'Process Failed');
            }
          }
        } catch (err) {
          console.error("Polling error", err);
        }
      }, 5000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [company?.crawl_status, company?.id]);

  // Load chat history from localStorage on component mount
  useEffect(() => {
    if (!domain) return;

    try {
      const chatKey = `company_chat_${domain}`;
      const savedHistory = localStorage.getItem(chatKey);
      if (savedHistory) {
        const parsed = JSON.parse(savedHistory);
        const historyWithDates = parsed.map(msg => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
        setChatHistory(historyWithDates);
      }
      
      const suggestionsKey = `company_chat_suggestions_${domain}`;
      const savedSuggestions = localStorage.getItem(suggestionsKey);
      if (savedSuggestions) {
        setSuggestions(JSON.parse(savedSuggestions));
      }
    } catch (error) {
      console.error('Error loading chat history from localStorage:', error);
    }
  }, [domain]);

  // Save chat history to localStorage whenever it changes
  useEffect(() => {
    if (!domain) return;

    try {
      const chatKey = `company_chat_${domain}`;
      if (chatHistory.length > 0) {
        localStorage.setItem(chatKey, JSON.stringify(chatHistory));
      }
      
      const suggestionsKey = `company_chat_suggestions_${domain}`;
      localStorage.setItem(suggestionsKey, JSON.stringify(suggestions));
    } catch (error) {
      console.error('Error saving chat history to localStorage:', error);
    }
  }, [chatHistory, suggestions, domain]);

  useEffect(() => {
    loadCompanyData();
  }, [domain]);

  const loadCompanyData = async () => {
    try {
      // Don't set full page loading on reload
      if (!company) setLoading(true);
      
      const companyRes = await api.companies.getByDomain(domain);
      const companyData = companyRes.data;
      const companyId = companyData.id;

      const [productsRes, historyRes] = await Promise.all([
        api.products.list({ company_id: companyId }).catch(() => ({ data: { products: [] } })),
        api.companies.getEnrichmentHistory(companyId).catch(() => ({ data: [] })),
      ]);

      setCompany(companyData);
      setContacts(companyData.contacts || []);
      setProducts(productsRes.data?.products || productsRes.data || []);
      setEnrichmentHistory(historyRes.data || []);
    } catch (error) {
      console.error('Failed to load company:', error);
      error('Failed to load company data');
    } finally {
      setLoading(false);
    }
  };

  const handleAiQuery = async (e, customQuery = null) => {
    if (e) e.preventDefault();
    const queryText = customQuery || aiQuery;
    if (!queryText.trim()) return;

    const userMessage = {
      type: 'user',
      content: queryText,
      timestamp: new Date(),
    };

    const newHistory = [...chatHistory, userMessage];
    setChatHistory(newHistory);
    setAiQuery('');
    setSuggestions([]); // Clear suggestions while thinking
    setAiLoading(true);

    try {
      // Logic for Rolling Window + Summary
      // We want to keep the last 6 messages as "active window"
      // Messages older than that (but not yet summarized) go to 'to_summarize'
      
      const WINDOW_SIZE = 6;
      // Index where the active window starts (anything before this is "old")
      const windowStartIndex = Math.max(0, newHistory.length - WINDOW_SIZE);
      
      // Messages that are "old" but haven't been summarized yet
      // slice(processedCount, windowStartIndex)
      const msgsToSummarize = newHistory.slice(processedCount, windowStartIndex).map(msg => ({
        role: msg.type === 'user' ? 'user' : 'assistant',
        content: msg.content
      }));

      // Active Window messages
      const historyWindow = newHistory.slice(windowStartIndex).map(msg => ({
        role: msg.type === 'user' ? 'user' : 'assistant',
        content: msg.content
      }));

      const response = await api.rag.query({
        query: queryText,
        company_domain: company.domain,
        top_k: 5,
        history: historyWindow,
        summary: summary,
        to_summarize: msgsToSummarize
      });

      // Clean up answer text if it still contains suggestions (safety measure)
      let cleanAnswer = response.data.answer;
      // Remove standard header block
      cleanAnswer = cleanAnswer.replace(/(?:\n|^)(?:Suggested|Follow-up|Recommended)(?:.*)(?:Questions|Queries|Topics)(?:[:\s]*)(?:[\s\S]*)$/i, '');
      // Remove trailing orphan headers like "Suggested"
      cleanAnswer = cleanAnswer.replace(/(?:\n|^)(?:Suggested|Follow-up|Recommended)[\s:.-]*$/i, '');
      cleanAnswer = cleanAnswer.trim();

      const aiMessage = {
        type: 'ai',
        content: cleanAnswer,
        sources: response.data.sources || [],
        timestamp: new Date(),
      };

      setChatHistory((prev) => [...prev, aiMessage]);
      
      // Update Context State
      if (response.data.new_summary) {
        setSummary(response.data.new_summary);
        // We effectively summarized everything up to the start of the current window
        // But wait, the window moves *after* this turn. 
        // We successfully summarized `msgsToSummarize`. So we advance processedCount by their length.
        setProcessedCount(prev => prev + msgsToSummarize.length);
      }
      
      if (response.data.suggested_questions) {
        setSuggestions(response.data.suggested_questions);
      }

    } catch (err) {
      console.error('AI query failed:', err);
      const errorMessage = {
        type: 'error',
        content: 'Failed to get response. Please try again.',
        timestamp: new Date(),
      };
      setChatHistory((prev) => [...prev, errorMessage]);
    } finally {
      setAiLoading(false);
    }
  };

  const clearChatHistory = () => {
    if (window.confirm('Clear all chat history for this company?')) {
      setChatHistory([]);
      const chatKey = `company_chat_${domain}`;
      localStorage.removeItem(chatKey);
    }
  };

  // Action Handlers
  const initiateAction = (type) => {
    let title = '';
    let message = '';

    switch (type) {
      case 'recrawl':
        title = 'Recrawl Company Website';
        message = `Are you sure you want to recrawl ${company.domain}? This will update all data from the website and may take a few minutes.`;
        break;
      case 'extract':
        title = 'Extract Data';
        message = 'Start data extraction from crawled pages? This process runs without re-crawling the website.';
        break;
      case 'embed':
        title = 'Update AI Knowledge Base';
        message = 'Embed extracted data into the vector database? This will update the "Chat with Data" capabilities.';
        break;
      default:
        return;
    }

    setConfirmModal({
      isOpen: true,
      type,
      title,
      message
    });
  };

  const handleConfirmAction = async () => {
    const { type } = confirmModal;
    if (!type) return;

    setActionLoading(prev => ({ ...prev, [type]: true }));
    // Close modal immediately or keep open with loading state?
    // Let's keep modal logic simple: Action starts, close modal, show toast.
    setConfirmModal(prev => ({ ...prev, isOpen: false }));

    try {
      if (type === 'recrawl') {
        await api.companies.crawl(company.id);
        success('Crawl started successfully. Data will update automatically.', 'Crawl Initiated');
        // Update local status to trigger polling
        setCompany(prev => ({ ...prev, crawl_status: 'queued' }));
      } else if (type === 'extract') {
        await api.companies.extract(company.id);
        success('Extraction task started.', 'Extraction Initiated');
      } else if (type === 'embed') {
        await api.companies.embed(company.id);
        success('Embedding task started.', 'Embedding Initiated');
      }
    } catch (err) {
      console.error(`Failed to start ${type}:`, err);
      error(`Failed to start ${type}. Please try again.`, 'Error');
    } finally {
      setActionLoading(prev => ({ ...prev, [type]: false }));
    }
  };

  const tabs = [
    { id: 'overview', name: 'Overview', icon: Building2 },
    { id: 'contacts', name: 'Contacts', icon: Mail, count: contacts.length },
    { id: 'products', name: 'Products', icon: Package, count: products.length },
    { id: 'ai-chat', name: 'Chat with Data', icon: MessageSquare },
    { id: 'history', name: 'History', icon: History },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Company not found</p>
        <Link to="/companies" className="text-blue-600 hover:underline mt-4 inline-block">
          Back to Companies
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 relative">
      <ToastContainer toasts={toasts} removeToast={removeToast} />
      
      <ConfirmationModal
        isOpen={confirmModal.isOpen}
        onClose={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}
        onConfirm={handleConfirmAction}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmText="Start"
        isLoading={actionLoading[confirmModal.type]}
      />

      {/* Header */}
      <div>
        <Link
          to="/companies"
          className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to Companies
        </Link>

        <div className="flex items-start justify-between">
          <div className="flex-1">
            <h1 className="text-3xl font-bold text-gray-900">
              {company.company_name || company.domain}
            </h1>
            <a
              href={`https://${company.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center text-blue-600 hover:underline mt-2 mb-3"
            >
              <ExternalLink className="w-4 h-4 mr-1" />
              {company.domain}
            </a>
            {/* Small Description in Header */}
            {company.description && (
              <p className="text-sm text-gray-600 max-w-2xl line-clamp-2">
                {company.description}
              </p>
            )}
            {/* Status Indicators */}
            <div className="flex gap-2 mt-2">
               {company.crawl_status === 'crawling' && (
                 <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                   <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                   Crawling...
                 </span>
               )}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => initiateAction('recrawl')}
              disabled={company.crawl_status === 'crawling' || actionLoading.recrawl}
              className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Re-run crawler"
            >
              {actionLoading.recrawl || company.crawl_status === 'crawling' ? (
                 <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                 <RefreshCw className="w-4 h-4 mr-2" />
              )}
              {company.crawl_status === 'crawling' ? 'Crawling...' : 'Recrawl'}
            </button>
            <button
              onClick={() => initiateAction('extract')}
              disabled={actionLoading.extract}
              className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              title="Run extraction on crawled data"
            >
              {actionLoading.extract ? (
                 <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                 <FileText className="w-4 h-4 mr-2" />
              )}
              Extract
            </button>
            <button
              onClick={() => initiateAction('embed')}
              disabled={actionLoading.embed}
              className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              title="Update AI knowledge base"
            >
              {actionLoading.embed ? (
                 <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                 <Database className="w-4 h-4 mr-2" />
              )}
              Embed
            </button>
            <button className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">
              Enrich Data
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <tab.icon className="w-5 h-5 mr-2" />
              {tab.name}
              {tab.count !== undefined && (
                <span className="ml-2 px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full text-xs">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {company.description && (
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Description</h3>
                <p className="text-gray-700">{company.description}</p>
              </div>
            )}

            {company.smykm_notes && company.smykm_notes.length > 0 && (
              <div className="mt-8">
                <div className="flex items-center mb-4">
                  <div className="p-2 bg-yellow-100 rounded-lg mr-3">
                    <svg className="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    Key Insights & Personalization
                  </h3>
                </div>
                
                {(() => {
                  const notes = Array.isArray(company.smykm_notes) 
                    ? company.smykm_notes 
                    : JSON.parse(company.smykm_notes || '[]');
                  const visibleNotes = showAllInsights ? notes : notes.slice(0, 3);
                  
                  return (
                    <>
                      <div className="grid grid-cols-1 gap-4">
                        {visibleNotes.map((note, idx) => (
                          <div 
                            key={idx} 
                            className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow duration-200 flex items-start group"
                          >
                            <span className="flex-shrink-0 w-6 h-6 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center text-xs font-medium mr-3 mt-0.5 group-hover:bg-blue-100 transition-colors">
                              {idx + 1}
                            </span>
                            <p className="text-gray-700 leading-relaxed text-sm">
                              {note}
                            </p>
                          </div>
                        ))}
                      </div>
                      
                      {notes.length > 3 && (
                        <div className="mt-4 text-center">
                          <button
                            onClick={() => setShowAllInsights(!showAllInsights)}
                            className="text-sm font-medium text-blue-600 hover:text-blue-800 focus:outline-none"
                          >
                            {showAllInsights ? 'Show Less' : `Show ${notes.length - 3} More Insights`}
                          </button>
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-500">Contact Score</p>
                <p className="text-lg font-semibold text-gray-900">
                  {company.contact_score || 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Search Mode</p>
                <p className="text-lg font-semibold text-gray-900">
                  {company.search_mode || 'N/A'}
                </p>
              </div>
            </div>

            {/* Timestamps */}
            <div className="mt-8 pt-6 border-t border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Data Timeline</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-gray-500 mb-1">Crawled At</p>
                  <p className="text-base font-medium text-gray-900">
                    {company.crawled_at
                      ? formatDate(company.crawled_at)
                      : 'Not crawled'}
                  </p>
                  {company.crawled_pages && (
                    <p className="text-xs text-gray-500 mt-1">
                      {company.crawled_pages} pages
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-sm text-gray-500 mb-1">Extracted At</p>
                  <p className="text-base font-medium text-gray-900">
                    {company.extracted_at
                      ? formatDate(company.extracted_at)
                      : 'Not extracted'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 mb-1">Enriched At</p>
                  <p className="text-base font-medium text-gray-900">
                    {company.enriched_at
                      ? formatDate(company.enriched_at)
                      : 'Not enriched'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Contacts Tab */}
        {activeTab === 'contacts' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Contacts</h3>
              <button className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">
                <Plus className="w-4 h-4 mr-2" />
                Add Contact
              </button>
            </div>

            {contacts.length === 0 ? (
              <div className="text-center py-12">
                <Mail className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500">No contacts found</p>
              </div>
            ) : (
              <div className="space-y-3">
                {contacts.map((contact, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-4 border border-gray-200 rounded-lg"
                  >
                    <div className="flex items-center">
                      {contact.type === 'email' && <Mail className="w-5 h-5 text-blue-600 mr-3" />}
                      {contact.type === 'phone' && <Phone className="w-5 h-5 text-green-600 mr-3" />}
                      {contact.type === 'linkedin' && (
                        <Linkedin className="w-5 h-5 text-blue-700 mr-3" />
                      )}
                      <div>
                        <p className="text-sm font-medium text-gray-900">{contact.value}</p>
                        <p className="text-xs text-gray-500">
                          {contact.source} • Confidence: {contact.confidence || 'N/A'}
                        </p>
                      </div>
                    </div>
                    {contact.is_primary && (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded">
                        Primary
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Products Tab */}
        {activeTab === 'products' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Products</h3>

            {products.length === 0 ? (
              <div className="text-center py-12">
                <Package className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500">No products found</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {products.map((product, idx) => (
                  <div
                    key={idx}
                    onClick={() => setSelectedProduct(product)}
                    className="border border-gray-200 rounded-lg p-4 cursor-pointer hover:shadow-lg hover:border-blue-300 transition-all"
                  >
                    {product.image_url && (
                      <img
                        src={product.image_url}
                        alt={product.name}
                        className="w-full h-48 object-cover rounded-lg mb-3"
                      />
                    )}
                    <h4 className="font-semibold text-gray-900 mb-1">{product.name}</h4>
                    {product.brand && (
                      <p className="text-sm text-gray-600 mb-2">{product.brand}</p>
                    )}
                    {product.price && (
                      <p className="text-lg font-bold text-blue-600 mb-2">{product.price}</p>
                    )}
                    {product.description && (
                      <p className="text-sm text-gray-700 line-clamp-2">{product.description}</p>
                    )}
                    <p className="text-xs text-blue-600 mt-2 font-medium">Click for details →</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* AI Chat Tab */}
        {activeTab === 'ai-chat' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Chat with Data</h3>
              {chatHistory.length > 0 && (
                <button
                  onClick={clearChatHistory}
                  className="px-3 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Clear History
                </button>
              )}
            </div>

            {/* Chat History */}
            <div className="space-y-4 max-h-[600px] overflow-y-auto bg-gray-50 rounded-xl p-4 mb-4 border border-gray-100 shadow-inner">
              {chatHistory.length === 0 ? (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center mx-auto mb-4">
                    <MessageSquare className="w-8 h-8" />
                  </div>
                  <h4 className="text-lg font-medium text-gray-900 mb-1">Ask about {company?.company_name || domain}</h4>
                  <p className="text-sm text-gray-500 max-w-sm mx-auto">
                    Use our AI agent to query extracted data, find specific products, or draft emails based on this company's profile.
                  </p>
                </div>
              ) : (
                chatHistory.map((message, idx) => (
                  <div
                    key={idx}
                    className={`flex gap-3 ${
                      message.type === 'user' ? 'flex-row-reverse' : ''
                    }`}
                  >
                    <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                      message.type === 'user' 
                        ? 'bg-blue-600 text-white' 
                        : message.type === 'error'
                        ? 'bg-red-100 text-red-600'
                        : 'bg-purple-100 text-purple-600'
                    }`}>
                      {message.type === 'user' && <span className="text-xs font-bold">You</span>}
                      {message.type === 'ai' && <Sparkles className="w-4 h-4" />}
                      {message.type === 'error' && <XCircle className="w-4 h-4" />}
                    </div>

                    <div className={`flex-1 max-w-[80%] rounded-2xl p-4 ${
                      message.type === 'user'
                        ? 'bg-blue-600 text-white shadow-md rounded-tr-none'
                        : message.type === 'error'
                        ? 'bg-red-50 border border-red-200 text-red-700'
                        : 'bg-white border border-gray-200 shadow-sm rounded-tl-none'
                    }`}>
                      {message.type === 'user' ? (
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      ) : (
                        <div className="prose prose-sm max-w-none prose-blue">
                          <ReactMarkdown>{message.content}</ReactMarkdown>
                        </div>
                      )}

                      {message.sources && message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-100">
                          <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">Sources Used</p>
                          <div className="flex flex-wrap gap-2">
                            {message.sources.map((source, sidx) => (
                              <span 
                                key={sidx} 
                                className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200"
                              >
                                {source.name || source.type || source.title || "Data Source"}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      <div className={`text-[10px] mt-2 text-right ${
                        message.type === 'user' ? 'text-blue-200' : 'text-gray-400'
                      }`}>
                        {message.timestamp && new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  </div>
                ))
              )}
              {aiLoading && (
                <div className="flex gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center">
                    <Sparkles className="w-4 h-4 animate-pulse" />
                  </div>
                  <div className="bg-white border border-gray-200 shadow-sm rounded-2xl rounded-tl-none p-4 flex items-center space-x-2">
                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Suggested Questions */}
            {suggestions.length > 0 && !aiLoading && (
              <div className="flex flex-wrap gap-2 mb-3 px-1">
                {suggestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={(e) => handleAiQuery(e, question)}
                    className="text-xs bg-blue-50 text-blue-700 px-3 py-1.5 rounded-full border border-blue-100 hover:bg-blue-100 hover:border-blue-200 transition-colors text-left"
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}

            {/* Input Form */}
            <form onSubmit={(e) => handleAiQuery(e)} className="flex gap-2">
              <input
                type="text"
                value={aiQuery}
                onChange={(e) => setAiQuery(e.target.value)}
                placeholder="Ask anything about this company..."
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={aiLoading}
              />
              <button
                type="submit"
                disabled={aiLoading || !aiQuery.trim()}
                className="px-6 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center gap-2"
              >
                {aiLoading ? (
                  <>
                    <Loader className="w-5 h-5 animate-spin" />
                    <span className="text-sm">Processing...</span>
                  </>
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </button>
            </form>
          </div>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Enrichment History</h3>

            {enrichmentHistory.length === 0 ? (
              <div className="text-center py-12">
                <History className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500">No enrichment history</p>
              </div>
            ) : (
              <div className="space-y-3">
                {enrichmentHistory.map((entry, idx) => (
                  <div key={idx} className="flex items-start p-4 border border-gray-200 rounded-lg">
                    {entry.status === 'success' ? (
                      <CheckCircle className="w-5 h-5 text-green-600 mr-3 mt-0.5" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-600 mr-3 mt-0.5" />
                    )}
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="font-medium text-gray-900">{entry.source}</p>
                        <span className="text-xs text-gray-500">
                          {new Date(entry.enriched_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">Status: {entry.status}</p>
                      {entry.details && (
                        <p className="text-xs text-gray-500 mt-1">
                          {JSON.stringify(entry.details)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Product Detail Modal */}
      {selectedProduct && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setSelectedProduct(null)}>
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <h2 className="text-2xl font-bold text-gray-900">{selectedProduct.name}</h2>
              <button
                onClick={() => setSelectedProduct(null)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-6 h-6 text-gray-500" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-6">
              {/* Product Image */}
              {selectedProduct.image_url && (
                <div className="w-full">
                  <img
                    src={selectedProduct.image_url}
                    alt={selectedProduct.name}
                    className="w-full max-h-96 object-contain rounded-lg border border-gray-200"
                  />
                </div>
              )}

              {/* Basic Info Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {selectedProduct.brand && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <p className="text-sm text-gray-500 mb-1">Brand</p>
                    <p className="text-lg font-semibold text-gray-900">{selectedProduct.brand}</p>
                  </div>
                )}

                {selectedProduct.category && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <p className="text-sm text-gray-500 mb-1">Category</p>
                    <p className="text-lg font-semibold text-gray-900">{selectedProduct.category}</p>
                  </div>
                )}

                {selectedProduct.price && (
                  <div className="bg-blue-50 p-4 rounded-lg">
                    <p className="text-sm text-blue-600 mb-1">Price</p>
                    <p className="text-2xl font-bold text-blue-700">{selectedProduct.price}</p>
                  </div>
                )}

                {selectedProduct.product_external_id && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <p className="text-sm text-gray-500 mb-1">Product ID</p>
                    <p className="text-sm font-mono text-gray-900">{selectedProduct.product_external_id}</p>
                  </div>
                )}
              </div>

              {/* Description */}
              {selectedProduct.description && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Description</h3>
                  <p className="text-gray-700 leading-relaxed">{selectedProduct.description}</p>
                </div>
              )}

              {/* Specifications */}
              {selectedProduct.specs && Object.keys(selectedProduct.specs).length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Specifications</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(selectedProduct.specs).map(([key, value]) => (
                      <div key={key} className="flex items-start border-b border-gray-200 pb-2">
                        <span className="text-sm font-medium text-gray-600 w-1/2">{key}:</span>
                        <span className="text-sm text-gray-900 w-1/2">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Reviews */}
              {selectedProduct.reviews && selectedProduct.reviews.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                    <Star className="w-5 h-5 text-yellow-500 mr-2" />
                    Customer Reviews ({selectedProduct.reviews.length})
                  </h3>
                  <div className="space-y-3">
                    {selectedProduct.reviews.map((review, idx) => (
                      <div key={idx} className="bg-gray-50 p-4 rounded-lg">
                        {typeof review === 'string' ? (
                          <p className="text-sm text-gray-700 italic">"{review}"</p>
                        ) : (
                          <>
                            {review.rating && (
                              <div className="flex items-center mb-2">
                                {[...Array(5)].map((_, i) => (
                                  <Star
                                    key={i}
                                    className={`w-4 h-4 ${
                                      i < review.rating ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300'
                                    }`}
                                  />
                                ))}
                              </div>
                            )}
                            {review.title && (
                              <p className="font-semibold text-gray-900 mb-1">{review.title}</p>
                            )}
                            {review.text && (
                              <p className="text-sm text-gray-700">{review.text}</p>
                            )}
                            {review.author && (
                              <p className="text-xs text-gray-500 mt-2">— {review.author}</p>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Product URL */}
              {selectedProduct.url && (
                <div className="pt-4 border-t border-gray-200">
                  <a
                    href={selectedProduct.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    <ShoppingCart className="w-5 h-5 mr-2" />
                    View on Website
                    <ExternalLink className="w-4 h-4 ml-2" />
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
