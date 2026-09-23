import React, { createContext, useState, useContext } from 'react';

const PersonaContext = createContext();

export const PersonaProvider = ({ children }) => {
  const [persona, setPersona] = useState('worker'); // 'worker' or 'bank'

  const togglePersona = () => {
    setPersona((prev) => (prev === 'worker' ? 'bank' : 'worker'));
  };

  return (
    <PersonaContext.Provider value={{ persona, togglePersona }}>
      {children}
    </PersonaContext.Provider>
  );
};

export const usePersona = () => useContext(PersonaContext);
