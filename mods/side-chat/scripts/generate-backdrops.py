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
LOOP_FRAMES = {'fish': 480, 'stars': 480, 'orbit': 360, 'fireflies': 360, 'aurora': 360, 'blackhole': 480, 'cabin': 360}
X, Y = np.meshgrid(np.linspace(-1.15, 1.15, COLS), np.linspace(-2.16, 2.16, ROWS))
RAMP = ' .,:;-=+*#%@'
SCENES = ['orbit', 'dunes', 'tide', 'rain', 'garden', 'fish', 'stars', 'fireflies', 'aurora', 'cabin', 'blackhole']
RNG = np.random.default_rng(34)
FONT_FILES = ['/System/Library/Fonts/Menlo.ttc', 'C:/Windows/Fonts/consola.ttf', 'DejaVuSansMono.ttf']


def mono_font(size):
    for path in FONT_FILES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise OSError('No monospace font found; add one to FONT_FILES')
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


class Layers:
    """Brightest value wins each cell and carries its color, as in the koi pond."""
    def __init__(self, shape):
        self.value = np.zeros(shape)
        self.color = np.zeros((*shape, 3))

    def add(self, value, rgb):
        take = value > self.value
        self.color = np.where(take[..., None], rgb, self.color)
        self.value = np.maximum(self.value, value)


def ramp(stops, amount):
    # Piecewise-linear color ramp over evenly spaced stops.
    stops = np.array(stops, dtype=float)
    position = np.clip(amount, 0, 1) * (len(stops) - 1)
    low = np.minimum(np.asarray(position).astype(int), len(stops) - 2)
    mix = (position - low)[..., None]
    return stops[low] + (stops[low + 1] - stops[low]) * mix


# Aurora: folded curtains over far mountains, mirrored in a still lake.
AURORA_LAKE = 1.86
AURORA_CURTAINS = [
    # base, amplitude, frequency, height, phase multipliers, offset, strength
    (.98, .16, 2.3, .55, (1, 2, 3), .4, 1.0),
    (.62, .12, 3.1, .42, (2, 1, 4), 2.2, .72),
    (1.22, .08, 4.2, .30, (1, 3, 5), 4.1, .55),
]


def aurora_ridge(x):
    return (1.72 - .40 * np.exp(-((x - .58) / .19) ** 2) - .25 * np.exp(-((x + .30) / .24) ** 2)
        - .20 * np.exp(-((x - 1.02) / .15) ** 2) - .08 * np.exp(-((x + .95) / .2) ** 2)
        + .018 * np.sin(x * 27) + .01 * np.sin(x * 61))


def aurora_light(x, y, phase):
    total = np.zeros_like(x)
    height_mix = np.zeros_like(x)
    for base, amp, freq, height, (k1, k2, k3), offset, strength in AURORA_CURTAINS:
        edge = base + amp * np.sin(freq * x + k1 * phase + offset) + amp * .45 * np.sin(freq * 2.3 * x - k2 * phase + offset * 2)
        d = edge - y
        # A bright ribbon along the lower hem, with rays rising off it and fading.
        hem = np.exp(-(d / .035) ** 2)
        upper = np.where(d > 0, np.exp(-np.maximum(d, 0) / height), 0)
        rays = .10 + .90 * (.5 + .5 * np.sin(x * 33 + d * 6 + 2.4 * np.sin(x * 3.7 + k3 * phase + offset))) ** 3
        vertical = hem * (.55 + .45 * rays) + upper * rays * .85
        envelope = np.clip((x + .85) / 1.1, 0, 1) ** 1.5 * gaussian(x - .45, 1.0)
        pulse = .78 + .22 * np.sin(k2 * phase + x * 2.5 + offset)
        light = vertical * envelope * pulse * strength
        height_mix = np.where(light > total, np.clip(d / (height * 2.4), 0, 1), height_mix)
        total = np.maximum(total, light)
    return np.clip(total * 1.25, 0, 1), ramp([[96, 236, 156], [86, 214, 196], [128, 156, 232], [188, 120, 226]], height_mix)


