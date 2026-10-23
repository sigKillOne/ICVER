const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1';
const API_BASE_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');

/**
 * Build a readable message from a FastAPI error detail value.
 * @param {unknown} detail
 * @param {number} status
 * @returns {string}
 */
function formatApiErrorDetail(detail, status) {
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') {
          return item;
        }
        if (item && typeof item === 'object') {
          if (typeof item.msg === 'string') {
            return item.msg;
          }
          if (typeof item.message === 'string') {
            return item.message;
          }
        }
        return '';
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join('; ');
    }
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message;
  }

  return `API request failed with status ${status}`;
}

/**
 * Helper to handle fetch requests with readable error handling.
 * @param {string} endpoint
 * @param {RequestInit} [options]
 * @returns {Promise<unknown>}
 */
async function fetchJson(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  let response;
  try {
    response = await fetch(url, config);
  } catch (error) {
    if (error && error.name === 'AbortError') {
      throw error;
    }

    const networkError = new Error(
      `Unable to reach the ICVER API at ${API_BASE_URL}. Check that the backend is running and VITE_API_URL is set correctly.`,
    );
    networkError.status = null;
    networkError.detail = null;
    throw networkError;
  }

  if (!response.ok) {
    let errorData = null;
    try {
      errorData = await response.json();
    } catch {
      errorData = null;
    }

    const detail =
      errorData &&
      typeof errorData === 'object' &&
      Object.prototype.hasOwnProperty.call(errorData, 'detail')
        ? errorData.detail
        : null;

    const requestError = new Error(formatApiErrorDetail(detail, response.status));
    requestError.status = response.status;
    requestError.detail = detail;
    throw requestError;
  }

  return response.json();
}

/**
 * Record worker data access consent.
 * @param {Object} consentData
 * @param {string} consentData.worker_id
 * @param {string} consentData.phone_number
 * @param {boolean} consentData.consent_given
 * @param {string} consentData.consent_purpose
 * @returns {Promise<{consent_id: string, worker_id: string, phone_number: string, status: string, message: string, created_at: string}>}
 */
export async function submitConsent(consentData) {
  return fetchJson('/consent', {
    method: 'POST',
    body: JSON.stringify(consentData),
  });
}

/**
 * Fetch consent status by consent ID.
 * @param {string} consentId
 * @returns {Promise<{consent_id: string, worker_id: string, phone_number: string, status: string, message: string, created_at: string}>}
 */
export async function getConsentStatus(consentId) {
  return fetchJson(`/consent/${encodeURIComponent(consentId)}`, {
    method: 'GET',
  });
}

/**
 * Revoke a previously recorded consent.
 * @param {string} consentId
 * @returns {Promise<{consent_id: string, worker_id: string, phone_number: string, status: string, message: string, created_at: string}>}
 */
export async function revokeConsent(consentId) {
  return fetchJson(`/consent/${encodeURIComponent(consentId)}/revoke`, {
    method: 'POST',
  });
}

/**
 * Verify income and obtain repayment-risk decision support.
 * @param {Object} payload
 * @param {string} payload.worker_id
 * @param {string} [payload.consent_id]
 * @param {string} [payload.phone_number]
 * @param {number} [payload.stated_monthly_income]
 * @param {Object<string, number>} [payload.monthly_outgoings]
 * @param {number} [payload.household_size]
 * @param {string} [payload.occupation_type]
 * @param {Array<{text: string, received_at: string}>} [payload.sms_log]
 * @param {number} [payload.proposed_emi]
 * @param {number} [payload.tenure_months]
 * @returns {Promise<{
 *   verification_id: string,
 *   worker_id: string,
 *   consent_id: string,
 *   created_at: string,
 *   income: {low: number|null, mid: number|null, high: number|null, conservative: number|null, stated: number|null, stated_vs_evidence_ratio: number|null},
 *   expenses: {estimated: number|null, complete: boolean},
 *   surplus_conservative: number|null,
 *   evidence: {confidence_score: number, confidence_level: string, confidence_capped: boolean, components: Object, months: number, provenance: Object, flags: Array<Object>, reasons: Array<string>, consistency_note: string|null},
 *   affordability: {foir_current: number|null, foir_with_proposed: number|null, foir_cap: number, max_affordable_emi: number|null},
 *   risk_signal: {available: boolean, display_priority: string, display_note: string|null, band: string|null, risk_score_0_100: number|null, reference_population_pd: number|null, reference_note: string|null, reliability: string|null, reliability_note: string|null, inputs_provided_count: number, inputs_missing: Array<string>, top_factors_raising_risk: Array<Object>, top_factors_lowering_risk: Array<Object>, reason: string|null},
 *   recommendation: {code: string, reasons: Array<string>, caveats: Array<string>},
 *   sms_summary: {received: number, used: number, dropped: number, dropped_by_reason: Object, clipped_months: Array<Object>, monthly_credits: Object},
 *   model_version: string,
 *   engine_version: string,
 *   sms_ignored_reason: string|null,
 *   data_notice: string|null,
 *   disclaimer: string
 * }>}
 */
