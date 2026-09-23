import React from 'react';

export default function LoanOffers() {
  return (
    <div>
      <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '24px' }}>Loan Offers</h2>
      <div className="glass-card" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <p>Pre-approved loan offers based on your credit score will appear here.</p>
      </div>
    </div>
  );
}
