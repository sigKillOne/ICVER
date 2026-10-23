import React, { useMemo, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  FileText,
  Gauge,
  Info,
  Loader2,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import { useVerification } from '../context/VerificationContext';
import {
  getFlagLabel,
  getFlagSource,
  getRecommendationMeta,
  getSeverityLabel,
  getToneName,
} from '../config/recommendationLabels';

const CURRENCY_FORMATTER = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const DATE_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const TONE_STYLES = {
  positive: {
    background: 'var(--accent-subtle)',
    border: '#ccfbf1',
    color: 'var(--accent)',
    icon: CheckCircle2,
  },
  caution: {
    background: 'var(--warning-subtle)',
    border: '#fde68a',
    color: 'var(--warning)',
    icon: AlertTriangle,
  },
  attention: {
    background: 'var(--danger-subtle)',
    border: '#fecaca',
    color: 'var(--danger)',
    icon: AlertCircle,
  },
  neutral: {
    background: 'var(--bg-page)',
    border: 'var(--border)',
    color: 'var(--text-secondary)',
    icon: Info,
  },
};

const SEVERITY_STYLES = {
  INFO: { background: '#eff6ff', color: '#2563eb', border: '#bfdbfe' },
  MEDIUM: { background: 'var(--warning-subtle)', color: 'var(--warning)', border: '#fde68a' },
  HIGH: { background: 'var(--danger-subtle)', color: 'var(--danger)', border: '#fecaca' },
  CRITICAL: { background: '#450a0a', color: '#ffffff', border: '#450a0a' },
};

const OUTGOING_FIELDS = [
  { key: 'rent', label: 'Rent' },
  { key: 'utilities', label: 'Utilities' },
  { key: 'groceries', label: 'Groceries and food' },
  { key: 'existing_emi', label: 'Existing EMI' },
  { key: 'recharge', label: 'Mobile recharge' },
  { key: 'other', label: 'Other monthly costs' },
];

const COMPONENT_LABELS = {
  coverage: 'Coverage',
  agreement: 'Source agreement',
  stability: 'Stability',
  diversity: 'Sender diversity',
};

const INITIAL_FORM = {
  stated_monthly_income: '',
  household_size: '',
  occupation_type: '',
  proposed_emi: '',
  tenure_months: '',
  rent: '',
  utilities: '',
  groceries: '',
  existing_emi: '',
  recharge: '',
  other: '',
};

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatMoney(value) {
  return isFiniteNumber(value) ? CURRENCY_FORMATTER.format(value) : '—';
}

function formatPercent(value, digits = 1) {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(digits)}%` : '—';
}

function formatScore(value) {
  return isFiniteNumber(value) ? Math.round(value).toString() : '—';
}

function formatDate(value) {
  if (!value) {
    return '—';
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : DATE_FORMATTER.format(parsed);
}

function humanizeKey(value) {
  if (typeof value !== 'string' || !value) {
    return value || '—';
  }

  const text = value.replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function parseOptionalNumber(rawValue, label) {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return undefined;
  }

  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a number of zero or more.`);
  }

  return value;
}

