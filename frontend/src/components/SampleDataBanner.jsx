import React from 'react';
import { Info } from 'lucide-react';

export default function SampleDataBanner() {
  return (
    <div
      role="note"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        padding: '12px 14px',
        marginBottom: '20px',
        background: 'var(--warning-subtle)',
        border: '1px solid #fde68a',
        borderLeft: '4px solid var(--warning)',
      }}
    >
      <Info size={18} color="var(--warning)" style={{ flexShrink: 0, marginTop: '1px' }} />
      <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
        Sample data: this page is not connected to the verification API
      </p>
    </div>
  );
}
