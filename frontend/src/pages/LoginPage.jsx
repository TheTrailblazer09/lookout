import { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { LockKeyhole } from 'lucide-react';
import { Brand } from '../components/Brand';
import { LighthouseScene } from '../components/LighthouseScene';
import { useAuth } from '../lib/auth';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // if RequireAuth bounced them here, send them back afterwards
  const next = location.state?.from ?? '/overview';

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      await signIn(email.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-left">
        <div className="eyebrow accent">PORTFOLIO WATCH · BUILT AT HACKGT 13</div>
        <Brand large />
        <h2>
          Keeps watch over your stocks,
          <br />
          so you don't have to.
        </h2>
        <div className="about-box dashed">
          <div className="eyebrow accent">ABOUT US</div>
          <p>
            We're a team of Georgia Tech students who think everyday investors deserve the same
            watchful eye big funds have. Lookout's bots scan price moves, earnings, news mood and
            the economy around the clock, and a small AI running on your own computer tells you
            what matters in plain English. Your holdings never leave your machine.
          </p>
        </div>
        <LighthouseScene variant="login" />
      </div>

      <div className="login-right">
        {/* a real form: Enter submits, and browsers offer to save the password */}
        <form className="login-card" onSubmit={handleSubmit}>
          <h1>Welcome aboard</h1>
          <p>Sign in to see what Lookout spotted while you were away.</p>

          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <div className="label-row">
            <label htmlFor="password">Password</label>
            <Link className="text-link" to="/signup">
              Need an account?
            </Link>
          </div>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <button className="sign-btn" type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in →'}
          </button>

          <div className="new-here">
            New here? <Link className="text-link" to="/signup">Create an account</Link>
          </div>

          {/* judges can look around without making an account */}
          <button
            className="text-link demo-link"
            type="button"
            onClick={() => navigate('/overview')}
          >
            Or explore the demo portfolio →
          </button>

          <div className="secure-note">
            <LockKeyhole size={14} /> The AI runs on your computer. We never see your portfolio.
          </div>
        </form>
      </div>
    </div>
  );
}