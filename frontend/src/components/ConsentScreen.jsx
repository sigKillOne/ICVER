import React, { useState } from 'react';
import { Shield, CheckCircle2, Lock, ArrowRight, Smartphone, CreditCard, Layers, AlertCircle } from 'lucide-react';
import { submitConsent, calculateScore } from '../services/api';

export default function ConsentScreen({ onConsentSuccess, savedConsent }) {
  const [workerId, setWorkerId] = useState(savedConsent?.worker_id || 'WRK-7712');
  const [phoneNumber, setPhoneNumber] = useState('+91 98765 43210');
  const [agreedTerms, setAgreedTerms] = useState(true);
  const [loading, setLoading] = useState(false);
  const [consentRecord, setConsentRecord] = useState(savedConsent || null);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!agreedTerms) {
      setError('You must grant data processing consent to proceed.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await submitConsent({
        worker_id: workerId,
        phone_number: phoneNumber,
        consent_given: agreedTerms,
        consent_purpose: 'Income verification for credit assessment'
      });

      // Verify that records exist for this phone number
      try {
        await calculateScore({
          worker_id: workerId,
          consent_id: response.consent_id,
          phone_number: phoneNumber
        });
      } catch (scoreErr) {
        if (scoreErr.message && scoreErr.message.includes('No financial records found')) {
          setError('No records found for this mobile number.');
          setLoading(false);
          return;
        }
        throw scoreErr;
      }

      setConsentRecord(response);
      if (onConsentSuccess) {
        onConsentSuccess(response);
      }
    } catch (err) {
      if (err.message && err.message.includes('No financial records found')) {
          setError('No records found for this mobile number.');
      } else {
          setError(err.message || 'Failed to submit consent. Ensure FastAPI server is running on port 8000.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1px', background: 'var(--border)', border: '1px solid var(--border)', maxWidth: '800px' }}>
      {/* Left: Consent Form */}
      <div style={{ background: 'var(--bg-card)', padding: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
          <Shield size={20} color="var(--accent)" />
          <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Data Consent</h2>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: 1.6 }}>
          Grant permission for ICVER to aggregate UPI transactions, mobile recharges, and gig income to verify your financial profile.
        </p>

        {error && (
          <div style={{
            background: 'var(--danger-subtle)',
            border: '1px solid #fecaca',
            padding: '10px 12px',
            color: 'var(--danger)',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {consentRecord ? (
          <div style={{
            background: 'var(--accent-subtle)',
            border: '1px solid #ccfbf1',
            padding: '24px',
            textAlign: 'center'
          }}>
            <CheckCircle2 size={36} color="var(--accent)" style={{ margin: '0 auto 10px' }} />
            <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>Consent Recorded</h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Consent ID: <span style={{ color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{consentRecord.consent_id}</span>
            </p>
            <span className="badge badge-eligible" style={{ marginBottom: '16px' }}>
              {consentRecord.status}
            </span>

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
            <div className="form-group">
              <label className="form-label">Worker ID</label>
              <input
                type="text"
                className="form-input"
                value={workerId}
                onChange={(e) => setWorkerId(e.target.value)}
                placeholder="e.g. WRK-7712"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Mobile Number</label>
              <input
                type="text"
                className="form-input"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="+91 98765 43210"
                required
              />
            </div>

            {/* Data scopes */}
            <div style={{ margin: '16px 0', background: 'var(--bg-page)', padding: '14px', border: '1px solid var(--border)' }}>
              <span className="form-label" style={{ marginBottom: '10px' }}>Data Access Scopes</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px', color: 'var(--text-primary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <CreditCard size={14} color="var(--accent)" />
                  <span>UPI Payment History</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Smartphone size={14} color="var(--violet)" />
                  <span>Mobile Recharge Logs</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={14} color="var(--accent)" />
                  <span>Gig Platform Payouts</span>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', margin: '16px 0' }}>
              <input
                type="checkbox"
                id="consent-check"
                checked={agreedTerms}
                onChange={(e) => setAgreedTerms(e.target.checked)}
                style={{ width: '16px', height: '16px', marginTop: '2px', accentColor: 'var(--accent)', cursor: 'pointer' }}
              />
              <label htmlFor="consent-check" style={{ fontSize: '12px', color: 'var(--text-secondary)', cursor: 'pointer', lineHeight: 1.5 }}>
                I authorize ICVER to verify my informal income records for credit scoring. Data is encrypted and governed by DPDP regulations.
              </label>
            </div>

            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
              {loading ? 'Submitting…' : 'Authorize Access'}
            </button>
          </form>
        )}
      </div>

      {/* Right: Trust info */}
      <div style={{ background: 'var(--bg-card)', padding: '32px', display: 'flex', flexDirection: 'column', gap: '1px' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
            <Lock size={16} color="var(--accent)" />
            <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Privacy & Encryption</h3>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Banking credentials are never stored. Data is evaluated statelessly to produce an aggregated score and income estimate.
          </p>
        </div>

        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px' }}>How It Works</h3>
          <ol style={{ paddingLeft: '18px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            <li>Worker grants one-time consent.</li>
            <li>UPI & recharge patterns are aggregated.</li>
            <li>SHAP-explainable model scores cashflow.</li>
            <li>Lenders receive a verified score (0–100).</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
