export function Card({ children, className = '', dark = false }) {
  return <section className={`card ${dark ? 'card-dark' : ''} ${className}`}>{children}</section>;
}

export function Tag({ children, tone = 'yellow' }) {
  return <span className={`tag ${tone}`}>{children}</span>;
}

export function MetricCard({ label, value, detail, foot, danger = false }) {
  return (
    <Card className="metric-card">
      <div className="eyebrow">{label}</div>
      <div className={`metric-value ${danger ? 'danger-text' : ''}`}>{value}</div>
      {detail && <div className="metric-detail">{detail}</div>}
      {foot && <p className="muted">{foot}</p>}
    </Card>
  );
}

export function FooterNote() {
  return <div className="footer-note">Demo data for illustration only · Not investment advice · Built at HackGT 13</div>;
}

export function TinyLine({ rising = true }) {
  const points = rising
    ? '0,33 14,37 28,34 44,40 62,31 82,30 100,25 120,23 145,18 166,20 190,14 220,12'
    : '0,15 20,17 42,20 68,23 95,25 122,30 145,32 170,34 194,35 220,36';
  return (
    <svg viewBox="0 0 220 46" className="tiny-line" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2.2" />
      <polygon points={`${points} 220,46 0,46`} fill="currentColor" opacity=".07" />
    </svg>
  );
}
