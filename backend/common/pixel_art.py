"""Tiny PNG generator for the demo's product pictures.

Standard library only (zlib + struct): a PNG is a signature followed by
chunks, each "length, type, data, CRC". No Pillow.
"""
import struct
import zlib

# 16 x 16 sprites, one character per pixel:
#   . background   # main colour   + lighter shade   - darker shade   o outline
HOODIE = [
    '................',
    '.....oooooo.....',
    '....o++++++o....',
    '...o+o----o+o...',
    '..oo##o--o##oo..',
    '.o####oooo####o.',
    'o######++######o',
    'o##o###++###o##o',
    'o##o###++###o##o',
    'o##o########o##o',
    '.oo.o######o.oo.',
    '....o#----#o....',
    '....o#----#o....',
    '....o######o....',
    '....o------o....',
    '.....oooooo.....',
]
T_SHIRT = [
    '................',
    '................',
    '...ooo....ooo...',
    '..o###o--o###o..',
    '.o####oooo####o.',
    'o##############o',
    'o###o######o###o',
    '.ooo.o####o.ooo.',
    '.....o#++#o.....',
    '.....o#++#o.....',
    '.....o####o.....',
    '.....o####o.....',
    '.....o####o.....',
    '.....o----o.....',
    '.....oooooo.....',
    '................',
]


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))


def render(sprite, palette, scale=16):
    """Return PNG bytes for a sprite, each sprite pixel drawn as a
    scale x scale block (16 x 16 at scale 16 gives a crisp 256 x 256 image).
    palette maps the sprite's characters to (red, green, blue).
    """
    width = len(sprite[0]) * scale
    rows = []
    for line in sprite:
        pixels = b''.join(bytes(palette[char]) * scale for char in line)
        # Each PNG row starts with a filter byte; 0 means "no filter".
        rows.extend([b'\x00' + pixels] * scale)
    header = struct.pack('>IIBBBBB', width, len(rows), 8, 2, 0, 0, 0)     # 8-bit RGB
    return (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', header)
        + _chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
        + _chunk(b'IEND', b'')
    )


BACKGROUND, OUTLINE = (33, 37, 41), (10, 12, 14)      # the frontend's #212529

HOODIE_PNG = render(HOODIE, {
    '.': BACKGROUND, 'o': OUTLINE, '#': (48, 98, 201), '+': (120, 164, 240), '-': (30, 62, 140),
})
T_SHIRT_PNG = render(T_SHIRT, {
    '.': BACKGROUND, 'o': OUTLINE, '#': (226, 92, 54), '+': (255, 205, 86), '-': (160, 56, 30),
})