def aurora_field(phase):
    layers = Layers(X.shape)
    ridge = aurora_ridge(X)
    sky = Y < np.minimum(ridge, AURORA_LAKE)
    light, color = aurora_light(X, Y, phase)
    layers.add(np.where(sky, light, 0), color)
    # Mountains: a crisp ridge line, snow hatching near the peaks, sparse rock below.
    depth = Y - ridge
    land = (depth > 0) & (Y < AURORA_LAKE)
    snow = np.where(depth < .09, .24 + .14 * np.sin(X * 52 + Y * 38) ** 8, .07 + .06 * np.sin(X * 71 - Y * 55) ** 12)
    layers.add(np.where(land, snow, 0), np.array([170, 186, 214]))
    layers.add(gaussian(depth, .011) * .46 * (Y < AURORA_LAKE), np.array([196, 208, 232]))
    # Lake: ripple-broken reflections of both.
    lake = Y >= AURORA_LAKE
    mirror_y = 2 * AURORA_LAKE - Y
    wobble_x = X + .018 * np.sin(Y * 95 + 2 * phase) + .008 * np.sin(Y * 210 - 3 * phase)
    mirrored_ridge = aurora_ridge(wobble_x)
    reflected, reflected_color = aurora_light(wobble_x, mirror_y, phase)
    streak = .45 + .55 * np.sin(Y * 150 + 3 * np.sin(X * 9 + phase)) ** 2
    layers.add(np.where(lake & (mirror_y < mirrored_ridge), reflected * .6 * streak, 0), reflected_color)
    layers.add(np.where(lake & (mirror_y >= mirrored_ridge), .03 + .14 * np.sin(Y * 150 + 2 * np.sin(X * 7 + phase)) ** 16 * (np.sin(X * 13 + 2 * phase) > .2), 0), np.array([120, 136, 168]))
    layers.add(gaussian(Y - AURORA_LAKE, .008) * .30, np.array([150, 190, 210]))
    return layers.value, layers.color


# Cabin: a log cabin in the snow at night, firelight flickering in its windows,
# smoke curling from the chimney, snow-laden pines and snow drifting down.
CABIN = (.30, 1.50)  # center x, and the ground line under its walls
FLAKES = RNG.uniform(0, 1, (90, 4))


def paint(layers, mask, value, rgb):
    # Painter's order: whatever is nearer the viewer covers what is behind it.
    layers.value = np.where(mask, value, layers.value)
    layers.color = np.where(mask[..., None], rgb, layers.color)


def snow_line(x):
    return 1.52 + .05 * np.sin(x * 2.3 + .4) + .025 * np.sin(x * 6.1) - .03 * x


def pine(layers, x0, base, height, width):
    # Three tiers of branches with snow weighing on their drooping tips.
    snow, needles = np.array([222, 232, 242]), np.array([70, 116, 94])
    trunk = (np.abs(X - x0) < width * .07) & (Y > base - height * .2) & (Y < base)
    paint(layers, trunk, .24 + .06 * np.sin(Y * 90) ** 2, np.array([108, 78, 56]))
    for tier in range(3):
        top = base - height + tier * height * .27
        bottom = top + height * (.40 + tier * .04)
        rel = (Y - top) / (bottom - top)
        half = width * (.42 + .26 * tier) * rel * (1 + .06 * np.sin(X * 70))
        inside = (rel > 0) & (rel < 1) & (np.abs(X - x0) < half)
        out = np.abs(X - x0) / np.maximum(half, 1e-3)
        laden = (rel > .80 - .15 * out) | (np.sin(X * 37 + Y * 21 + tier) ** 2 * out > .78)
        boughs = .20 + .10 * np.sin((X - x0) * 55 + Y * 40) ** 2 + .06 * (1 - out)
        paint(layers, inside, np.where(laden, .40 + .10 * rel, boughs), np.where(laden[..., None], snow, needles))


