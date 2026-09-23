import React, { useState, useEffect } from 'react';
import { Sliders, TrendingUp } from 'lucide-react';

export default function WhatIfSimulator({ currentScore }) {
  const [inflow, setInflow] = useState(25000);
  const [freq, setFreq] = useState(12);
  const [regularity, setRegularity] = useState(0.7);
  const [predictedScore, setPredictedScore] = useState(currentScore);

  useEffect(() => {
    const inflow_norm = Math.min(Math.max(inflow / 60000, 0), 1);
    const freq_norm = Math.min(Math.max(freq / 25.0, 0), 1);
    const regularity_norm = Math.min(Math.max(regularity, 0), 1);
    const recency_norm = Math.min(Math.max(1.0 - (7.0 / 90.0), 0), 1);

    const calcScore = 
      30 * inflow_norm + 
      25 * freq_norm + 
      25 * regularity_norm + 
      20 * recency_norm;

    let finalScore = Math.round(calcScore + 2);
    finalScore = Math.min(Math.max(finalScore, 0), 100);
    
    setPredictedScore(finalScore);
  }, [inflow, freq, regularity]);

  const scoreDiff = predictedScore - currentScore;

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h3 className="card-title" style={{ marginBottom: '4px' }}><Sliders size={14} color="var(--accent)" /> What-If Simulator</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Adjust parameters to see projected score changes.
          </p>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 16px', background: 'var(--bg-page)', border: '1px solid var(--border)' }}>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', fontWeight: 600 }}>Predicted</span>
            <span style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{predictedScore}</span>
          </div>
          
          {scoreDiff !== 0 && (
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '3px', fontSize: '13px', fontWeight: 600,
              color: scoreDiff > 0 ? 'var(--accent)' : 'var(--danger)',
              background: scoreDiff > 0 ? 'var(--accent-subtle)' : 'var(--danger-subtle)',
              padding: '3px 8px'
            }}>
              <TrendingUp size={14} style={{ transform: scoreDiff < 0 ? 'rotate(180deg)' : 'none' }} />
              {scoreDiff > 0 ? '+' : ''}{scoreDiff}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px' }}>
        
        {/* Slider 1 */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Monthly UPI Inflow (₹)</label>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>₹{inflow.toLocaleString()}</span>
          </div>
          <input 
            type="range" 
            min="5000" max="60000" step="1000" 
            value={inflow} 
            onChange={(e) => setInflow(Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>₹5k</span>
            <span>₹60k</span>
          </div>
        </div>

        {/* Slider 2 */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Weekly Txn Frequency</label>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{freq}</span>
          </div>
          <input 
            type="range" 
            min="1" max="35" step="1" 
            value={freq} 
            onChange={(e) => setFreq(Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>1</span>
            <span>35</span>
          </div>
        </div>

        {/* Slider 3 */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Recharge Regularity</label>
            <span style={{ fontSize: '13px', color: 'var(--violet)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{Math.round(regularity * 100)}%</span>
          </div>
          <input 
            type="range" 
            min="0" max="1" step="0.05" 
            value={regularity} 
            onChange={(e) => setRegularity(Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--violet)' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            <span>0%</span>
            <span>100%</span>
          </div>
        </div>

      </div>
    </div>
  );
}
