import { useEffect, useState } from 'react';
import { Cpu } from 'lucide-react';
import { api } from '../lib/api';

/**
 * Shown on every page while the local model is not ready.
 *
 * It fetches its own status rather than waiting to be handed one, because
 * the earlier version only appeared when an alert had no text — and an
 * alert left over from an older build has text, so the notice (and its
 * setup button) stayed hidden exactly when it was needed.
 *
 * Nothing here blocks the app: every number is already real. This only
 * offers to turn on the part that writes the explanations.
 */
export function NarratorNotice({ compact = false }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .llmStatus()
      .then((s) => !cancelled && setStatus(s))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status || status.ready) return null;

  async function setup() {
    setBusy(true);
    setError('');
    try {
      await api.llmEnsure();
      // poll: starting the server is quick, pulling a model is not
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const s = await api.llmStatus();
        setStatus(s);
        if (s.ready) {
          window.location.reload();   // alerts rewrite themselves on reload
          return;
        }
        if (s.error) {
          setError(s.error);
          return;
        }
        if (!s.downloading && !s.server_running) {
          setError(s.message);
          return;
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const downloading = status.downloading;
  const label = downloading
    ? `Downloading ${status.model} — ${status.percent}%`
    : error || status.message;

  return (
    <div className={`narrator-notice ${compact ? 'compact' : ''}`}>
      <Cpu size={16} />
      <div>
        <b>
          {downloading
            ? 'Setting up the local model…'
            : "Explanations are off: the local model isn't running."}
        </b>
        <span>{label}</span>
        {downloading && (
          <div className="narrator-bar">
            <i style={{ width: `${status.percent ?? 0}%` }} />
          </div>
        )}
      </div>
      {!downloading && (
        <button type="button" onClick={setup} disabled={busy}>
          {busy ? 'Starting…' : status.server_running ? `Get ${status.model}` : 'Turn it on'}
        </button>
      )}
    </div>
  );
}