def cabin(layers, phase):
    cx, ground = CABIN
    x0, x1, wall_top = cx - .40, cx + .40, ground - .36
    eave, apex, reach = wall_top + .01, wall_top - .36, .54
    flicker = .86 + .09 * np.sin(5 * phase) + .05 * np.sin(13 * phase + 1)
    # Log walls: stacked rounded logs with grain, ends poking out at the corners.
    walls = (X > x0) & (X < x1) & (Y > wall_top) & (Y < ground)
    band = ((Y - wall_top) / .06) % 1
    rounded = np.sin(band * np.pi)
    paint(layers, walls, .22 + .26 * rounded + .05 * np.sin(X * 80 + Y * 30) ** 2,
        ramp([[130, 88, 56], [204, 146, 92]], rounded * .8))
    for row in np.arange(wall_top + .03, ground, .06):
        for end in (x0 - .012, x1 + .012):
            cut = np.hypot((X - end) / .02, (Y - row) / .028)
            paint(layers, cut < 1, .30 + .18 * np.sin(cut * 9) ** 2, np.array([196, 150, 102]))
    # Windows: warm panes with dark crossbars and frames, light spilling onto the snow.
    for n, wx in enumerate((cx - .24, cx + .24)):
        wy = ground - .19
        frame = (np.abs(X - wx) < .080) & (np.abs(Y - wy) < .086)
        pane = (np.abs(X - wx) < .064) & (np.abs(Y - wy) < .070)
        bars = (np.abs(X - wx) < .007) | (np.abs(Y - wy) < .009)
        paint(layers, frame, .30, np.array([120, 84, 56]))
        glow = (.80 + .20 * gaussian(np.hypot(X - wx, Y - wy), .06)) * (flicker + .04 * np.sin(7 * phase + n * 2))
        paint(layers, pane & ~bars, glow, ramp([[240, 150, 70], [255, 226, 160]], glow - .6))
        paint(layers, pane & bars, .14, np.array([110, 74, 50]))
        spill = gaussian(np.hypot((X - wx) / 1.6, Y - ground - .09), .07) * (Y > ground)
        layers.add(spill * .32 * flicker, np.array([238, 168, 92]))
    # Plank door with a small brass handle.
    door = (np.abs(X - cx) < .07) & (Y > ground - .28) & (Y < ground)
    paint(layers, door, .26 + .12 * np.sin((X - cx) * 90) ** 2, np.array([150, 100, 62]))
    paint(layers, np.hypot((X - cx - .042) / .01, (Y - ground + .12) / .014) < 1, .6, np.array([240, 204, 126]))
    # Chimney on the right slope, then the roof: dark shingles under a thick snow blanket.
    surface = apex + (eave - apex) * np.abs(X - cx) / reach
    chimney = (X > cx + .17) & (X < cx + .27) & (Y > apex + .02) & (Y < surface + .02)
    stones = .22 + .10 * np.sin(X * 140) ** 2 * np.sin(Y * 90) ** 2
    paint(layers, chimney, stones, np.array([138, 128, 124]))
    paint(layers, (X > cx + .16) & (X < cx + .28) & (Y > apex - .01) & (Y < apex + .025), .44, np.array([226, 234, 244]))
    roof = (Y > surface) & (Y < eave + .015) & (np.abs(X - cx) < reach) & ~chimney
    blanket = (Y - surface) < .075 + .012 * np.sin(X * 31)
    shingles = .14 + .08 * (((Y - apex) / .035) % 1 > .5) + .04 * np.sin(X * 90) ** 2
    sparkle = .06 * (np.sin(X * 173 + Y * 91) > .92)
    paint(layers, roof, np.where(blanket, .42 + sparkle, shingles), np.where(blanket[..., None], np.array([226, 234, 244]), np.array([96, 82, 78])))
    lip = (np.abs(X - cx) < reach + .02) & (Y > eave - .012) & (Y < eave + .02)
    paint(layers, lip, .40, np.array([222, 232, 242]))
    # Icicles hanging from the eave.
    for ix in np.arange(cx - reach + .03, cx + reach, .055):
        length = .03 + .025 * (np.sin(ix * 53) ** 2)
        icicle = (np.abs(X - ix) < .006 + .006 * (1 - (Y - eave) / length)) & (Y > eave + .02) & (Y < eave + .02 + length)
        paint(layers, icicle, .30, np.array([200, 220, 236]))
    # Snow drifted against the bottom of the walls.
    drift = (Y > ground - .035 + .015 * np.sin(X * 11)) & (np.abs(X - cx) < .48) & (Y < ground + .02)
    paint(layers, drift, .34 + .06 * np.sin(X * 60) ** 2, np.array([220, 230, 240]))
    # Smoke rising from the chimney and drifting left in slow curls.
    rise = apex - .01 - Y
    lifted = np.clip(rise, 0, None)
    center = cx + .22 - .10 * lifted - .08 * lifted ** 2 + (.10 * np.sin(lifted * 3 - 2 * phase) + .03 * np.sin(lifted * 7 - 3 * phase)) * np.clip(lifted * 2, 0, 1)
    wisp = gaussian(X - center, .025 + .08 * np.clip(lifted, 0, 1.5)) * np.clip(lifted * 6, 0, 1) * np.exp(-lifted / .9)
    puffs = (.5 + .5 * np.sin(lifted * 10 - 4 * phase + X * 4)) ** 2
    layers.add(np.where(rise > 0, wisp * (.45 + .55 * puffs) * .24, 0), np.array([170, 172, 182]))


