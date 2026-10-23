import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { verifyWorker } from '../services/api';

const VerificationContext = createContext(null);

export function VerificationProvider({ consentRecord, children }) {
  const [verification, setVerification] = useState(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const requestIdRef = useRef(0);
  const loadingRef = useRef(false);

  const runVerification = useCallback(
    async (extra = {}) => {
      if (loadingRef.current) {
        return null;
      }

      loadingRef.current = true;
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setStatus('loading');
      setError(null);

      const payload = {
        ...(consentRecord
          ? {
              worker_id: consentRecord.worker_id,
              consent_id: consentRecord.consent_id,
              phone_number: consentRecord.phone_number,
            }
          : {}),
        ...extra,
      };

      if (!payload.worker_id || !payload.consent_id) {
        const missingConsentError = new Error(
          'A consent record is required before verification can run.',
        );
        missingConsentError.status = null;
        missingConsentError.detail = null;

        if (requestIdRef.current === requestId) {
          loadingRef.current = false;
          setVerification(null);
          setStatus('error');
          setError(missingConsentError.message);
        }

        throw missingConsentError;
      }

      try {
        const result = await verifyWorker(payload);

        if (requestIdRef.current !== requestId) {
          return null;
        }

        setVerification(result);
        setStatus('ready');
        return result;
      } catch (verificationError) {
        if (requestIdRef.current !== requestId) {
          return null;
        }

        setVerification(null);
        setStatus('error');
        setError(
          verificationError instanceof Error
            ? verificationError.message
            : 'Verification failed.',
        );
        throw verificationError;
      } finally {
        if (requestIdRef.current === requestId) {
          loadingRef.current = false;
        }
      }
    },
    [consentRecord],
  );

  const clearVerification = useCallback(() => {
    requestIdRef.current += 1;
    loadingRef.current = false;
    setVerification(null);
    setStatus('idle');
    setError(null);
  }, []);

  return (
    <VerificationContext.Provider
      value={{
        verification,
        status,
        error,
        runVerification,
        clearVerification,
      }}
    >
      {children}
    </VerificationContext.Provider>
  );
}

export function useVerification() {
  const context = useContext(VerificationContext);

  if (!context) {
    throw new Error('useVerification must be used within a VerificationProvider.');
  }

  return context;
}
