/**
 * Design tokens — single source of truth for colors, spacing, typography,
 * radii, shadows.
 *
 * Phase 9 ported the client prototype's visual identity onto these tokens: a
 * warm "paper" palette, the Geist typeface, and soft/ink semantic color pairs.
 * The hex values were converted from the prototype CSS's `oklch()` (RN can't
 * parse `oklch`) — see the prototype's `:root`.
 *
 * No theme provider yet (single theme on day one; dark mode stays deferred).
 * When dark mode lands, swap this for a context-driven palette but keep the
 * export names stable so call sites don't churn.
 *
 * ## Color convention — soft/ink pairs
 *
 * Each semantic color (green/amber/red/info/primary) comes as a triplet:
 *   - base  (`green`)      — the saturated line/icon/text-on-paper color
 *   - soft  (`greenSoft`)  — a low-saturation surface fill (pill/banner bg)
 *   - ink   (`greenInk`)   — high-contrast text to sit ON the soft fill
 * A pill or banner uses `xSoft` as fill + `xInk` as text. Reach for the pair,
 * not a base-color outline.
 *
 * ## Typography — Geist
 *
 * Custom RN fonts do NOT synthesize weight: `fontFamily:'Geist'` +
 * `fontWeight:'700'` renders Regular, not Bold. Every weight is loaded as its
 * own family (`Geist-Regular/Medium/SemiBold/Bold`, `GeistMono-Regular/Medium`)
 * in `app/_layout.tsx`, and `fontFamilies` below is the only place that maps a
 * (weight, mono) pair to a family string. The `<Text>` primitive consumes it —
 * never hardcode a family name or a `fontWeight` in a component.
 */

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

export const colors = {
  // Surfaces (warm paper)
  bg: '#fcfaf6', // app background
  bgSoft: '#f4f1ed', // sunken / grouped surface
  bgSunk: '#f1eee9', // deepest sunken
  bgElev: '#ffffff', // elevated card

  // Text (cool ink ramp)
  ink: '#0e1217', // primary text
  ink2: '#484e54', // secondary text
  ink3: '#7c8186', // muted text
  // Faint / placeholder. Darkened from #a1a5a9 (2.4:1 on `bg`) in Phase 11 to
  // pass the WCAG 3:1 large-text/UI floor (3.1:1). True 4.5:1 is unreachable
  // here — it would land DARKER than ink3 (itself 3.8:1) and invert the ramp.
  ink4: '#8a8f94',

  // Borders
  line: '#e6e4e1', // hairline border
  lineStrong: '#d0cdc9', // stronger border

  // Brand navy
  primary: '#18364a',
  primarySoft: '#e4f0fa',
  primaryInk: '#ffffff',

  // Semantic — base / soft / ink triplets
  green: '#2d8949',
  greenSoft: '#e4f8e7',
  greenInk: '#005f21',

  amber: '#df9b44',
  amberSoft: '#fff0d4',
  amberInk: '#945000',

  red: '#cb473f',
  redSoft: '#ffebe8',
  redInk: '#970004',

  info: '#287aa3',
  infoSoft: '#e3f5ff',
  infoInk: '#004e75',

  // ---- Backwards-compatible aliases (pre-Phase-9 export names) -------------
  // Keep these pointing at the new palette so screens importing `colors.text`
  // etc. don't churn. Prefer the names above in new code.
  text: '#0e1217', // → ink
  textMuted: '#7c8186', // → ink3
  border: '#e6e4e1', // → line
  surface: '#f4f1ed', // → bgSoft
  primaryText: '#ffffff', // → primaryInk
  error: '#cb473f', // → red
  errorSurface: '#ffebe8', // → redSoft
  warning: '#df9b44', // → amber
  success: '#2d8949', // → green
} as const;

// ---------------------------------------------------------------------------
// Spacing (unchanged — the prototype's rhythm fits the existing scale)
// ---------------------------------------------------------------------------

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

// ---------------------------------------------------------------------------
// Sizes (non-spacing dimensions)
// ---------------------------------------------------------------------------

/**
 * Fixed component dimensions that aren't rhythm/spacing: progress-track
 * heights, indicator dots, icon containers. One source so the same visual
 * element is the same size everywhere (e.g. every thin progress bar is
 * `trackThin`, every stepper segment is `trackMicro`).
 */
export const sizes = {
  /** Thin determinate progress track (ProgressBar, banked progress). */
  trackThin: 6,
  /** Micro segmented track (BookingStepper / BookingCard segments). */
  trackMicro: 4,
  /** Small status/urgency dot (DemurrageCard rows). */
  dotSm: 8,
  /** Square icon container (admin menu, security panel rows). */
  iconBox: 36,
  /** Minimum touch-target height for tappable rows (HIG 44pt). */
  touchTarget: 44,
} as const;

