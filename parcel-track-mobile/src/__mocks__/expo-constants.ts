/**
 * In-memory stand-in for expo-constants under jest (node env).
 *
 * The real module loads the Expo native bridge (`requireOptionalNativeModule`)
 * and pulls in ESM from `expo-modules-core`, neither of which transpile under
 * the project's plain ts-jest preset. This mock supplies just the shape the
 * code reads at runtime — `expoConfig.extra.eas.projectId` — so the helper's
 * "thread projectId through if present" branch can be exercised in tests by
 * overwriting these fields.
 */

const Constants = {
  expoConfig: {
    extra: {
      eas: undefined as { projectId?: string } | undefined,
    } as { eas?: { projectId?: string } },
  } as { extra?: { eas?: { projectId?: string } } } | null,
  easConfig: undefined as { projectId?: string } | undefined,
};

export default Constants;
