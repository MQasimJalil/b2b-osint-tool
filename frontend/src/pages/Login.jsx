/**
 * Login Page
 * For development: provides simple dev login
 * For production: will integrate with Auth0
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const navigate = useNavigate();
  const { devLogin, login, loading, error } = useAuth();
  const [email, setEmail] = useState('dev@local.com');
  const [username, setUsername] = useState('Dev User');
  const [auth0Token, setAuth0Token] = useState('');
  const [mode, setMode] = useState('dev'); // 'dev' or 'auth0'

  const handleDevLogin = async (e) => {
    e.preventDefault();
    try {
      await devLogin(email, username);
      navigate('/');
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  const handleAuth0Login = async (e) => {
    e.preventDefault();
    try {
      await login(auth0Token);
      navigate('/');
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            B2B OSINT Tool
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign in to your account
          </p>
        </div>

        <div className="flex justify-center space-x-4">
          <button
            onClick={() => setMode('dev')}
            className={`px-4 py-2 rounded-md ${
              mode === 'dev'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700'
            }`}
          >
            Dev Login
          </button>
          <button
            onClick={() => setMode('auth0')}
            className={`px-4 py-2 rounded-md ${
              mode === 'auth0'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700'
            }`}
          >
            Auth0 Login
          </button>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-4">
            <div className="text-sm text-red-800">{error}</div>
          </div>
        )}

        {mode === 'dev' ? (
          <form className="mt-8 space-y-6" onSubmit={handleDevLogin}>
            <div className="rounded-md shadow-sm -space-y-px">
              <div>
                <label htmlFor="email-address" className="sr-only">
                  Email address
                </label>
                <input
                  id="email-address"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                  placeholder="Email address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="username" className="sr-only">
                  Username
                </label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={loading}
                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {loading ? 'Signing in...' : 'Sign in (Dev Mode)'}
              </button>
            </div>

            <div className="text-xs text-gray-500 text-center">
              Development mode only - no real authentication required
            </div>
          </form>
        ) : (
          <form className="mt-8 space-y-6" onSubmit={handleAuth0Login}>
            <div>
              <label htmlFor="auth0-token" className="sr-only">
                Auth0 Token
              </label>
              <textarea
                id="auth0-token"
                name="auth0Token"
                required
                rows={6}
                className="appearance-none rounded-md relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="Paste your Auth0 JWT token here..."
                value={auth0Token}
                onChange={(e) => setAuth0Token(e.target.value)}
              />
            </div>

            <div>
              <button
                type="submit"
                disabled={loading}
                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {loading ? 'Verifying...' : 'Sign in with Auth0'}
              </button>
            </div>

            <div className="text-xs text-gray-500 text-center">
              Production mode - requires valid Auth0 token
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
