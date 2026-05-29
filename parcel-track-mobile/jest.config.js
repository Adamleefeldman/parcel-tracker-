/**
 * Jest configuration.
 *
 * Pure-logic tests only (ts-jest preset, node env). React Native components
 * are NOT covered by this setup — that would need jest-expo + react-native
 * presets, which are noisy to maintain. When component tests become worth
 * it, add a separate project or switch to jest-expo.
 *
 * Why node, not jsdom: this codebase explicitly avoids browser globals
 * (see AGENTS.md "No browser globals"). A node env makes accidental use of
 * `window`/`document` fail loudly in tests, matching the Hermes runtime.
 */

/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['<rootDir>/src/**/*.test.ts'],
  setupFiles: ['<rootDir>/jest.setup.js'],
  // expo-secure-store, jwt-decode, react-native, etc. are not exercised in
  // these tests — anything that touches them is mocked at the module level.
  moduleNameMapper: {
    '^expo-secure-store$': '<rootDir>/src/__mocks__/expo-secure-store.ts',
    '^expo-crypto$': '<rootDir>/src/__mocks__/expo-crypto.ts',
  },
};
