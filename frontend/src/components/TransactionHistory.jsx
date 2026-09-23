import React from 'react';

export default function TransactionHistory() {
  return (
    <div>
      <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '24px' }}>Transaction History</h2>
      <div className="glass-card" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <p>Full transaction history will be available here.</p>
      </div>
    </div>
  );
}
