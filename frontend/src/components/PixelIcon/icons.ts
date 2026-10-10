export interface PixelIconDef {
  grid: string[];
  palette: Record<string, string>;
}

export const PIXEL_ICONS = {
  coin: {
    grid: [
      '.BBBBBBBB.',
      'BBGGGGGGBB',
      'BGGGGGGGGB',
      'BGGWWGGGGB',
      'BGGWWGGGGB',
      'BGGGGGGGGB',
      'BGGGGGGGGB',
      'BGGGGGGGGB',
      'BBGGGGGGBB',
      '.BBBBBBBB.',
    ],
    palette: { B: '#c9972a', G: '#ffd34d', W: '#fff6d8' },
  },
  trophy: {
    grid: [
      '..BBBBBB..',
      '.BGGGGGGB.',
      'BGGGGGGGGB',
      'BGGGGGGGGB',
      'BGWGGGGWGB',
      '.BGGGGGGB.',
      '..BGGGGB..',
      '...BGGB...',
      '...BGGB...',
      '..BGGGGB..',
      '.BGGGGGGB.',
      'BBBBBBBBBB',
    ],
    palette: { B: '#c9972a', G: '#ffd34d', W: '#fff6d8' },
  },
  chest: {
    grid: [
      '.BBBBBBBB.',
      'BDDDDDDDDB',
      'BDDDDDDDDB',
      'BBBBBBBBBB',
      'BDDDGGDDDB',
      'BDDDGGDDDB',
      'BDDDDDDDDB',
      'BDDDDDDDDB',
      'BDDDDDDDDB',
      'BBBBBBBBBB',
    ],
    palette: { B: '#1a0f08', D: '#8a5a2b', G: '#ffd34d' },
  },
  badge: {
    grid: [
      '..BBBBBB..',
      '.BGGGGGGB.',
      'BGGWWWWGGB',
      'BGGWWWWGGB',
      'BGGGGGGGGB',
      'BGGGGGGGGB',
      '.BGGGGGGB.',
      '..BGGGGB..',
      '...BGGB...',
      '....BB....',
    ],
    palette: { B: '#1e4f73', G: '#52c7ff', W: '#e8f8ff' },
  },
  ghost: {
    grid: [
      '..BBBBBB..',
      '.BWWWWWWB.',
      'BWWWWWWWWB',
      'BWWBWWBWWB',
      'BWWWWWWWWB',
      'BWWWWWWWWB',
      'BWWWWWWWWB',
      'BWWWWWWWWB',
      'BWBWBWBWBB',
    ],
    palette: { B: '#4a4466', W: '#f5f1e8' },
  },
} satisfies Record<string, PixelIconDef>;

export type PixelIconName = keyof typeof PIXEL_ICONS;
