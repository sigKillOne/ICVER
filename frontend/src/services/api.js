const API_BASE_URL = 'http://localhost:8000/api/v1';

/**
 * Helper to handle fetch requests with error handling
 */
async function fetchJson(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || `API Request failed with status ${response.status}`;
      throw new Error(errorMessage);
    }

    return await response.json();
  } catch (error) {
    console.error(`API Error on ${endpoint}:`, error);
    throw error;
  }
}

/**
 * Record worker data access consent
 * @param {Object} consentData - { worker_id, phone_number, consent_given, consent_purpose }
 */
export async function submitConsent(consentData) {
  return fetchJson('/consent', {
    method: 'POST',
    body: JSON.stringify(consentData),
  });
}

/**
 * Fetch consent status by consent ID
 * @param {string} consentId 
 */
export async function getConsentStatus(consentId) {
  return fetchJson(`/consent/${encodeURIComponent(consentId)}`, {
    method: 'GET',
  });
}

/**
 * Calculate creditworthiness and verified income score
 * @param {Object} scoringData - { worker_id, consent_id, upi_transaction_history, mobile_recharge_logs, monthly_cashflow_avg, gig_platform_earnings }
 */
export async function calculateScore(scoringData) {
  return fetchJson('/score', {
    method: 'POST',
    body: JSON.stringify(scoringData),
  });
}

/**
 * Get latest verified score for a worker
 * @param {string} workerId 
 */
export async function getWorkerScore(workerId) {
  return fetchJson(`/score/${encodeURIComponent(workerId)}`, {
    method: 'GET',
  });
}
