import React, { useState, useEffect } from 'react';
import {
  Award, Zap, CheckCircle, RefreshCw, AlertCircle,
  Lightbulb, Users, CalendarCheck, Star, Clock, Briefcase, BarChart3,
  ShieldCheck, ShieldAlert, Landmark, Building2, Wallet, Scale, CheckCircle2, XCircle, Percent
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import { calculateScore } from '../services/api';
import WhatIfSimulator from './WhatIfSimulator';
import { motion } from 'framer-motion';

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } }
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } }
};

const mockChartData = [
  { name: 'Apr', inflow: 18000 },
  { name: 'May', inflow: 22000 },
  { name: 'Jun', inflow: 19500 },
  { name: 'Jul', inflow: 28000 },
  { name: 'Aug', inflow: 25000 },
  { name: 'Sep', inflow: 31000 },
];

export default function ScoreDashboard({ consentRecord }) {
  const [loading, setLoading] = useState(false);
  const [scoreData, setScoreData] = useState(null);
  const [error, setError] = useState('');

  const [workerId, setWorkerId] = useState(consentRecord?.worker_id || 'WRK-7712');
  const [consentId, setConsentId] = useState(consentRecord?.consent_id || 'CNS-DEMO-2026');
  const [phoneNumber, setPhoneNumber] = useState(consentRecord?.phone_number || '9876543210');
  const [monthlyCashflow, setMonthlyCashflow] = useState(28500);
  const [gigEarnings, setGigEarnings] = useState(15000);

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
        monthly_cashflow_avg: parseFloat(monthlyCashflow),
        gig_platform_earnings: parseFloat(gigEarnings)
      };

      const res = await calculateScore(payload);
      setScoreData(res);
    } catch (err) {
      setError(err.message || 'Failed to calculate income verification score.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScore();
  }, []);

  const radius = 65;
  const circumference = 2 * Math.PI * radius;
  const scoreVal = scoreData?.creditworthiness_score ?? 78;
  const strokeDashoffset = circumference - (scoreVal / 100) * circumference;

  const isGigWorker = scoreData?.is_gig_worker ?? false;

  // --- Regulatory & Underwriting Fields from /score response ---
  const foirPercentage = scoreData?.foir_percentage ?? 12.0;
  const availableSurplus = scoreData?.available_surplus ?? 7000.0;
  const rbiCompliant = scoreData?.rbi_compliant ?? true;
  const rbiMaxCap = scoreData?.rbi_max_cap ?? 50.0;

  // --- Dynamic Risk-Based Pricing Engine Fields ---
  const interestRateApr = scoreData?.interest_rate_apr ?? 0.0;
  const maxLoanLimit = scoreData?.max_loan_limit ?? 0.0;
  const estimatedEmi = scoreData?.estimated_emi ?? 0.0;

  // --- Institutional Partner Match Logic (Karnataka MFI / SFB Ecosystem) ---
  const getPartnerMatch = () => {
    if (!rbiCompliant || foirPercentage > 50.0) {
      return {
        personaTitle: 'Over-Indebted (Non-Compliant)',
        displayMatch: 'Partner Status: Ineligible for new MFI credit under RBI 50% FOIR Guidelines',
        partner: 'No MFI Underwriting Permitted',
        scheme: 'Restricted by RBI 50% FOIR Cap',
        isEligible: false,
        badgeStyle: { background: 'var(--danger-subtle)', color: 'var(--danger)', border: '1px solid #fecaca' },
        description: 'Borrower total debt service exceeds 50% of monthly household income. Mandatory deleveraging required before fresh credit sanctions.'
      };
    }

    if (isGigWorker) {
      return {
        personaTitle: 'Gig Worker (Compliant)',
        displayMatch: 'Target Partner Match: Ujjivan SFB / Northern Arc Capital (Gig Enterprise Credit)',
        partner: 'Ujjivan SFB / Northern Arc Capital',
        scheme: 'Gig Enterprise Credit',
        isEligible: true,
        badgeStyle: { background: '#fef3c7', color: '#b45309', border: '1px solid #fde68a' },
        description: 'Tailored for mobility and delivery partners with verified platform ratings, active weekly gig hours, and digital payout stability.'
      };
    }

    const incomeEst = scoreData?.verified_income_estimate ?? 25000;
    if (incomeEst < 20000 || (scoreData?.unique_sender_count && scoreData.unique_sender_count < 10)) {
      return {
        personaTitle: 'Low-Ticket / Street Vendor',
        displayMatch: 'Target Partner Match: PM SVANidhi Scheme (Jana SFB / Ujjivan SFB)',
        partner: 'Jana SFB / Ujjivan SFB',
        scheme: 'PM SVANidhi Scheme (Urban Livelihood Credit)',
        isEligible: true,
        badgeStyle: { background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe' },
        description: 'Government-backed micro working capital with 7% interest subsidy on digital transaction adoption and timely repayment cycles.'
      };
    }

    return {
      personaTitle: 'Standard Vendor (Compliant)',
      displayMatch: 'Target Partner Match: CreditAccess Grameen / NABFINS (Microfinance Income Generation Loan)',
      partner: 'CreditAccess Grameen / NABFINS',
      scheme: 'Microfinance Income Generation Loan (IGL)',
      isEligible: true,
      badgeStyle: { background: 'var(--accent-subtle)', color: 'var(--accent)', border: '1px solid #ccfbf1' },
      description: 'Karnataka MFI partner facility for registered retail and kirana vendors with proven UPI cashflow turnover and healthy repayment buffers.'
    };
  };

  const partnerInfo = getPartnerMatch();

  return (
    <div>
      {/* Page header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Dashboard</h2>
            {isGigWorker && (
              <span className="badge badge-gig" style={{ background: '#f59e0b20', color: '#b45309', border: '1px solid #f59e0b40', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', borderRadius: '16px', fontSize: '12px', fontWeight: 600 }}>
                <Briefcase size={12} /> Verified Gig Partner
              </span>
            )}
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Financial overview, RBI regulatory compliance, and ML credit scoring status.</p>
        </div>
        <button className="btn-primary" onClick={fetchScore} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-pulse' : ''} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Prominent Red Alert Banner if Non-Compliant with RBI FOIR Cap */}
      {scoreData && !rbiCompliant && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            background: 'var(--danger-subtle)',
            border: '1px solid #fca5a5',
            borderLeft: '5px solid var(--danger)',
            padding: '16px 20px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            flexWrap: 'wrap'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <ShieldAlert size={26} color="var(--danger)" style={{ flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--danger)', marginBottom: '2px' }}>
                RBI Guardrail Violation: Debt Burden Exceeds 50% Cap (FOIR: {foirPercentage.toFixed(1)}%)
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Statutory MFI underwriting limit breached. Monthly debt obligations account for {foirPercentage.toFixed(1)}% of household income (limit: {rbiMaxCap}%). Credit decision automatically overridden to <strong>High Risk</strong>.
              </div>
            </div>
          </div>
          <span style={{
            background: 'var(--danger)', color: '#ffffff', padding: '4px 12px',
            fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em'
          }}>
            NON-COMPLIANT
          </span>
        </motion.div>
      )}

      <motion.div
        className="dashboard-grid"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >

        {/* Score card with Dial and RBI FOIR Compliance Badge */}
        <motion.div variants={itemVariants} className="glass-card grid-col-4" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '28px 24px' }}>
          <div className="card-header" style={{ width: '100%', justifyContent: 'center' }}>
            <h3 className="card-title">
              <Award size={14} color="var(--accent)" /> Credit Score
            </h3>
          </div>

          <div className="score-circle-container" style={{ margin: '8px 0' }}>
            <svg className="score-circle-svg" viewBox="0 0 160 160">
              <defs>
                <linearGradient id="score-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor={rbiCompliant ? "#0f766e" : "#dc2626"} />
                  <stop offset="100%" stopColor={rbiCompliant ? "#0d9488" : "#ef4444"} />
                </linearGradient>
              </defs>
              <circle className="score-circle-bg" cx="80" cy="80" r={radius} />
              <circle
                className="score-circle-bar"
                cx="80"
                cy="80"
                r={radius}
                style={{
                  stroke: rbiCompliant ? 'var(--accent)' : 'var(--danger)',
                  strokeDasharray: circumference,
                  strokeDashoffset: loading ? circumference : strokeDashoffset
                }}
              />
            </svg>
            <div className="score-number-overlay">
              <span className="score-val" style={{ color: rbiCompliant ? 'inherit' : 'var(--danger)' }}>
                {loading ? '—' : scoreVal}
              </span>
              <span className="score-max">out of 100</span>
            </div>
          </div>

          <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', width: '100%' }}>
            <span className={`badge ${rbiCompliant ? 'badge-eligible' : ''}`} style={!rbiCompliant ? { background: 'var(--danger-subtle)', color: 'var(--danger)', border: '1px solid #fecaca' } : {}}>
              {rbiCompliant ? <CheckCircle size={12} /> : <AlertCircle size={12} />} {scoreData?.decision_tier || (rbiCompliant ? 'Eligible' : 'High Risk')}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              Confidence: {scoreData ? `${(scoreData.confidence_score * 100).toFixed(0)}%` : '89%'}
            </span>

            {/* Dedicated RBI FOIR Compliance Badge / Card near Dial */}
            {scoreData && (
              <div style={{ marginTop: '6px', width: '100%' }}>
                {rbiCompliant ? (
                  <div style={{
                    background: 'var(--accent-subtle)',
                    border: '1px solid #ccfbf1',
                    color: 'var(--accent)',
                    padding: '8px 12px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    textAlign: 'center',
                    lineHeight: 1.4
                  }}>
                    <ShieldCheck size={14} style={{ flexShrink: 0 }} />
                    <span>RBI Household Debt Cap: Compliant (FOIR: {foirPercentage.toFixed(1)}% ≤ 50%)</span>
                  </div>
                ) : (
                  <div style={{
                    background: 'var(--danger-subtle)',
                    border: '1px solid #fecaca',
                    color: 'var(--danger)',
                    padding: '8px 10px',
                    fontSize: '11px',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    textAlign: 'left',
                    lineHeight: 1.3
                  }}>
                    <ShieldAlert size={14} style={{ flexShrink: 0 }} />
                    <span>RBI Guardrail Violation: Debt Burden Exceeds 50% Cap (FOIR: {foirPercentage.toFixed(1)}%)</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>

        {/* Feature Verification Metrics Badges / Cards */}
        <motion.div variants={itemVariants} className="glass-card grid-col-8" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div className="card-header">
            <h3 className="card-title"><BarChart3 size={14} color="var(--accent)" /> Feature Verification Metrics</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{isGigWorker ? 'Gig Worker Pipeline (8 Features)' : 'Standard Pipeline (6 Features)'}</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: isGigWorker ? 'repeat(4, 1fr)' : 'repeat(2, 1fr)', gap: '14px', margin: '12px 0' }}>
            <div style={{ background: 'var(--bg-page)', padding: '14px', border: '1px solid var(--border)', borderRadius: '0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 500, marginBottom: '4px' }}>
                <Users size={14} color="var(--accent)" /> Unique Senders
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {scoreData?.unique_sender_count ?? 15} <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontWeight: 400 }}>senders</span>
              </div>
            </div>

            <div style={{ background: 'var(--bg-page)', padding: '14px', border: '1px solid var(--border)', borderRadius: '0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 500, marginBottom: '4px' }}>
                <CalendarCheck size={14} color="var(--violet)" /> Utility Streak
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {scoreData?.utility_payment_streak ?? 6} <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontWeight: 400 }}>months</span>
              </div>
            </div>

            {isGigWorker && (
              <>
                <div style={{ background: '#f59e0b10', padding: '14px', border: '1px solid #f59e0b30', borderRadius: '0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#b45309', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                    <Star size={14} fill="#f59e0b" color="#f59e0b" /> Gig Rating
                  </div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#b45309' }}>
                    {scoreData?.gig_rating ? scoreData.gig_rating.toFixed(1) : '4.8'} <span style={{ fontSize: '12px', color: '#b45309', fontWeight: 400 }}>/ 5.0</span>
                  </div>
                </div>

                <div style={{ background: '#f59e0b10', padding: '14px', border: '1px solid #f59e0b30', borderRadius: '0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#b45309', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                    <Clock size={14} color="#b45309" /> Weekly Hours
                  </div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#b45309' }}>
                    {scoreData?.gig_hours_per_week ?? 50} <span style={{ fontSize: '12px', color: '#b45309', fontWeight: 400 }}>hrs/wk</span>
                  </div>
                </div>
              </>
            )}
          </div>

          <div style={{ flexGrow: 1, width: '100%', minHeight: '130px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={mockChartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorInflow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0f766e" stopOpacity={0.12} />
                    <stop offset="95%" stopColor="#0f766e" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" vertical={false} />
                <XAxis dataKey="name" stroke="#a8a29e" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#a8a29e" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val / 1000}k`} />
                <Tooltip cursor={{ stroke: '#d6d3d1' }} />
                <Area type="monotone" dataKey="inflow" stroke="#0f766e" strokeWidth={2} fillOpacity={1} fill="url(#colorInflow)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        {/* Surplus & Affordability Card */}
        <motion.div variants={itemVariants} className="glass-card grid-col-5" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="card-header">
              <h3 className="card-title">
                <Wallet size={14} color="var(--accent)" /> Surplus & Affordability
              </h3>
              <span className="badge" style={{
                background: availableSurplus >= 0 ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                color: availableSurplus >= 0 ? 'var(--accent)' : 'var(--danger)',
                border: `1px solid ${availableSurplus >= 0 ? '#ccfbf1' : '#fecaca'}`
              }}>
                {availableSurplus >= 0 ? 'SURPLUS BUFFER' : 'DEFICIT'}
              </span>
            </div>

            {/* Metric Box */}
            <div style={{
              background: 'var(--bg-page)',
              border: '1px solid var(--border)',
              padding: '16px',
              marginTop: '8px',
              marginBottom: '14px'
            }}>
              <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                Available Monthly Surplus (₹)
              </div>
              <div style={{
                fontSize: '28px',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: availableSurplus >= 0 ? 'var(--accent)' : 'var(--danger)',
                display: 'flex',
                alignItems: 'baseline',
                gap: '4px'
              }}>
                <span>₹{loading ? '—' : Math.abs(availableSurplus).toLocaleString('en-IN')}</span>
                {availableSurplus < 0 && <span style={{ fontSize: '13px', fontWeight: 600 }}> (Deficit)</span>}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                (income − total obligations)
              </div>
            </div>

            {/* Underwriting Indicators */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Calculated FOIR Ratio</span>
                  <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: foirPercentage <= 50 ? 'var(--accent)' : 'var(--danger)' }}>
                    {foirPercentage.toFixed(1)}% <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>/ 50% cap</span>
                  </span>
                </div>
                {/* FOIR Progress Bar */}
                <div style={{ height: '7px', background: '#e7e5e4', width: '100%', position: 'relative', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(foirPercentage, 100)}%`,
                      background: foirPercentage <= 50 ? 'var(--accent)' : 'var(--danger)',
                      transition: 'width 0.4s ease'
                    }}
                  />
                  {/* 50% Marker */}
                  <div style={{
                    position: 'absolute',
                    left: '50%',
                    top: 0,
                    bottom: 0,
                    width: '2px',
                    background: '#1c1917',
                    zIndex: 2
                  }} title="50% RBI Maximum Limit" />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '3px' }}>
                  <span>0%</span>
                  <span style={{ fontWeight: 600, color: '#1c1917' }}>50% RBI Cap</span>
                  <span>100%</span>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 10px', background: 'var(--bg-page)', fontSize: '12px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Debt Service Burden</span>
                <span style={{ fontWeight: 600, color: rbiCompliant ? 'var(--accent)' : 'var(--danger)' }}>
                  {rbiCompliant ? 'Within RBI 50% Threshold' : 'Exceeds Statutory Ceiling'}
                </span>
              </div>
            </div>
          </div>

          <div style={{ marginTop: '12px', fontSize: '11px', color: 'var(--text-tertiary)', borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
            Governed by RBI/2021-22/185 Master Direction for Microfinance Loans.
          </div>
        </motion.div>

        {/* Risk-Based Pricing Offer Card */}
        <motion.div
          variants={itemVariants}
          className="glass-card grid-col-7"
          style={{
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
            <div className="card-header">
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
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginTop: '8px', marginBottom: '14px' }}>
                  {/* Approved APR */}
                  <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                      Approved APR (%)
                    </div>
                    <div style={{ fontSize: '26px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                      {loading ? '—' : `${interestRateApr.toFixed(1)}%`}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      Tier: {scoreVal >= 80 ? 'Prime / Excellent (12.5%)' : scoreVal >= 60 ? 'Standard MFI (18.0%)' : 'Subprime (24.0%)'}
                    </div>
                  </div>

                  {/* Maximum Sanction Limit */}
                  <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                      Maximum Sanction Limit (₹)
                    </div>
                    <div style={{ fontSize: '26px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                      {loading ? '—' : `₹${Math.round(maxLoanLimit).toLocaleString('en-IN')}`}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      12-Month Conservative Surplus Buffer
                    </div>
                  </div>
                </div>

                {/* Quick Summary Callout */}
                <div style={{
                  background: 'var(--accent-subtle)',
                  border: '1px solid #ccfbf1',
                  borderLeft: '4px solid var(--accent)',
                  padding: '12px 16px',
                  marginBottom: '10px'
                }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--accent)', lineHeight: 1.5 }}>
                    Estimated EMI for ₹50,000 over 12 months: ₹{estimatedEmi}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    Calculated using standard annuity amortisation formula at {interestRateApr.toFixed(1)}% APR.
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* Non-Compliant / Greyed-out State Content */}
                <div style={{
                  background: '#fecaca30',
                  border: '1px solid #fca5a5',
                  borderLeft: '4px solid var(--danger)',
                  padding: '14px 16px',
                  marginTop: '8px',
                  marginBottom: '14px'
                }}>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--danger)', marginBottom: '4px' }}>
                    Offer Unavailable
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Lending restricted under RBI 50% FOIR statutory ceiling. Total monthly obligations consume {foirPercentage.toFixed(1)}% of household income. Deleveraging required before fresh credit sanctions can be approved.
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '14px' }}>
                  <div style={{ background: '#f5f5f4', border: '1px solid #e7e5e4', padding: '14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                      Approved APR (%)
                    </div>
                    <div style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                      0.0%
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                      Pricing Disabled (Non-Compliant)
                    </div>
                  </div>

                  <div style={{ background: '#f5f5f4', border: '1px solid #e7e5e4', padding: '14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                      Maximum Sanction Limit (₹)
                    </div>
                    <div style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                      ₹0.00
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                      Zero Sanction Permitted
                    </div>
                  </div>
                </div>

                <div style={{
                  background: '#f5f5f4',
                  border: '1px solid #e7e5e4',
                  padding: '10px 14px',
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
            Risk-based pricing matrix calculated via XGBoost score tiers and RBI debt service buffer.
          </div>
        </motion.div>

        {/* Institutional Partner Match Card */}
        <motion.div variants={itemVariants} className="glass-card grid-col-12" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="card-header">
              <h3 className="card-title">
                <Landmark size={14} color="var(--accent)" /> Institutional Partner Match
              </h3>
              <span className="badge" style={partnerInfo.badgeStyle}>
                {partnerInfo.isEligible ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                {partnerInfo.personaTitle}
              </span>
            </div>

            {/* Recommended Target Partner Callout */}
            <div style={{
              background: partnerInfo.isEligible ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
              border: `1px solid ${partnerInfo.isEligible ? '#ccfbf1' : '#fecaca'}`,
              borderLeft: `4px solid ${partnerInfo.isEligible ? 'var(--accent)' : 'var(--danger)'}`,
              padding: '16px',
              marginTop: '8px',
              marginBottom: '14px'
            }}>
              <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: '4px' }}>
                Lending Partner Recommendation
              </div>
              <div style={{
                fontSize: '15px',
                fontWeight: 700,
                color: partnerInfo.isEligible ? 'var(--accent)' : 'var(--danger)',
                lineHeight: 1.4,
                marginBottom: '6px'
              }}>
                {partnerInfo.displayMatch}
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>
                {partnerInfo.description}
              </p>
            </div>

            {/* Karnataka Institutional Ecosystem Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '10px' }}>
              <div style={{
                padding: '10px 12px',
                background: 'var(--bg-page)',
                border: '1px solid var(--border)',
                borderLeft: partnerInfo.personaTitle.includes('Standard') ? '3px solid var(--accent)' : '1px solid var(--border)'
              }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Building2 size={12} color="var(--accent)" /> CreditAccess Grameen / NABFINS
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                  Microfinance Income Generation Loan
                </div>
              </div>

              <div style={{
                padding: '10px 12px',
                background: 'var(--bg-page)',
                border: '1px solid var(--border)',
                borderLeft: partnerInfo.personaTitle.includes('Gig') ? '3px solid #f59e0b' : '1px solid var(--border)'
              }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Building2 size={12} color="#b45309" /> Ujjivan SFB / Northern Arc
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                  Gig Enterprise Credit Facility
                </div>
              </div>

              <div style={{
                padding: '10px 12px',
                background: 'var(--bg-page)',
                border: '1px solid var(--border)',
                borderLeft: partnerInfo.personaTitle.includes('Street') ? '3px solid #2563eb' : '1px solid var(--border)'
              }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Building2 size={12} color="#2563eb" /> PM SVANidhi (Jana SFB / Ujjivan)
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                  Urban Street Vendor Micro-Credit
                </div>
              </div>

              <div style={{
                padding: '10px 12px',
                background: 'var(--bg-page)',
                border: '1px solid var(--border)',
                borderLeft: !partnerInfo.isEligible ? '3px solid var(--danger)' : '1px solid var(--border)'
              }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: !partnerInfo.isEligible ? 'var(--danger)' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Scale size={12} color={!partnerInfo.isEligible ? 'var(--danger)' : 'var(--text-tertiary)'} /> RBI FOIR Cap Policy
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                  Max 50% debt servicing cap
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: '12px', fontSize: '11px', color: 'var(--text-tertiary)', borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
            Direct partner API underwriting integration with Karnataka microfinance lending desks.
          </div>
        </motion.div>

        {/* SHAP Explainer Visualization */}
        <motion.div variants={itemVariants} className="glass-card grid-col-8">
          <div className="card-header">
            <h3 className="card-title"><Lightbulb size={14} color="var(--accent)" /> SHAP Feature Explainability</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>Model feature contributions</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {scoreData?.shap_reasons && scoreData.shap_reasons.length > 0 ? (
              scoreData.shap_reasons.map((reason, idx) => {
                const isViolation = reason.toLowerCase().includes('violation');
                const isPositive = !isViolation && reason.trim().startsWith('+');
                return (
                  <div key={idx} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 14px', borderRadius: '0',
                    background: isViolation ? '#fef2f2' : isPositive ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                    borderLeft: `3px solid ${isViolation ? 'var(--danger)' : isPositive ? 'var(--accent)' : 'var(--danger)'}`
                  }}>
                    <span style={{ fontSize: '13px', fontWeight: isViolation ? 600 : 500, color: isViolation ? 'var(--danger)' : 'var(--text-primary)' }}>
                      {reason}
                    </span>
                    <span style={{
                      fontSize: '11px', fontWeight: 700,
                      color: isViolation ? 'var(--danger)' : isPositive ? 'var(--accent)' : 'var(--danger)'
                    }}>
                      {isViolation ? 'REGULATORY GUARDRAIL' : isPositive ? 'POSITIVE IMPACT' : 'RISK FACTOR'}
                    </span>
                  </div>
                );
              })
            ) : (
              <div style={{ color: 'var(--text-tertiary)', fontSize: '13px' }}>Loading SHAP explanations...</div>
            )}
          </div>
        </motion.div>

        {/* Insights */}
        <motion.div variants={itemVariants} className="glass-card grid-col-4">
          <div className="card-header">
            <h3 className="card-title"><Zap size={14} color="var(--warning)" /> Model Insights</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ background: 'var(--accent-subtle)', borderLeft: '3px solid var(--accent)', padding: '12px 14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Unique Senders.</strong> Having {scoreData?.unique_sender_count ?? 15} unique senders demonstrates organic cashflow diversity.
              </p>
            </div>
            <div style={{ background: 'var(--warning-subtle)', borderLeft: '3px solid var(--warning)', padding: '12px 14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Utility Streak.</strong> {scoreData?.utility_payment_streak ?? 6} consecutive months of utility bill payments boosts credit stability.
              </p>
            </div>
            {isGigWorker && (
              <div style={{ background: '#f59e0b10', borderLeft: '3px solid #f59e0b', padding: '12px 14px' }}>
                <p style={{ fontSize: '13px', color: '#b45309', margin: 0, lineHeight: 1.5 }}>
                  <strong>Gig Performance.</strong> {scoreData?.gig_rating ?? 4.8}★ rating across {scoreData?.gig_hours_per_week ?? 50} weekly gig hours unlocks premier credit terms.
                </p>
              </div>
            )}
          </div>
        </motion.div>

        {/* Simulator */}
        <motion.div variants={itemVariants} className="grid-col-12">
          <WhatIfSimulator
            scoreData={scoreData}
            workerId={workerId}
            consentId={consentId}
            phoneNumber={phoneNumber}
          />
        </motion.div>

      </motion.div>
    </div>
  );
}
