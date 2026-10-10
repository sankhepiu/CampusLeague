import { PIXEL_ICONS, type PixelIconName } from './icons';

interface PixelIconProps {
  name: PixelIconName;
  size?: number;
  className?: string;
}

/** Renders a tiny original pixel-art glyph from a character grid, so Phase 0
 * needs no sprite sheets or external image assets. See ./icons.ts for the grids. */
export function PixelIcon({ name, size = 48, className }: PixelIconProps) {
  const { grid, palette } = PIXEL_ICONS[name];
  const colorMap = palette as Record<string, string>;
  const cols = grid[0]?.length ?? 0;
  const rows = grid.length;

  return (
    <svg
      viewBox={`0 0 ${cols} ${rows}`}
      width={size}
      height={size}
      className={className}
      shapeRendering="crispEdges"
      role="img"
      aria-label={name}
    >
      {grid.flatMap((row, y) =>
        row.split('').map((cell, x) => {
          if (cell === '.' || !colorMap[cell]) return null;
          return <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={colorMap[cell]} />;
        }),
      )}
    </svg>
  );
}
