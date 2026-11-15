#!/usr/bin/env python3
"""Build original ASCII scenes as native-playback WebP clips. No runtime drawing."""
import argparse
import gc
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path.home() / '.local/share/herdr-art-tools'))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

COLS, ROWS, CW, CH = 96, 100, 5, 9
WIDTH, HEIGHT, FPS, COUNT = COLS * CW, ROWS * CH, 30, 240
LOOP_FRAMES = {'fish': 480, 'stars': 480, 'orbit': 360, 'fireflies': 360}
X, Y = np.meshgrid(np.linspace(-1.15, 1.15, COLS), np.linspace(-2.16, 2.16, ROWS))
RAMP = ' .,:;-=+*#%@'
SCENES = ['orbit', 'dunes', 'tide', 'rain', 'garden', 'fish', 'stars', 'fireflies']
RNG = np.random.default_rng(34)
STARS = RNG.uniform([-1.2, -2.2, 0.3, 0], [1.2, 2.2, 1, 6.28], (100, 4))
DROPS = RNG.uniform([-1.4, -2.3, 0.4, 0], [1.4, 2.3, 1.1, 1], (18, 4))


def gaussian(distance, width):
    return np.exp(-(distance / width) ** 2)


def field(name, phase):
    t = phase / (2 * np.pi)
    if name == 'orbit':
        xx, yy = X - .49, Y - 1.10
        r = np.hypot(xx, yy)
        z = np.sqrt(np.maximum(0, .64 ** 2 - r ** 2))
        longitude = np.arctan2(xx, z + 1e-6)
        bands = .5 + .5 * np.sin(yy * 43 + 1.4 * np.sin(longitude * 7 + phase))
        light = np.clip((-.55 * xx - .35 * yy + .8 * z) / .64, 0, 1)
        planet = np.where(r < .64, .15 + light * (.4 + .35 * bands), 0)
        tilt = -.38 + .04 * np.sin(phase)
        a, b = xx * np.cos(tilt) + yy * np.sin(tilt), -xx * np.sin(tilt) + yy * np.cos(tilt)
        q = np.hypot(a / 1.00, b / .31)
        rings = np.where((q > .75) & (q < 1.12), .3 + .45 * np.sin(q * 240) ** 4, 0)
        rings = np.where((r > .64) | (b > 0), rings, 0)
        sky = np.zeros_like(X)
        # A separate crescent and small moon leave room between the main objects.
        moon_x, moon_y = X + .65, Y + .34
        moon = np.hypot(moon_x, moon_y)
        crescent = np.where((moon < .15) & (np.hypot(moon_x - .055, moon_y + .025) > .142), .48, 0)
        sky += crescent
        sky += gaussian(np.hypot(xx - .9 * np.cos(phase), yy - .65 * np.sin(phase)), .025) * .65
        dust = gaussian(Y - (1.8 - .28 * X + .06 * np.sin(phase + X * 3)), .18)
        dust *= (.12 + .16 * np.sin(X * 57 + Y * 83 + phase) ** 8) * np.clip((X + .5), 0, 1)
        sky += dust
        return np.maximum.reduce([sky, planet, rings])
    if name == 'dunes':
        sun_x = .42 + .035 * np.sin(phase)
        sun_y = .15 + .045 * np.cos(phase)
        sun_r = np.hypot(X - sun_x, Y - sun_y)
        radius = .25 + .008 * np.sin(phase)
        out = gaussian(sun_r - radius, .015) * .6
        stripes = .5 + .5 * np.sin((Y - sun_y) * 58 - phase * 2)
        out += np.where(sun_r < radius - .018, .16 + .30 * stripes ** 4, 0)
        horizon = .88 - .23 * X + .12 * np.sin(X * 3 + .025 * np.sin(phase))
        depth = Y - horizon
        fill = np.clip(depth / .65, 0, 1)
        grain = np.sin(X * 93 + Y * 71 + .6 * np.sin(phase)) ** 2
        wind = np.sin(depth * 73 + X * 9 + 2 * np.sin(X * 4 + phase)) ** 8
        out += fill * (.09 + .11 * grain + .15 * wind)
        for n in range(9):
            ridge = horizon + n * .17 + .065 * np.sin(X * (3 + n * .2) + n + phase)
            out += gaussian(Y - ridge, .014) * (.50 - n * .025)
        return out
    if name == 'tide':
        shore = .95 - .28 * X + .13 * np.sin(X * 2.8 + phase)
        depth = Y - shore
        water = np.clip(depth / .45, 0, 1)
        caustic = np.sin(X * 17 + 2 * np.sin(Y * 6 + phase)) * np.cos(Y * 23 + np.sin(X * 8 - phase))
        out = water * (.09 + .34 * gaussian(caustic, .12))
        for n in range(8):
            curve = shore + n * .16 + .045 * np.sin(X * 8 + phase + n * .55)
            out += gaussian(Y - curve, .016) * (.48 - n * .025)
        return out
    if name == 'fireflies':
        out = np.zeros_like(X)
        for n in range(17):
            bx = -.95 + n * .14
            top = 1.8 - .7 * ((n % 6) / 6) - .35 * (bx + 1)
            stem = bx + .035 * np.sin(phase + n + Y * 2) * (2.16 - Y)
            out += gaussian(X - stem, .006) * .40 * ((Y > top) & (Y < 2.16))
            head = np.hypot((X - stem) / .03, (Y - top) / .10)
            out += np.where(head < 1, .24 + .15 * np.sin(Y * 120) ** 2, 0)
        return out
    if name == 'rain':
        out = np.zeros_like(X)
        for sx, sy, speed, offset in DROPS:
            cy = (sy + t * 4.6 * (1 + int(speed * 3))) % 4.6 - 2.3
            cx = sx - .16 * (cy - sy)
            drop = gaussian(X - cx + .16 * (Y - cy), .006 + speed * .003) * gaussian(Y - cy, .07 + speed * .06)
            out += drop * (.35 + speed * .25)
        for n in range(9):
            radius = (t + n * .31) % 1
            cx, cy = -.85 + (n % 4) * .63, 1.2 + (n // 4) * .35
            ellipse = np.hypot((X - cx) / .25, (Y - cy) / .07)
            out += gaussian(ellipse - radius * 2, .13) * np.sin(radius * np.pi) ** 2 * .48
        pool = np.clip((Y - (1.15 - .20 * X)) / .6, 0, 1)
        out += pool * (.08 + .10 * np.sin(Y * 85 + .5 * np.sin(X * 12 + phase)) ** 8)
        return out
    if name == 'garden':
        out = np.zeros_like(X)
        for stem, (base, top, size) in enumerate([(.88, .12, 1.15), (.47, .63, .92), (.10, 1.13, .8), (-.58, 1.57, .65)]):
            sway = .05 * np.sin(phase + stem + Y) * np.clip((2.1 - Y), 0, 1.8)
            center = base + sway + .07 * np.sin(Y * 1.4 + stem)
            dx = X - center
            out += gaussian(dx, .009) * .65 * ((Y > top) & (Y < 2.16))
            for leaf in range(int((2.16 - top) / .19)):
                yy = Y - (leaf * .19 + top + .12)
                side = -1 if leaf % 2 else 1
                xx = dx - side * .13 * size
                a, b = xx * .78 + yy * side * .62, -xx * side * .62 + yy * .78
                shape = (a / (.23 * size)) ** 2 + (b / (.075 * size)) ** 2
                veins = gaussian(np.sin(a * 100 + np.abs(b) * 180), .24)
                density = .20 + .28 * (1 - np.clip(shape, 0, 1)) + .18 * veins
                out = np.maximum(out, np.where(shape < 1, density, 0))
        return out
    raise ValueError(name)


def koi_field(phase):
    # More glyphs across each fish keep curved spines and fins legible as they turn.
    x, y = np.meshgrid(np.linspace(-1.15, 1.15, COLS * 2), np.linspace(-2.16, 2.16, ROWS * 2))
    out = np.zeros_like(x)
    colors = np.zeros((*x.shape, 3))

    def layer(value, rgb):
        nonlocal out, colors
        take = value > out
        colors = np.where(take[..., None], rgb, colors)
        out = np.maximum(out, value)

    # Lily pads drift in place, away from the fish's paths.
    for n, (px, py, radius) in enumerate([(.77, 1.62, .29), (-.78, 1.85, .19)]):
        dx = x - px - .015 * np.sin(phase + n)
        dy = y - py - .012 * np.cos(phase + n)
        angle = np.arctan2(dy, dx)
        r = np.hypot(dx, dy)
        edge = radius * (1 + .035 * np.sin(angle * 5 + phase))
        pad = (r < edge) & (np.abs(np.arctan2(np.sin(angle + 1), np.cos(angle + 1))) > .23)
        veins = gaussian(np.sin(angle * 6 + r * 2), .12)
        density = np.where(pad, .24 + .18 * (1 - r / radius) + .12 * veins, 0)
        layer(density, np.array([94, 169, 116]))
        layer(gaussian(r - radius * 1.15, .008) * .13, np.array([97, 170, 176]))
    dx, dy = x - .72, y - 1.40
    petal_angle = np.arctan2(dy, dx) + .04 * np.sin(phase)
    petal_r = np.hypot(dx, dy)
    petals = .055 + .045 * np.cos(petal_angle * 6) ** 2
    layer(np.where(petal_r < petals, .55 + .2 * (1 - petal_r / .10), 0), np.array([238, 177, 195]))
    layer(np.where(petal_r < .024, .8, 0), np.array([246, 209, 130]))

    fish = [(.25, -.50, .30, .40, .3, 1, 1.12), (-.28, .75, .27, .32, 2.6, -1, 1.0)]
    for n, (bx, by, rx, ry, offset, direction, scale) in enumerate(fish):
        # Gentle changes in speed have zero velocity discontinuity at the loop boundary.
        angle = direction * (phase + .10 * np.sin(phase * 2 + offset)) + offset
        cx, cy = bx + rx * np.cos(angle), by + ry * np.sin(angle)
        heading = np.arctan2(direction * ry * np.cos(angle), -direction * rx * np.sin(angle))
        dx, dy = x - cx, y - cy
        u = (dx * np.cos(heading) + dy * np.sin(heading)) / scale
        raw_v = (-dx * np.sin(heading) + dy * np.cos(heading)) / scale
        distance_from_head = np.clip((.38 - u) / .98, 0, 1)
        # A traveling wave grows from the shoulders to the tail, rather than rotating a rigid fish.
        swim = phase * 8 + offset
        bend = (.009 + .14 * distance_from_head ** 1.8) * np.sin(swim - distance_from_head * 5.2)
        bend += .025 * distance_from_head * np.sin(phase * 2 + offset)
        v = raw_v - bend
        width = .133 * np.sqrt(np.clip(1 - ((u - .015) / .365) ** 2, 0, 1)) * (1 + .5 * u)
        body = (u > -.35) & (u < .38) & (np.abs(v) < width)
        highlight = np.clip(1 - (v / np.maximum(width, .005)) ** 2, 0, 1)
        patches = gaussian(u - .18, .10) * gaussian(v + .02, .075) + gaussian(u + .10, .12) * gaussian(v - .035, .07)
        patch = np.clip(patches * 1.4, 0, 1)
        ivory = np.array([238, 230, 205])
        marking = np.array([238, 104, 61]) if n == 0 else np.array([239, 177, 67])
        body_color = ivory + (marking - ivory) * patch[..., None]
        dark_patch = gaussian(u + .23, .065) * gaussian(v + .035, .055)
        body_color *= (1 - .48 * dark_patch[..., None])
        scales = .045 * np.sin(u * 120 + np.sin(v * 100)) ** 2
        skin = .36 + .43 * highlight + scales
        eyes = gaussian(u - .275, .021) * (gaussian(v - .066, .014) + gaussian(v + .066, .014))
        body_color *= (1 - .82 * eyes[..., None])
        koi = np.zeros_like(x)
        fish_color = np.broadcast_to(np.array([211, 191, 150]), colors.shape).copy()
        for side in [-1, 1]:
            fin_swing = .055 * np.sin(swim + side * .7)
            fin_dx, fin_dy = u - .055 + fin_swing, v - side * .15
            a = fin_dx * .8 + fin_dy * side * .6
            b = -fin_dx * side * .6 + fin_dy * .8
            shape = (a / .145) ** 2 + (b / .057) ** 2
            fin = np.where(shape < 1, .23 + .15 * np.cos(a * 150) ** 2, 0)
            koi = np.maximum(koi, fin)
        tail_progress = np.clip((-.30 - u) / .32, 0, 1)
        tail_width = .022 + tail_progress * .15
        tail = (u < -.30) & (u > -.62) & (np.abs(v) < tail_width)
        tail &= ~((u < -.54) & (np.abs(v) < (-.54 - u) * 1.15))
        rays = .27 + .18 * np.cos(np.arctan2(v, -.28 - u) * 13) ** 2
        koi = np.maximum(koi, np.where(tail, rays, 0))
        koi = np.where(body, skin, koi)
        fish_color = np.where(body[..., None], body_color, fish_color)
        for side in [-1, 1]:
            barbel = gaussian(v - side * (.03 + (u - .34) * .36), .005)
            koi = np.maximum(koi, np.where((u > .33) & (u < .43), barbel * .48, 0))
        layer(koi, fish_color)
    return out, colors


def atlas():
    font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 9)
    tiles = []
    for char in RAMP:
        image = Image.new('L', (CW, CH))
        ImageDraw.Draw(image).text((0, -2), char, font=font, fill=255)
        tiles.append(np.asarray(image))
    return np.stack(tiles)


