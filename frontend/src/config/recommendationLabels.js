const RECOMMENDATION_LABELS = {
  PROCEED_TO_UNDERWRITING: {
    label: 'Proceed to normal underwriting',
    summary:
      'The available evidence supports taking this request through the normal underwriting process.',
    tone: 'positive',
  },
  NEEDS_MORE_EVIDENCE: {
    label: 'Needs more evidence',
    summary:
      'The available evidence is not yet strong enough for this assessment. Additional or corroborating records may help.',
    tone: 'caution',
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    summary:
      'There is not enough reliable income evidence to produce a useful verification result.',
    tone: 'attention',
  },
  NOT_AFFORDABLE_AT_REQUESTED_EMI: {
    label: 'Requested EMI exceeds what the verified income supports',
    summary:
      'The proposed repayment amount is above the maximum monthly amount supported by conservative verified income.',
    tone: 'attention',
  },
  MANUAL_REVIEW_HIGH_RISK: {
    label: 'Manual review recommended (higher reference risk)',
    summary:
      'The reference-population risk signal is higher, so a person should review the application before proceeding.',
    tone: 'caution',
  },
};

const FLAG_LABELS = {
  SOURCES_DISAGREE: 'UPI and SMS records disagree',
  SINGLE_SOURCE: 'Single evidence source',
  EXPENSES_INCOMPLETE: 'Living or food costs missing',
  NO_EVIDENCE: 'No usable income evidence',
  SHORT_HISTORY: 'Limited income history',
  HIGH_VOLATILITY: 'Income varies sharply',
  FEW_SENDERS: 'Few income senders',
  STATED_OVERSTATED: 'Stated income is above evidence',
  STATED_CONSISTENT: 'Stated income is consistent with evidence',
  STATED_UNDERSTATED: 'Stated income is below evidence',
  UNVERIFIED_SMS: 'SMS evidence is unverified',
  UNVERIFIED_EVIDENCE_ONLY: 'Only unverified SMS evidence',
  EVIDENCE_MALFORMED: 'Evidence month format was invalid',
  EVIDENCE_GAP: 'Missing calendar months',
  LATEST_MONTH_SPIKE: 'Latest month inflow spike',
  CONSTANT_INFLOW: 'Same inflow repeated across months',
  SENDER_DROP: 'Fewer unique senders recently',
};

const SEVERITY_LABELS = {
  INFO: 'Information',
  MEDIUM: 'Medium',
  HIGH: 'High',
  CRITICAL: 'Critical',
};

const CONSISTENCY_FLAG_CODES = new Set([
  'EVIDENCE_MALFORMED',
  'EVIDENCE_GAP',
  'LATEST_MONTH_SPIKE',
  'CONSTANT_INFLOW',
  'SENDER_DROP',
]);

const PIPELINE_FLAG_CODES = new Set([
  'UNVERIFIED_SMS',
  'UNVERIFIED_EVIDENCE_ONLY',
]);

const TONE_NAMES = {
  positive: 'Positive',
  caution: 'Caution',
  attention: 'Attention',
  neutral: 'Neutral',
};

const FLAG_SOURCE_LABELS = {
  income_engine: 'Income engine',
  consistency_checks: 'Consistency check',
  evidence_pipeline: 'Evidence pipeline',
};

export function getRecommendationMeta(code) {
  if (typeof code === 'string' && RECOMMENDATION_LABELS[code]) {
    return { code, ...RECOMMENDATION_LABELS[code], known: true };
  }

  return {
    code: typeof code === 'string' && code ? code : 'UNKNOWN',
    label: typeof code === 'string' && code ? code : 'Unknown recommendation',
    summary: 'No explanation is available for this recommendation code.',
    tone: 'neutral',
    known: false,
  };
}

export function getFlagLabel(code) {
  if (typeof code === 'string' && FLAG_LABELS[code]) {
    return FLAG_LABELS[code];
  }

  return typeof code === 'string' && code ? code : 'Unknown flag';
}

export function getSeverityLabel(severity) {
  if (typeof severity === 'string' && SEVERITY_LABELS[severity]) {
    return SEVERITY_LABELS[severity];
  }

  return typeof severity === 'string' && severity ? severity : 'Unknown severity';
}

export function getFlagSource(flagOrCode) {
  const flag =
    flagOrCode && typeof flagOrCode === 'object' ? flagOrCode : { code: flagOrCode };
  const source = typeof flag.source === 'string' ? flag.source : '';

  if (FLAG_SOURCE_LABELS[source]) {
    return FLAG_SOURCE_LABELS[source];
  }

  if (source) {
    return source.replaceAll('_', ' ');
  }

  if (CONSISTENCY_FLAG_CODES.has(flag.code)) {
    return 'Consistency check';
  }

  if (PIPELINE_FLAG_CODES.has(flag.code)) {
    return 'Evidence pipeline';
  }

  return 'Income engine';
}

export function getToneName(tone) {
  return TONE_NAMES[tone] || TONE_NAMES.neutral;
}
