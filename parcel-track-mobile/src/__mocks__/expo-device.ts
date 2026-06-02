/**
 * In-memory stand-in for expo-device under jest (node env).
 *
 * `isDevice` defaults to `true` so the push-registration helper's "skip on
 * simulator" branch does not short-circuit in unit tests. Test cases that
 * want the simulator path can override via `(Device as any).isDevice = false`.
 */

export let isDevice = true;

export function __setIsDeviceForTests(value: boolean): void {
  isDevice = value;
}
