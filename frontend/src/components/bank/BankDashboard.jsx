import React, { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { ShieldAlert, CheckCircle, Search, X } from 'lucide-react';

const riskData = [
  { name: 'Eligible', value: 450, color: '#0f766e' },
  { name: 'Pending', value: 200, color: '#d97706' },
  { name: 'Rejected', value: 150, color: '#dc2626' },
];

const mockApplicants = [
  { id: 'APP-1001', name: 'Ravi Kumar', score: 82, status: 'approved', risk: 'Low', requested: '₹50,000' },
  { id: 'APP-1002', name: 'Sunita Devi', score: 65, status: 'pending', risk: 'Medium', requested: '₹20,000' },
  { id: 'APP-1003', name: 'Amit Singh', score: 45, status: 'rejected', risk: 'High', requested: '₹10,000', fraudFlag: true },
  { id: 'APP-1004', name: 'Priya Sharma', score: 88, status: 'approved', risk: 'Low', requested: '₹75,000' },
  { id: 'APP-1005', name: 'Rahul Verma', score: 58, status: 'pending', risk: 'Medium', requested: '₹15,000' },
];

const mockShapData = [
  { feature: 'UPI Monthly Inflow', value: '+18.5', type: 'positive' },
  { feature: 'Weekly Txn Frequency', value: '+12.1', type: 'positive' },
  { feature: 'Recharge Regularity Index', value: '+8.3', type: 'positive' },
  { feature: 'Days Since Last Txn', value: '-4.2', type: 'negative' },
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Lender Overview</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Portfolio risk and applicant management.</p>
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

        {/* Applicants table */}
        <div className="glass-card grid-col-8" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-header" style={{ marginBottom: '12px' }}>
            <h3 className="card-title">Recent Applicants</h3>
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
                  <th>Loan Req.</th>
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
                      <span style={{ fontWeight: 700, fontSize: '13px', fontFamily: 'var(--font-mono)', color: app.score > 70 ? 'var(--accent)' : app.score > 50 ? 'var(--warning)' : 'var(--danger)' }}>
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

      {/* Audit Modal */}
      {auditModalOpen && selectedApplicant && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100
        }}>
          <div style={{ width: '100%', maxWidth: '480px', background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '28px', position: 'relative' }}>
            <button 
              onClick={() => setAuditModalOpen(false)}
              style={{ position: 'absolute', top: '20px', right: '20px', background: 'transparent', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
            
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>Audit Log</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '20px' }}>
              SHAP attribution for {selectedApplicant.name} ({selectedApplicant.id}).
            </p>
            
            {selectedApplicant.fraudFlag && (
              <div style={{ background: 'var(--danger-subtle)', border: '1px solid #fecaca', padding: '12px', marginBottom: '16px', display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                <ShieldAlert color="var(--danger)" size={20} />
                <div>
                  <h4 style={{ color: 'var(--danger)', fontSize: '13px', fontWeight: 600, margin: '0 0 2px 0' }}>Synthetic Volume Detected</h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>Cyclic P2P transactions detected. 20% penalty applied.</p>
                </div>
              </div>
            )}

            <div style={{ background: 'var(--bg-page)', padding: '16px', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', borderBottom: '1px solid var(--border)', paddingBottom: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Feature</span>
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>SHAP Value</span>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {mockShapData.map((data, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{data.feature}</span>
                    <span style={{ 
                      fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)',
                      color: data.type === 'positive' ? 'var(--accent)' : 'var(--danger)' 
                    }}>
                      {data.value}
                    </span>
                  </div>
                ))}
                {selectedApplicant.fraudFlag && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--danger-subtle)', padding: '4px 8px' }}>
                    <span style={{ fontSize: '13px', color: 'var(--danger)' }}>Synthetic Penalty</span>
                    <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--danger)' }}>-20%</span>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 500 }}>Base Score</span>
                <span style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>45.0</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
                <span style={{ fontSize: '14px', fontWeight: 600 }}>Final Score</span>
                <span style={{ fontSize: '14px', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{selectedApplicant.score}</span>
              </div>
            </div>

            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn-secondary" onClick={() => setAuditModalOpen(false)}>Close</button>
              <button className="btn-primary">Download PDF</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
