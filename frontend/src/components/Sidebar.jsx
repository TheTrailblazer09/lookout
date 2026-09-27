import { NavLink, useNavigate, useSearchParams } from 'react-router-dom';
import { Anchor, Bell, Cloud, Grid2X2, LogOut, Map, ShipWheel, Sparkles } from 'lucide-react';
import { Brand } from './Brand';
import { useAuth } from '../lib/auth';
import { useSummary } from '../lib/useSummary';

const nav = [
  ['/overview', 'Overview', Grid2X2],
  ['/signals', 'Signal log', Bell],
  ['/course', 'Chart a course', Map],
  ['/holdings', 'Holdings', Anchor],
  ['/weather', 'Weather report', Cloud],
  ['/drivers', 'What moves my stocks', ShipWheel],
];

export function Sidebar() {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const { holdings, totalValue, bots, alerts, loading } = useSummary();
  const [params] = useSearchParams();
  // keep the replayed date when moving between pages
  const qs = params.get('as_of') ? `?as_of=${params.get('as_of')}` : '';

  const money =
    totalValue == null
      ? null
      : `$${Number(totalValue).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  return (
    <aside className="sidebar">
      <Brand />

      <nav className="side-nav">
        {nav.map(([to, label, Icon]) => (
          <NavLink
            key={to}
            to={`${to}${qs}`}
            className={({ isActive }) => `side-link ${isActive ? 'active' : ''}`}
          >
            <Icon size={17} strokeWidth={1.7} />
            <span>{label}</span>
            {/* always shown once the count is known, including zero */}
            {to === '/signals' && alerts != null && (
              <span className={`badge-dot ${alerts === 0 ? 'quiet' : ''}`}>{alerts}</span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="sample-box dashed">
          <div className="eyebrow accent">
            {user ? (user.display_name || user.email).toUpperCase() : 'DEMO PORTFOLIO'}
          </div>

          <div className="sample-big">
            {loading
              ? '…'
              : holdings
                ? `${holdings} ${holdings === 1 ? 'holding' : 'holdings'}`
                : 'No holdings yet'}
          </div>

          <div className="muted-dark">
            {loading ? '' : holdings && money ? money : 'Add what you own to get started'}
          </div>
          {!loading && bots != null && holdings > 0 && (
            <div className="muted-dark">
              {bots} {bots === 1 ? 'bot' : 'bots'} on watch
            </div>
          )}

          <button className="text-link light" type="button" onClick={() => navigate('/onboarding')}>
            {holdings ? 'Edit holdings →' : 'Add holdings →'}
          </button>
        </div>

        {user ? (
          <button
            className="side-signout"
            type="button"
            onClick={() => {
              signOut();
              navigate('/login');
            }}
          >
            <LogOut size={14} /> Sign out
          </button>
        ) : (
          <button className="side-signout" type="button" onClick={() => navigate('/login')}>
            Sign in to use your own portfolio →
          </button>
        )}

        <div className="privacy-note">
          <Sparkles size={14} />
          <span>The model runs on this machine. Your holdings never leave it.</span>
        </div>
      </div>
    </aside>
  );
}