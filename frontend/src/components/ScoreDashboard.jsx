import React, { useState, useEffect } from 'react';
import { 
  Award, Zap, CheckCircle, TrendingUp, RefreshCw, AlertCircle, 
  ArrowUpRight, ArrowDownRight, Smartphone, IndianRupee, Lightbulb,
  Users, CalendarCheck, Star, Clock, Briefcase, BarChart3
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

const mockTransactions = [
  { id: 'TXN-901', date: '21 Sep, 14:30', desc: 'UPI: Payment from Client', amount: '+₹4,500', type: 'credit' },
  { id: 'TXN-902', date: '19 Sep, 09:15', desc: 'UPI: Grocery Store', amount: '-₹850', type: 'debit' },
  { id: 'TXN-903', date: '15 Sep, 18:00', desc: 'Recharge: Jio 299 Plan', amount: '-₹299', type: 'debit' },
  { id: 'TXN-904', date: '12 Sep, 11:20', desc: 'UPI: Payment from Client', amount: '+₹2,100', type: 'credit' },
  { id: 'TXN-905', date: '08 Sep, 20:45', desc: 'UPI: Pharmacy', amount: '-₹420', type: 'debit' },
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
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Financial overview and ML credit scoring status.</p>
        </div>
        <button className="btn-primary" onClick={fetchScore} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-pulse' : ''} />
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <motion.div 
        className="dashboard-grid"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        
        {/* Score card */}
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
                  <stop offset="0%" stopColor="#0f766e" />
                  <stop offset="100%" stopColor="#0d9488" />
                </linearGradient>
              </defs>
              <circle className="score-circle-bg" cx="80" cy="80" r={radius} />
              <circle
                className="score-circle-bar"
                cx="80"
                cy="80"
                r={radius}
                style={{ strokeDasharray: circumference, strokeDashoffset: loading ? circumference : strokeDashoffset }}
              />
            </svg>
            <div className="score-number-overlay">
              <span className="score-val">{loading ? '—' : scoreVal}</span>
              <span className="score-max">out of 100</span>
            </div>
          </div>

          <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <span className="badge badge-eligible">
              <CheckCircle size={12} /> {scoreData?.decision_tier || 'Eligible'}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              Confidence: {scoreData ? `${(scoreData.confidence_score * 100).toFixed(0)}%` : '89%'}
            </span>
          </div>
        </motion.div>

        {/* Feature Metrics Badges / Cards */}
        <motion.div variants={itemVariants} className="glass-card grid-col-8" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div className="card-header">
            <h3 className="card-title"><BarChart3 size={14} color="var(--accent)" /> Feature Verification Metrics</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{isGigWorker ? 'Gig Worker Pipeline (8 Features)' : 'Standard Pipeline (6 Features)'}</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: isGigWorker ? 'repeat(4, 1fr)' : 'repeat(2, 1fr)', gap: '14px', margin: '12px 0' }}>
            <div style={{ background: 'var(--bg-page)', padding: '14px', border: '1px solid var(--border)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 500, marginBottom: '4px' }}>
                <Users size={14} color="var(--accent)" /> Unique Senders
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {scoreData?.unique_sender_count ?? 15} <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontWeight: 400 }}>senders</span>
              </div>
            </div>

            <div style={{ background: 'var(--bg-page)', padding: '14px', border: '1px solid var(--border)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 500, marginBottom: '4px' }}>
                <CalendarCheck size={14} color="var(--violet)" /> Utility Streak
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {scoreData?.utility_payment_streak ?? 6} <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontWeight: 400 }}>months</span>
              </div>
            </div>

            {isGigWorker && (
              <>
                <div style={{ background: '#f59e0b10', padding: '14px', border: '1px solid #f59e0b30', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#b45309', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                    <Star size={14} fill="#f59e0b" color="#f59e0b" /> Gig Rating
                  </div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#b45309' }}>
                    {scoreData?.gig_rating ? scoreData.gig_rating.toFixed(1) : '4.8'} <span style={{ fontSize: '12px', color: '#b45309', fontWeight: 400 }}>/ 5.0</span>
                  </div>
                </div>

                <div style={{ background: '#f59e0b10', padding: '14px', border: '1px solid #f59e0b30', borderRadius: '8px' }}>
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
                    <stop offset="5%" stopColor="#0f766e" stopOpacity={0.12}/>
                    <stop offset="95%" stopColor="#0f766e" stopOpacity={0.01}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" vertical={false} />
                <XAxis dataKey="name" stroke="#a8a29e" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#a8a29e" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val/1000}k`} />
                <Tooltip cursor={{ stroke: '#d6d3d1' }} />
                <Area type="monotone" dataKey="inflow" stroke="#0f766e" strokeWidth={2} fillOpacity={1} fill="url(#colorInflow)" />
              </AreaChart>
            </ResponsiveContainer>
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
                const isPositive = reason.trim().startsWith('+');
                return (
                  <div key={idx} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 14px', borderRadius: '6px',
                    background: isPositive ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                    borderLeft: `3px solid ${isPositive ? 'var(--accent)' : 'var(--danger)'}`
                  }}>
                    <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                      {reason}
                    </span>
                    <span style={{
                      fontSize: '11px', fontWeight: 700,
                      color: isPositive ? 'var(--accent)' : 'var(--danger)'
                    }}>
                      {isPositive ? 'POSITIVE IMPACT' : 'RISK FACTOR'}
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
            <div style={{ background: 'var(--accent-subtle)', borderLeft: '3px solid var(--accent)', padding: '12px 14px', borderRadius: '4px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Unique Senders.</strong> Having {scoreData?.unique_sender_count ?? 15} unique senders demonstrates organic cashflow diversity.
              </p>
            </div>
            <div style={{ background: 'var(--warning-subtle)', borderLeft: '3px solid var(--warning)', padding: '12px 14px', borderRadius: '4px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Utility Streak.</strong> {scoreData?.utility_payment_streak ?? 6} consecutive months of utility bill payments boosts credit stability.
              </p>
            </div>
            {isGigWorker && (
              <div style={{ background: '#f59e0b10', borderLeft: '3px solid #f59e0b', padding: '12px 14px', borderRadius: '4px' }}>
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
