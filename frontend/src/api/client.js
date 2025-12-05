import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Token storage keys
const TOKEN_KEY = 'b2b_osint_token';
const USER_KEY = 'b2b_osint_user';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // If we get a 401 or 403, try to re-authenticate
    if ((error.response?.status === 401 || error.response?.status === 403) && !error.config._retry) {
      error.config._retry = true;
      try {
        await performDevLogin();
        // Retry the original request
        return apiClient(error.config);
      } catch (loginError) {
        console.error('Failed to re-authenticate:', loginError);
      }
    }
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// Authentication helpers
export const performDevLogin = async () => {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/v1/auth/dev-login`, {
      email: 'dev@local.com',
      username: 'Dev User',
    });

    const { access_token, user } = response.data;
    localStorage.setItem(TOKEN_KEY, access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));

    console.log('✓ Authenticated as:', user.email);
    return { access_token, user };
  } catch (error) {
    console.error('Dev login failed:', error);
    throw error;
  }
};

export const getStoredUser = () => {
  const userStr = localStorage.getItem(USER_KEY);
  return userStr ? JSON.parse(userStr) : null;
};

export const logout = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

// Initialize auth on module load
const initAuth = async () => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    try {
      await performDevLogin();
    } catch (error) {
      console.error('Auto-authentication failed:', error);
    }
  }
};

// Auto-authenticate when the module loads
initAuth();

export default apiClient;

// API Service methods matching actual backend endpoints
export const api = {
  // Health check
  health: () => apiClient.get('/health'),

  // Authentication
  auth: {
    devLogin: performDevLogin,
    logout,
    getUser: getStoredUser,
  },

  // Discovery
  discovery: {
    start: (data) => apiClient.post('/api/v1/discovery/start', data),
    listJobs: (params) => apiClient.get('/api/v1/discovery/jobs', { params }),
    getJob: (jobId) => apiClient.get(`/api/v1/discovery/jobs/${jobId}`),
    revet: (data) => apiClient.post('/api/v1/discovery/revet', data),
    recrawl: (data) => apiClient.post('/api/v1/discovery/recrawl', data),
  },

  // Jobs
  jobs: {
    list: (params) => apiClient.get('/api/v1/jobs/', { params }),
    get: (jobId) => apiClient.get(`/api/v1/jobs/${jobId}`),
    cancel: (jobId) => apiClient.post(`/api/v1/jobs/${jobId}/cancel`),
    delete: (jobId) => apiClient.delete(`/api/v1/jobs/${jobId}`),
  },

  // Companies
  companies: {
    stats: () => apiClient.get('/api/v1/companies/stats'),
    list: (params) => apiClient.get('/api/v1/companies/', { params }),
    get: (id) => apiClient.get(`/api/v1/companies/${id}`),
    getByDomain: (domain) => apiClient.get(`/api/v1/companies/by-domain/${domain}`),
    create: (data) => apiClient.post('/api/v1/companies/', data),
    update: (id, data) => apiClient.put(`/api/v1/companies/${id}`, data),
    delete: (id) => apiClient.delete(`/api/v1/companies/${id}`),
    getContacts: (id, contactType) => apiClient.get(`/api/v1/companies/${id}/contacts`, { params: { contact_type: contactType } }),
    createContact: (id, data) => apiClient.post(`/api/v1/companies/${id}/contacts`, data),
    getEnrichmentHistory: (id) => apiClient.get(`/api/v1/companies/${id}/enrichment-history`),
    // Crawl operations
    crawl: (id) => apiClient.post(`/api/v1/companies/${id}/crawl`),
    crawlBatch: (companyIds) => apiClient.post('/api/v1/companies/crawl/batch', companyIds),
    extract: (id) => apiClient.post(`/api/v1/companies/${id}/extract`),
    embed: (id) => apiClient.post(`/api/v1/companies/${id}/embed`),
    getCrawlStatus: (id) => apiClient.get(`/api/v1/companies/${id}/crawl-status`),
  },

  // Products
  products: {
    list: (params) => apiClient.get('/api/v1/products/', { params }),
    get: (id) => apiClient.get(`/api/v1/products/${id}`),
    create: (data) => apiClient.post('/api/v1/products/', data),
    update: (id, data) => apiClient.put(`/api/v1/products/${id}`, data),
    delete: (id) => apiClient.delete(`/api/v1/products/${id}`),
  },

  // Enrichment
  enrichment: {
    run: (data) => apiClient.post('/api/v1/enrichment/run', data),
    status: (taskId) => apiClient.get(`/api/v1/enrichment/status/${taskId}`),
  },

  // Campaigns
  campaigns: {
    list: () => apiClient.get('/api/v1/campaigns/'),
    create: (data) => apiClient.post('/api/v1/campaigns/', data),
    get: (id) => apiClient.get(`/api/v1/campaigns/${id}`),
    delete: (id) => apiClient.delete(`/api/v1/campaigns/${id}`),
    listDrafts: (id) => apiClient.get(`/api/v1/campaigns/${id}/drafts`),
    generateDrafts: (id, companyIds) => apiClient.post(`/api/v1/campaigns/${id}/generate-drafts`, companyIds),
    generateSelected: (id, draftIds) => apiClient.post(`/api/v1/campaigns/${id}/generate-selected`, draftIds),
    updateDraft: (id, data) => apiClient.put(`/api/v1/campaigns/drafts/${id}`, data),
  },

  // Email
  email: {
    verify: (emails) => apiClient.post('/api/v1/email/verify', { emails }),
    send: (data) => apiClient.post('/api/v1/email/send', data, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
    generateDraft: (companyId) => apiClient.post(`/api/v1/email/generate-draft/${companyId}`),
  },

  // RAG (AI Query)
  rag: {
    query: (data) => apiClient.post('/api/v1/rag/query', data),
    embed: (companyId) => apiClient.post(`/api/v1/rag/embed/${companyId}`),
  },

  // Users (for subscription info)
  users: {
    me: () => apiClient.get('/api/v1/users/me'),
    subscription: () => apiClient.get('/api/v1/users/me/subscription'),
  },
};
