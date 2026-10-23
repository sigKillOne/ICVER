import React, { useState } from 'react';
import {
  Shield,
  CheckCircle2,
  Lock,
  ArrowRight,
  Smartphone,
  CreditCard,
  AlertCircle,
} from 'lucide-react';
import { submitConsent } from '../services/api';
import { useVerification } from '../context/VerificationContext';
import { DEMO_WORKERS } from '../config/demoWorkers';

const IS_DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export default function ConsentScreen({ onConsentSuccess, savedConsent }) {
  const { runVerification } = useVerification();
  const [workerId, setWorkerId] = useState(savedConsent?.worker_id || '');
  const [phoneNumber, setPhoneNumber] = useState(savedConsent?.phone_number || '');
  const [agreedTerms, setAgreedTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [consentRecord, setConsentRecord] = useState(savedConsent || null);
  const [verification, setVerification] = useState(null);
  const [demoWorkerId, setDemoWorkerId] = useState('');
  const [error, setError] = useState('');

  const handleDemoWorkerChange = (event) => {
    const selectedWorkerId = event.target.value;
    setDemoWorkerId(selectedWorkerId);

    const selectedWorker = DEMO_WORKERS.find(
      (worker) => worker.worker_id === selectedWorkerId,
    );

    if (selectedWorker) {
      setWorkerId(selectedWorker.worker_id);
      setPhoneNumber(selectedWorker.phone_number);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!agreedTerms) {
      setError('You must grant data processing consent to proceed.');
      return;
    }

    setLoading(true);
    setError('');
    setVerification(null);

    try {
      const response = await submitConsent({
        worker_id: workerId,
        phone_number: phoneNumber,
        consent_given: agreedTerms,
        consent_purpose: 'Income verification for credit assessment',
      });

      const result = await runVerification({
        worker_id: response.worker_id,
        consent_id: response.consent_id,
        phone_number: response.phone_number,
      });

      if (!result) {
        setError('Verification could not be started. Please try again.');
        return;
      }

      setConsentRecord(response);
      setVerification(result);
    } catch (err) {
      if (err?.status === 403) {
        setError('Consent is not valid or has been revoked. Please try again.');
      } else if (err?.status === 503) {
        setError(
          'The repayment-risk signal is temporarily unavailable. Please try again later.',
        );
      } else {
        setError(
          err?.message ||
            'Failed to submit consent. Check that the backend API is running.',
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const recommendationCode = verification?.recommendation?.code;
  const hasInsufficientEvidence = recommendationCode === 'INSUFFICIENT_EVIDENCE';

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: '1px',
        background: 'var(--border)',
        border: '1px solid var(--border)',
        maxWidth: '800px',
      }}
    >
      <div style={{ background: 'var(--bg-card)', padding: '32px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            marginBottom: '16px',
          }}
        >
          <Shield size={20} color="var(--accent)" />
          <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Data Consent</h2>
        </div>
        <p
          style={{
            fontSize: '13px',
            color: 'var(--text-secondary)',
            marginBottom: '20px',
            lineHeight: 1.6,
          }}
        >
          ICVER verifies income for a lender&apos;s assessment using stored UPI
          evidence and, only when provided, bank SMS to cross-check income. ICVER
          does not approve or reject credit.
        </p>

        {error && (
          <div
            style={{
              background: 'var(--danger-subtle)',
              border: '1px solid #fecaca',
              padding: '10px 12px',
              color: 'var(--danger)',
              fontSize: '13px',
              marginBottom: '16px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {consentRecord ? (
          <div
            style={{
              background: 'var(--accent-subtle)',
              border: '1px solid #ccfbf1',
              padding: '24px',
              textAlign: 'center',
            }}
          >
            <CheckCircle2
              size={36}
              color="var(--accent)"
              style={{ margin: '0 auto 10px' }}
            />
            <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>
              Consent Recorded
            </h3>
            <p
              style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                marginBottom: '12px',
              }}
            >
              Consent ID:{' '}
              <span
                style={{
                  color: 'var(--accent)',
                  fontWeight: 600,
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {consentRecord.consent_id}
              </span>
            </p>
            <span className="badge badge-eligible" style={{ marginBottom: '16px' }}>
              {consentRecord.status}
            </span>

            <p
              style={{
                fontSize: '13px',
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
                marginTop: '16px',
              }}
            >
              {hasInsufficientEvidence
                ? 'Consent recorded. The available evidence is not sufficient for a full income verification. The lender may request additional documents.'
                : 'Consent recorded. Income verification is complete. The lender receives the verification result and makes the final credit decision.'}
            </p>

            <div style={{ marginTop: '16px' }}>
              <button
                className="btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => onConsentSuccess(consentRecord)}
              >
                Continue to Dashboard <ArrowRight size={14} />
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {IS_DEMO_MODE && (
              <div className="form-group">
                <label className="form-label" htmlFor="demo-worker-select">
                  Demo mode
                </label>
                <select
                  id="demo-worker-select"
                  className="form-input"
                  value={demoWorkerId}
                  onChange={handleDemoWorkerChange}
                >
                  <option value="">Select a seeded demo worker</option>
                  {DEMO_WORKERS.map((worker) => (
                    <option key={worker.worker_id} value={worker.worker_id}>
                      {worker.label} ({worker.worker_id})
                    </option>
                  ))}
                </select>
                <p
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    marginTop: '6px',
                  }}
                >
                  Demo mode prefills a seeded worker with made-up demonstration
                  data.
                </p>
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="worker-id">
                Worker ID
              </label>
              <input
                id="worker-id"
                type="text"
                className="form-input"
                value={workerId}
                onChange={(event) => setWorkerId(event.target.value)}
                placeholder="Enter worker ID"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="phone-number">
                Mobile Number
              </label>
              <input
                id="phone-number"
                type="text"
                className="form-input"
                value={phoneNumber}
                onChange={(event) => setPhoneNumber(event.target.value)}
                placeholder="Enter registered mobile number"
                required
              />
            </div>

            <div
              style={{
                margin: '16px 0',
                background: 'var(--bg-page)',
                padding: '14px',
                border: '1px solid var(--border)',
              }}
            >
              <span className="form-label" style={{ marginBottom: '10px' }}>
                Data Access Scopes
              </span>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  fontSize: '13px',
                  color: 'var(--text-primary)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <CreditCard size={14} color="var(--accent)" />
                  <span>UPI payment history (stored evidence)</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Smartphone size={14} color="var(--violet)" />
                  <span>
                    Bank SMS (optional, client-supplied, used only to cross-check)
                  </span>
                </div>
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                margin: '16px 0',
              }}
            >
              <input
                type="checkbox"
                id="consent-check"
                checked={agreedTerms}
                onChange={(event) => setAgreedTerms(event.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  marginTop: '2px',
                  accentColor: 'var(--accent)',
                  cursor: 'pointer',
                }}
              />
              <label
                htmlFor="consent-check"
                style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  lineHeight: 1.5,
                }}
              >
                I authorize ICVER to verify my income for a lender&apos;s
                assessment, not to generate a credit score. I understand the lender makes
                the final credit decision.
              </label>
            </div>

            <button
              type="submit"
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
              disabled={loading}
            >
              {loading ? 'Verifying…' : 'Authorize Access'}
            </button>
          </form>
        )}
      </div>

      <div
        style={{
          background: 'var(--bg-card)',
          padding: '32px',
          display: 'flex',
          flexDirection: 'column',
          gap: '1px',
        }}
      >
        <div style={{ marginBottom: '24px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '10px',
            }}
          >
            <Lock size={16} color="var(--accent)" />
            <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Privacy &amp; Data Use</h3>
          </div>
          <p
            style={{
              fontSize: '13px',
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
            }}
          >
            Your consent is recorded and can be revoked. Verification results are
            stored for the lender&apos;s assessment. Raw SMS text you provide is not
            stored.
          </p>
        </div>

        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>
            How It Works
          </h3>
          <ol
            style={{
              paddingLeft: '18px',
              fontSize: '13px',
              color: 'var(--text-secondary)',
              lineHeight: 1.8,
            }}
          >
            <li>Worker grants consent.</li>
            <li>Income is verified from stored evidence.</li>
            <li>
              A repayment-risk signal and a recommendation are produced for the
              lender.
            </li>
            <li>The lender makes the credit decision.</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
