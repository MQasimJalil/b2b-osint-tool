import { useState, useEffect, useRef } from 'react';
import { MessageSquare, Send, Loader, Database, Sparkles, XCircle, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api/client';

const CHAT_HISTORY_KEY = 'knowledgebase_chat_history';

export default function KnowledgeBase() {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // Context & Memory State
  const [summary, setSummary] = useState('');
  const [processedCount, setProcessedCount] = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  
  const messagesEndRef = useRef(null);

  // Load chat history from localStorage on component mount
  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem(CHAT_HISTORY_KEY);
      if (savedHistory) {
        const parsed = JSON.parse(savedHistory);
        // Convert timestamp strings back to Date objects
        const historyWithDates = parsed.map(msg => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
        setChatHistory(historyWithDates);
        
        // Restore processed count from history length (assuming all old history is "processed" or lost context)
        // A better way would be to save summary to localStorage too, but for now we reset context on refresh
        // to keep implementation simple. Or we could save summary. 
        // Let's just start fresh context for now or if history exists, assume it's unsummarized?
        // Actually, if we reload page, 'processedCount' resets to 0. 
        // This means the FIRST new message will try to summarize EVERYTHING in history. 
        // This is actually GOOD - it restores context from the persistent history!
      }
    } catch (error) {
      console.error('Error loading chat history from localStorage:', error);
    }
  }, []);

  // Save chat history to localStorage whenever it changes
  useEffect(() => {
    try {
      if (chatHistory.length > 0) {
        localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
      }
    } catch (error) {
      console.error('Error saving chat history to localStorage:', error);
    }
  }, [chatHistory]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, loading]);

  const handleQuery = async (e, customQuery = null) => {
    if (e) e.preventDefault();
    const queryText = customQuery || query;
    if (!queryText.trim()) return;

    const userMessage = {
      type: 'user',
      content: queryText,
      timestamp: new Date(),
    };

    const newHistory = [...chatHistory, userMessage];
    setChatHistory(newHistory);
    setQuery('');
    setSuggestions([]);
    setLoading(true);

    try {
      // Logic for Rolling Window + Summary
      const WINDOW_SIZE = 6;
      const windowStartIndex = Math.max(0, newHistory.length - WINDOW_SIZE);
      
      const msgsToSummarize = newHistory.slice(processedCount, windowStartIndex).map(msg => ({
        role: msg.type === 'user' ? 'user' : 'assistant',
        content: msg.content
      }));

      const historyWindow = newHistory.slice(windowStartIndex).map(msg => ({
        role: msg.type === 'user' ? 'user' : 'assistant',
        content: msg.content
      }));

      // Query without company_domain to search across all companies
      const response = await api.rag.query({
        query: queryText,
        top_k: 10,
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
      
      if (response.data.new_summary) {
        setSummary(response.data.new_summary);
        setProcessedCount(prev => prev + msgsToSummarize.length);
      }
      
      if (response.data.suggested_questions) {
        setSuggestions(response.data.suggested_questions);
      }

    } catch (error) {
      console.error('AI query failed:', error);
      const errorMessage = {
        type: 'error',
        content: 'Failed to get response. Please try again.',
        timestamp: new Date(),
      };
      setChatHistory((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    if (window.confirm('Clear all chat history?')) {
      setChatHistory([]);
      setSummary('');
      setProcessedCount(0);
      setSuggestions([]);
      localStorage.removeItem(CHAT_HISTORY_KEY);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center">
            <Database className="w-8 h-8 mr-3 text-blue-600" />
            Knowledge Base
          </h1>
          <p className="text-gray-600 mt-2">
            Ask questions about any company in your database
          </p>
        </div>
        {chatHistory.length > 0 && (
          <button
            onClick={clearHistory}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Clear History
          </button>
        )}
      </div>

      {/* Chat Container */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        {/* Chat Messages */}
        <div className="h-[600px] overflow-y-auto p-6 space-y-4">
          {chatHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-20 h-20 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center mb-6">
                <Sparkles className="w-10 h-10" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">
                Welcome to Knowledge Base
              </h3>
              <p className="text-gray-600 max-w-md mx-auto">
                Ask questions about any company in your database. I'll search across all your
                collected data to provide comprehensive answers.
              </p>
              <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-3 text-left w-full max-w-2xl">
                {[
                  "Which companies sell fishing equipment?",
                  "Tell me about companies with LinkedIn profiles",
                  "What products are available in the sports category?",
                  "Which companies have email contacts?"
                ].map((q, idx) => (
                  <button 
                    key={idx}
                    onClick={() => setQuery(q)}
                    className="p-3 text-sm text-gray-600 bg-gray-50 hover:bg-blue-50 border border-gray-200 hover:border-blue-200 rounded-lg transition-colors text-left"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {chatHistory.map((message, idx) => (
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
              ))}

              {loading && (
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
            </>
          )}
        </div>

        {/* Suggested Questions */}
        {suggestions.length > 0 && !loading && (
          <div className="bg-gray-50 px-4 pt-3 pb-0 flex flex-wrap gap-2">
            {suggestions.map((question, idx) => (
              <button
                key={idx}
                onClick={(e) => handleQuery(e, question)}
                className="text-xs bg-blue-50 text-blue-700 px-3 py-1.5 rounded-full border border-blue-100 hover:bg-blue-100 hover:border-blue-200 transition-colors text-left"
              >
                {question}
              </button>
            ))}
          </div>
        )}

        {/* Input Form */}
        <div className="border-t border-gray-200 p-4 bg-gray-50 rounded-b-lg">
          <form onSubmit={(e) => handleQuery(e)} className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask anything about your companies..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center gap-2"
            >
              {loading ? (
                <>
                  <Loader className="w-5 h-5 animate-spin" />
                  <span className="hidden sm:inline">Thinking...</span>
                </>
              ) : (
                <>
                  <Send className="w-5 h-5" />
                  <span className="hidden sm:inline">Send</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