export async function verifyWorker(payload) {
  return fetchJson('/verify', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieve a previously stored verification result.
 * @param {string} verificationId
 * @param {string} consentId
 * @returns {Promise<Object>} The stored verification response.
 */
export async function getVerification(verificationId, consentId) {
  const params = new URLSearchParams();
  if (consentId) {
    params.set('consent_id', consentId);
  }

  const query = params.toString();
  return fetchJson(
    `/verify/${encodeURIComponent(verificationId)}${query ? `?${query}` : ''}`,
    {
      method: 'GET',
    },
  );
}

/**
 * Preview a hypothetical verification scenario without persisting it.
 * @param {Object} payload
 * @param {string} payload.worker_id
 * @param {string} [payload.consent_id]
 * @param {string} [payload.phone_number]
 * @param {Array<number>} [payload.hypothetical_upi_monthly_inflows]
 * @param {Array<number>} [payload.hypothetical_unique_senders]
 * @param {number} [payload.stated_monthly_income]
 * @param {Object<string, number>} [payload.monthly_outgoings]
 * @param {number} [payload.household_size]
 * @param {number} [payload.proposed_emi]
 * @param {number} [payload.tenure_months]
 * @returns {Promise<{
 *   hypothetical: boolean,
 *   baseline: {income_low: number|null, income_mid: number|null, surplus_conservative: number|null, confidence_score: number, confidence_level: string, max_affordable_emi: number|null, flags: Array<Object>, recommendation_code: string},
 *   scenario: {income_low: number|null, income_mid: number|null, surplus_conservative: number|null, confidence_score: number, confidence_level: string, max_affordable_emi: number|null, flags: Array<Object>, hypothetical_recommendation_code: string},
 *   deltas: {income_low: number|null, surplus: number|null, max_affordable_emi: number|null, confidence_score: number|null},
 *   notes: Array<string>,
 *   data_notice: string|null,
 *   disclaimer: string
 * }>}
 */
export async function whatIf(payload) {
  return fetchJson('/verify/what-if', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * @deprecated Use verifyWorker() for the current income-verification flow.
 * Legacy scoring endpoint retained for backwards compatibility.
 * @param {Object} scoringData
 * @param {string} scoringData.worker_id
 * @param {string} scoringData.consent_id
 * @param {string} [scoringData.phone_number]
 * @param {string} [scoringData.sms_log] Raw SMS text, accepted only by the legacy endpoint.
 * @param {Array<Object>} [scoringData.upi_transaction_history]
 * @param {Array<Object>} [scoringData.mobile_recharge_logs]
 * @param {number} [scoringData.monthly_cashflow_avg]
 * @param {number} [scoringData.gig_platform_earnings]
 * @returns {Promise<Object>} Legacy scoring response.
 */
export async function calculateScore(scoringData) {
  return fetchJson('/score', {
    method: 'POST',
    body: JSON.stringify(scoringData),
  });
}

/**
 * @deprecated Use getVerification() for persisted verification results.
 * Get the latest legacy score for a worker.
 * @param {string} workerId
 * @returns {Promise<Object>} Legacy scoring response.
 */
export async function getWorkerScore(workerId) {
  return fetchJson(`/score/${encodeURIComponent(workerId)}`, {
    method: 'GET',
  });
}
