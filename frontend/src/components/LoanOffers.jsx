import React, { useState, useEffect } from 'react';
import {
  Percent, ShieldCheck, ShieldAlert, Award, ArrowRight,
  Building2, CheckCircle2, XCircle, RefreshCw, Calculator,
  Landmark, FileText, Check, AlertCircle, Sparkles, IndianRupee
} from 'lucide-react';
import { motion } from 'framer-motion';
import { calculateScore } from '../services/api';

export default function LoanOffers({ consentRecord }) {
  const [loading, setLoading] = useState(false);
  const [scoreData, setScoreData] = useState(null);
  const [error, setError] = useState('');
  const [loanAmount, setLoanAmount] = useState(50000);
  const [loanTenure, setLoanTenure] = useState(12);
  const [appliedModal, setAppliedModal] = useState(null);

  const workerId = consentRecord?.worker_id || 'WRK-7712';
  const consentId = consentRecord?.consent_id || 'CNS-DEMO-2026';
  const phoneNumber = consentRecord?.phone_number || '9876543210';

  const fetchScore = async () => {
    setLoading(true);
    setError('');

    try {
      const payload = {
        worker_id: workerId,
        consent_id: consentId,
        phone_number: phoneNumber,
        upi_transaction_history: [],
        mobile_recharge_logs: [],
        monthly_cashflow_avg: 28500.0,
        gig_platform_earnings: 15000.0
      };

      const res = await calculateScore(payload);
      setScoreData(res);
      if (res?.max_loan_limit && res.max_loan_limit > 0) {
        setLoanAmount(Math.min(50000, Math.round(res.max_loan_limit)));
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch loan underwriting terms.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScore();
  }, [consentRecord]);

  // Extract Pricing & Underwriting Fields from API response
  const interestRateApr = scoreData?.interest_rate_apr ?? 0.0;
  const maxLoanLimit = scoreData?.max_loan_limit ?? 0.0;
  const estimatedEmi = scoreData?.estimated_emi ?? 0.0;
  const rbiCompliant = scoreData?.rbi_compliant ?? true;
  const foirPercentage = scoreData?.foir_percentage ?? 12.0;
  const scoreVal = scoreData?.creditworthiness_score ?? 78;
  const isGigWorker = scoreData?.is_gig_worker ?? false;

  // Custom EMI calculation for interactive calculator
  const calculateCustomEmi = (principal, tenureMonths, apr) => {
    if (!rbiCompliant || apr <= 0 || tenureMonths <= 0) return 0.0;
    const r = (apr / 100.0) / 12.0;
    const n = tenureMonths;
    const numerator = principal * r * Math.pow(1.0 + r, n);
    const denominator = Math.pow(1.0 + r, n) - 1.0;
    return Math.round((numerator / denominator) * 100) / 100;
  };

  const customEmi = calculateCustomEmi(loanAmount, loanTenure, interestRateApr);

  return (
    <div style={{ maxWidth: '1100px' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Pre-Approved Loan Offers</h2>
            <span
              className="badge"
              style={
                rbiCompliant
                  ? { background: 'var(--accent-subtle)', color: 'var(--accent)', border: '1px solid #ccfbf1' }
                  : { background: 'var(--danger-subtle)', color: 'var(--danger)', border: '1px solid #fecaca' }
              }
            >
              {rbiCompliant ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
              {rbiCompliant ? 'RBI COMPLIANT SANCTION' : 'SANCTION RESTRICTED'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            Dynamic underwriting and risk-based loan pricing calibrated to UPI cashflow velocity.
          </p>
        </div>
        <button className="btn-secondary" onClick={fetchScore} disabled={loading} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <RefreshCw size={14} className={loading ? 'animate-pulse' : ''} />
          {loading ? 'Refreshing…' : 'Re-calculate Offers'}
        </button>
      </div>

      {/* Prominent Banner if Non-Compliant */}
      {scoreData && !rbiCompliant && (
        <div style={{
          background: 'var(--danger-subtle)',
          border: '1px solid #fca5a5',
          borderLeft: '5px solid var(--danger)',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          flexWrap: 'wrap'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <ShieldAlert size={26} color="var(--danger)" style={{ flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--danger)', marginBottom: '2px' }}>
                Credit Sanctions Paused: RBI 50% Household Debt Cap Exceeded (FOIR: {foirPercentage.toFixed(1)}%)
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Statutory MFI ceiling prevents additional loan disbursement until existing debt servicing drops below 50% of monthly household income.
              </div>
            </div>
          </div>
          <span style={{
            background: 'var(--danger)', color: '#ffffff', padding: '4px 12px',
            fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em'
          }}>
            OFFER RESTRICTED
          </span>
        </div>
      )}

      {/* Risk-Based Pricing Offer Card */}
      <div
        className="glass-card"
        style={{
          marginBottom: '24px',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          ...(rbiCompliant
            ? { borderTop: '3px solid var(--accent)' }
            : {
                opacity: 0.65,
                background: '#f5f5f4',
                border: '1px dashed #d6d3d1'
              })
        }}
      >
        <div>
          <div className="card-header" style={{ marginBottom: '16px' }}>
            <h3 className="card-title">
              <Percent size={14} color={rbiCompliant ? "var(--accent)" : "var(--text-tertiary)"} /> Risk-Based Pricing Offer
            </h3>
            <span
              className="badge"
              style={
                rbiCompliant
                  ? { background: 'var(--accent-subtle)', color: 'var(--accent)', border: '1px solid #ccfbf1' }
                  : { background: 'var(--danger-subtle)', color: 'var(--danger)', border: '1px solid #fecaca' }
              }
            >
              {rbiCompliant ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
              {rbiCompliant ? 'PRE-APPROVED PRICING' : 'OFFER UNAVAILABLE'}
            </span>
          </div>

          {rbiCompliant ? (
            <>
              {/* Metric Highlights Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                {/* Approved APR */}
                <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Approved APR (%)
                  </div>
                  <div style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                    {loading ? '—' : `${interestRateApr.toFixed(1)}%`}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Risk Tier: {scoreVal >= 80 ? 'Prime (Score ≥ 80)' : scoreVal >= 60 ? 'Standard (Score 60-79)' : 'Subprime (Score < 60)'}
                  </div>
                </div>

                {/* Maximum Sanction Limit */}
                <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Maximum Sanction Limit (₹)
                  </div>
                  <div style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    {loading ? '—' : `₹${Math.round(maxLoanLimit).toLocaleString('en-IN')}`}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    12-Month Conservative Surplus Buffer
                  </div>
                </div>

                {/* Benchmark Baseline EMI */}
                <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Baseline EMI (₹50k / 12m)
                  </div>
                  <div style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    {loading ? '—' : `₹${estimatedEmi.toLocaleString('en-IN')}`}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Standard Amortisation Schedule
                  </div>
                </div>
              </div>

              {/* Quick Summary Callout */}
              <div style={{
                background: 'var(--accent-subtle)',
                border: '1px solid #ccfbf1',
                borderLeft: '4px solid var(--accent)',
                padding: '14px 18px',
                marginBottom: '10px'
              }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent)', lineHeight: 1.5 }}>
                  Estimated EMI for ₹50,000 over 12 months: ₹{estimatedEmi}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Calculated using standard annuity amortisation formula at {interestRateApr.toFixed(1)}% APR.
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Greyed-out or 'Offer Unavailable' state */}
              <div style={{
                background: '#fecaca30',
                border: '1px solid #fca5a5',
                borderLeft: '4px solid var(--danger)',
                padding: '16px',
                marginBottom: '16px'
              }}>
                <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--danger)', marginBottom: '4px' }}>
                  Offer Unavailable
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  Lending restricted under RBI 50% FOIR statutory ceiling. Total monthly obligations consume {foirPercentage.toFixed(1)}% of household income. Deleveraging required before fresh credit sanctions can be approved.
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                <div style={{ background: '#f5f5f4', border: '1px solid #e7e5e4', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Approved APR (%)
                  </div>
                  <div style={{ fontSize: '26px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                    0.0%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                    Pricing Disabled (Non-Compliant)
                  </div>
                </div>

                <div style={{ background: '#f5f5f4', border: '1px solid #e7e5e4', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Maximum Sanction Limit (₹)
                  </div>
                  <div style={{ fontSize: '26px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                    ₹0.00
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                    Zero Sanction Permitted
                  </div>
                </div>

                <div style={{ background: '#f5f5f4', border: '1px solid #e7e5e4', padding: '16px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                    Baseline EMI
                  </div>
                  <div style={{ fontSize: '26px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                    ₹0.00
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                    No Active Loan Facility
                  </div>
                </div>
              </div>

              <div style={{
                background: '#f5f5f4',
                border: '1px solid #e7e5e4',
                padding: '12px 16px',
                fontSize: '12px',
                color: 'var(--text-tertiary)',
                marginBottom: '10px'
              }}>
                Estimated EMI for ₹50,000 over 12 months: ₹{estimatedEmi}
              </div>
            </>
          )}
        </div>

        <div style={{ marginTop: '12px', fontSize: '11px', color: 'var(--text-tertiary)', borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
          Dynamic risk pricing matrix governed by RBI/2021-22/185 Master Direction for Microfinance Loans.
        </div>
      </div>

      {/* Interactive EMI Simulator & Product Cards Section */}
      {rbiCompliant ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
          {/* Interactive EMI Calculator Card */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div className="card-header">
              <h3 className="card-title">
                <Calculator size={14} color="var(--accent)" /> Interactive Sanction Calculator
              </h3>
              <span className="badge badge-eligible">{interestRateApr.toFixed(1)}% APR</span>
            </div>

            <div style={{ marginBottom: '18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Select Loan Amount:</span>
                <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                  ₹{loanAmount.toLocaleString('en-IN')}
                </span>
              </div>
              <input
                type="range"
                min={10000}
                max={Math.max(50000, Math.round(maxLoanLimit))}
                step={5000}
                value={loanAmount}
                onChange={(e) => setLoanAmount(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--accent)' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                <span>₹10,000</span>
                <span>Max Sanction: ₹{Math.round(maxLoanLimit).toLocaleString('en-IN')}</span>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Select Repayment Tenure:</span>
                <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                  {loanTenure} Months
                </span>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                {[6, 12, 18, 24].map((tenure) => (
                  <button
                    key={tenure}
                    type="button"
                    onClick={() => setLoanTenure(tenure)}
                    className={loanTenure === tenure ? 'btn-primary' : 'btn-secondary'}
                    style={{ flex: 1, padding: '8px', fontSize: '12px', justifyContent: 'center' }}
                  >
                    {tenure}M
                  </button>
                ))}
              </div>
            </div>

            <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '16px', marginBottom: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '2px' }}>
                Calculated Monthly EMI
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                ₹{customEmi.toLocaleString('en-IN')} <span style={{ fontSize: '13px', fontWeight: 400, color: 'var(--text-secondary)' }}>/ month</span>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Total repayment: ₹{(customEmi * loanTenure).toLocaleString('en-IN')} (Includes ₹{(customEmi * loanTenure - loanAmount).toLocaleString('en-IN')} total interest)
              </div>
            </div>

            <button
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
              onClick={() => setAppliedModal({ amount: loanAmount, tenure: loanTenure, emi: customEmi, partner: 'CreditAccess Grameen / NABFINS' })}
            >
              Apply for Sanction <ArrowRight size={14} />
            </button>
          </div>

          {/* Pre-Approved Partner Offer Cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Offer 1: Microfinance Income Generation Loan */}
            <div className="glass-card" style={{ padding: '20px', borderLeft: '4px solid var(--accent)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--accent)', textTransform: 'uppercase' }}>
                    Karnataka MFI Partner
                  </div>
                  <h4 style={{ fontSize: '15px', fontWeight: 600, marginTop: '2px' }}>
                    CreditAccess Grameen / NABFINS
                  </h4>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '2px 0 0' }}>
                    Microfinance Income Generation Loan (IGL)
                  </p>
                </div>
                <span className="badge badge-eligible">{interestRateApr.toFixed(1)}% APR</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', margin: '12px 0', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--text-tertiary)' }}>Sanction Limit:</span>{' '}
                  <strong style={{ fontFamily: 'var(--font-mono)' }}>₹{Math.round(maxLoanLimit).toLocaleString('en-IN')}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-tertiary)' }}>Processing Fee:</span>{' '}
                  <strong>Zero (MFI Scheme)</strong>
                </div>
              </div>
              <button
                className="btn-secondary"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => setAppliedModal({ amount: Math.min(50000, maxLoanLimit), tenure: 12, emi: estimatedEmi, partner: 'CreditAccess Grameen' })}
              >
                Select CreditAccess Grameen
              </button>
            </div>

            {/* Offer 2: Gig Enterprise Credit or PM SVANidhi */}
            <div className="glass-card" style={{ padding: '20px', borderLeft: isGigWorker ? '4px solid #f59e0b' : '4px solid #2563eb' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: isGigWorker ? '#b45309' : '#2563eb', textTransform: 'uppercase' }}>
                    {isGigWorker ? 'Mobility / Delivery Partner Credit' : 'Urban Street Livelihood'}
                  </div>
                  <h4 style={{ fontSize: '15px', fontWeight: 600, marginTop: '2px' }}>
                    {isGigWorker ? 'Ujjivan SFB / Northern Arc Capital' : 'PM SVANidhi Micro-Credit (Jana SFB)'}
                  </h4>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '2px 0 0' }}>
                    {isGigWorker ? 'Gig Enterprise Working Capital' : 'Urban Livelihood Working Capital'}
                  </p>
                </div>
                <span className="badge" style={{ background: isGigWorker ? '#fef3c7' : '#eff6ff', color: isGigWorker ? '#b45309' : '#2563eb' }}>
                  {isGigWorker ? `${interestRateApr.toFixed(1)}% APR` : '7% Subsidized'}
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', margin: '12px 0', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--text-tertiary)' }}>Sanction Limit:</span>{' '}
                  <strong style={{ fontFamily: 'var(--font-mono)' }}>₹{Math.round(maxLoanLimit).toLocaleString('en-IN')}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-tertiary)' }}>Disbursal:</span>{' '}
                  <strong>Instant UPI Payout</strong>
                </div>
              </div>
              <button
                className="btn-secondary"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => setAppliedModal({ amount: Math.min(30000, maxLoanLimit), tenure: 12, emi: estimatedEmi, partner: isGigWorker ? 'Ujjivan SFB' : 'PM SVANidhi' })}
              >
                Select {isGigWorker ? 'Ujjivan SFB' : 'PM SVANidhi'}
              </button>
            </div>
          </div>
        </div>
      ) : (
        /* If non-compliant, explain how to become eligible */
        <div className="glass-card" style={{ padding: '28px', textAlign: 'center' }}>
          <ShieldAlert size={36} color="var(--danger)" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>
            No Active Sanctions Available Under Current Debt Profile
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '600px', margin: '0 auto 18px', lineHeight: 1.6 }}>
            Your current debt obligations account for {foirPercentage.toFixed(1)}% of household income, which exceeds the RBI 50% statutory threshold. You can simulate debt paydowns in the What-If Simulator on the Dashboard to see when pre-approved pricing unlocks.
          </p>
          <a href="/worker/dashboard" className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            Go to What-If Simulator <ArrowRight size={14} />
          </a>
        </div>
      )}

      {/* Applied Modal */}
      {appliedModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px'
        }}>
          <div className="glass-card" style={{ background: '#ffffff', maxWidth: '440px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ textAlign: 'center', marginBottom: '16px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'var(--accent-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px' }}>
                <Check size={24} color="var(--accent)" />
              </div>
              <h3 style={{ fontSize: '17px', fontWeight: 700 }}>Loan Sanction In Progress</h3>
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Application initiated with {appliedModal.partner}
              </p>
            </div>

            <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '14px', marginBottom: '18px', fontSize: '13px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Sanction Amount:</span>
                <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>₹{appliedModal.amount.toLocaleString('en-IN')}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Repayment Tenure:</span>
                <span style={{ fontWeight: 600 }}>{appliedModal.tenure} Months</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Approved APR:</span>
                <span style={{ fontWeight: 700, color: 'var(--accent)' }}>{interestRateApr.toFixed(1)}%</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '6px', marginTop: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Monthly EMI:</span>
                <span style={{ fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>₹{appliedModal.emi.toLocaleString('en-IN')}</span>
              </div>
            </div>

            <button
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => setAppliedModal(null)}
            >
              Acknowledge & Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
