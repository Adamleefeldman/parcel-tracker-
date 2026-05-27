/**
 * Design tokens — single source of truth for colors, spacing, typography, radii.
 *
 * No theme provider yet (single theme on day one). When dark mode lands, swap
 * this for a context-driven palette but keep the export names stable so call
 * sites don't churn.
 */

export const colors = {
  bg: '#fff',
  text: '#111',
  textMuted: '#666',
  primary: '#0a7',
  primaryText: '#fff',
  border: '#ddd',
  error: '#c00',
  warning: '#c80',
  success: '#0a7',
  surface: '#f7f7f7',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const type = {
  body: { fontSize: 16, lineHeight: 22 },
  small: { fontSize: 13, lineHeight: 18 },
  heading: { fontSize: 22, fontWeight: '700' as const, lineHeight: 28 },
  display: { fontSize: 32, fontWeight: '700' as const, lineHeight: 38 },
} as const;

export const radii = {
  sm: 4,
  md: 8,
  lg: 12,
} as const;
