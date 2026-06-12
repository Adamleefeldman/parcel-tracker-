import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { colors, radii, sizes } from '../../theme/tokens';

/**
 * The 36×36 soft-square icon container used on menu/info rows (admin section
 * menu, security panel). One component so the box size, radius, and fill stay
 * identical everywhere.
 */
export interface IconBoxProps {
  icon: keyof typeof Ionicons.glyphMap;
  /** Icon glyph color. Defaults to the secondary ink. */
  color?: string;
}

export function IconBox({ icon, color = colors.ink2 }: IconBoxProps) {
  return (
    <View style={styles.box}>
      <Ionicons name={icon} size={20} color={color} />
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    width: sizes.iconBox,
    height: sizes.iconBox,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bgSoft,
  },
});
