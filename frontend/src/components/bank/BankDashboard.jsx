import React, { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import {
  ShieldAlert, CheckCircle, Search, X, ShieldCheck, AlertCircle,
  Scale, Landmark, BarChart3
} from 'lucide-react';

const riskData = [
  { name: 'Eligible', value: 450, color: '#0f766e' },
  { name: 'Pending', value: 200, color: '#d97706' },
  { name: 'Rejected', value: 150, color: '#dc2626' },
];

const mockApplicants = [
  {
    id: 'APP-1001',
    name: 'Ravi Kumar',
    persona: 'Standard Vendor (Compliant)',
    score: 82,
    status: 'approved',
    risk: 'Low',
    requested: '₹50,000',
    monthlyHouseholdIncome: 25000,
    bizExpense: 10000,
    householdExpense: 5000,
    existingEmi: 1000,
    proposedEmi: 2000,
    totalDebtObligations: 3000,
    foirRatio: 12.0,
    rbiRegulatoryStatus: 'PASS',
    availableSurplus: 7000,
    partnerMatch: 'CreditAccess Grameen / NABFINS',
    shapData: [
      { feature: 'UPI Monthly Inflow (₹50k)', value: 18.5, formatted: '+18.5', type: 'positive' },
      { feature: 'Weekly Txn Frequency (15 txns)', value: 12.1, formatted: '+12.1', type: 'positive' },
      { feature: 'Recharge Regularity Index (0.90)', value: 8.3, formatted: '+8.3', type: 'positive' },
      { feature: 'Unique Senders Count (45 senders)', value: 6.4, formatted: '+6.4', type: 'positive' },
      { feature: 'Days Since Last Txn (1 day)', value: 4.2, formatted: '+4.2', type: 'positive' },
      { feature: 'Utility Streak (6 months)', value: -2.5, formatted: '-2.5', type: 'negative' },
    ]
  },
  {
    id: 'APP-1002',
    name: 'Sunita Devi',
    persona: 'Gig Worker (Compliant)',
    score: 79,
    status: 'approved',
    risk: 'Low',
    requested: '₹35,000',
    monthlyHouseholdIncome: 30000,
    bizExpense: 8000,
    householdExpense: 8000,
    existingEmi: 2000,
    proposedEmi: 3000,
    totalDebtObligations: 5000,
    foirRatio: 16.7,
    rbiRegulatoryStatus: 'PASS',
    availableSurplus: 9000,
    partnerMatch: 'Ujjivan SFB / Northern Arc Capital',
    shapData: [
      { feature: 'Gig Partner Rating (4.8★)', value: 16.8, formatted: '+16.8', type: 'positive' },
      { feature: 'Weekly Gig Hours (50 hrs)', value: 13.5, formatted: '+13.5', type: 'positive' },
      { feature: 'Utility Payment Streak (12 mo)', value: 9.4, formatted: '+9.4', type: 'positive' },
      { feature: 'Platform Payout Consistency', value: 7.2, formatted: '+7.2', type: 'positive' },
      { feature: 'Active Working Capital Demand', value: -4.9, formatted: '-4.9', type: 'negative' },
    ]
  },
  {
    id: 'APP-1003',
    name: 'Amit Singh',
    persona: 'Over-Indebted (High Risk)',
    score: 38,
    status: 'rejected',
    risk: 'High',
    requested: '₹20,000',
    monthlyHouseholdIncome: 15000,
    bizExpense: 6000,
    householdExpense: 4000,
    existingEmi: 6500,
    proposedEmi: 2000,
    totalDebtObligations: 8500,
    foirRatio: 56.7,
    rbiRegulatoryStatus: 'FAIL',
    availableSurplus: -3500,
    partnerMatch: 'Ineligible (Exceeds RBI 50% FOIR Cap)',
    rbiViolation: 'RBI Guardrail Violation: Household Debt Burden exceeds 50% Cap (FOIR: 56.7%)',
    shapData: [
      { feature: 'RBI Guardrail Breach (FOIR 56.7%)', value: -35.0, formatted: '-35.0', type: 'negative' },
      { feature: 'Depressed UPI Inflow (₹10k)', value: -14.2, formatted: '-14.2', type: 'negative' },
      { feature: 'High Recency Lag (14 days idle)', value: -9.8, formatted: '-9.8', type: 'negative' },
      { feature: 'Zero Utility Payment Streak', value: -6.5, formatted: '-6.5', type: 'negative' },
      { feature: 'Low Senders Breadth (3 senders)', value: -4.5, formatted: '-4.5', type: 'negative' },
    ]
  },
  {
    id: 'APP-1004',
    name: 'Kiran Patel',
    persona: 'Circular Fraud Suspect',
    score: 42,
    status: 'rejected',
    risk: 'High',
    requested: '₹60,000',
    fraudFlag: true,
    monthlyHouseholdIncome: 22000,
    bizExpense: 9000,
    householdExpense: 5000,
    existingEmi: 1500,
    proposedEmi: 2000,
    totalDebtObligations: 3500,
    foirRatio: 15.9,
    rbiRegulatoryStatus: 'PASS',
    availableSurplus: 4500,
    partnerMatch: 'Blocked (Circular P2P Fraud Detection)',
    shapData: [
      { feature: 'Synthetic Volume Flag (Circular P2P)', value: -20.0, formatted: '-20.0', type: 'negative' },
      { feature: 'Low Counterparty Diversity (2 VPAs)', value: -12.4, formatted: '-12.4', type: 'negative' },
      { feature: 'Inflated Txn Frequency (50/wk)', value: -8.7, formatted: '-8.7', type: 'negative' },
      { feature: 'Nominal Mobile Recharge Regularity', value: 5.1, formatted: '+5.1', type: 'positive' },
    ]
  },
  {
    id: 'APP-1005',
    name: 'Lakshmi Bai',
    persona: 'Street Vendor (Low-Ticket)',
    score: 68,
    status: 'pending',
    risk: 'Medium',
    requested: '₹15,000',
    monthlyHouseholdIncome: 16500,
    bizExpense: 5500,
    householdExpense: 4500,
    existingEmi: 800,
    proposedEmi: 1200,
    totalDebtObligations: 2000,
    foirRatio: 12.1,
    rbiRegulatoryStatus: 'PASS',
    availableSurplus: 4500,
    partnerMatch: 'PM SVANidhi Scheme (Jana SFB / Ujjivan SFB)',
    shapData: [
      { feature: 'Daily Micro-QR Velocity', value: 12.4, formatted: '+12.4', type: 'positive' },
      { feature: 'Low Debt Obligation (FOIR 12.1%)', value: 8.9, formatted: '+8.9', type: 'positive' },
      { feature: 'Utility Regularity (4 months)', value: 5.2, formatted: '+5.2', type: 'positive' },
      { feature: 'Limited Formal Ticket History', value: -4.3, formatted: '-4.3', type: 'negative' },
    ]
  },
];

export default function BankDashboard() {
  const [filter, setFilter] = useState('all');
  const [auditModalOpen, setAuditModalOpen] = useState(false);
  const [selectedApplicant, setSelectedApplicant] = useState(null);

  const filteredApplicants = mockApplicants.filter(app => {
    if (filter === 'all') return true;
    if (filter === 'approved') return app.status === 'approved';
    if (filter === 'pending') return app.status === 'pending';
    return true;
  });

  const openAudit = (app) => {
    setSelectedApplicant(app);
    setAuditModalOpen(true);
  };

  return (
    <div style={{ position: 'relative' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Lender Overview</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            Portfolio risk, statutory RBI MFI underwriting compliance, and SHAP explainability audit.
          </p>
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Risk chart */}
        <div className="glass-card grid-col-4" style={{ minHeight: '280px', display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <h3 className="card-title"><ShieldAlert size={14} color="var(--warning)" /> Risk Distribution</h3>
          </div>
          <div style={{ flexGrow: 1, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={riskData}
                  innerRadius={55}
                  outerRadius={75}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {riskData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ background: '#fff', border: '1px solid var(--border)', borderRadius: '0', fontSize: '12px' }}
                />
                <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Applicants table with Underwriting Metrics */}
        <div className="glass-card grid-col-8" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-header" style={{ marginBottom: '12px' }}>
            <h3 className="card-title">Recent Applicants & Regulatory Audit</h3>
            <div style={{ display: 'flex', gap: '0', border: '1px solid var(--border)' }}>
              {['all', 'pending', 'approved'].map(f => (
                <button 
                  key={f}
                  onClick={() => setFilter(f)}
                  style={{ 
                    padding: '5px 12px', fontSize: '12px', fontWeight: 500, border: 'none', cursor: 'pointer',
                    background: filter === f ? 'var(--bg-page)' : 'var(--bg-card)',
                    color: filter === f ? 'var(--text-primary)' : 'var(--text-secondary)',
                    borderRight: f !== 'approved' ? '1px solid var(--border)' : 'none',
                    fontFamily: 'var(--font-sans)'
                  }}
                >{f === 'all' ? 'All' : f === 'pending' ? 'Pending' : 'Approved'}</button>
              ))}
            </div>
          </div>

          <div style={{ overflowX: 'auto', flexGrow: 1 }}>
            <table className="fintech-table">
              <thead>
                <tr>
                  <th>Applicant</th>
                  <th>Score</th>
                  <th>Risk</th>
                  <th>Household Inc.</th>
                  <th>FOIR Ratio</th>
                  <th>RBI Status</th>
                  <th>Req. Loan</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredApplicants.map((app) => (
                  <tr key={app.id}>
                    <td>
                      <div style={{ fontWeight: 500, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {app.name}
                        {app.fraudFlag && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', background: 'var(--danger-subtle)', color: 'var(--danger)', padding: '1px 6px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            <ShieldAlert size={10} style={{ marginRight: '3px' }}/> Fraud
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{app.id}</div>
                    </td>
                    <td>
                      <span style={{ fontWeight: 700, fontSize: '13px', fontFamily: 'var(--font-mono)', color: app.score >= 70 ? 'var(--accent)' : app.score >= 50 ? 'var(--warning)' : 'var(--danger)' }}>
                        {app.score}
                      </span>
                    </td>
                    <td>
                      <span className="badge" style={{
                        background: app.risk === 'Low' ? 'var(--accent-subtle)' : app.risk === 'Medium' ? 'var(--warning-subtle)' : 'var(--danger-subtle)',
                        color: app.risk === 'Low' ? 'var(--accent)' : app.risk === 'Medium' ? 'var(--warning)' : 'var(--danger)',
                        border: `1px solid ${app.risk === 'Low' ? '#ccfbf1' : app.risk === 'Medium' ? '#fde68a' : '#fecaca'}`
                      }}>
                        {app.risk === 'Low' && <CheckCircle size={10} />}
                        {app.risk}
                      </span>
                    </td>
                    <td style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
                      ₹{app.monthlyHouseholdIncome.toLocaleString('en-IN')}
                    </td>
                    <td>
                      <span style={{
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        fontSize: '12px',
                        color: app.foirRatio <= 50 ? 'var(--accent)' : 'var(--danger)'
                      }}>
                        {app.foirRatio.toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      <span className="badge" style={{
                        background: app.rbiRegulatoryStatus === 'PASS' ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                        color: app.rbiRegulatoryStatus === 'PASS' ? 'var(--accent)' : 'var(--danger)',
                        border: `1px solid ${app.rbiRegulatoryStatus === 'PASS' ? '#ccfbf1' : '#fecaca'}`,
                        fontSize: '10px',
                        padding: '2px 8px'
                      }}>
                        {app.rbiRegulatoryStatus === 'PASS' ? <ShieldCheck size={10} /> : <ShieldAlert size={10} />}
                        {app.rbiRegulatoryStatus}
                      </span>
                    </td>
                    <td style={{ fontSize: '13px', fontFamily: 'var(--font-mono)' }}>{app.requested}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button 
                        onClick={() => openAudit(app)}
                        className="btn-secondary"
                        style={{ padding: '4px 10px', fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        <Search size={12} /> Audit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Comprehensive Underwriting Audit Modal */}
      {auditModalOpen && selectedApplicant && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.45)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
          padding: '20px'
        }}>
          <div style={{
            width: '100%', maxWidth: '680px', maxHeight: '90vh', overflowY: 'auto',
            background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '28px', position: 'relative'
          }}>
            <button 
              onClick={() => setAuditModalOpen(false)}
              style={{ position: 'absolute', top: '20px', right: '20px', background: 'transparent', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Scale size={18} color="var(--accent)" />
              <h3 style={{ fontSize: '17px', fontWeight: 600 }}>Institutional Underwriting & Audit Dossier</h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '20px' }}>
              Comprehensive cash-flow underwriting, statutory RBI compliance verification, and SHAP explainability for <strong>{selectedApplicant.name}</strong> ({selectedApplicant.id}).
            </p>
            
            {/* Synthetic Volume Fraud Banner */}
            {selectedApplicant.fraudFlag && (
              <div style={{ background: 'var(--danger-subtle)', border: '1px solid #fecaca', padding: '12px', marginBottom: '16px', display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                <ShieldAlert color="var(--danger)" size={20} />
                <div>
                  <h4 style={{ color: 'var(--danger)', fontSize: '13px', fontWeight: 600, margin: '0 0 2px 0' }}>Synthetic Volume Detected</h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>Cyclic P2P transactions detected via network graph layer. 20% penalty applied.</p>
                </div>
              </div>
            )}

            {/* Over-Indebted RBI Breach Banner */}
            {selectedApplicant.rbiRegulatoryStatus === 'FAIL' && (
              <div style={{ background: 'var(--danger-subtle)', border: '1px solid #fecaca', borderLeft: '4px solid var(--danger)', padding: '12px 14px', marginBottom: '16px', display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                <AlertCircle color="var(--danger)" size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <h4 style={{ color: 'var(--danger)', fontSize: '13px', fontWeight: 700, margin: '0 0 2px 0' }}>
                    RBI Regulatory Guardrail Breach: Debt Burden Exceeds 50% Cap
                  </h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>
                    Applicant obligations of ₹{selectedApplicant.totalDebtObligations.toLocaleString('en-IN')}/mo consume {selectedApplicant.foirRatio.toFixed(1)}% of household income (statutory max: 50.0%). Credit is restricted under RBI Master Direction RBI/2021-22/185.
                  </p>
                </div>
              </div>
            )}

            {/* 1. Institutional Underwriting Overview Panel */}
            <div style={{ background: 'var(--bg-page)', border: '1px solid var(--border)', padding: '18px', marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', borderBottom: '1px solid var(--border)', paddingBottom: '10px' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Landmark size={14} color="var(--accent)" /> Institutional Underwriting Overview
                </div>
                <span className="badge" style={{
                  background: selectedApplicant.rbiRegulatoryStatus === 'PASS' ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                  color: selectedApplicant.rbiRegulatoryStatus === 'PASS' ? 'var(--accent)' : 'var(--danger)',
                  border: `1px solid ${selectedApplicant.rbiRegulatoryStatus === 'PASS' ? '#ccfbf1' : '#fecaca'}`,
                  fontWeight: 700
                }}>
                  RBI STATUS: {selectedApplicant.rbiRegulatoryStatus}
                </span>
              </div>

              {/* Complete Cash-flow Breakdown Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '14px' }}>
                <div style={{ background: 'var(--bg-card)', padding: '12px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '2px' }}>
                    Monthly Household Income
                  </div>
                  <div style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    ₹{selectedApplicant.monthlyHouseholdIncome.toLocaleString('en-IN')}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '2px' }}>Verified gross inflow</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '12px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '2px' }}>
                    Total Debt Obligations
                  </div>
                  <div style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--danger)' }}>
                    ₹{selectedApplicant.totalDebtObligations.toLocaleString('en-IN')}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '2px' }}>Existing + Proposed EMI</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '12px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '2px' }}>
                    Calculated FOIR Ratio
                  </div>
                  <div style={{
                    fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-mono)',
                    color: selectedApplicant.foirRatio <= 50 ? 'var(--accent)' : 'var(--danger)'
                  }}>
                    {selectedApplicant.foirRatio.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '2px' }}>Cap: ≤ 50.0% max</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '12px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '2px' }}>
                    RBI Regulatory Status
                  </div>
                  <div style={{
                    fontSize: '18px', fontWeight: 700,
                    color: selectedApplicant.rbiRegulatoryStatus === 'PASS' ? 'var(--accent)' : 'var(--danger)'
                  }}>
                    {selectedApplicant.rbiRegulatoryStatus}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                    {selectedApplicant.rbiRegulatoryStatus === 'PASS' ? 'Compliant with Cap' : 'Exceeds 50% Cap'}
                  </div>
                </div>
              </div>

              {/* Extended Affordability Sub-Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', fontSize: '12px', borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>Available Monthly Surplus:</span>{' '}
                  <strong style={{
                    fontFamily: 'var(--font-mono)',
                    color: selectedApplicant.availableSurplus >= 0 ? 'var(--accent)' : 'var(--danger)'
                  }}>
                    {selectedApplicant.availableSurplus >= 0 ? `₹${selectedApplicant.availableSurplus.toLocaleString('en-IN')}` : `-₹${Math.abs(selectedApplicant.availableSurplus).toLocaleString('en-IN')}`}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>Existing / Proposed EMI:</span>{' '}
                  <strong style={{ fontFamily: 'var(--font-mono)' }}>
                    ₹{selectedApplicant.existingEmi.toLocaleString('en-IN')} / ₹{selectedApplicant.proposedEmi.toLocaleString('en-IN')}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)' }}>Karnataka Partner Match:</span>{' '}
                  <strong style={{ color: selectedApplicant.rbiRegulatoryStatus === 'PASS' ? 'var(--text-primary)' : 'var(--danger)' }}>
                    {selectedApplicant.partnerMatch}
                  </strong>
                </div>
              </div>
            </div>

            {/* 2. SHAP Feature Contribution Bar Chart (Remains Visible Below Underwriting Summary) */}
            <div style={{ background: 'var(--bg-page)', padding: '18px', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--border)', paddingBottom: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <BarChart3 size={14} color="var(--accent)" /> XGBoost SHAP Feature Contribution Chart
                </div>
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>Explainable AI attribution</span>
              </div>
              
              {/* SHAP Bars with Values & Relative Weights */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {selectedApplicant.shapData.map((data, idx) => {
                  const isPositive = data.type === 'positive';
                  const absVal = Math.min(Math.abs(data.value) * 2.5, 100);
                  return (
                    <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                        <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{data.feature}</span>
                        <span style={{ 
                          fontWeight: 700, fontFamily: 'var(--font-mono)',
                          color: isPositive ? 'var(--accent)' : 'var(--danger)' 
                        }}>
                          {data.formatted}
                        </span>
                      </div>
                      {/* Bar Visualization */}
                      <div style={{ height: '6px', background: '#e7e5e4', width: '100%', position: 'relative' }}>
                        <div style={{
                          height: '100%',
                          width: `${absVal}%`,
                          background: isPositive ? 'var(--accent)' : 'var(--danger)',
                          transition: 'width 0.3s ease'
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Model Output Reconciliation */}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>Base Model Heuristic</span>
                <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>45.0</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600 }}>Final Credit Score (0–100)</span>
                <span style={{
                  fontSize: '15px', fontWeight: 700, fontFamily: 'var(--font-mono)',
                  color: selectedApplicant.score >= 70 ? 'var(--accent)' : selectedApplicant.score >= 50 ? 'var(--warning)' : 'var(--danger)'
                }}>
                  {selectedApplicant.score} / 100 ({selectedApplicant.risk} Risk)
                </span>
              </div>
            </div>

            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn-secondary" onClick={() => setAuditModalOpen(false)}>Close Dossier</button>
              <button className="btn-primary" onClick={() => alert(`Exporting Underwriting Report for ${selectedApplicant.name} (${selectedApplicant.id})`)}>
                Download Credit Memo PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