def cabin_field(phase):
    layers = Layers(X.shape)
    # Snowy ground: a soft drift line over a lightly textured, glinting field.
    surface = snow_line(X)
    depth = Y - surface
    glint = .10 * (np.sin(X * 157 + Y * 83) * np.sin(X * 61 - Y * 47) > .55) * (.6 + .4 * np.sin(2 * phase + X * 40) ** 2)
    speckle = .09 * (np.sin(X * 41 + depth * 13) * np.sin(depth * 37 - X * 7) > .45)
    layers.add(np.where(depth > 0, speckle + glint, 0), np.array([206, 218, 234]))
    for k in range(1, 5):
        contour = Y - (surface + k * .14 + .035 * np.sin(X * (2.4 + k * .5) + k))
        layers.add(gaussian(contour, .011) * (.26 - k * .03), np.array([200, 212, 230]))
    layers.add(gaussian(depth, .012) * .38, np.array([222, 232, 242]))
    pine(layers, -1.06, snow_line(-1.06) + .02, .66, .36)
    pine(layers, -.74, snow_line(-.74) + .02, .98, .46)
    cabin(layers, phase)
    pine(layers, 1.06, snow_line(1.06) + .03, .80, .40)
    return layers.value, layers.color


def snow_overlay(phase):
    # Flakes fall the whole panel height once or twice per loop, swaying as they go,
    # thinner near the top so the upper area stays calm.
    canvas = Image.new('RGBA', (WIDTH * 2, HEIGHT * 2))
    draw = ImageDraw.Draw(canvas)
    small, big = mono_font(18), mono_font(24)
    t = phase / (2 * np.pi)
    for n, (x, offset, size, sway) in enumerate(FLAKES):
        progress = (t * (1 + n % 2) + offset) % 1
        py = -20 + progress * (HEIGHT + 40)
        px = x * WIDTH + 14 * np.sin(2 * np.pi * progress * (1 + n % 3) + sway * 6)
        alpha = int(215 * (.30 + .70 * np.clip((py / HEIGHT - .2) / .4, 0, 1)) * (.55 + .45 * size))
        draw.text((px * 2, py * 2), '*' if size > .85 else '.', font=big if size > .5 else small, fill=(226, 236, 248, alpha))
    return canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


