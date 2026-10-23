import React from 'react';
import { Activity, Bell, User, Building, Users } from 'lucide-react';
import { usePersona } from '../context/PersonaContext';
import { useVerification } from '../context/VerificationContext';
import { useNavigate } from 'react-router-dom';

export default function Header() {
  const { persona, togglePersona } = usePersona();
  const { status } = useVerification();
  const navigate = useNavigate();
  const statusText = persona === 'bank'
    ? 'Institution view'
    : status === 'ready'
      ? 'Verification ready'
      : status === 'loading'
        ? 'Verification in progress'
        : status === 'error'
          ? 'Verification needs attention'
          : 'Awaiting verification';
  const statusColor = persona === 'bank'
    ? 'var(--violet)'
    : status === 'ready'
      ? 'var(--accent)'
      : status === 'error'
        ? 'var(--danger)'
        : 'var(--text-tertiary)';

  const handleToggle = () => {
    togglePersona();
    if (persona === 'worker') {
      navigate('/bank/overview');
    } else {
      navigate('/worker/dashboard');
    }
  };

  return (
    <header style={{ marginBottom: '24px', padding: '12px 0', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
      
      {/* View mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0', border: '1px solid var(--border)' }}>
        <button 
          onClick={persona === 'bank' ? handleToggle : undefined}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px', 
            border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontWeight: 500, fontSize: '13px',
            background: persona === 'worker' ? 'var(--accent)' : 'var(--bg-card)',
            color: persona === 'worker' ? '#fff' : 'var(--text-secondary)',
            transition: 'background 0.1s'
          }}>
          <Users size={14} /> Worker
        </button>
        
        <button 
          onClick={persona === 'worker' ? handleToggle : undefined}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px', 
            border: 'none', borderLeft: '1px solid var(--border)', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontWeight: 500, fontSize: '13px',
            background: persona === 'bank' ? 'var(--violet)' : 'var(--bg-card)',
            color: persona === 'bank' ? '#fff' : 'var(--text-secondary)',
            transition: 'background 0.1s'
          }}>
          <Building size={14} /> Bank
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: statusColor, fontWeight: 500 }}>
          <Activity size={12} className={status === 'loading' ? 'animate-pulse' : undefined} />
          {statusText}
        </div>

        {/* Bell */}
        <button style={{ background: 'transparent', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: '4px' }}>
          <Bell size={18} />
        </button>

        {/* User */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '16px', borderLeft: '1px solid var(--border)' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {persona === 'worker' ? 'Vineet' : 'Lending Officer'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              {persona === 'worker' ? 'Worker account' : 'Admin'}
            </div>
          </div>
          <div style={{ width: '32px', height: '32px', background: 'var(--bg-page)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {persona === 'worker' ? <User size={16} color="var(--text-secondary)" /> : <Building size={16} color="var(--text-secondary)" />}
          </div>
        </div>
      </div>
    </header>
  );
}
