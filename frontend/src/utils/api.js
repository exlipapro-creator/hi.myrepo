/**
 * hi.myrepo — Centralized API Configuration
 *
 * VITE_API_BASE_URL determines the backend URL:
 * - Development (Vite proxy): VITE_API_BASE_URL is empty → relative URLs
 * - Production (deployed backend): VITE_API_BASE_URL = https://<railway-domain>
 *
 * Set VITE_API_BASE_URL in your .env file or Vercel environment variables.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Build a full API URL.
 * @param {string} path — API path, e.g. '/api/v1/projects'
 * @returns {string} Full URL (with base if configured)
 */
export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

/**
 * Build standard auth headers.
 * @param {string} token — JWT access token
 * @returns {object} Headers object
 */
export function authHeaders(token) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}