# Black hole: real Schwarzschild ray tracing, not a drawing of one. Every glyph
# fires 3x3 light rays that bend around the hole (u'' = 3u^2 - u, in units of M).
# Rays that cross the disk light it, rays that fall in make the shadow, rays that
# escape look up a star map. The lensed far side of the disk arches over the
# shadow, Doppler beaming brightens the approaching side, and stars drifting
# behind the hole smear into arcs along the Einstein ring. The geometry is traced
# once; each frame only spins the disk and moves the sky.
BH_CENTER, BH_SCALE, BH_DISTANCE, BH_TILT = (.06, 1.02), 13.0, 40.0, np.radians(18)
BH_CRITICAL = 3 * np.sqrt(3)  # impact parameter of the photon sphere, in M
BH_INNER, BH_OUTER, BH_SUPER, BH_SPIN = 6.0, 16.0, 3, 2
BH_WAVES = RNG.uniform([0, .4, 0, .8], [1, 1, 6.28, 2.6], (7, 4))
_BH = {}


def black_hole_geometry():
    if _BH:
        return _BH
    s = BH_SUPER
    xs, ys = np.linspace(-1.15, 1.15, COLS), np.linspace(-2.16, 2.16, ROWS)
    offsets = (np.arange(s) - (s - 1) / 2) / s
    gx, gy = np.meshgrid((xs[:, None] + offsets * (xs[1] - xs[0])).ravel(), (ys[:, None] + offsets * (ys[1] - ys[0])).ravel())
    px, py = (gx - BH_CENTER[0]) * BH_SCALE, -(gy - BH_CENTER[1]) * BH_SCALE
    rho = np.maximum(np.hypot(px, py), 1e-4)
    alpha = np.arctan(rho / BH_DISTANCE)
    e1 = np.array([0, -np.cos(BH_TILT), np.sin(BH_TILT)])
    right, up = np.array([1., 0, 0]), np.array([0, np.sin(BH_TILT), np.cos(BH_TILT)])
    n = (px[..., None] * right + py[..., None] * up) / rho[..., None]
    u = np.full(rho.shape, 1 / BH_DISTANCE)
    du = np.sqrt(1 - 2 / BH_DISTANCE) / np.tan(alpha) / BH_DISTANCE
    phi = np.zeros_like(u)
    # Each ray's plane cuts the disk plane at fixed angles, pi apart.
    crossing = np.mod(np.arctan2(n[..., 2], e1[2]) + np.pi / 2, np.pi)
    crossing = np.where(crossing < 1e-6, np.pi, crossing)
    found = np.zeros(u.shape, dtype=int)
    hit_r, hit_theta, hit_kv, hit_phi = (np.full((3, *u.shape), np.nan) for _ in range(4))
    state = np.zeros(u.shape, dtype=int)  # 0 travelling, 1 captured, 2 escaped
    escape_phi = np.zeros_like(u)

    def accel(value):
        return 3 * value * value - value

    step = .006
    for _ in range(int(4.2 * np.pi / step)):
        live = state == 0
        if not live.any():
            break
        k1u, k1v = du, accel(u)
        k2u, k2v = du + step / 2 * k1v, accel(u + step / 2 * k1u)
        k3u, k3v = du + step / 2 * k2v, accel(u + step / 2 * k2u)
        k4u, k4v = du + step * k3v, accel(u + step * k3u)
        nu = u + step / 6 * (k1u + 2 * k2u + 2 * k3u + k4u)
        ndu = du + step / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        cross = live & (crossing <= phi + step) & (found < 3)
        if cross.any():
            f = (crossing - phi) / step
            uc, duc = u + f * (nu - u), du + f * (ndu - du)
            uc = np.maximum(uc, 1e-9)
            point = np.cos(crossing)[..., None] * e1 + np.sin(crossing)[..., None] * n
            tangent = -np.sin(crossing)[..., None] * e1 + np.cos(crossing)[..., None] * n
            # Photon heads back toward the camera: opposite to the traced direction.
            travel = (duc / uc ** 2)[..., None] * point - (1 / uc)[..., None] * tangent
            travel /= np.linalg.norm(travel, axis=-1, keepdims=True)
            theta = np.arctan2(point[..., 1], point[..., 0])
            kv = travel[..., 0] * -np.sin(theta) + travel[..., 1] * np.cos(theta)
            for slot in range(3):
                write = cross & (found == slot)
                hit_r[slot][write] = 1 / uc[write]
                hit_theta[slot][write] = theta[write]
                hit_kv[slot][write] = kv[write]
                hit_phi[slot][write] = crossing[write]
            found += cross
            crossing = np.where(cross, crossing + np.pi, crossing)
        u, du = np.where(live, nu, u), np.where(live, ndu, du)
        phi = np.where(live, phi + step, phi)
        state = np.where(live & (u > .5), 1, state)
        out = live & (state == 0) & (du < 0) & (u < .15 / BH_DISTANCE)
        escape_phi = np.where(out, phi + u / np.maximum(-du, 1e-9), escape_phi)
        state = np.where(out, 2, state)
    state = np.where(state == 0, 1, state)  # rays still orbiting count as captured
    # The first crossing inside the disk hides everything behind it.
    valid = (hit_r > BH_INNER) & (hit_r < BH_OUTER)
    first = np.argmax(valid, axis=0)

    def pick(values):
        return np.take_along_axis(values, first[None], 0)[0]

    disk = valid.any(axis=0)
    direction = np.cos(escape_phi)[..., None] * e1 + np.sin(escape_phi)[..., None] * n
    _BH.update(disk=disk, r=np.where(disk, pick(hit_r), BH_INNER + 1), theta=np.where(disk, pick(hit_theta), 0),
        kv=np.where(disk, pick(hit_kv), 0), escaped=(state == 2) & ~disk, image_order=np.where(disk, first, -1),
        bend=np.where(disk, pick(hit_phi), 0), angle=np.arctan2(py, px),
        impact=BH_DISTANCE * np.sin(alpha) / np.sqrt(1 - 2 / BH_DISTANCE),
        lon=np.arctan2(direction @ right, -(direction @ e1)), lat=np.arcsin(np.clip(direction @ up, -1, 1)))
    # Star map: equirectangular star ids at 0.1 degree per texel.
    sky_rng = np.random.default_rng(71)
    count = 1100
    star_lon = sky_rng.uniform(-np.pi, np.pi, count)
    star_lat = np.arcsin(sky_rng.uniform(-1, 1, count))
    texels = np.full((1800, 3600), -1, dtype=np.int32)
    weight = np.zeros((1800, 3600))
    for index, (lon, lat) in enumerate(zip(star_lon, star_lat)):
        cx, cy = int((lon + np.pi) / (2 * np.pi) * 3600), int((lat + np.pi / 2) / np.pi * 1800)
        radius = 2 if index % 9 == 0 else 1
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                falloff = 1 - np.hypot(ox, oy) / (radius + .5)
                ty, tx = cy + oy, (cx + ox) % 3600
                if falloff > 0 and 0 <= ty < 1800 and falloff > weight[ty, tx]:
                    texels[ty, tx], weight[ty, tx] = index, falloff
    _BH.update(texels=texels, weight=weight, star_bright=.30 + .70 * sky_rng.power(3.5, count),
        star_rate=sky_rng.integers(1, 4, count), star_offset=sky_rng.uniform(0, 6.28, count))
    return _BH


