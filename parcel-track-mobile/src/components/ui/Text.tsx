import React from 'react';
import { StyleSheet, Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { colors, fontFamily, type, type FontWeight, type TypeVariant } from '../../theme/tokens';

/**
 * The font funnel. Geist is applied HERE, not in 40 screens — every bit of text
 * routes through this primitive so the typeface + weight-by-family rule lives
 * in one place.
 *
 * - `variant` picks the size/line-height/default-weight from the type scale.
 * - `weight` overrides the variant's default cut (custom fonts don't synthesize
 *   weight — see `fontFamily` in tokens). Never set `fontWeight` on a style.
 * - `mono` swaps to Geist Mono — for refs/IDs/amounts (BL numbers, container
 *   IDs, invoice numbers, monetary figures in dense rows).
 */

export interface TextProps extends RNTextProps {
  variant?: TypeVariant;
  /** Override the variant's default weight. */
  weight?: FontWeight;
  /** Render in Geist Mono (refs/IDs/amounts). */
  mono?: boolean;
  /** Muted (ink3) instead of primary ink. */
  muted?: boolean;
  /** Explicit color override (wins over `muted`). */
  color?: string;
}

export function Text({ variant = 'body', weight, mono, muted, color, style, ...rest }: TextProps) {
  const spec = type[variant];
  const resolvedWeight: FontWeight = weight ?? spec.weight;
  const textColor = color ?? (muted ? colors.ink3 : colors.ink);
  return (
    <RNText
      style={[
        styles[variant],
        { fontFamily: fontFamily(resolvedWeight, mono), color: textColor },
        style,
      ]}
      {...rest}
    />
  );
}

// Strip the non-style `weight` key out of each variant spec before handing it
// to StyleSheet (it's metadata, not an RN style prop).
function toStyle({ weight: _weight, ...rest }: (typeof type)[TypeVariant]) {
  return rest;
}

const styles = StyleSheet.create({
  display: toStyle(type.display),
  heading: toStyle(type.heading),
  title: toStyle(type.title),
  body: toStyle(type.body),
  label: toStyle(type.label),
  small: toStyle(type.small),
  overline: toStyle(type.overline),
});
