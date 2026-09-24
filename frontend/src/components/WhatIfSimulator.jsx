import React, { useState, useEffect, useCallback } from 'react';
import { Sliders, TrendingUp, RefreshCw, Star, Clock, Users, CalendarCheck, Zap } from 'lucide-react';
import { calculateScore } from '../services/api';

export default function WhatIfSimulator({ scoreData, workerId, consentId, phoneNumber }) {
  const isGig = scoreData?.is_gig_worker ?? false;
  const currentScore = scoreData?.creditworthiness_score ?? 78;

  const [inflow, setInflow] = useState( scoreData?.upi_monthly_inflow ?? 25000 );
  const [freq, setFreq] = useState( scoreData?.weekly_txn_frequency ?? 15 );
  const [regularity, setRegularity] = useState( scoreData?.recharge_regularity_index ?? 0.8 );
  const [recency, setRecency] = useState( scoreData?.days_since_last_txn ?? 3 );
  const [senders, setSenders] = useState( scoreData?.unique_sender_count ?? 15 );
  const [streak, setStreak] = useState( scoreData?.utility_payment_streak ?? 6 );
  const [gigRating, setGigRating] = useState( scoreData?.gig_rating ?? 4.8 );
  const [gigHours, setGigHours] = useState( scoreData?.gig_hours_per_week ?? 40 );

  const [predictedScore, setPredictedScore] = useState(currentScore);
  const [loading, setLoading] = useState(false);

  // Sync state if initial scoreData updates
  useEffect(() => {
    if (scoreData) {
      if (scoreData.unique_sender_count !== undefined) setSenders(scoreData.unique_sender_count);
      if (scoreData.utility_payment_streak !== undefined) setStreak(scoreData.utility_payment_streak);
      if (scoreData.gig_rating !== undefined && scoreData.gig_rating !== null) setGigRating(scoreData.gig_rating);
      if (scoreData.gig_hours_per_week !== undefined && scoreData.gig_hours_per_week !== null) setGigHours(scoreData.gig_hours_per_week);
      if (scoreData.creditworthiness_score !== undefined) setPredictedScore(scoreData.creditworthiness_score);
    }
  }, [scoreData]);

  // Debounced API score prediction calculation
  const runSimulation = useCallback(async (vals) => {
    setLoading(true);
    try {
      const payload = {
        worker_id: workerId || 'WRK-7712',
        consent_id: consentId || 'CNS-DEMO-2026',
        phone_number: phoneNumber || '9876543210',
        upi_monthly_inflow: vals.inflow,
        weekly_txn_frequency: vals.freq,
        recharge_regularity_index: vals.regularity,
        days_since_last_txn: vals.recency,
        unique_sender_count: vals.senders,
        utility_payment_streak: vals.streak,
        ...(isGig ? {
          gig_rating: vals.gigRating,
          gig_hours_per_week: vals.gigHours,
        } : {})
      };

      const res = await calculateScore(payload);
      if (res && res.creditworthiness_score !== undefined) {
        setPredictedScore(res.creditworthiness_score);
      }
    } catch (err) {
      console.warn('Simulation API call failed, fallback to live calculation', err);
      // Fallback local heuristic estimation if backend API unavailable
      let normScore = 20 * (vals.inflow / 60000) + 15 * (vals.freq / 25) + 15 * vals.regularity + 10 * (1 - vals.recency / 90) + 10 * (vals.senders / 50) + 10 * (vals.streak / 12);
      if (isGig) {
        normScore += 10 * ((vals.gigRating - 3.0) / 2.0) + 10 * (vals.gigHours / 60);
      }
      setPredictedScore(Math.min(Math.max(Math.round(normScore), 0), 100));
    } finally {
      setLoading(false);
    }
  }, [workerId, consentId, phoneNumber, isGig]);

  const handleChange = (setter, key, val) => {
    setter(val);
    const updatedValues = {
      inflow, freq, regularity, recency, senders, streak, gigRating, gigHours,
      [key]: val
    };
    runSimulation(updatedValues);
  };

  const scoreDiff = predictedScore - currentScore;

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <h3 className="card-title"><Sliders size={16} color="var(--accent)" /> What-If Credit Simulator</h3>
            {isGig && (
              <span style={{ fontSize: '11px', background: '#f59e0b20', color: '#b45309', padding: '2px 8px', borderRadius: '12px', fontWeight: 600 }}>
                Gig Worker Pipeline Active
              </span>
            )}
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Adjust parameters dynamically to see real-time XGBoost ML score projections.
          </p>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '10px 18px', background: 'var(--bg-page)', border: '1px solid var(--border)', borderRadius: '8px' }}>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', fontWeight: 600 }}>Projected Score</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '26px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{loading ? '…' : predictedScore}</span>
              {loading && <RefreshCw size={14} className="animate-pulse" color="var(--accent)" />}
            </div>
          </div>
          
          {scoreDiff !== 0 && !loading && (
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px', fontWeight: 700,
              color: scoreDiff > 0 ? 'var(--accent)' : 'var(--danger)',
              background: scoreDiff > 0 ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
              padding: '4px 10px', borderRadius: '6px'
            }}>
              <TrendingUp size={14} style={{ transform: scoreDiff < 0 ? 'rotate(180deg)' : 'none' }} />
              {scoreDiff > 0 ? '+' : ''}{scoreDiff} pts
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px' }}>
        
        {/* Slider 1: UPI Inflow */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Monthly UPI Inflow (₹)</label>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>₹{inflow.toLocaleString()}</span>
          </div>
          <input 
            type="range" 
            min="5000" max="60000" step="1000" 
            value={inflow} 
            onChange={(e) => handleChange(setInflow, 'inflow', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>₹5k</span>
            <span>₹60k</span>
          </div>
        </div>

        {/* Slider 2: Txn Frequency */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Weekly Txn Frequency</label>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{freq} / wk</span>
          </div>
          <input 
            type="range" 
            min="1" max="35" step="1" 
            value={freq} 
            onChange={(e) => handleChange(setFreq, 'freq', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>1</span>
            <span>35</span>
          </div>
        </div>

        {/* Slider 3: Recharge Regularity */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Recharge Regularity</label>
            <span style={{ fontSize: '13px', color: 'var(--violet)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{Math.round(regularity * 100)}%</span>
          </div>
          <input 
            type="range" 
            min="0" max="1" step="0.05" 
            value={regularity} 
            onChange={(e) => handleChange(setRegularity, 'regularity', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--violet)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>0%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Slider 4: Recency of Txn */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Days Since Last Txn</label>
            <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{recency} days</span>
          </div>
          <input 
            type="range" 
            min="0" max="90" step="1" 
            value={recency} 
            onChange={(e) => handleChange(setRecency, 'recency', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>0 days</span>
            <span>90 days</span>
          </div>
        </div>

        {/* Slider 5: Unique Senders */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Users size={13} color="var(--accent)" /> Unique Senders
            </label>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{senders} customers</span>
          </div>
          <input 
            type="range" 
            min="0" max="100" step="1" 
            value={senders} 
            onChange={(e) => handleChange(setSenders, 'senders', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>0</span>
            <span>100</span>
          </div>
        </div>

        {/* Slider 6: Utility Payment Streak */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CalendarCheck size={13} color="var(--violet)" /> Utility Payment Streak
            </label>
            <span style={{ fontSize: '13px', color: 'var(--violet)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{streak} months</span>
          </div>
          <input 
            type="range" 
            min="0" max="24" step="1" 
            value={streak} 
            onChange={(e) => handleChange(setStreak, 'streak', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--violet)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>0 months</span>
            <span>24 months</span>
          </div>
        </div>

        {/* GIG WORKER SPECIFIC SLIDERS */}
        {isGig && (
          <>
            {/* Slider 7: Gig Rating */}
            <div style={{ background: '#f59e0b10', padding: '12px', borderRadius: '8px', border: '1px solid #f59e0b30' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600, color: '#b45309', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Star size={13} fill="#f59e0b" color="#f59e0b" /> Gig Rating
                </label>
                <span style={{ fontSize: '13px', color: '#b45309', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{gigRating.toFixed(1)} / 5.0</span>
              </div>
              <input 
                type="range" 
                min="3.0" max="5.0" step="0.1" 
                value={gigRating} 
                onChange={(e) => handleChange(setGigRating, 'gigRating', Number(e.target.value))}
                style={{ width: '100%', accentColor: '#f59e0b' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#b45309', marginTop: '2px' }}>
                <span>3.0</span>
                <span>5.0</span>
              </div>
            </div>

            {/* Slider 8: Weekly Gig Hours */}
            <div style={{ background: '#f59e0b10', padding: '12px', borderRadius: '8px', border: '1px solid #f59e0b30' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600, color: '#b45309', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={13} color="#b45309" /> Weekly Hours
                </label>
                <span style={{ fontSize: '13px', color: '#b45309', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{gigHours} hrs/wk</span>
              </div>
              <input 
                type="range" 
                min="0" max="80" step="1" 
                value={gigHours} 
                onChange={(e) => handleChange(setGigHours, 'gigHours', Number(e.target.value))}
                style={{ width: '100%', accentColor: '#f59e0b' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#b45309', marginTop: '2px' }}>
                <span>0 hrs</span>
                <span>80 hrs</span>
              </div>
            </div>
          </>
        )}

      </div>
    </div>
  );
}
