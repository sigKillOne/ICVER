import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, History, Settings, ShieldCheck, Users, Briefcase, FileSearch } from 'lucide-react';
import { usePersona } from '../context/PersonaContext';
import { useVerification } from '../context/VerificationContext';

export default function Sidebar() {
  const { persona } = usePersona();
  const { verification, status } = useVerification();
  const confidenceLevel = verification?.evidence?.confidence_level;
  const verificationStatus = status === 'ready' && confidenceLevel
    ? `Evidence confidence: ${confidenceLevel}`
    : status === 'loading'
      ? 'Verification in progress'
      : status === 'error'
        ? 'Verification needs attention'
        : 'Start verification from the dashboard.';

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            background: persona === 'worker' ? 'var(--accent)' : 'var(--violet)',
            width: '28px',
            height: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <ShieldCheck size={16} color="#fff" />
          </div>
          <div>
            <h2 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.01em' }}>ICVER</h2>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              {persona === 'worker' ? 'Worker Verification' : 'Lender Portal'}
            </span>
          </div>
        </div>
      </div>
      
      <nav className="sidebar-nav">
        {persona === 'worker' ? (
          <>
            <NavLink to="/worker/dashboard" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <LayoutDashboard size={16} />
              Income Verification
            </NavLink>
            <NavLink to="/worker/transactions" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <History size={16} />
              Transactions
            </NavLink>
            <NavLink to="/worker/settings" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <Settings size={16} />
              Settings
            </NavLink>
          </>
        ) : (
          <>
            <NavLink to="/bank/overview" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <Briefcase size={16} />
              Overview
            </NavLink>
            <NavLink to="/bank/applicants" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <Users size={16} />
              Applicants
            </NavLink>
            <NavLink to="/bank/compliance" className={({ isActive }) => isActive ? 'sidebar-link active' : 'sidebar-link'}>
              <FileSearch size={16} />
              Compliance
            </NavLink>
          </>
        )}
      </nav>
      
      {persona === 'worker' && (
        <div style={{ padding: '16px 12px', marginTop: 'auto' }}>
          <div style={{ padding: '12px', background: 'var(--accent-subtle)', border: '1px solid #ccfbf1' }}>
            <p style={{ fontSize: '12px', color: 'var(--text-primary)', marginBottom: '4px', fontWeight: 600 }}>Income verification</p>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: 0 }}>{verificationStatus}</p>
          </div>
        </div>
      )}
    </aside>
  );
}
