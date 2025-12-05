/**
 * Authentication Context
 * Provides auth state and methods throughout the application
 */
import { createContext, useContext, useState, useEffect } from 'react';
import authAPI from '../api/auth';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initialize auth state from localStorage
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem('token');
      const storedUser = localStorage.getItem('user');

      if (storedToken && storedUser) {
        setToken(storedToken);
        try {
          setUser(JSON.parse(storedUser));
        } catch (e) {
          console.error('Failed to parse stored user:', e);
          localStorage.removeItem('user');
        }
      }

      // In development, auto-login if no token
      if (!storedToken && import.meta.env.DEV) {
        try {
          await devLogin();
        } catch (error) {
          console.error('Auto dev-login failed:', error);
        }
      }

      setLoading(false);
    };

    initAuth();
  }, []);

  /**
   * Login with Auth0 token
   */
  const login = async (auth0Token) => {
    try {
      setLoading(true);
      setError(null);

      const response = await authAPI.login(auth0Token);

      setToken(response.access_token);
      setUser(response.user);

      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));

      return response;
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  /**
   * Signup with Auth0 token
   */
  const signup = async (auth0Token, name = null) => {
    try {
      setLoading(true);
      setError(null);

      const response = await authAPI.signup(auth0Token, name);

      setToken(response.access_token);
      setUser(response.user);

      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));

      return response;
    } catch (err) {
      setError(err.response?.data?.detail || 'Signup failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  /**
   * Dev login (for development only)
   */
  const devLogin = async (email = 'dev@local.com', username = 'Dev User') => {
    try {
      setLoading(true);
      setError(null);

      const response = await authAPI.devLogin(email, username);

      setToken(response.access_token);
      setUser(response.user);

      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));

      return response;
    } catch (err) {
      setError(err.response?.data?.detail || 'Dev login failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  /**
   * Logout
   */
  const logout = async () => {
    try {
      await authAPI.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setToken(null);
      setUser(null);
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    }
  };

  /**
   * Refresh user data from server
   */
  const refreshUser = async () => {
    try {
      const userData = await authAPI.getCurrentUser();
      setUser(userData);
      localStorage.setItem('user', JSON.stringify(userData));
      return userData;
    } catch (error) {
      console.error('Failed to refresh user:', error);
      throw error;
    }
  };

  /**
   * Refresh JWT token
   */
  const refreshToken = async () => {
    try {
      const response = await authAPI.refreshToken();
      setToken(response.access_token);
      localStorage.setItem('token', response.access_token);
      return response;
    } catch (error) {
      console.error('Failed to refresh token:', error);
      // If refresh fails, logout
      await logout();
      throw error;
    }
  };

  const value = {
    user,
    token,
    loading,
    error,
    isAuthenticated: !!token && !!user,
    login,
    signup,
    devLogin,
    logout,
    refreshUser,
    refreshToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthContext;
