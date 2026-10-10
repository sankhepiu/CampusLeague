import type { CSSProperties, HTMLAttributes } from 'react';
import styles from './Panel.module.scss';

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  raised?: boolean;
  /** CSS color/var() reference the panel's glow should use, e.g. `var(--cl-accent-events)`.
   * Defaults to `--cl-accent-default` (gold) when omitted. */
  accent?: string;
}

/** Base NES-style notched-corner container other components sit inside. */
export function Panel({ raised, accent, className, style, ...rest }: PanelProps) {
  const classes = [styles.panel, raised ? styles.raised : '', className].filter(Boolean).join(' ');
  const mergedStyle: CSSProperties | undefined = accent
    ? ({ '--panel-accent': accent, ...style } as CSSProperties)
    : style;
  return <div className={classes} style={mergedStyle} {...rest} />;
}
