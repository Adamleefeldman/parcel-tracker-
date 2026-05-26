// React Native exposes a global `__DEV__` flag; src/config/api.ts checks it.
// Define it for the node-based jest env so the module loads.
// eslint-disable-next-line no-undef
globalThis.__DEV__ = false;
