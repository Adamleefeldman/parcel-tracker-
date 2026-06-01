// ESLint flat config (ESLint 9) for the Expo SDK 54 app.
//
// Extends `eslint-config-expo` (the SDK-aligned preset — it bundles the
// react-hooks, react, import and typescript-eslint plugins) and turns off any
// rule that conflicts with Prettier via `eslint-config-prettier`, so ESLint
// owns code-quality and Prettier owns formatting with no overlap.
//
// Lint is REPORT-ONLY in CI for now (the `mobile-lint` job is non-blocking) —
// the existing tree predates linting and surfaces pre-existing nits. A later
// cleanup pass will make the tree pass, then CI flips to blocking. The
// highest-value signals meanwhile are react-hooks/rules-of-hooks and
// exhaustive-deps in this react-query app, which this preset enables.

const expoConfig = require('eslint-config-expo/flat');
const eslintConfigPrettier = require('eslint-config-prettier');

module.exports = [
  ...expoConfig,
  eslintConfigPrettier,
  {
    ignores: ['node_modules/', 'dist/', '.expo/', 'web-build/', 'expo-env.d.ts'],
  },
];
