export function LighthouseMark({ className = 'lighthouse-mark' }) {
  return (
    <svg className={className} viewBox="0 0 32 36" aria-hidden="true">
      <path d="M14 8h4l2 20H12L14 8Z" fill="#f6f1e6" />
      <path d="M10 8h12v3H10z" fill="#f6f1e6" />
      <path d="M12 4h8l-4-4z" fill="#f6a62f" />
      <path d="M13 18h6l.6 5H12.4z" fill="#e65b2f" />
      <path d="M2 10h9L2 6z" fill="#f2b539" opacity=".55" />
      <path d="M21 10h9V6z" fill="#f2b539" opacity=".55" />
      <path d="M4 31c3-2 5-2 8 0s5 2 8 0 5-2 8 0" fill="none" stroke="#2f87af" strokeWidth="2" />
    </svg>
  );
}

export function Brand({ large = false }) {
  return (
    <div className={large ? 'brand brand-large' : 'brand'}>
      {!large && <LighthouseMark />}
      <div>
        <div className="brand-name">Lookout</div>
        {!large && (
          <div className="brand-tag">
            keeps watch so you don't
            <br />
            have to
          </div>
        )}
      </div>
    </div>
  );
}
