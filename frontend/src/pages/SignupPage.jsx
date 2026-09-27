import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LockKeyhole } from 'lucide-react';
import { Brand } from '../components/Brand';
import { LighthouseScene } from '../components/LighthouseScene';
import { useAuth } from '../lib/auth';

const MIN_PASSWORD = 8;   // matches PASSWORD_MIN_LENGTH in the backend config

export default function SignupPage() {
  const navigate = useNavigate();
  const { signUp } = useAuth();

  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;

    // check what we can here, so an obvious mistake costs no round trip
    if (form.password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (form.password !== form.confirm) {
      setError('Those passwords do not match.');
      return;
    }

    setError('');
    setBusy(true);
    try {
      await signUp(form.email.trim(), form.password, form.name.trim());
      navigate('/onboarding', { replace: true });   // straight to adding holdings
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
          Start keeping watch
          <br />
          over your portfolio.
        </h2>
        <div className="about-box dashed">
          <div className="eyebrow accent">WHAT YOU GET</div>
          <p>
            Four bots watch your stocks around the clock: price moves, earnings, news mood and the
            economy. When something genuinely matters for your holdings, a small AI running on your
            own computer explains it in plain English, with the history behind it.
          </p>
          <span>Your holdings never leave your machine.</span>
        </div>
        <LighthouseScene variant="login" />
      </div>

      <div className="login-right">
        <form className="login-card compact" onSubmit={handleSubmit}>
          <h1>Create an account</h1>
          <p>It takes a moment. Next you'll add the stocks you own.</p>

          <label htmlFor="name">Your name</label>
          <input
            id="name"
            autoComplete="name"
            placeholder="Vani"
            value={form.name}
            onChange={set('name')}
          />

          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@gatech.edu"
            value={form.email}
            onChange={set('email')}
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            placeholder={`At least ${MIN_PASSWORD} characters`}
            value={form.password}
            onChange={set('password')}
            required
          />

          <label htmlFor="confirm">Confirm password</label>
          <input
            id="confirm"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            value={form.confirm}
            onChange={set('confirm')}
            required
          />

          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <button className="sign-btn" type="submit" disabled={busy}>
            {busy ? 'Creating…' : 'Create account →'}
          </button>

          <div className="new-here">
            Already aboard? <Link className="text-link" to="/login">Sign in</Link>
          </div>

          <div className="secure-note">
            <LockKeyhole size={14} /> Your password is hashed. Holdings stay on this machine.
          </div>
        </form>
      </div>
    </div>
  );
}