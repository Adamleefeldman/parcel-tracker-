/**
 * Minimal react-native stand-in for the node-env jest setup.
 *
 * The real `react-native` package ships Flow-typed ESM (`import typeof * as …`)
 * that the project's plain ts-jest preset cannot transform. Pure-logic
 * modules that need `Platform.OS` (e.g. `pushRegistration.ts`) end up
 * importing react-native at module top-level even though their tests never
 * exercise UI code paths — this mock just papers over that. UI tests, when
 * they arrive, will switch to jest-expo or a separate jest project.
 *
 * `Platform.OS` defaults to `'ios'`; bump it via `__setPlatformOSForTests`
 * if a test needs to exercise the Android branch.
 */

let osValue: 'ios' | 'android' | 'web' = 'ios';

export const Platform = {
  get OS() {
    return osValue;
  },
  select<T>(spec: { ios?: T; android?: T; default?: T; web?: T; native?: T }): T | undefined {
    return spec[osValue] ?? spec.native ?? spec.default;
  },
};

export function __setPlatformOSForTests(value: 'ios' | 'android' | 'web'): void {
  osValue = value;
}
