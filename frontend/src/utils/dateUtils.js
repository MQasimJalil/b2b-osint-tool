/**
 * Date and domain utilities
 */

/**
 * Extract base domain name without TLD
 * Examples:
 *   advantagegk.com => advantagegk
 *   elitesportspecial.com => elitesportspecial
 *   catchandkeep.eu => catchandkeep
 *   eu.t1tan.com => eu.t1tan
 */
export const getBaseDomain = (domain) => {
  if (!domain) return '';
  const parts = domain.split('.');
  if (parts.length <= 1) return domain;
  // Remove the last part (TLD)
  return parts.slice(0, -1).join('.');
};

/**
 * Convert UTC date to Pakistan Standard Time (PKT = UTC+5)
 * @param {string|Date} utcDate - UTC date string or Date object
 * @returns {string} Formatted date string in PKT
 */
export const toPakistanTime = (utcDate) => {
  if (!utcDate) return null;

  const date = new Date(utcDate);

  // Convert to Pakistan timezone (UTC+5)
  const pktDate = new Date(date.getTime() + (5 * 60 * 60 * 1000));

  // Format as: "Jan 27, 2025, 9:30 PM PKT"
  const options = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC'
  };

  const formatted = pktDate.toLocaleString('en-US', options);
  return `${formatted} PKT`;
};

/**
 * Format date for display with Pakistan timezone
 * @param {string|Date} date - Date string or Date object
 * @returns {string} Formatted date string
 */
export const formatDate = (date) => {
  return toPakistanTime(date);
};

/**
 * Get relative time (e.g., "2 hours ago")
 * @param {string|Date} date - Date string or Date object
 * @returns {string} Relative time string
 */
export const getRelativeTime = (date) => {
  if (!date) return null;

  const now = new Date();
  const past = new Date(date);
  const diffMs = now - past;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  return formatDate(date);
};
