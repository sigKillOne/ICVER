import React, { useState, useMemo } from 'react';
import { Search, Filter, IndianRupee, ArrowDownLeft, ArrowUpRight, CheckCircle2 } from 'lucide-react';
import { usePersona } from '../context/PersonaContext';

const generateMockData = (phone) => {
  if (phone === '5556667777') {
    return [
      { id: 'TXN-G1', date: '25 Sep, 10:00', vpa: 'swiggy@hdfc', category: 'Platform Payout', type: 'credit', amount: 3200, status: 'Completed' },
      { id: 'TXN-G2', date: '24 Sep, 18:30', vpa: 'iocl@sbi', category: 'Fuel', type: 'debit', amount: 150, status: 'Completed' },
      { id: 'TXN-G3', date: '24 Sep, 14:20', vpa: 'customer@okicici', category: 'Tip', type: 'credit', amount: 40, status: 'Completed' },
      { id: 'TXN-G4', date: '20 Sep, 09:15', vpa: 'jio@ril', category: 'Mobile Recharge', type: 'debit', amount: 299, status: 'Completed' },
      { id: 'TXN-G5', date: '18 Sep, 10:00', vpa: 'zomato@icici', category: 'Platform Payout', type: 'credit', amount: 3150, status: 'Completed' },
      { id: 'TXN-G6', date: '17 Sep, 19:45', vpa: 'iocl@sbi', category: 'Fuel', type: 'debit', amount: 200, status: 'Completed' },
      { id: 'TXN-G7', date: '15 Sep, 13:10', vpa: 'customer2@ybl', category: 'Tip', type: 'credit', amount: 50, status: 'Completed' },
      { id: 'TXN-G8', date: '11 Sep, 10:00', vpa: 'swiggy@hdfc', category: 'Platform Payout', type: 'credit', amount: 3300, status: 'Completed' },
    ];
  } else if (phone === '9998887776') {
    return [
      { id: 'TXN-H1', date: '25 Sep, 14:00', vpa: 'cashout@bank', category: 'Transfer', type: 'debit', amount: 15000, status: 'Completed' },
      { id: 'TXN-H2', date: '15 Sep, 09:30', vpa: 'unknown@ybl', category: 'Transfer', type: 'credit', amount: 15500, status: 'Completed' },
      { id: 'TXN-H3', date: '02 Sep, 11:20', vpa: 'atm@sbi', category: 'Transfer', type: 'debit', amount: 10000, status: 'Completed' },
      { id: 'TXN-H4', date: '22 Aug, 16:40', vpa: 'friend@okicici', category: 'Transfer', type: 'credit', amount: 10500, status: 'Completed' },
      { id: 'TXN-H5', date: '10 Aug, 10:10', vpa: 'cashout@bank', category: 'Transfer', type: 'debit', amount: 20000, status: 'Completed' },
      { id: 'TXN-H6', date: '28 Jul, 08:05', vpa: 'unknown2@ybl', category: 'Transfer', type: 'credit', amount: 20000, status: 'Completed' },
      { id: 'TXN-H7', date: '15 Jul, 12:00', vpa: 'atm@sbi', category: 'Transfer', type: 'debit', amount: 5000, status: 'Completed' },
      { id: 'TXN-H8', date: '01 Jul, 14:30', vpa: 'friend@okicici', category: 'Transfer', type: 'credit', amount: 6000, status: 'Completed' },
    ];
  } else if (phone === '1112223334') {
    return [
      { id: 'TXN-F1', date: '25 Sep, 10:05', vpa: 'accomplice@ybl', category: 'Transfer', type: 'debit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F2', date: '25 Sep, 10:03', vpa: 'accomplice@ybl', category: 'Transfer', type: 'credit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F3', date: '25 Sep, 09:58', vpa: 'accomplice@ybl', category: 'Transfer', type: 'debit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F4', date: '25 Sep, 09:55', vpa: 'accomplice@ybl', category: 'Transfer', type: 'credit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F5', date: '25 Sep, 09:50', vpa: 'accomplice@ybl', category: 'Transfer', type: 'debit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F6', date: '25 Sep, 09:48', vpa: 'accomplice@ybl', category: 'Transfer', type: 'credit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F7', date: '25 Sep, 09:45', vpa: 'accomplice@ybl', category: 'Transfer', type: 'debit', amount: 5000, status: 'Completed' },
      { id: 'TXN-F8', date: '25 Sep, 09:42', vpa: 'accomplice@ybl', category: 'Transfer', type: 'credit', amount: 5000, status: 'Completed' },
    ];
  } else {
    // Default Good Credit Vendor (9876543210)
    return [
      { id: 'TXN-V1', date: '25 Sep, 14:30', vpa: 'customer1@ybl', category: 'UPI Sale', type: 'credit', amount: 150, status: 'Completed' },
      { id: 'TXN-V2', date: '25 Sep, 13:15', vpa: 'customer2@okicici', category: 'UPI Sale', type: 'credit', amount: 350, status: 'Completed' },
      { id: 'TXN-V3', date: '25 Sep, 11:45', vpa: 'customer3@sbi', category: 'UPI Sale', type: 'credit', amount: 50, status: 'Completed' },
      { id: 'TXN-V4', date: '24 Sep, 18:20', vpa: 'customer4@ybl', category: 'UPI Sale', type: 'credit', amount: 200, status: 'Completed' },
      { id: 'TXN-V5', date: '24 Sep, 15:10', vpa: 'customer5@hdfc', category: 'UPI Sale', type: 'credit', amount: 120, status: 'Completed' },
      { id: 'TXN-V6', date: '23 Sep, 10:00', vpa: 'electricity@bescom', category: 'Utility Bill', type: 'debit', amount: 420, status: 'Completed' },
      { id: 'TXN-V7', date: '22 Sep, 09:15', vpa: 'jio@ril', category: 'Mobile Recharge', type: 'debit', amount: 299, status: 'Completed' },
      { id: 'TXN-V8', date: '21 Sep, 16:40', vpa: 'customer6@okicici', category: 'UPI Sale', type: 'credit', amount: 250, status: 'Completed' },
    ];
  }
};

