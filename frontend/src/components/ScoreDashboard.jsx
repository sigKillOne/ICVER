import React, { useState, useEffect } from 'react';
import { 
  Award, Zap, CheckCircle, TrendingUp, RefreshCw, AlertCircle, 
  ArrowUpRight, ArrowDownRight, Smartphone, IndianRupee, Lightbulb
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
  const [monthlyCashflow, setMonthlyCashflow] = useState(28500);
  const [gigEarnings, setGigEarnings] = useState(15000);

  const fetchScore = async () => {
    setLoading(true);
    setError('');

    try {
      const payload = {
        worker_id: workerId,
        consent_id: consentId,
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

  return (
    <div>
      {/* Page header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Dashboard</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Financial overview and income verification status.</p>
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
        <motion.div variants={itemVariants} className="glass-card grid-col-4" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 24px' }}>
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

          <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <span className="badge badge-eligible">
              <CheckCircle size={12} /> {scoreData?.decision_tier || 'Prime Eligible'}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              Confidence: {scoreData ? `${(scoreData.confidence_score * 100).toFixed(0)}%` : '89%'}
            </span>
          </div>
        </motion.div>

        {/* Chart card */}
        <motion.div variants={itemVariants} className="glass-card grid-col-8" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <h3 className="card-title"><TrendingUp size={14} color="var(--accent)" /> UPI Inflows</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>Last 6 months</span>
          </div>
          <div style={{ flexGrow: 1, width: '100%', minHeight: '200px' }}>
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

        {/* Transactions */}
        <motion.div variants={itemVariants} className="glass-card grid-col-8">
          <div className="card-header">
            <h3 className="card-title"><IndianRupee size={14} color="var(--violet)" /> Recent Transactions</h3>
            <button className="btn-secondary">View All</button>
          </div>
          <table className="fintech-table">
            <thead>
              <tr>
                <th>Description</th>
                <th>Date</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {mockTransactions.map((txn) => (
                <tr key={txn.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ 
                        width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: txn.type === 'credit' ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
                        color: txn.type === 'credit' ? 'var(--accent)' : 'var(--danger)'
                      }}>
                        {txn.type === 'credit' ? <ArrowDownRight size={16} /> : <ArrowUpRight size={16} />}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: '13px' }}>{txn.desc}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '1px' }}>{txn.id}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>{txn.date}</td>
                  <td style={{ textAlign: 'right', fontWeight: 600, fontSize: '13px', fontFamily: 'var(--font-mono)', color: txn.type === 'credit' ? 'var(--accent)' : 'var(--text-primary)' }}>
                    {txn.amount}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>

        {/* Insights */}
        <motion.div variants={itemVariants} className="glass-card grid-col-4">
          <div className="card-header">
            <h3 className="card-title"><Lightbulb size={14} color="var(--warning)" /> Insights</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ background: 'var(--accent-subtle)', borderLeft: '3px solid var(--accent)', padding: '12px 14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Score boost.</strong> Consistent UPI deposits last month added 15 points to your score.
              </p>
            </div>
            <div style={{ background: 'var(--warning-subtle)', borderLeft: '3px solid var(--warning)', padding: '12px 14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Recommendation.</strong> 5+ weekly UPI transactions for 30 days unlocks the Premium loan tier.
              </p>
            </div>
            <div style={{ background: 'var(--violet-subtle)', borderLeft: '3px solid var(--violet)', padding: '12px 14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
                <strong>Stability signal.</strong> Regular mobile recharges indicate financial consistency.
              </p>
            </div>
          </div>
        </motion.div>

        {/* Simulator */}
        <motion.div variants={itemVariants} className="grid-col-12">
          <WhatIfSimulator currentScore={scoreVal} />
        </motion.div>

      </motion.div>
    </div>
  );
}
