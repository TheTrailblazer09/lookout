/**
 * The nautical scene, drawn as one SVG instead of stacked divs.
 *
 * Why SVG: the old version positioned a tower, boat and four waves with
 * vw/vh offsets, so every screen size pulled the picture apart. Here the
 * whole scene lives in one 1440x1000 viewBox and scales as a unit, which
 * is also what makes it match the design canvas exactly.
 *
 * Three things move, all in CSS so they cost nothing:
 *   - the beam sweeps out from the lamp
 *   - the boat rides the swell and drifts across
 *   - the water scrolls (each wave band is drawn twice, end to end, and
 *     shifted by exactly one copy, so the loop has no visible seam)
 */
export function LighthouseScene({ variant = 'login' }) {
  return (
    <div className={`lighthouse-scene scene-${variant}`} aria-hidden="true">
      <svg
        className="scene-svg"
        viewBox={variant === 'onboard' ? '520 560 900 440' : '0 0 1440 1000'}
        preserveAspectRatio={variant === 'onboard' ? 'xMinYMax slice' : 'xMidYMax slice'}
        role="presentation"
      >
        <defs>
          <linearGradient id="lk-beam" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#F2B33D" stopOpacity="0.46" />
            <stop offset="55%" stopColor="#F2B33D" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#F2B33D" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="lk-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFE6A8" stopOpacity="0.95" />
            <stop offset="60%" stopColor="#F2B33D" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#F2B33D" stopOpacity="0" />
          </radialGradient>
          {/* one wave band, reused twice per layer for a seamless scroll */}
          <path
            id="lk-swell"
            d="M0 30 Q 60 12 120 30 T 240 30 T 360 30 T 480 30 T 600 30 T 720 30
               T 840 30 T 960 30 T 1080 30 T 1200 30 T 1320 30 T 1440 30
               L1440 200 L0 200 Z"
          />
        </defs>

        {/* ---- night sky ---- */}
        <g className="scene-stars">
          <circle cx="120" cy="90" r="2" />
          <circle cx="340" cy="60" r="1.5" />
          <circle cx="610" cy="130" r="2" />
          <circle cx="760" cy="50" r="1.5" />
          <circle cx="480" cy="210" r="1.5" />
          <circle cx="890" cy="170" r="2" />
          <circle cx="1120" cy="110" r="1.5" />
          <circle cx="1290" cy="220" r="2" />
          <circle cx="60" cy="330" r="1.5" />
        </g>

        {/* Beam and tower share one transform so the light always starts
            exactly at the lamp, wherever the lighthouse is placed. The beam
            is drawn FIRST so the tower hides it on the back half of the
            turn, which is what sells the rotation. */}
        <g className="scene-light">
          <g className="scene-beam">
            <polygon points="300,616 1900,146 1900,1086" fill="url(#lk-beam)" />
            <polygon points="300,616 1900,360 1900,872" fill="url(#lk-beam)" opacity="0.55" />
          </g>

        {/* ---- lighthouse ---- */}
        <g className="scene-tower">
          <path d="M150 864 Q235 790 300 792 Q375 790 450 864 Z" fill="#0E1828" />
          <path d="M268 818 L284 640 H316 L332 818 Z" fill="#F3EEE3" />
          <path d="M278.5 730 L281 700 H319 L321.5 730 Z" fill="#E0561F" />
          <path d="M273.4 792 L275.8 762 H324.2 L326.6 792 Z" fill="#E0561F" />
          <rect x="274" y="632" width="52" height="10" rx="2" fill="#16243A" stroke="#F3EEE3" strokeWidth="3" />
          <rect x="286" y="600" width="28" height="32" rx="3" fill="#16243A" />
          <circle className="scene-lamp-glow" cx="300" cy="616" r="36" fill="url(#lk-glow)" />
          <rect className="scene-lamp" x="290" y="606" width="20" height="20" rx="2" fill="#F2B33D" />
          <path d="M280 602 L300 576 L320 602 Z" fill="#E0561F" />
          <path d="M293 818 V800 a7 7 0 0 1 14 0 V818 Z" fill="#16243A" />
        </g>
        </g>

        {/* ---- water: three bands, each scrolling at its own pace ---- */}
        <g className="scene-water">
          <g className="scene-wave wave-back" fill="#1F6F99">
            <use href="#lk-swell" x="0" y="838" />
            <use href="#lk-swell" x="1440" y="838" />
          </g>
          {/* between bands on purpose: the nearer water hides the hull */}
          <g className="scene-boat">
            <g className="scene-boat-bob">
              <path d="M40 40 V-14" stroke="#F3EEE3" strokeWidth="3" strokeLinecap="round" />
              <path d="M0 40 H80 L66 58 H14 Z" fill="#F2B33D" />
              <path d="M43 38 V-10 L72 32 Z" fill="#F3EEE3" />
              <path d="M37 38 V0 L16 32 Z" fill="#E0561F" />
            </g>
          </g>

          <g className="scene-wave wave-mid" fill="#2E8BBF">
            <use href="#lk-swell" x="0" y="886" />
            <use href="#lk-swell" x="1440" y="886" />
          </g>
          <g className="scene-wave wave-front" fill="#8DB8D6">
            <use href="#lk-swell" x="0" y="936" />
            <use href="#lk-swell" x="1440" y="936" />
          </g>
        </g>
      </svg>
    </div>
  );
}