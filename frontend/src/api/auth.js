/**
 * Authentication API client
 */
import client from './client';

const authAPI = {
  /**
   * Login with Auth0 token
   * @param {string} auth0Token - Auth0 JWT token
   * @returns {Promise} Login response with JWT and user info
   */
  login: async (auth0Token) => {
    const response = await client.post('/api/v1/auth/login', {
      auth0_token: auth0Token,
    });
    return response.data;
  },

  /**
   * Signup with Auth0 token
   * @param {string} auth0Token - Auth0 JWT token
   * @param {string} name - User's name (optional)
   * @returns {Promise} Signup response with JWT and user info
   */
  signup: async (auth0Token, name = null) => {
    const response = await client.post('/api/v1/auth/signup', {
      auth0_token: auth0Token,
      name,
    });
    return response.data;
  },

  /**
   * Dev login (for development only)
   * @param {string} email - Email address
   * @param {string} username - Username
   * @returns {Promise} Login response with JWT and user info
   */
  devLogin: async (email = 'dev@local.com', username = 'Dev User') => {
    const response = await client.post('/api/v1/auth/dev-login', {
      email,
      username,
    });
    return response.data;
  },

  /**
   * Get current user info
   * @returns {Promise} Current user information
   */
  getCurrentUser: async () => {
    const response = await client.get('/api/v1/auth/me');
    return response.data;
  },

  /**
   * Refresh JWT token
   * @returns {Promise} New JWT token
   */
  refreshToken: async () => {
    const response = await client.post('/api/v1/auth/refresh');
    return response.data;
  },

  /**
   * Logout (client-side)
   * @returns {Promise} Logout confirmation
   */
  logout: async () => {
    const response = await client.post('/api/v1/auth/logout');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    return response.data;
  },
};

export default authAPI;