export default function TransactionHistory({ consentRecord }) {
  const { persona } = usePersona(); // to access PersonaContext as requested
  const rawPhone = consentRecord?.phone_number || '9876543210';
  const phoneNumber = rawPhone.replace(/\D/g, '').slice(-10);

  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('All');

  const transactions = useMemo(() => generateMockData(phoneNumber), [phoneNumber]);

  const filteredTransactions = useMemo(() => {
    return transactions.filter(txn => {
      const matchesSearch = txn.vpa.toLowerCase().includes(searchTerm.toLowerCase()) || 
                            txn.category.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesType = filterType === 'All' ? true : 
                          filterType === 'Credits Only' ? txn.type === 'credit' : 
                          txn.type === 'debit';
      return matchesSearch && matchesType;
    });
  }, [transactions, searchTerm, filterType]);

  const totalInflow = useMemo(() => {
    return transactions.filter(t => t.type === 'credit').reduce((sum, t) => sum + t.amount, 0);
  }, [transactions]);

  const avgSize = useMemo(() => {
    if (transactions.length === 0) return 0;
    const totalVolume = transactions.reduce((sum, t) => sum + t.amount, 0);
    return Math.round(totalVolume / transactions.length);
  }, [transactions]);

  return (
    <div>
      <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '24px' }}>Transaction History</h2>
      
      {/* Summary Metric Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px' }}>Total Monthly Inflow</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ background: '#ecfdf5', padding: '8px', borderRadius: '8px', color: '#059669' }}>
              <IndianRupee size={20} />
            </div>
            <h3 style={{ fontSize: '1.5rem', fontWeight: 700 }}>₹{totalInflow.toLocaleString()}</h3>
          </div>
        </div>
        
        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px' }}>Transaction Count</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ background: '#f0f9ff', padding: '8px', borderRadius: '8px', color: '#0284c7' }}>
              <CheckCircle2 size={20} />
            </div>
            <h3 style={{ fontSize: '1.5rem', fontWeight: 700 }}>{transactions.length}</h3>
          </div>
        </div>

        <div className="glass-card" style={{ padding: '20px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px' }}>Avg Transaction Size</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ background: '#fef2f2', padding: '8px', borderRadius: '8px', color: '#dc2626' }}>
              <IndianRupee size={20} />
            </div>
            <h3 style={{ fontSize: '1.5rem', fontWeight: 700 }}>₹{avgSize.toLocaleString()}</h3>
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ padding: '24px' }}>
        {/* Filter & Search Bar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '24px', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: '1', minWidth: '250px' }}>
            <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
            <input 
              type="text" 
              placeholder="Search by VPA or Category..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px 10px 40px',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                background: 'var(--bg-default)',
                color: 'var(--text-primary)',
                fontSize: '14px'
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Filter size={18} color="var(--text-secondary)" />
            <select 
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              style={{
                padding: '10px 12px',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                background: 'var(--bg-default)',
                color: 'var(--text-primary)',
                fontSize: '14px',
                cursor: 'pointer'
              }}
            >
              <option value="All">All Transactions</option>
              <option value="Credits Only">Credits Only</option>
              <option value="Debits Only">Debits Only</option>
            </select>
          </div>
        </div>

        {/* Ledger Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Date & Time</th>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Transaction ID / VPA</th>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Category</th>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Type</th>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Amount (₹)</th>
                <th style={{ padding: '12px', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '13px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.length > 0 ? (
                filteredTransactions.map((txn, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '16px 12px', fontSize: '14px' }}>{txn.date}</td>
                    <td style={{ padding: '16px 12px', fontSize: '14px' }}>
                      <div style={{ fontWeight: 500 }}>{txn.id}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{txn.vpa}</div>
                    </td>
                    <td style={{ padding: '16px 12px', fontSize: '14px' }}>{txn.category}</td>
                    <td style={{ padding: '16px 12px', fontSize: '14px' }}>
                      {txn.type === 'credit' ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: '#ecfdf5', color: '#059669', padding: '4px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 600 }}>
                          <ArrowDownLeft size={14} /> Credit
                        </span>
                      ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: '#fef2f2', color: '#dc2626', padding: '4px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 600 }}>
                          <ArrowUpRight size={14} /> Debit
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '16px 12px', fontSize: '14px', fontWeight: 600, color: txn.type === 'credit' ? '#059669' : '#dc2626' }}>
                      {txn.type === 'credit' ? '+' : '-'}₹{txn.amount.toLocaleString()}
                    </td>
                    <td style={{ padding: '16px 12px', fontSize: '14px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#059669', fontSize: '12px', fontWeight: 500 }}>
                        <CheckCircle2 size={14} /> {txn.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="6" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    No transactions found matching your criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
