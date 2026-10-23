import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import ConsentScreen from './components/ConsentScreen';
import VerificationDashboard from './components/VerificationDashboard';
import Sidebar from './components/Sidebar';
import TransactionHistory from './components/TransactionHistory';
import Settings from './components/Settings';
import BankDashboard from './components/bank/BankDashboard';
import { PersonaProvider } from './context/PersonaContext';
import { VerificationProvider } from './context/VerificationContext';

export default function App() {
  const [consentRecord, setConsentRecord] = useState(null);

  const handleConsentSuccess = (record) => {
    setConsentRecord(record);
  };

  return (
    <PersonaProvider>
      <VerificationProvider consentRecord={consentRecord}>
        <BrowserRouter>
          {!consentRecord ? (
            <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
              <ConsentScreen
                onConsentSuccess={handleConsentSuccess}
                savedConsent={consentRecord}
              />
            </div>
          ) : (
            <div className="app-layout">
              <Sidebar />

              <main className="main-content">
                <Header />

                <Routes>
                  {/* Redirect root to worker dashboard */}
                  <Route path="/" element={<Navigate to="/worker/dashboard" replace />} />
                  <Route path="/dashboard" element={<Navigate to="/worker/dashboard" replace />} />

                  {/* Worker Routes */}
                  <Route path="/worker/dashboard" element={<VerificationDashboard />} />
                  <Route path="/worker/transactions" element={<TransactionHistory consentRecord={consentRecord} />} />
                  <Route path="/worker/settings" element={<Settings />} />

                  {/* Bank Routes */}
                  <Route path="/bank/overview" element={<BankDashboard />} />
                  <Route path="/bank/applicants" element={<div className="glass-card"><h2 style={{fontSize: '16px', fontWeight: 600}}>Applicant List</h2><p style={{color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px'}}>Coming soon.</p></div>} />
                  <Route path="/bank/compliance" element={<div className="glass-card"><h2 style={{fontSize: '16px', fontWeight: 600}}>Compliance Audit</h2><p style={{color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px'}}>Coming soon.</p></div>} />

                  {/* Fallback */}
                  <Route path="*" element={<Navigate to="/worker/dashboard" replace />} />
                </Routes>
              </main>
            </div>
          )}
        </BrowserRouter>
      </VerificationProvider>
    </PersonaProvider>
  );
}
