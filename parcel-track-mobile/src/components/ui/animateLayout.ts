import { LayoutAnimation, Platform, UIManager } from 'react-native';

/**
 * One-line layout animation for collapsible toggles — call immediately before
 * the `setState` that expands/collapses, and the next layout pass animates
 * (ease-in-out) instead of snapping.
 *
 * Android old-arch requires the experimental flag; on the new architecture
 * (SDK 54 default) the setter either doesn't exist or is a no-op, so the guard
 * keeps this safe everywhere.
 */
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export function animateLayout(): void {
  LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
}
