/**
 * The nautical scene, drawn as one SVG.
 *
 * The lighthouse sits low on the left, under the headline. Its geometry is
 * written directly in viewBox coordinates rather than being nudged around
 * with a CSS transform on the group: the beam pivots about the lamp, and
 * CSS resolves transform-origin against the SVG viewport, so a translated
 * parent would leave the pivot behind and the light would swing around the
 * page instead of turning on the lamp.
 *
 * LAMP_X / LAMP_Y below are the single source of truth for where the light
 * turns; scene.css uses the same two numbers.
 *
 * Three things move, all in CSS:
 *   - the beam turns a full circle on the lamp
 *   - the boat rides the swell and drifts across
 *   - the water scrolls (each band is drawn twice and shifted by exactly
 *     one copy, so the loop has no seam)
 */
const LAMP_X = 268;
const LAMP_Y = 678;

export function LighthouseScene({ variant = 'login' }) {
  return (
    <div className={`lighthouse-scene scene-${variant}`} aria-hidden="true">
      <svg
        className="scene-svg"
        viewBox={variant === 'onboard' ? '110 590 780 410' : '0 0 1440 1000'}
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

        {/* One beam, pointing out to sea and tilting slowly up and down.
            Its apex sits exactly on the lamp, so the tilt reads as the
            light sweeping rather than the shape sliding. */}
        <g className="scene-beam">
          <polygon points={`${LAMP_X},${LAMP_Y} 2100,${LAMP_Y - 430} 2100,${LAMP_Y + 430}`} fill="url(#lk-beam)" />
          <polygon points={`${LAMP_X},${LAMP_Y} 2100,${LAMP_Y - 200} 2100,${LAMP_Y + 200}`} fill="url(#lk-beam)" opacity="0.55" />
        </g>

        {/* ---- lighthouse: left of the page, standing in the water ---- */}
        <g className="scene-tower">
          <path d="M136 892 Q212 828 268 834 Q326 828 400 892 Z" fill="#0E1828" />
          {/* tapered body */}
          <path d="M245 852 L256 700 H280 L291 852 Z" fill="#F3EEE3" />
          <path d="M252 776 L254 752 H282 L284 776 Z" fill="#E0561F" />
          <path d="M248 828 L250 804 H286 L288 828 Z" fill="#E0561F" />
          {/* gallery, lamp room, roof */}
          <rect x="246" y="692" width="44" height="9" rx="2" fill="#16243A" stroke="#F3EEE3" strokeWidth="2.5" />
          <rect x="255" y="663" width="26" height="29" rx="3" fill="#16243A" />
          <circle className="scene-lamp-glow" cx={LAMP_X} cy={LAMP_Y} r="30" fill="url(#lk-glow)" />
          <rect className="scene-lamp" x="259" y="669" width="18" height="18" rx="2" fill="#F2B33D" />
          <path d="M250 666 L268 642 L286 666 Z" fill="#E0561F" />
          {/* doorway */}
          <path d="M261 852 V836 a7 7 0 0 1 14 0 V852 Z" fill="#16243A" />
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