def black_hole_field(phase):
    g = black_hole_geometry()
    t = phase / (2 * np.pi)
    s = BH_SUPER
    r, theta = g['r'], g['theta']
    # Disk light: hot inner edge, Keplerian shear (inner rings lap outer ones),
    # spiral streaks whose speeds are whole laps per loop so the clip closes exactly.
    rise = 1 - np.exp(-(r - BH_INNER) / .7)
    fade = np.clip((BH_OUTER - r) / 3.5, 0, 1) ** 1.5
    profile = rise * (BH_INNER / r) ** 1.35 * fade
    streaks = np.zeros_like(r)
    for n, (_, amp, shift, twist) in enumerate(BH_WAVES):
        m = 3 + 2 * n
        laps = np.rint(m * BH_SPIN * (BH_INNER / r) ** 1.5)
        streaks += amp * (.5 + .5 * np.sin(m * theta - 2 * np.pi * laps * t + twist * r + shift + 1.4 * np.sin(r * .9 + n))) ** 3
    streaks /= BH_WAVES[:, 1].sum() * .45
    bands = .5 + .5 * np.sin(r * 4.3 + 1.6 * np.sin(r * 1.3))
    emitted = profile * (.30 + .52 * np.clip(streaks, 0, 1.6) + .18 * bands)
    beta = 1 / np.sqrt(np.maximum(r - 2, 1e-3))
    shift_g = np.sqrt(1 - 2 / r) * np.sqrt(1 - beta ** 2) / (1 - beta * g['kv'])
    disk_light = np.where(g['disk'], emitted * shift_g ** 2 * 1.5, 0)
    # Light from the far side of the disk that bent over or under the hole draws
    # the curves around the shadow; brighten it against the direct view of the disk.
    far_side = np.clip((g['bend'] - np.pi / 2) / (np.pi / 2), 0, 1.5)
    disk_light = disk_light * (1 + .45 * far_side)
    disk_light = np.where(g['image_order'] >= 2, disk_light * 1.6, disk_light)
    # Photon ring: light that orbits just outside the event horizon before escaping,
    # a thin bright circle at the shadow's edge. The front of the disk covers its lower part.
    ring = gaussian(g['impact'] - BH_CRITICAL - .15, .26)
    ring *= (.62 + .38 * -np.cos(g['angle'])) * (.82 + .18 * np.sin(3 * g['angle'] - 2 * phase))
    ring_light = np.where(~g['disk'] | (g['bend'] > np.pi / 2), ring * 2.6, 0)
    # The sky drifts in a small circle so stars pass behind the hole and get lensed.
    lon = g['lon'] + np.radians(4.5) * np.cos(phase)
    lat = g['lat'] + np.radians(3.0) * np.sin(phase)
    tx = ((lon + np.pi) / (2 * np.pi) * 3600).astype(int) % 3600
    ty = np.clip(((lat + np.pi / 2) / np.pi * 1800).astype(int), 0, 1799)
    ids = g['texels'][ty, tx]
    twinkle = .72 + .28 * np.sin(phase * g['star_rate'] + g['star_offset']) ** 2
    star = np.where((ids >= 0) & g['escaped'], g['weight'][ty, tx] * (g['star_bright'] * twinkle)[np.maximum(ids, 0)], 0)
    shape = (ROWS, s, COLS, s)
    blocks = (disk_light + ring_light).reshape(shape)
    disk_mean = blocks.mean(axis=(1, 3))
    star_max = star.reshape(shape).max(axis=(1, 3))
    # Stars use only '.', '+' and '*' so lensed streaks read as dotted arcs.
    star_max = np.select([star_max > .55, star_max > .30, star_max > .05], [8, 7, 1], 0) / (len(RAMP) - 1)
    doppler = (shift_g * disk_light + 1.7 * ring_light).reshape(shape).sum(axis=(1, 3)) / np.maximum(blocks.sum(axis=(1, 3)), 1e-9)
    disk_value = 1 - np.exp(-disk_mean * 1.9)
    values = np.maximum(disk_value, star_max)
    heat = np.clip(.55 * disk_value + .55 * (doppler - .75), 0, 1)
    disk_color = ramp([[150, 46, 28], [222, 98, 42], [246, 160, 82], [255, 224, 176], [236, 238, 255]], heat)
    colors = np.where((disk_value >= star_max)[..., None], disk_color, np.array([214, 226, 255]))
    return values, colors


CUSTOM_FIELDS = {'aurora': aurora_field, 'cabin': cabin_field, 'blackhole': black_hole_field}


def atlas():
    font = mono_font(9)
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
    fonts = {size: mono_font(size * 2) for size in [9, 11, 14, 19]}
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
    small, bright = mono_font(20), mono_font(28)
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
    elif name in CUSTOM_FIELDS:
        values, colors = CUSTOM_FIELDS[name](phase)
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
    if name == 'cabin':
        canvas.alpha_composite(snow_overlay(phase))
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
                'aurora': (0, 600, 480, 830), 'cabin': (20, 560, 480, 800), 'blackhole': (0, 500, 480, 800),
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