function parseOptionalInteger(rawValue, label, min, max) {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return undefined;
  }

  const value = Number(trimmed);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${label} must be a whole number between ${min} and ${max}.`);
  }

  return value;
}

function buildVerificationInput(form) {
  const extra = {};

  const statedIncome = parseOptionalNumber(
    form.stated_monthly_income,
    'Stated monthly income',
  );
  if (statedIncome !== undefined) {
    extra.stated_monthly_income = statedIncome;
  }

  const householdSize = parseOptionalInteger(
    form.household_size,
    'Household size',
    1,
    50,
  );
  if (householdSize !== undefined) {
    extra.household_size = householdSize;
  }

  const proposedEmi = parseOptionalNumber(form.proposed_emi, 'Requested EMI');
  if (proposedEmi !== undefined) {
    extra.proposed_emi = proposedEmi;
  }

  const tenureMonths = parseOptionalInteger(
    form.tenure_months,
    'Tenure',
    1,
    120,
  );
  if (tenureMonths !== undefined) {
    extra.tenure_months = tenureMonths;
  }

  const occupationType = form.occupation_type.trim();
  if (occupationType) {
    extra.occupation_type = occupationType;
  }

  const monthlyOutgoings = {};
  OUTGOING_FIELDS.forEach(({ key, label }) => {
    const value = parseOptionalNumber(form[key], label);
    if (value !== undefined) {
      monthlyOutgoings[key] = value;
    }
  });

  if (Object.keys(monthlyOutgoings).length > 0) {
    extra.monthly_outgoings = monthlyOutgoings;
  }

  return extra;
}

function SectionHeading({ icon: Icon, title, description, id }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <h3 id={id} className="card-title" style={{ marginBottom: description ? '4px' : 0 }}>
        {Icon ? <Icon size={14} /> : null}
        {title}
      </h3>
      {description ? (
        <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>
          {description}
        </p>
      ) : null}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, detail, tone = 'neutral' }) {
  const colors = {
    positive: 'var(--accent)',
    caution: 'var(--warning)',
    attention: 'var(--danger)',
    neutral: 'var(--text-primary)',
  };

  return (
    <div className="glass-card grid-col-3" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '28px',
            height: '28px',
            background: 'var(--bg-page)',
            color: colors[tone],
          }}
        >
          <Icon size={15} />
        </div>
        <p
          style={{
            margin: 0,
            color: 'var(--text-secondary)',
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </p>
      </div>
      <p style={{ margin: 0, color: colors[tone], fontSize: '22px', fontWeight: 700 }}>
        {value}
      </p>
      {detail ? (
        <p style={{ margin: '4px 0 0', color: 'var(--text-secondary)', fontSize: '12px' }}>
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function RecommendationBanner({ recommendation }) {
  const meta = getRecommendationMeta(recommendation?.code);
  const style = TONE_STYLES[meta.tone] || TONE_STYLES.neutral;
  const Icon = style.icon;
  const reasons = Array.isArray(recommendation?.reasons) ? recommendation.reasons : [];
  const caveats = Array.isArray(recommendation?.caveats) ? recommendation.caveats : [];

  return (
    <section
      aria-labelledby="recommendation-title"
      style={{
        padding: '20px',
        marginBottom: '20px',
        background: style.background,
        border: `1px solid ${style.border}`,
        borderLeft: `4px solid ${style.color}`,
      }}
    >
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <Icon size={22} color={style.color} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <h2
              id="recommendation-title"
              style={{ fontSize: '18px', fontWeight: 700, color: style.color, margin: 0 }}
            >
              {meta.label}
            </h2>
            <span
              style={{
                fontSize: '10px',
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: style.color,
              }}
            >
              {getToneName(meta.tone)}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: '4px 0 0' }}>
            {meta.summary}
          </p>
          <code style={{ display: 'inline-block', marginTop: '8px', fontSize: '11px' }}>
            {meta.code}
          </code>

          {reasons.length > 0 ? (
            <div style={{ marginTop: '14px' }}>
              <h3 style={{ fontSize: '12px', marginBottom: '6px' }}>Why this result</h3>
              <ul style={{ margin: 0, paddingLeft: '18px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                {reasons.map((reason, index) => (
                  <li key={`${reason}-${index}`} style={{ marginBottom: '4px' }}>
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {caveats.length > 0 ? (
            <div style={{ marginTop: '14px' }}>
              <h3 style={{ fontSize: '12px', marginBottom: '6px' }}>Caveats</h3>
              <ul style={{ margin: 0, paddingLeft: '18px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                {caveats.map((caveat, index) => (
                  <li key={`${caveat}-${index}`} style={{ marginBottom: '4px' }}>
                    {caveat}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function DataNotice({ notice }) {
  if (!notice) {
    return null;
  }

  return (
    <section
      aria-labelledby="data-notice-title"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        padding: '12px 14px',
        marginBottom: '20px',
        background: '#eff6ff',
        border: '1px solid #bfdbfe',
        borderLeft: '4px solid #2563eb',
      }}
    >
      <Info size={18} color="#2563eb" style={{ flexShrink: 0, marginTop: '1px' }} />
      <div>
        <h2 id="data-notice-title" style={{ fontSize: '12px', color: '#1d4ed8', marginBottom: '2px' }}>
          Data notice
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>{notice}</p>
      </div>
    </section>
  );
}

function LoadingState() {
  return (
    <div
      className="glass-card"
      role="status"
      aria-live="polite"
      style={{ display: 'flex', alignItems: 'center', gap: '12px' }}
    >
      <Loader2 size={20} className="animate-spin" color="var(--accent)" />
      <div>
        <h2 style={{ fontSize: '15px', marginBottom: '2px' }}>Verifying income evidence</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
          The result will appear here when the request completes.
        </p>
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry, retrying }) {
  return (
    <div
      className="glass-card"
      role="alert"
      style={{ borderLeft: '4px solid var(--danger)' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <AlertCircle size={20} color="var(--danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: '15px', color: 'var(--danger)', marginBottom: '4px' }}>
            Verification did not complete
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '14px' }}>
            {message || 'An unexpected error occurred while contacting the verification API.'}
          </p>
          <button type="button" className="btn-secondary" onClick={onRetry} disabled={retrying}>
            {retrying ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Retry verification
          </button>
        </div>
      </div>
    </div>
  );
}

function IdleState() {
  return (
    <div className="glass-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <ShieldCheck size={22} color="var(--accent)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <h2 style={{ fontSize: '16px', marginBottom: '4px' }}>No verification result yet</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '14px' }}>
            Grant consent and submit the worker details to start an income verification.
          </p>
          <a className="btn-primary" href="/" style={{ display: 'inline-flex', textDecoration: 'none' }}>
            Return to consent
          </a>
        </div>
      </div>
    </div>
  );
}

function IncomeCard({ verification }) {
  const income = verification.income || {};
  const expenses = verification.expenses || {};

  return (
    <section className="glass-card grid-col-6" aria-labelledby="income-title">
      <SectionHeading
        id="income-title"
        icon={Wallet}
        title="Income and expenses"
        description="Conservative income is the lower end of the evidence range."
      />
      <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '16px', margin: 0 }}>
        <div>
          <dt style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Conservative monthly income</dt>
          <dd style={{ margin: '2px 0 0', fontSize: '20px', fontWeight: 700 }}>{formatMoney(income.conservative)}</dd>
        </div>
        <div>
          <dt style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Estimated monthly expenses</dt>
          <dd style={{ margin: '2px 0 0', fontSize: '20px', fontWeight: 700 }}>{formatMoney(expenses.estimated)}</dd>
        </div>
      </dl>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Evidence range</p>
          <p style={{ fontSize: '13px', margin: 0 }}>
            {formatMoney(income.low)} to {formatMoney(income.high)}
          </p>
          <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', margin: '2px 0 0' }}>
            Midpoint {formatMoney(income.mid)}
          </p>
        </div>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Stated monthly income</p>
          <p style={{ fontSize: '13px', margin: 0 }}>{formatMoney(income.stated)}</p>
          <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', margin: '2px 0 0' }}>
            Relative to evidence {formatPercent(income.stated_vs_evidence_ratio)}
          </p>
        </div>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Expense detail</p>
          <p style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', margin: 0 }}>
            {expenses.complete ? <CheckCircle2 size={14} color="var(--accent)" /> : <AlertTriangle size={14} color="var(--warning)" />}
            {expenses.complete ? 'Living and food costs included' : 'Basic living costs not fully captured'}
          </p>
        </div>
      </div>
    </section>
  );
}

function EvidenceCard({ evidence }) {
  const score = isFiniteNumber(evidence.confidence_score)
    ? Math.max(0, Math.min(100, evidence.confidence_score))
    : null;
  const components = evidence.components && typeof evidence.components === 'object'
    ? Object.entries(evidence.components)
    : [];
  const provenance = evidence.provenance && typeof evidence.provenance === 'object'
    ? Object.entries(evidence.provenance)
    : [];

  return (
    <section className="glass-card grid-col-6" aria-labelledby="evidence-title">
      <SectionHeading
        id="evidence-title"
        icon={FileText}
        title="Evidence confidence"
        description="The score reflects coverage, source agreement, stability, and sender diversity."
      />
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '8px' }}>
        <span style={{ fontSize: '28px', fontWeight: 700 }}>{formatScore(score)}</span>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>out of 100</span>
        <span className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
          {evidence.confidence_level || 'Unknown'}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label="Evidence confidence score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score ?? 0}
        style={{ height: '8px', background: 'var(--bg-page)', border: '1px solid var(--border)', marginBottom: '16px' }}
      >
        <div
          style={{
            width: `${score ?? 0}%`,
            height: '100%',
            background: 'var(--accent)',
          }}
        />
      </div>

      {evidence.confidence_capped ? (
        <p style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '10px', marginBottom: '14px', background: 'var(--warning-subtle)', color: 'var(--text-secondary)', fontSize: '12px' }}>
          <AlertTriangle size={15} color="var(--warning)" style={{ flexShrink: 0, marginTop: '1px' }} />
          Confidence was capped by the evidence rules.
        </p>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
        {components.map(([key, component]) => (
          <div key={key} style={{ padding: '10px', background: 'var(--bg-page)' }}>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>
              {COMPONENT_LABELS[key] || humanizeKey(key)}
            </p>
            <p style={{ fontSize: '13px', margin: 0 }}>
              {isFiniteNumber(component?.points) ? component.points : '—'}
              {isFiniteNumber(component?.max) ? ` / ${component.max}` : ''}
            </p>
          </div>
        ))}
        {components.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>No component breakdown was returned.</p>
        ) : null}
      </div>

      <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '8px' }}>
          <p style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', margin: 0 }}>
            <CalendarDays size={14} /> {evidence.months ?? 0} month(s) of evidence
          </p>
        </div>
        {provenance.length > 0 ? (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {provenance.map(([key, value]) => (
              <span key={key} className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                {humanizeKey(key)}: {humanizeKey(String(value))}
              </span>
            ))}
          </div>
        ) : null}
        {evidence.consistency_note ? (
          <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginTop: '10px', marginBottom: 0 }}>
            {evidence.consistency_note}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function AffordabilityCard({ affordability }) {
  return (
    <section className="glass-card grid-col-6" aria-labelledby="affordability-title">
      <SectionHeading
        id="affordability-title"
        icon={ReceiptText}
        title="Affordability"
        description="Shares are based on conservative verified income and the recorded obligations."
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Existing obligations share</p>
          <p style={{ fontSize: '20px', fontWeight: 700, margin: 0 }}>{formatPercent(affordability.foir_current)}</p>
        </div>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Share with requested EMI</p>
          <p style={{ fontSize: '20px', fontWeight: 700, margin: 0 }}>{formatPercent(affordability.foir_with_proposed)}</p>
        </div>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Policy share cap</p>
          <p style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{formatPercent(affordability.foir_cap)}</p>
        </div>
        <div>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Maximum supported monthly repayment</p>
          <p style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{formatMoney(affordability.max_affordable_emi)}</p>
        </div>
      </div>
      <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginTop: '16px', marginBottom: 0 }}>
        These figures describe the verified cash flow and are decision support only.
      </p>
    </section>
  );
}

function RiskFactorList({ factors, direction }) {
  const Icon = direction === 'up' ? TrendingUp : TrendingDown;
  const color = direction === 'up' ? 'var(--danger)' : 'var(--accent)';
  const items = Array.isArray(factors) ? factors : [];

  return (
    <div>
      <h4 style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginBottom: '8px', color }}>
        <Icon size={14} /> {direction === 'up' ? 'Factors raising relative risk' : 'Factors lowering relative risk'}
      </h4>
      {items.length > 0 ? (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {items.map((factor, index) => (
            <li key={`${factor.feature || factor.label || 'factor'}-${index}`} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '8px 10px', background: 'var(--bg-page)', fontSize: '12px' }}>
              <span>{factor.label || humanizeKey(factor.feature)}</span>
              <span style={{ color: 'var(--text-secondary)' }}>{formatPercent(factor.relative_size)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ color: 'var(--text-tertiary)', fontSize: '12px', margin: 0 }}>No factors were returned in this direction.</p>
      )}
    </div>
  );
}

function RiskCard({ riskSignal }) {
  const risk = riskSignal || {};
  const secondary = risk.display_priority === 'secondary';

  return (
    <section
      className="glass-card grid-col-6"
      aria-labelledby="risk-title"
      style={{ opacity: secondary ? 0.82 : 1 }}
    >
      <SectionHeading
        id="risk-title"
        icon={Gauge}
        title="Reference-population risk signal"
        description="A model view based on similar applicants in a public dataset, not this person's own default rate."
      />

      {!risk.available ? (
        <div style={{ display: 'flex', gap: '10px', padding: '12px', background: 'var(--bg-page)' }}>
          <AlertCircle size={18} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: '1px' }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>
            {risk.reason || 'No reference-population risk signal is available for this worker.'}
          </p>
        </div>
      ) : (
        <>
          {secondary && risk.display_note ? (
            <p style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '10px', marginBottom: '14px', background: 'var(--warning-subtle)', color: 'var(--text-secondary)', fontSize: '12px' }}>
              <AlertTriangle size={15} color="var(--warning)" style={{ flexShrink: 0, marginTop: '1px' }} />
              {risk.display_note}
            </p>
          ) : null}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Reference band</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{humanizeKey(risk.band)}</p>
            </div>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Relative risk score</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{formatScore(risk.risk_score_0_100)}</p>
            </div>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Reference default rate</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{formatPercent(risk.reference_population_pd)}</p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
            <span className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
              Reliability: {humanizeKey(risk.reliability)}
            </span>
            <span className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
              Inputs provided: {risk.inputs_provided_count ?? 0}
            </span>
          </div>

          {risk.reliability_note ? (
            <p style={{ color: 'var(--text-secondary)', fontSize: '12px', marginBottom: '14px' }}>
              {risk.reliability_note}
            </p>
          ) : null}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '14px' }}>
            <RiskFactorList factors={risk.top_factors_raising_risk} direction="up" />
            <RiskFactorList factors={risk.top_factors_lowering_risk} direction="down" />
          </div>

          {Array.isArray(risk.inputs_missing) && risk.inputs_missing.length > 0 ? (
            <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginBottom: '10px' }}>
              Missing model inputs: {risk.inputs_missing.map(humanizeKey).join(', ')}
            </p>
          ) : null}

          {risk.reference_note ? (
            <p style={{ padding: '10px', background: 'var(--bg-page)', color: 'var(--text-tertiary)', fontSize: '11px', margin: 0 }}>
              {risk.reference_note}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function FlagsCard({ flags }) {
  const items = Array.isArray(flags) ? flags : [];

  return (
    <section className="glass-card grid-col-12" aria-labelledby="flags-title">
      <SectionHeading
        id="flags-title"
        icon={AlertTriangle}
        title="Evidence flags"
        description="Flags describe evidence quality and consistency; they are not a final credit decision."
      />
      {items.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>No evidence flags were returned.</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {items.map((flag, index) => {
            const severity = SEVERITY_STYLES[flag.severity] || {
              background: 'var(--bg-page)',
              color: 'var(--text-secondary)',
              border: 'var(--border)',
            };

            return (
              <li
                key={`${flag.code || 'flag'}-${index}`}
                style={{ padding: '12px', border: '1px solid var(--border)', background: 'var(--bg-card)' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '6px' }}>
                  <strong style={{ fontSize: '13px' }}>{getFlagLabel(flag.code)}</strong>
                  <span className="badge" style={{ background: severity.background, color: severity.color, border: `1px solid ${severity.border}` }}>
                    {getSeverityLabel(flag.severity)}
                  </span>
                  <span className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                    {getFlagSource(flag)}
                  </span>
                  <code style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>{flag.code}</code>
                </div>
                {flag.message ? (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>{flag.message}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function SmsCard({ smsSummary, smsIgnoredReason }) {
  const summary = smsSummary || {};
  const droppedByReason = summary.dropped_by_reason && typeof summary.dropped_by_reason === 'object'
    ? Object.entries(summary.dropped_by_reason)
    : [];
  const clippedMonths = Array.isArray(summary.clipped_months) ? summary.clipped_months : [];
  const received = summary.received ?? 0;

  return (
    <section className="glass-card grid-col-12" aria-labelledby="sms-title">
      <SectionHeading
        id="sms-title"
        icon={Users}
        title="SMS evidence summary"
        description="SMS messages are client-supplied and are used only as supporting evidence."
      />
      {received === 0 ? (
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
          No SMS messages were submitted for this verification.
        </p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginBottom: '14px' }}>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Received</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{received}</p>
            </div>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Used</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{summary.used ?? 0}</p>
            </div>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Dropped</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{summary.dropped ?? 0}</p>
            </div>
            <div>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Clipped months</p>
              <p style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>{clippedMonths.length}</p>
            </div>
          </div>

          {droppedByReason.length > 0 ? (
            <div style={{ marginBottom: '12px' }}>
              <h3 style={{ fontSize: '12px', marginBottom: '6px' }}>Dropped by reason</h3>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {droppedByReason.map(([reason, count]) => (
                  <span key={reason} className="badge" style={{ background: 'var(--bg-page)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                    {humanizeKey(reason)}: {count}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {clippedMonths.length > 0 ? (
            <div style={{ marginBottom: '12px' }}>
              <h3 style={{ fontSize: '12px', marginBottom: '6px' }}>Clipped months</h3>
              <ul style={{ margin: 0, paddingLeft: '18px', color: 'var(--text-secondary)', fontSize: '12px' }}>
                {clippedMonths.map((month, index) => (
                  <li key={`${month.month || 'month'}-${index}`}>
                    {month.month || 'Unknown month'}: SMS {formatMoney(month.sms_total)}, UPI {formatMoney(month.upi_total)}, used {formatMoney(month.used_total)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {smsIgnoredReason ? (
            <p style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '10px', background: 'var(--warning-subtle)', color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>
              <Info size={15} color="var(--warning)" style={{ flexShrink: 0, marginTop: '1px' }} />
              {smsIgnoredReason}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function ImproveEvidenceForm({ form, onChange, onSubmit, submitting, formError }) {
  const inputStyle = {
    width: '100%',
    padding: '8px 10px',
    border: '1px solid var(--border)',
    background: 'var(--bg-input)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-sans)',
    fontSize: '13px',
  };

  const field = (key, label, options = {}) => (
    <div key={key}>
      <label
        htmlFor={`verify-${key}`}
        style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}
      >
        {label}
      </label>
      <input
        id={`verify-${key}`}
        name={key}
        className="form-input"
        type={options.type || 'number'}
        inputMode={options.type === 'text' ? 'text' : 'decimal'}
        min={options.type === 'text' ? undefined : options.min ?? 0}
        max={options.max}
        step={options.step}
        value={form[key]}
        onChange={(event) => onChange(key, event.target.value)}
        style={inputStyle}
      />
    </div>
  );

  return (
    <section className="glass-card grid-col-12" aria-labelledby="refine-title">
      <SectionHeading
        id="refine-title"
        icon={SlidersHorizontal}
        title="Improve the evidence"
        description="Add any known details and run the verification again. Leave a field blank to omit it."
      />
      <form onSubmit={onSubmit} noValidate>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '14px' }}>
          {field('stated_monthly_income', 'Stated monthly income (INR)')}
          {field('household_size', 'Household size', { type: 'number', step: 1, min: 1, max: 50 })}
          {field('occupation_type', 'Occupation', { type: 'text' })}
          {field('proposed_emi', 'Requested monthly EMI (INR)')}
          {field('tenure_months', 'Tenure (months)', { type: 'number', step: 1, min: 1, max: 120 })}
        </div>

        <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: '12px', marginBottom: '4px' }}>Monthly outgoings</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginBottom: '12px' }}>
            Amounts in INR per month. Include groceries or food costs so the surplus is not overstated.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '14px' }}>
            {OUTGOING_FIELDS.map(({ key, label }) => field(key, `${label} (INR)`))}
          </div>
        </div>

        {formError ? (
          <p role="alert" style={{ marginTop: '14px', padding: '10px', background: 'var(--danger-subtle)', color: 'var(--danger)', fontSize: '12px' }}>
            {formError}
          </p>
        ) : null}

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '18px' }}>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Run verification again
          </button>
          <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', margin: 0 }}>
            Only the fields you fill in are sent.
          </p>
        </div>
      </form>
    </section>
  );
}

export default function VerificationDashboard() {
  const { verification, status, error, runVerification } = useVerification();
  const [form, setForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const recommendation = verification?.recommendation;
  const evidence = verification?.evidence || {};
  const riskSignal = verification?.risk_signal || {};
  const affordability = verification?.affordability || {};
  const income = verification?.income || {};
  const expenses = verification?.expenses || {};
  const flags = Array.isArray(evidence.flags) ? evidence.flags : [];
  const loading = status === 'loading' || submitting;

  const summaryDetail = useMemo(() => {
    const parts = [];
    if (isFiniteNumber(income.low)) {
      parts.push(`Low ${formatMoney(income.low)}`);
    }
    if (isFiniteNumber(income.high)) {
      parts.push(`High ${formatMoney(income.high)}`);
    }
    return parts.join(' · ');
  }, [income.low, income.high]);

  const handleChange = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError('');

    let extra;
    try {
      extra = buildVerificationInput(form);
    } catch (validationError) {
      setFormError(
        validationError instanceof Error ? validationError.message : 'Check the form values.',
      );
      return;
    }

    setSubmitting(true);
    try {
      await runVerification(extra);
    } catch (submitError) {
      setFormError(
        submitError instanceof Error ? submitError.message : 'Verification failed.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '2px' }}>Income Verification</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: 0 }}>
            Evidence-based decision support from the latest verification result.
          </p>
        </div>
        {verification ? (
          <div style={{ textAlign: 'right' }}>
            <p style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end', color: 'var(--text-secondary)', fontSize: '12px', margin: 0 }}>
              <ShieldCheck size={14} color="var(--accent)" /> Verification {verification.verification_id}
            </p>
            <p style={{ color: 'var(--text-tertiary)', fontSize: '11px', margin: '2px 0 0' }}>
              {formatDate(verification.created_at)}
            </p>
          </div>
        ) : null}
      </div>

      <DataNotice notice={verification?.data_notice} />

      {status === 'loading' && !verification ? <LoadingState /> : null}
      {status === 'error' && !verification ? (
        <ErrorState
          message={error}
          onRetry={() => runVerification().catch(() => {})}
          retrying={loading}
        />
      ) : null}
      {!verification && status !== 'loading' && status !== 'error' ? <IdleState /> : null}

      {verification ? (
        <>
          <RecommendationBanner recommendation={recommendation} />

          <div className="dashboard-grid" style={{ marginTop: 0, marginBottom: '20px' }}>
            <StatCard
              icon={Wallet}
              label="Conservative income"
              value={formatMoney(income.conservative)}
              detail={summaryDetail || undefined}
              tone="positive"
            />
            <StatCard
              icon={ReceiptText}
              label="Estimated expenses"
              value={formatMoney(expenses.estimated)}
              detail={expenses.complete ? 'Living and food costs included' : 'Living costs incomplete'}
              tone={expenses.complete ? 'neutral' : 'caution'}
            />
            <StatCard
              icon={TrendingUp}
              label="Conservative surplus"
              value={formatMoney(verification.surplus_conservative)}
              detail="Income less estimated expenses"
              tone={isFiniteNumber(verification.surplus_conservative) && verification.surplus_conservative < 0 ? 'attention' : 'positive'}
            />
            <StatCard
              icon={FileText}
              label="Evidence confidence"
              value={formatScore(evidence.confidence_score)}
              detail={`${evidence.confidence_level || 'Unknown'} confidence${evidence.confidence_capped ? ' · capped' : ''}`}
              tone={evidence.confidence_level === 'HIGH' ? 'positive' : evidence.confidence_level === 'LOW' ? 'caution' : 'neutral'}
            />
          </div>

          <div className="dashboard-grid" style={{ marginTop: 0 }}>
            <IncomeCard verification={verification} />
            <EvidenceCard evidence={evidence} />
            <AffordabilityCard affordability={affordability} />
            <RiskCard riskSignal={riskSignal} />
            <FlagsCard flags={flags} />
            <SmsCard
              smsSummary={verification.sms_summary}
              smsIgnoredReason={verification.sms_ignored_reason}
            />
            <ImproveEvidenceForm
              form={form}
              onChange={handleChange}
              onSubmit={handleSubmit}
              submitting={loading}
              formError={formError}
            />
          </div>

          <footer style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid var(--border)', color: 'var(--text-tertiary)', fontSize: '11px' }}>
            <p style={{ margin: 0 }}>{verification.disclaimer}</p>
            <p style={{ margin: '6px 0 0' }}>
              Engine {verification.engine_version || '—'} · Model {verification.model_version || '—'} · Worker {verification.worker_id || '—'}
            </p>
          </footer>
        </>
      ) : null}
    </div>
  );
}