def scene_colors(name, values, phase):
    palettes = {
        'orbit': ([113, 163, 220], [230, 194, 140]),
        'dunes': ([173, 115, 80], [246, 198, 126]),
        'tide': ([79, 145, 170], [149, 222, 210]),
        'rain': ([103, 144, 193], [182, 210, 235]),
        'garden': ([92, 137, 105], [170, 202, 131]),
        'fireflies': ([72, 118, 97], [143, 175, 109]),
    }
    low, high = map(np.array, palettes[name])
    mix = np.clip(.25 + values * .65 + .15 * np.sin(X * 2 + Y), 0, 1)
    colors = low + (high - low) * mix[..., None]
    if name == 'dunes':
        colors = np.where((Y < .5)[..., None], np.array([248, 199, 112]), colors)
    return colors


def glyph_image(values, colors, tiles):
    values = np.clip(values, 0, 1)
    rows, cols = values.shape
    indices = np.rint(values * (len(RAMP) - 1)).astype(np.uint8)
    mask = tiles[indices].transpose(0, 2, 1, 3).reshape(rows * CH, cols * CW)
    pixels = np.zeros((rows * CH, cols * CW, 4), dtype=np.uint8)
    pixels[:, :, :3] = np.clip(colors, 0, 255).astype(np.uint8).repeat(CH, axis=0).repeat(CW, axis=1)
    pixels[:, :, 3] = mask
    result = Image.fromarray(pixels)
    return result if result.size == (WIDTH, HEIGHT) else result.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def sky_overlay(name, phase):
    # Draw at twice the output size so tiny drifting glyphs move between pixels smoothly.
    canvas = Image.new('RGBA', (WIDTH * 2, HEIGHT * 2))
    draw = ImageDraw.Draw(canvas)
    font_file = '/System/Library/Fonts/Menlo.ttc'
    fonts = {size: ImageFont.truetype(font_file, size * 2) for size in [9, 11, 14, 19]}
    count = 51 if name == 'stars' else 43
    for n, (x, y, brightness, offset) in enumerate(STARS[:count]):
        # Keep a wide quiet patch in the upper-left, with smaller stars between focal points.
        if -.95 < x < -.15 and -1.45 < y < -.45 and n % 3:
            continue
        if name == 'orbit' and y > .35 and x > -.45:
            continue
        strong = n % 7 == 0
        alpha = int((140 + 110 * np.sin(phase + offset) ** 2) * (.75 if strong else brightness))
        px = (x + 1.2) / 2.4 * WIDTH + 1.2 * np.sin(phase + offset)
        py = (y + 2.2) / 4.4 * HEIGHT + .7 * np.cos(phase + offset)
        size = 19 if strong else 14 if n % 5 == 0 else 11 if n % 3 == 0 else 9
        rgb = [216, 232, 255] if n % 3 else [246, 220, 173]
        glyph = '*' if strong else '+' if n % 5 == 0 else '.'
        draw.text((px * 2, py * 2), glyph, font=fonts[size], fill=(*rgb, min(255, alpha + (45 if strong else 0))))
        if strong:
            draw.text(((px - 4) * 2, (py - 3) * 2), '.', font=fonts[9], fill=(*rgb, alpha // 3))
    # Short isolated meteor passes, with a tail made from fading ASCII slashes.
    for start, x, y, travel_x, travel_y in [(.13, 70, 205, 200, 112), (.68, 245, 460, 175, 100)][:2 if name == 'stars' else 1]:
        progress = (phase / (2 * np.pi) - start) / .045
        if not 0 < progress < 1:
            continue
        fade = np.sin(progress * np.pi) ** .6
        px, py = x + travel_x * progress, y + travel_y * progress
        for trail in range(10, -1, -1):
            alpha = int(245 * fade * (1 - trail / 11) ** 1.6)
            draw.text(((px - trail * 6) * 2, (py - trail * 3.4) * 2), '*' if trail == 0 else '\\', font=fonts[11], fill=(200, 226, 255, alpha))
    return canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def firefly_overlay(phase):
    canvas = Image.new('RGBA', (WIDTH * 2, HEIGHT * 2))
    draw = ImageDraw.Draw(canvas)
    font_file = '/System/Library/Fonts/Menlo.ttc'
    small, bright = ImageFont.truetype(font_file, 20), ImageFont.truetype(font_file, 28)
    for n, (x, y, brightness, offset) in enumerate(STARS[:22]):
        # Most lights gather above the meadow; a few wander farther up.
        bx = 235 + x * 160
        by = 600 + y * 72 if n % 6 else 330 + y * 65
        px = bx + 25 * np.sin(phase + offset) + 7 * np.sin(phase * 3 + offset)
        py = by + 30 * np.cos(phase + offset) + 9 * np.sin(phase * 2 + offset)
        glow = (.5 + .5 * np.sin(phase * 2 + offset)) ** 2
        alpha = int(45 + 205 * glow)
        for k in range(4, 0, -1):
            past = phase - k * .045
            tx = bx + 25 * np.sin(past + offset) + 7 * np.sin(past * 3 + offset)
            ty = by + 30 * np.cos(past + offset) + 9 * np.sin(past * 2 + offset)
            draw.text((tx * 2, ty * 2), '.', font=small, fill=(220, 184, 95, int(alpha * .18 * (1 - k / 5))))
        draw.text((px * 2, py * 2), '*' if n % 4 == 0 else '.', font=bright, fill=(246, 218, 132, alpha))
    return canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def render(name, i, tiles):
    phase = i / LOOP_FRAMES.get(name, COUNT) * np.pi * 2
    if name == 'stars':
        return sky_overlay(name, phase)
    if name == 'fish':
        values, colors = koi_field(phase)
    else:
        values = field(name, phase)
        colors = scene_colors(name, values, phase)
    canvas = glyph_image(values, colors, tiles)
    if name == 'fish':
        # Downsampling fine glyphs softens them; restore their contrast without widening them.
        alpha = np.array(canvas.getchannel('A'), dtype=np.float32)
        canvas.putalpha(Image.fromarray(np.clip(alpha * 1.8, 0, 255).astype(np.uint8)))
    if name == 'orbit':
        canvas.alpha_composite(sky_overlay(name, phase))
    if name == 'fireflies':
        canvas.alpha_composite(firefly_overlay(phase))
    return canvas


def koi_color_frame(frame):
    # Large continuous-color koi clips failed to display in Herdr. A fixed palette
    # keeps the native export small while preserving the orange, gold and pond colors.
    swatches = [(0, 0, 0)]
    for base in [(238, 230, 205), (238, 104, 61), (239, 177, 67), (211, 191, 150),
            (94, 169, 116), (238, 177, 195), (97, 170, 176), (246, 209, 130)]:
        for shade in [.45, .65, .82, 1]:
            swatches.append(tuple(round(c * shade) for c in base))
    palette = Image.new('P', (1, 1))
    palette.putpalette(sum((list(c) for c in swatches), []) + [0] * (768 - len(swatches) * 3))
    small = frame.resize((320, 600), Image.Resampling.LANCZOS)
    result = small.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE).convert('RGBA')
    result.putalpha(small.getchannel('A'))
    return result


def variant_frame(frame, variant, color, scene=None):
    if color and scene == 'fish':
        frame = koi_color_frame(frame)
    pixels = np.array(frame)
    if not color:
        pixels[:, :, :3] = 255 if variant == 'dark' else 0
    elif variant == 'light':
        pixels[:, :, :3] = np.rint(pixels[:, :, :3] * .58).astype(np.uint8)
    return Image.fromarray(pixels)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent / 'assets')
    parser.add_argument('--theme', choices=SCENES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tiles = atlas()
    manifest = {'fps': FPS, 'width': WIDTH, 'height': HEIGHT, 'columns': COLS, 'rows': ROWS,
        'transparent': True, 'colorModes': ['monochrome', 'color'],
        'scenes': {name: {'frames': LOOP_FRAMES.get(name, COUNT), 'durationMs': LOOP_FRAMES.get(name, COUNT) * 1000 // FPS,
            **({'colorWidth': 320, 'colorHeight': 600} if name == 'fish' else {})} for name in SCENES}}
    for name in ([args.theme] if args.theme else SCENES):
        started = time.monotonic()
        count = LOOP_FRAMES.get(name, COUNT)
        durations = [33, 33, 34] * (count // 3)
        frames = [render(name, i, tiles) for i in range(count)]
        for variant, color in [('dark', False), ('light', False), ('dark', True), ('light', True)]:
            first = variant_frame(frames[0], variant, color, name)
            stem = f'{"pond" if name == "fish" else name}-{variant}' + ('-color' if color else '')
            first.save(args.output / f'{stem}.webp', format='WEBP', save_all=True,
                append_images=(variant_frame(frame, variant, color, name) for frame in frames[1:]),
                duration=durations, loop=0, lossless=True, method=3 if name == 'fish' or not color else 1,
                quality=40 if name == 'fish' and color else 20 if color else 80)
            if name == 'fish' and color and (args.output / f'{stem}.webp').stat().st_size >= 16 * 1024 * 1024:
                raise ValueError('Koi color animation exceeds the native playback export budget')
            first.save(args.output / f'{stem}-still.webp', format='WEBP', lossless=True)
            crops = {
                'orbit': (40, 430, 480, 760), 'dunes': (0, 430, 480, 800),
                'tide': (0, 530, 480, 780), 'garden': (0, 570, 480, 900),
                'fireflies': (60, 420, 480, 840),
            }
            preview = first.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).crop((220, 220, 480, 490)).rotate(90, expand=True) if name == 'fish' else first.crop(crops.get(name, (0, 0, WIDTH, HEIGHT)))
            thumb = ImageOps.fit(preview, (300, 144), method=Image.Resampling.LANCZOS)
            thumb.save(args.output / f'{stem}-preview.webp', format='WEBP', lossless=True)
            del first
            gc.collect()
        print(json.dumps({'theme': name, 'seconds': round(time.monotonic()-started, 1),
            'bytes': (args.output / f'{"pond" if name == "fish" else name}-dark.webp').stat().st_size}), flush=True)
        del frames;gc.collect()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__':main()