// ---------------------------------------------------------------------------
// Overlays
// ---------------------------------------------------------------------------

/**
 * Translucent scrims. Kept out of `colors` because they're alpha composites
 * over arbitrary content, not surface/text pairs — and tokenizing them keeps a
 * future dark mode cheap.
 */
export const overlays = {
  /** Modal/backdrop dim behind bottom sheets (Select, DateField). */
  dim: 'rgba(14,18,23,0.4)',
  /** Android pressed-state ripple on tappable rows. */
  ripple: 'rgba(14,18,23,0.08)',
} as const;

// ---------------------------------------------------------------------------
// Typography
// ---------------------------------------------------------------------------

export type FontWeight = 'regular' | 'medium' | 'semibold' | 'bold';

const SANS: Record<FontWeight, string> = {
  regular: 'Geist-Regular',
  medium: 'Geist-Medium',
  semibold: 'Geist-SemiBold',
  bold: 'Geist-Bold',
};

// Geist Mono is only loaded in Regular + Medium (refs/IDs/amounts don't need
// heavier cuts). semibold/bold fall back to Medium — the heaviest mono we ship.
const MONO: Record<FontWeight, string> = {
  regular: 'GeistMono-Regular',
  medium: 'GeistMono-Medium',
  semibold: 'GeistMono-Medium',
  bold: 'GeistMono-Medium',
};

/**
 * The single weight→family resolver. Custom RN fonts don't synthesize weight,
 * so a family string is the only way to pick a cut. The `<Text>` primitive is
 * the sole caller; components never reference a family name directly.
 */
export function fontFamily(weight: FontWeight, mono = false): string {
  return (mono ? MONO : SANS)[weight];
}

/**
 * The font family asset keys, loaded by `useFonts` in `app/_layout.tsx`. Kept
 * here next to `fontFamily` so the family-name strings have one source.
 */
export const FONT_FAMILY_KEYS = [
  'Geist-Regular',
  'Geist-Medium',
  'Geist-SemiBold',
  'Geist-Bold',
  'GeistMono-Regular',
  'GeistMono-Medium',
] as const;

/**
 * Type scale (px / line-heights from the prototype). `weight` is the variant's
 * default cut; `<Text>` resolves it to a family via `fontFamily`. Letter
 * spacing is in points (RN units), negative on display/heading for the tight
 * prototype look, positive on `overline` for tracked uppercase labels.
 *
 * NOTE: no `fontWeight` here on purpose — it does nothing for custom RN fonts
 * and would mislead. Weight lives in the family name.
 */
export const type = {
  display: { fontSize: 28, lineHeight: 34, letterSpacing: -0.5, weight: 'bold' as FontWeight },
  heading: { fontSize: 22, lineHeight: 28, letterSpacing: -0.3, weight: 'bold' as FontWeight },
  title: { fontSize: 17, lineHeight: 23, letterSpacing: -0.2, weight: 'semibold' as FontWeight },
  body: { fontSize: 15, lineHeight: 22, weight: 'regular' as FontWeight },
  label: { fontSize: 13, lineHeight: 18, weight: 'medium' as FontWeight },
  small: { fontSize: 12, lineHeight: 16, weight: 'regular' as FontWeight },
  overline: {
    fontSize: 10,
    lineHeight: 14,
    letterSpacing: 0.8,
    textTransform: 'uppercase' as const,
    weight: 'semibold' as FontWeight,
  },
} as const;

export type TypeVariant = keyof typeof type;

// ---------------------------------------------------------------------------
// Radii
// ---------------------------------------------------------------------------

export const radii = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

// ---------------------------------------------------------------------------
// Shadows
// ---------------------------------------------------------------------------

/**
 * RN-friendly shadow presets (iOS `shadow*` + Android `elevation`). The
 * prototype layers a soft drop shadow over a 1px hairline "ring"; RN can't do
 * the ring via shadow, so cards that want it set `borderWidth:1` + `line`
 * alongside these (see `Card`). Spread `...shadows.sh2` onto a style.
 *
 *   sh1   hairline lift
 *   sh2   resting card
 *   sh3   raised / pressed-forward (modals-on-list, active hero)
 *   sheet bottom sheets / modals (shadow casts upward)
 */
export const shadows = {
  sh1: {
    shadowColor: '#14161e',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 0,
    elevation: 1,
  },
  sh2: {
    shadowColor: '#14161e',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 2,
    elevation: 2,
  },
  sh3: {
    shadowColor: '#14161e',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 6,
  },
  sheet: {
    shadowColor: '#14161e',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.18,
    shadowRadius: 30,
    elevation: 12,
  },
} as const;

export type ShadowLevel = keyof typeof shadows;
