"""Parametric rally-car generator for Mud Rally.

Builds four original car designs in Blender and exports each as a Draco-compressed GLB plus a
thumbnail render. Run:  blender --background --python build_cars.py  (or: python3 build_cars.py with the bpy module)

Conventions: Blender Z up, car nose towards -Y (the glTF exporter turns that into +Z, the game's forward).
Material names the game relies on: Paint (recoloured per car), Stripe, Roof. Wheel objects: WheelFL/FR/RL/RR.
"""
import bpy, bmesh, math, random, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUTDIR = os.path.dirname(os.path.abspath(__file__))
ONLY = [a for a in sys.argv if a.startswith('only=')]
lerp = lambda a, b, t: a + (b - a) * t
clamp = lambda v, a, b: max(a, min(b, v))

# ------------------------------------------------------------------ curve helpers
def pchip(pts):
    """Monotone cubic interpolation through (x, y) points: smooth, no overshoot."""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else 2 / (1 / d[i - 1] + 1 / d[i]) for i in range(1, n - 1)] + [d[-1]]
    def f(x):
        if x <= xs[0]: return ys[0]
        if x >= xs[-1]: return ys[-1]
        i = max(k for k in range(n - 1) if xs[k] <= x)
        h = xs[i + 1] - xs[i]; t = (x - xs[i]) / h
        h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
        return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]
    return f

def sgnpow(v, p): return math.copysign(abs(v) ** p, v)

def inpoly(u, v, poly):
    c = False; j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > v) != (yj > v) and u < (xj - xi) * (v - yi) / (yj - yi + 1e-12) + xi:
            c = not c
        j = i
    return c

ELLIPSE = [(0.5 + 0.5 * math.cos(a / 24 * 6.283), 0.5 + 0.5 * math.sin(a / 24 * 6.283)) for a in range(24)]

# ------------------------------------------------------------------ car designs
CARS = {
  'hatch': dict(
    title='Hatch R5', paint=(0.95, 0.32, 0.04),
    yf=-2.0, yr=2.05, wheels=(-1.26, 1.28), R=0.37, track=0.85, tyre_w=0.27,
    top=[(-2.0, .7), (-1.92, .8), (-1.5, .87), (-1.0, .92), (-0.55, .97), (0.5, 1.0), (1.5, 1.02), (1.9, .98), (2.05, .84)],
    bot=[(-2.0, .36), (-1.8, .31), (1.8, .31), (2.05, .4)],
    width=[(-2.0, .62), (-1.88, .84), (-1.3, .97), (-0.7, .92), (0.6, .91), (1.3, .99), (1.85, .92), (2.05, .72)],
    roof=[(-0.66, .96), (-0.3, 1.16), (0.1, 1.4), (0.45, 1.46), (1.2, 1.45), (1.55, 1.4), (1.8, 1.22), (1.97, 1.0)],
    zb=0.9, wb=0.86, wt=0.64, doors=[-0.5, 0.8], pillars=[(0.64, 0.76)],
    head=dict(x=(0.36, 0.8), z=(0.56, 0.72), shape=[(0, .25), (1, .05), (1, .85), (.05, 1)]),
    grille=dict(x=0.42, z=(0.44, 0.56), shape=[(.12, 0), (.88, 0), (1, 1), (0, 1)]),
    tail=dict(x=(0.5, 0.86), z=(0.84, 0.97), shape=[(0, .2), (1, 0), (1, 1), (0, .8)]),
    rim_spokes=6, rim_style='dish', wing='big', pod=True, scoop=True, flares='paint', roof_black=False, rails=False,
    stripes='twin', hood_vents=True),
  'supermini': dict(
    title='Supermini 5D', paint=(0.05, 0.36, 0.9),
    yf=-2.02, yr=2.0, wheels=(-1.28, 1.27), R=0.36, track=0.84, tyre_w=0.25,
    top=[(-2.02, .7), (-1.92, .8), (-1.5, .88), (-1.0, .94), (-0.6, .99), (0.5, 1.02), (1.6, 1.03), (1.9, .99), (2.0, .86)],
    bot=[(-2.02, .36), (-1.8, .3), (1.8, .3), (2.0, .4)],
    width=[(-2.02, .6), (-1.9, .82), (-1.3, .95), (-0.7, .92), (0.6, .92), (1.3, .96), (1.85, .9), (2.0, .7)],
    roof=[(-0.7, .98), (-0.35, 1.2), (0.05, 1.45), (0.4, 1.51), (1.2, 1.5), (1.6, 1.44), (1.85, 1.26), (1.97, 1.02)],
    zb=0.92, wb=0.86, wt=0.66, doors=[-0.55, 0.38, 1.22], pillars=[(0.3, 0.44), (1.12, 1.22)],
    head=dict(x=(0.34, 0.8), z=(0.56, 0.74), shape=[(0, .15), (1, 0), (1, .8), (.1, 1)]),
    grille=dict(x=0.5, z=(0.46, 0.56), shape=[(.08, .1), (.92, .1), (1, .9), (0, .9)]),
    tail=dict(x=(0.52, 0.86), z=(0.82, 1.02), shape=[(.2, 0), (1, 0), (1, 1), (.2, 1)]),
    rim_spokes=5, rim_style='split', wing='lip', pod=False, scoop=True, flares='paint', roof_black=True, rails=False,
    stripes='side', hood_vents=False),
  'coupe': dict(
    title='Coupe GT', paint=(0.8, 0.04, 0.05),
    yf=-2.2, yr=2.15, wheels=(-1.35, 1.25), R=0.37, track=0.85, tyre_w=0.27,
    top=[(-2.2, .66), (-2.08, .75), (-1.6, .82), (-1.0, .88), (-0.45, .93), (0.6, .96), (1.6, .98), (2.0, .95), (2.15, .82)],
    bot=[(-2.2, .35), (-2.0, .3), (1.95, .3), (2.15, .38)],
    width=[(-2.2, .6), (-2.05, .84), (-1.4, .97), (-0.7, .92), (0.6, .92), (1.25, .99), (1.9, .93), (2.15, .72)],
    roof=[(-0.55, .93), (-0.1, 1.12), (0.4, 1.32), (0.8, 1.35), (1.2, 1.3), (1.6, 1.17), (1.95, 1.0), (2.05, .97)],
    zb=0.88, wb=0.84, wt=0.6, doors=[-0.42, 0.92], pillars=[(0.95, 1.05)],
    head=dict(x=(0.3, 0.82), z=(0.57, 0.69), shape=[(0, .45), (1, 0), (1, .6), (0, 1)]),
    grille=dict(x=0.36, z=(0.45, 0.55), shape=[(0, 0), (1, 0), (1, 1), (0, 1)]),
    tail=dict(x=(0.0, 0.84), z=(0.86, 0.93), shape=[(0, .2), (1, 0), (1, 1), (0, .8)]),
    rim_spokes=10, rim_style='mesh', wing='big', pod=True, scoop=False, flares='paint', roof_black=False, rails=False,
    stripes='twin', hood_vents=True),
  'crossover': dict(
    title='Crossover RX', paint=(0.95, 0.75, 0.05),
    yf=-2.1, yr=2.1, wheels=(-1.32, 1.32), R=0.41, track=0.86, tyre_w=0.28,
    top=[(-2.1, .9), (-2.0, .98), (-1.5, 1.03), (-1.0, 1.06), (-0.6, 1.1), (0.6, 1.13), (1.6, 1.14), (1.95, 1.1), (2.1, .98)],
    bot=[(-2.1, .58), (-1.9, .45), (1.9, .45), (2.1, .58)],
    width=[(-2.1, .66), (-1.98, .86), (-1.32, .97), (-0.7, .93), (0.6, .93), (1.32, .98), (1.95, .92), (2.1, .74)],
    roof=[(-0.6, 1.1), (-0.25, 1.32), (0.15, 1.56), (0.5, 1.62), (1.1, 1.6), (1.5, 1.5), (1.85, 1.3), (2.0, 1.12)],
    zb=1.03, wb=0.86, wt=0.64, doors=[-0.48, 0.42, 1.2], pillars=[(0.34, 0.48), (1.15, 1.26)],
    head=dict(x=(0.42, 0.84), z=(0.84, 0.9), shape=[(0, 0), (1, .2), (1, 1), (0, .6)]),
    head2=dict(x=(0.5, 0.82), z=(0.64, 0.76)),
    grille=dict(x=0.5, z=(0.6, 0.82), shape=[(.18, 0), (.82, 0), (1, 1), (0, 1)]),
    tail=dict(x=(0.45, 0.88), z=(0.96, 1.08), shape=[(0, .4), (1, 0), (1, 1), (0, 1)]),
    rim_spokes=6, rim_style='dish', wing='lip', pod=True, scoop=False, flares='plastic', roof_black=True, rails=True,
    stripes='side', hood_vents=False),
}

# ------------------------------------------------------------------ build one car
def build(key, C):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    def mat(name, color, metal=0.0, rough=0.5, emit=None, strength=0.0, alpha=1.0):
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes.get('Principled BSDF')
        b.inputs['Base Color'].default_value = (*color, 1)
        b.inputs['Metallic'].default_value = metal; b.inputs['Roughness'].default_value = rough
        if emit:
            b.inputs['Emission Color'].default_value = (*emit, 1); b.inputs['Emission Strength'].default_value = strength
        return m
    M = {
        'Paint': mat('Paint', C['paint'], 0.4, 0.28),
        'Stripe': mat('Stripe', (0.95, 0.95, 0.95), 0.1, 0.35),
        'Roof': mat('Roof', (0.02, 0.02, 0.025), 0.3, 0.25),
        'Glass': mat('Glass', (0.015, 0.022, 0.03), 0.9, 0.05),
        'Trim': mat('Trim', (0.012, 0.012, 0.014), 0.1, 0.35),
        'Plastic': mat('Plastic', (0.03, 0.03, 0.033), 0.0, 0.75),
        'Mud': mat('Mud', (0.16, 0.095, 0.045), 0.0, 0.95),
        'Rim': mat('Rim', (0.88, 0.88, 0.86) if C['rim_style'] != 'mesh' else (0.55, 0.45, 0.2), 0.6, 0.3),
        'Tire': mat('Tire', (0.02, 0.02, 0.022), 0.0, 0.92),
        'Brake': mat('Brake', (0.45, 0.45, 0.47), 0.9, 0.35),
        'Caliper': mat('Caliper', (0.85, 0.08, 0.04), 0.2, 0.4),
        'Lamp': mat('Lamp', (0.6, 0.62, 0.65), 1.0, 0.12),
        'Light': mat('Light', (1, 1, 0.97), 0.0, 0.1, (1, 0.97, 0.88), 3.0),
        'Tail': mat('Tail', (0.45, 0.0, 0.0), 0.2, 0.15, (1, 0.04, 0.02), 1.6),
        'Flap': mat('Flap', (0.08, 0.08, 0.09) if key == 'crossover' else (0.7, 0.05, 0.03), 0.0, 0.8),
        'Chrome': mat('Chrome', (0.85, 0.85, 0.88), 1.0, 0.15),
        'Plate': mat('Plate', (0.92, 0.92, 0.88), 0.0, 0.6),
        'Red': mat('Red', (0.85, 0.05, 0.03), 0.0, 0.5),
    }
    ORDER = list(M.keys()); IX = {n: i for i, n in enumerate(ORDER)}
    link = lambda o: (scene.collection.objects.link(o), o)[1]

    def apply_mods(obj):
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
        obj.modifiers.clear(); old = obj.data; obj.data = me; bpy.data.meshes.remove(old)
    def smooth(o):
        for p in o.data.polygons: p.use_smooth = True

    top, bot, width, roof = pchip(C['top']), pchip(C['bot']), pchip(C['width']), pchip(C['roof'])
    yf, yr, R = C['yf'], C['yr'], C['R']
    ZB, WB, WT = C['zb'], C['wb'], C['wt']
    cy0, cy1 = C['roof'][0][0], C['roof'][-1][0]
    ymax = max(C['roof'], key=lambda p: p[1])[0]
    zroof = max(p[1] for p in C['roof'])

    def loft(name, ys, ring, n):
        bm = bmesh.new(); rings = []
        for y in ys:
            rings.append([bm.verts.new((ring(y, i, n)[0], y, ring(y, i, n)[1])) for i in range(n)])
        for a, b in zip(rings, rings[1:]):
            for i in range(n):
                bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        o = link(bpy.data.objects.new(name, me))
        for m in ORDER: o.data.materials.append(M[m])
        return o

    # ---- lower body
    def body_ring(y, i, n):
        a = i / n * 2 * math.pi; t, b, w = top(y), bot(y), width(y)
        c, h = (t + b) / 2, (t - b) / 2
        s = math.sin(a)
        # slightly narrower at the bottom (tumble-under) for a less boxy section
        wz = w * (1 - 0.06 * max(0, -s))
        return (wz * sgnpow(math.cos(a), 0.32), c + h * sgnpow(s, 0.42))
    ys = [yf + (yr - yf) * (0.5 - 0.5 * math.cos(math.pi * t / 51)) for t in range(52)]
    body = loft('Body', ys, body_ring, 32)
    sub = body.modifiers.new('s', 'SUBSURF'); sub.levels = 1; apply_mods(body)
    for wy in C['wheels']:
        bpy.ops.mesh.primitive_cylinder_add(radius=R + 0.045, depth=3, vertices=40, location=(0, wy, R + 0.02), rotation=(0, math.pi / 2, 0))
        cut = bpy.context.active_object
        bmod = body.modifiers.new('cut', 'BOOLEAN'); bmod.operation = 'DIFFERENCE'; bmod.object = cut
        apply_mods(body); bpy.data.objects.remove(cut)
    clad = C['flares'] == 'plastic'
    for p in body.data.polygons:
        x, y, z = p.center
        low = bot(y) + (0.2 if clad else 0.07)
        p.material_index = IX['Plastic'] if z < low else IX['Paint']
    smooth(body)

    # ---- cabin
    def cab_ring(y, i, n):
        zt = max(roof(y), ZB + 0.05); a = i / n * 2 * math.pi
        sx, sz = sgnpow(math.cos(a), 0.3), sgnpow(math.sin(a), 0.3)
        z = ZB + (zt - ZB) * (sz * 0.5 + 0.5); t = (z - ZB) / max(0.01, zt - ZB)
        return ((WB + (WT - WB) * t) * sx, z)
    cab = loft('Cabin', [cy0 + (cy1 - cy0) * t / 41 for t in range(42)], cab_ring, 28)
    sub = cab.modifiers.new('s', 'SUBSURF'); sub.levels = 1; apply_mods(cab)
    for p in cab.data.polygons:
        p.material_index = IX['Roof'] if (C['roof_black'] and p.normal.z > 0.8) else IX['Paint']
    smooth(cab)

    # ---- projected decals
    dg = bpy.context.evaluated_depsgraph_get()
    TREES = [BVHTree.FromObject(body, dg), BVHTree.FromObject(cab, dg)]
    parts = []
    def hit(o, d):
        best = None
        for t in TREES:
            r = t.ray_cast(Vector(o), Vector(d).normalized())
            if r[0] is not None and (best is None or r[3] < best[3]): best = r
        return best
    def decal(name, mname, nu, nv, fn, keep=None, off=0.008, nf=None):
        grid = []
        for j in range(nv + 1):
            row = []
            for i in range(nu + 1):
                o, d = fn(i / nu, j / nv); r = hit(o, d)
                row.append(None if (r is None or (nf and not nf(r[1]))) else r[0] + r[1] * off)
            grid.append(row)
        bm = bmesh.new(); vid = {}
        def V(i, j):
            if (i, j) not in vid: vid[(i, j)] = bm.verts.new(grid[j][i])
            return vid[(i, j)]
        for j in range(nv):
            for i in range(nu):
                c = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
                if any(p is None for p in c) or max((c[0] - c[2]).length, (c[1] - c[3]).length) > 0.4: continue
                if keep and not keep((i + .5) / nu, (j + .5) / nv): continue
                try: bm.faces.new([V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)])
                except ValueError: pass
        if not bm.faces: bm.free(); return None
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        o = link(bpy.data.objects.new(name, me)); o.data.materials.append(M[mname]); smooth(o)
        for p in o.data.polygons:
            c = p.center
            if p.normal.dot(Vector((c.x, c.y * 0.5, c.z - 0.8))) < 0: p.flip()
        parts.append(o); return o

    def y_front(z):
        lo, hi = cy0, ymax
        for _ in range(30):
            mid = (lo + hi) / 2
            if roof(mid) < z: lo = mid
            else: hi = mid
        return lo
    def y_rear(z):
        lo, hi = ymax, cy1
        for _ in range(30):
            mid = (lo + hi) / 2
            if roof(mid) > z: lo = mid
            else: hi = mid
        return lo

    # side glass with black surrounds, split at pillars
    zlo = max(top(y) for y in (cy0 + 0.3, (cy0 + cy1) / 2, cy1 - 0.3)) + 0.035
    zhi = zroof - 0.075
    for s in (-1, 1):
        for grow, mname, off in ((0.035, 'Trim', 0.005), (0.0, 'Glass', 0.01)):
            segs = []; ystart = None
            cuts = [(-9, None)] + [(a, b) for a, b in C['pillars']] + [(None, 9)]
            for (a0, a1), (b0, b1) in zip(cuts, cuts[1:]):
                segs.append((a1, b0))
            for a, b in segs:
                def fn(u, v, a=a, b=b, s=s, g=grow):
                    z = lerp(zlo - g, zhi + g, v)
                    y0 = (y_front(z) + 0.1 - g) if a is None else a + (0 if g else 0.0)
                    y1 = (y_rear(z) - 0.1 + g) if b is None else b
                    if g and a is not None: y0 = a - g * 0.2
                    if g and b is not None: y1 = b + g * 0.2
                    return ((s * 3, lerp(y0, y1, u), z), (-s, 0, 0))
                decal('Side' + mname, mname, 16, 9, fn, off=off, nf=lambda n: abs(n.x) > 0.45)
    # windscreen and rear window (+ trim)
    zw0 = roof(cy0 + 0.06) + 0.03
    zr0 = roof(cy1 - 0.06) + 0.05
    for g, mname, off in ((0.04, 'Trim', 0.005), (0.0, 'Glass', 0.01)):
        decal('Windscreen', mname, 18, 10, lambda u, v, g=g: ((lerp(-1, 1, u) * (lerp(WT - 0.04, WT - 0.15, v) + g), -6, lerp(zw0 - g, zroof - 0.06 + g * .5, v)), (0, 1, 0)),
              off=off, nf=lambda n: n.y < -0.25)
        decal('RearWin', mname, 16, 8, lambda u, v, g=g: ((lerp(-1, 1, u) * (lerp(WT - 0.06, WT - 0.16, v) + g), 6, lerp(zr0 - g, zroof - 0.08 + g * .5, v)), (0, -1, 0)),
              off=off, nf=lambda n: n.y > 0.25)

    # door shut lines and handles
    for s in (-1, 1):
        for yd in C['doors']:
            zt = min(top(yd), roof(yd) if cy0 < yd < cy1 else 9) - 0.02
            decal('DoorLine', 'Trim', 1, 10, lambda u, v, yd=yd, s=s, zt=zt: ((s * 3, yd + (u - .5) * 0.012, lerp(bot(yd) + 0.12, zt, v)), (-s, 0, 0)), off=0.004)
        for a, b in zip(C['doors'], C['doors'][1:]):
            yh = b - 0.2; zh = top(yh) - 0.1
            decal('Handle', 'Trim', 4, 2, lambda u, v, yh=yh, s=s, zh=zh: ((s * 3, yh + (u - .5) * 0.16, zh + (v - .5) * 0.04), (-s, 0, 0)), off=0.012)

    # headlights, grille, intake, fog and tail lights: the decal grid is mapped onto each outline (clean edges)
    def quadmap(q, u, v):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = q
        bx, by = lerp(x0, x1, u), lerp(y0, y1, u); tx, ty = lerp(x3, x2, u), lerp(y3, y2, u)
        return lerp(bx, tx, v), lerp(by, ty, v)
    def ell(u, v, cx=.5, cy=.5, rx=.5, ry=.5):
        a = u * 2 * math.pi; return cx + rx * v * math.cos(a), cy + ry * v * math.sin(a)
    FRONT = lambda n: n.y < -0.12
    REAR = lambda n: n.y > 0.12
    def front_ray(x, z, s, tilt=0.45):
        return ((x - s * tilt * (6 + yf), -6, z), (s * tilt, 1, 0))
    H = C['head']
    for s in (-1, 1):
        def hp(pu, pv, s=s, H=H):
            return front_ray(s * lerp(H['x'][0], H['x'][1], pu), lerp(H['z'][0], H['z'][1], pv), s)
        decal('HeadHousing', 'Lamp', 20, 10, lambda u, v: hp(*quadmap(H['shape'], u, v)), off=0.009, nf=FRONT)
        decal('HeadLamp', 'Light', 20, 6, lambda u, v: hp(*quadmap(H['shape'], *ell(u, v, .62, .48, .26, .32))), off=0.013, nf=FRONT)
        decal('DRL', 'Light', 24, 2, lambda u, v: hp(*quadmap(H['shape'], lerp(.06, .94, u), lerp(.8, .93, v))), off=0.014, nf=FRONT)
        if 'head2' in C:
            H2 = C['head2']
            def hp2(pu, pv, s=s):
                return front_ray(s * lerp(H2['x'][0], H2['x'][1], pu), lerp(H2['z'][0], H2['z'][1], pv), s)
            decal('Head2', 'Lamp', 12, 8, lambda u, v: hp2(u, v), off=0.009, nf=FRONT)
            decal('Head2L', 'Light', 20, 6, lambda u, v: hp2(*ell(u, v, .5, .5, .42, .4)), off=0.013, nf=FRONT)
        zf = bot(yf + .2)
        decal('Fog', 'Light', 16, 4, lambda u, v, s=s: front_ray(s * lerp(0.52, 0.66, ell(u, v)[0]), lerp(zf + 0.06, zf + 0.16, ell(u, v)[1]), s, 0.2),
              off=0.012, nf=FRONT)
    G = C['grille']
    decal('Grille', 'Trim', 24, 8, lambda u, v: (lambda p: ((lerp(-G['x'], G['x'], p[0]), -6, lerp(G['z'][0], G['z'][1], p[1])), (0, 1, 0)))(quadmap(G['shape'], u, v)),
          off=0.008, nf=FRONT)
    decal('GrilleBar', 'Chrome', 20, 1, lambda u, v: ((lerp(-G['x'] * .8, G['x'] * .8, u), -6, lerp(G['z'][0], G['z'][1], .55) + (v - .5) * 0.014), (0, 1, 0)), off=0.011, nf=FRONT)
    zb0 = bot(yf + 0.2)
    decal('Intake', 'Trim', 24, 6, lambda u, v: (lambda p: ((lerp(-0.72, 0.72, p[0]), -6, lerp(zb0 + 0.02, zb0 + 0.2, p[1])), (0, 1, 0)))(quadmap([(.07, 0), (.93, 0), (1, 1), (0, 1)], u, v)),
          off=0.007, nf=FRONT)
    T = C['tail']
    for s in (-1, 1):
        def tp(pu, pv, s=s):
            return ((s * lerp(T['x'][0], T['x'][1], pu) - s * 0.45 * (6 - yr), 6, lerp(T['z'][0], T['z'][1], pv)), (s * 0.45, -1, 0))
        decal('Tail', 'Tail', 20, 6, lambda u, v: tp(*quadmap(T['shape'], u, v)), off=0.011, nf=REAR)
    zp = (top(yr - .1) + bot(yr - .1)) / 2 - 0.04
    decal('Plate', 'Plate', 8, 3, lambda u, v: ((lerp(-0.26, 0.26, u), 6, lerp(zp - 0.06, zp + 0.06, v)), (0, -1, 0)), off=0.01, nf=lambda n: n.y > 0.12)

    # stripes
    if C['stripes'] == 'twin':
        for sx in (-1, 1):
            for y0, y1 in ((yf, y_front(zw0 + 0.01) - 0.05), (y_front(zroof - 0.07) + 0.08, y_rear(zroof - 0.09) - 0.05)):
                decal('TopStripe', 'Stripe', 2, 40, lambda u, v, sx=sx, y0=y0, y1=y1: ((sx * lerp(0.07, 0.2, u), lerp(y0, y1, v), 6), (0, 0, -1)), off=0.009)
    for s in (-1, 1):
        decal('SideStripe', 'Stripe', 70, 3, lambda u, v, s=s: ((s * 3, lerp(yf + 0.25, yr - 0.25, u), bot(0) + 0.2 + 0.18 * u + 0.07 * v), (-s, 0, 0)),
              off=0.009, nf=lambda n: abs(n.x) > 0.5)
    if C['hood_vents']:
        for sx in (-1, 1):
            decal('Vent', 'Trim', 6, 6, lambda u, v, sx=sx: ((sx * lerp(0.3, 0.6, u), lerp(-1.6, -1.3, v), 6), (0, 0, -1)), off=0.008,
                  keep=lambda u, v: int(v * 6) % 2 == 0)

    # mud
    rng = random.Random(hash(key) & 0xffff)
    ph = [rng.random() * 6.28 for _ in range(8)]
    def noise(a, b):
        return (math.sin(a * 13 + ph[0]) * math.sin(b * 11 + ph[1]) + 0.55 * math.sin(a * 29 + b * 17 + ph[2]) + 0.3 * math.sin(a * 47 - b * 37 + ph[3]))
    for wy in C['wheels']:
        for s in (-1, 1):
            def keep(u, v, wy=wy, s=s):
                y, z = lerp(wy - 0.8, wy + 0.85, u), lerp(bot(wy) + 0.04, bot(wy) + 0.5, v)
                return noise(y * s, z) + 1.25 - v * 2.6 + (0.4 if y > wy else 0) > 0.9
            decal('Mud', 'Mud', 70, 22, lambda u, v, wy=wy, s=s: ((s * 3, lerp(wy - 0.8, wy + 0.85, u), lerp(bot(wy) + 0.04, bot(wy) + 0.5, v)), (-s, 0, 0)), keep=keep, off=0.013)
    decal('MudRear', 'Mud', 60, 14, lambda u, v: ((lerp(-0.9, 0.9, u), 6, lerp(bot(yr) + .02, bot(yr) + 0.36, v)), (0, -1, 0)),
          keep=lambda u, v: noise(u * 2, v) + 1.3 - v * 2.4 > 0.9, off=0.016)

    # ---- solid parts
    def box(name, size, loc, mname, rot=(0, 0, 0), bevel=0.0):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
        o = bpy.context.active_object; o.name = name; o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        if bevel:
            b = o.modifiers.new('bv', 'BEVEL'); b.width = bevel; b.segments = 2; apply_mods(o)
        o.data.materials.append(M[mname]); parts.append(o); return o
    def cyl(name, r, d, loc, rot, mname, verts=20):
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=verts, location=loc, rotation=rot)
        o = bpy.context.active_object; o.name = name; o.data.materials.append(M[mname]); parts.append(o); return o
    def surf_x(y, z, s):
        r = hit((s * 3, y, z), (-s, 0, 0)); return abs(r[0].x) if r else width(y)

    for wy in C['wheels']:
        # arch liner (hides the inside of the body shell)
        bpy.ops.mesh.primitive_cylinder_add(radius=R + 0.04, depth=1.75, vertices=32, end_fill_type='NOTHING', location=(0, wy, R + 0.02), rotation=(0, math.pi / 2, 0))
        o = bpy.context.active_object; bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if (o.matrix_world @ v.co).z < R - 0.05], context='VERTS')
        bm.to_mesh(o.data); bm.free(); bpy.ops.object.transform_apply(rotation=True)
        o.data.materials.append(M['Plastic']); parts.append(o)
        for s in (-1, 1):
            # fender flares
            fr = 0.075 if C['flares'] == 'plastic' else 0.05
            bpy.ops.mesh.primitive_torus_add(major_radius=R + 0.065, minor_radius=fr, major_segments=40, minor_segments=8,
                                             location=(s * (surf_x(wy, R + .3, s) - 0.02), wy, R + 0.02), rotation=(0, math.pi / 2, 0))
            o = bpy.context.active_object; bm = bmesh.new(); bm.from_mesh(o.data)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if (o.matrix_world @ v.co).z < R - 0.04], context='VERTS')
            bm.to_mesh(o.data); bm.free(); o.scale = (1.0, 1.0, 1.0 if C['flares'] == 'plastic' else 1.25)
            bpy.ops.object.transform_apply(rotation=True, scale=True)
            o.data.materials.append(M['Plastic' if C['flares'] == 'plastic' else 'Paint']); smooth(o); parts.append(o)
            # brake caliper (on the body so it does not spin)
            box('Caliper', (0.07, 0.12, 0.16), (s * (C['track'] - 0.1), wy + (0.16 if wy < 0 else -0.16), R + 0.1), 'Caliper', bevel=0.02)
            # mudflap
            box('Flap', (0.26, 0.02, 0.28), (s * (C['track'] - 0.02), wy + R + 0.12, bot(wy + R + .12) - 0.08), 'Flap')

    for s in (-1, 1):
        ym = cy0 + 0.22; zm = ZB + 0.12
        xm = surf_x(ym, zm - 0.06, s)
        box('Mirror', (0.12, 0.2, 0.12), (s * (xm + 0.1), ym, zm), 'Paint', bevel=0.035)
        box('MirrorArm', (0.1, 0.05, 0.035), (s * (xm + 0.02), ym, zm - 0.04), 'Trim')
        # side skirt
        box('Skirt', (0.06, (C['wheels'][1] - C['wheels'][0]) - 2 * R - 0.25, 0.08),
            (s * (surf_x(0, bot(0) + 0.1, s) - 0.01), sum(C['wheels']) / 2, bot(0) + 0.05), 'Plastic', bevel=0.02)
        # tow hooks
        bpy.ops.mesh.primitive_torus_add(major_radius=0.05, minor_radius=0.012, location=(s * 0.5, yf - 0.01 + (0.06 if s > 0 else 0), bot(yf + .1) + 0.05), rotation=(0, math.pi / 2, 0))
        o = bpy.context.active_object; o.data.materials.append(M['Red']); parts.append(o)
    # wipers
    for x in (-0.35, 0.25):
        box('Wiper', (0.55, 0.02, 0.015), (x, y_front(zw0 + 0.02) - 0.02, zw0 + 0.02), 'Trim', rot=(math.radians(-30), 0, math.radians(-8)))
    box('Splitter', (1.75, 0.3, 0.035), (0, yf + 0.18, bot(yf + .2) - 0.03), 'Plastic')
    box('Diffuser', (1.4, 0.3, 0.06), (0, yr - 0.12, bot(yr - .1) - 0.0), 'Plastic')
    cyl('Exhaust', 0.055, 0.3, (0.55, yr - 0.05, bot(yr) + 0.0), (math.pi / 2, 0, 0), 'Chrome', 14)
    cyl('Antenna', 0.007, 0.4, (0.3, y_rear(zroof - 0.02) - 0.15, zroof + 0.18), (0, 0, 0), 'Trim', 6)
    if C['pod']:
        yp = yf + 0.22; zp = top(yp) + 0.08
        box('Pod', (1.05, 0.1, 0.07), (0, yp + 0.04, zp - 0.02), 'Trim', bevel=0.015)
        for x in (-0.38, -0.13, 0.13, 0.38):
            cyl('PodRing', 0.1, 0.11, (x, yp - 0.03, zp + 0.04), (math.pi / 2, 0, 0), 'Trim', 18)
            cyl('PodLamp', 0.082, 0.115, (x, yp - 0.035, zp + 0.04), (math.pi / 2, 0, 0), 'Light', 18)
    if C['scoop']:
        ys_ = y_front(zroof - 0.02) + 0.3
        box('Scoop', (0.38, 0.4, 0.07), (0, ys_ + 0.2, roof(ys_ + .2) + 0.02), 'Paint', bevel=0.03)
        box('ScoopMouth', (0.28, 0.04, 0.045), (0, ys_ + 0.005, roof(ys_) + 0.035), 'Trim')
    if C['rails']:
        for s in (-1, 1):
            y0, y1 = y_front(zroof - 0.02) + 0.1, y_rear(zroof - 0.04) - 0.1
            box('Rail', (0.04, y1 - y0, 0.035), (s * (WT - 0.12), (y0 + y1) / 2, zroof + 0.06), 'Chrome', bevel=0.01)
            for yy in (y0 + 0.05, y1 - 0.05):
                box('RailFoot', (0.05, 0.08, 0.07), (s * (WT - 0.12), yy, roof(yy) + 0.02), 'Trim')
    yw = y_rear(zroof - 0.05)
    if C['wing'] == 'big':
        zw = roof(yw) + 0.12
        box('Wing', (1.74, 0.36, 0.045), (0, yw + 0.1, zw), 'Paint', rot=(math.radians(-7), 0, 0), bevel=0.012)
        for s in (-1, 1):
            box('Endplate', (0.035, 0.4, 0.13), (s * 0.88, yw + 0.1, zw - 0.01), 'Trim', bevel=0.008)
            box('Strut', (0.04, 0.1, 0.14), (s * 0.42, yw + 0.06, zw - 0.08), 'Trim')
    else:
        box('Lip', (WT * 2 - 0.02, 0.3, 0.035), (0, yw + 0.12, roof(yw) - 0.01), 'Roof' if C['roof_black'] else 'Paint', rot=(math.radians(8), 0, 0), bevel=0.012)

    # join body + parts
    bpy.ops.object.select_all(action='DESELECT')
    for o in [cab] + parts: o.select_set(True)
    body.select_set(True); bpy.context.view_layer.objects.active = body
    bpy.ops.object.join(); body.name = 'Body'

    # ---- one wheel mesh shared by four objects
    objs = []
    bpy.ops.mesh.primitive_cylinder_add(radius=R, depth=C['tyre_w'], vertices=40, rotation=(0, math.pi / 2, 0))
    t = bpy.context.active_object; b = t.modifiers.new('bv', 'BEVEL'); b.width = 0.06; b.segments = 3; apply_mods(t)
    t.data.materials.append(M['Tire']); smooth(t); objs.append(t)
    rr = R * 0.66; dw = C['tyre_w'] + 0.01
    cyl('Barrel', rr, dw - 0.02, (0, 0, 0), (0, math.pi / 2, 0), 'Trim', 28); objs.append(parts.pop())
    cyl('Disc', rr * 0.82, 0.05, (0, 0, 0), (0, math.pi / 2, 0), 'Brake', 28); objs.append(parts.pop())
    for side in (-1, 1):
        bpy.ops.mesh.primitive_torus_add(major_radius=rr - 0.012, minor_radius=0.016, major_segments=32, minor_segments=6, location=(side * dw / 2, 0, 0), rotation=(0, math.pi / 2, 0))
        o = bpy.context.active_object; o.data.materials.append(M['Rim']); smooth(o); objs.append(o)
        cyl('Hub', 0.065, 0.03, (side * (dw / 2 + 0.005), 0, 0), (0, math.pi / 2, 0), 'Rim', 14); objs.append(parts.pop())
        n = C['rim_spokes']
        for k in range(n):
            a = k / n * 2 * math.pi
            for da in ((-0.07, 0.07) if C['rim_style'] == 'split' else (0,)):
                aa = a + da
                w = 0.05 if C['rim_style'] == 'dish' else 0.03
                ln = rr - 0.05 if C['rim_style'] != 'dish' else rr * 0.45
                cz = math.cos(aa) * (0.065 + ln / 2); cy = math.sin(aa) * (0.065 + ln / 2)
                box('Spoke', (0.025, w, ln), (side * (dw / 2 - 0.005), cy, cz), 'Rim', rot=(-aa, 0, 0)); objs.append(parts.pop())
        if C['rim_style'] == 'dish':
            # gravel dish rim: solid face with round holes look (dark discs over a white face)
            cyl('Face', rr - 0.01, 0.012, (side * (dw / 2 - 0.012), 0, 0), (0, math.pi / 2, 0), 'Rim', 28); objs.append(parts.pop())
            for k in range(n):
                a = (k + 0.5) / n * 2 * math.pi
                cyl('Hole', 0.045, 0.014, (side * (dw / 2 - 0.004), math.sin(a) * rr * 0.6, math.cos(a) * rr * 0.6), (0, math.pi / 2, 0), 'Trim', 12); objs.append(parts.pop())
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = t; bpy.ops.object.join()
    bpy.ops.object.select_all(action='DESELECT'); t.select_set(True); bpy.context.view_layer.objects.active = t
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    wheel_mesh = t.data; t.name = 'WheelFL'; tr = C['track']
    t.location = (tr, C['wheels'][0], R)
    for name, loc in (('WheelFR', (-tr, C['wheels'][0], R)), ('WheelRL', (tr, C['wheels'][1], R)), ('WheelRR', (-tr, C['wheels'][1], R))):
        o = bpy.data.objects.new(name, wheel_mesh); o.location = loc; scene.collection.objects.link(o)

    door = hit((3, (C['doors'][0] + C['doors'][1]) / 2, (bot(0) + top(0)) / 2), (-1, 0, 0))
    tris = sum(len(p.vertices) - 2 for p in body.data.polygons) + sum(len(p.vertices) - 2 for p in wheel_mesh.polygons)
    print(f'[{key}] tris body+1 wheel {tris}  door_x {door[0].x if door else None:.3f} door_y {(C["doors"][0] + C["doors"][1]) / 2:.2f} door_z {(bot(0) + top(0)) / 2:.2f}')

    glb = os.path.join(OUTDIR, f'car_{key}.glb')
    try:
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_yup=True, export_apply=True,
                                  export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                                  export_draco_position_quantization=14, export_draco_normal_quantization=10, export_texcoords=False)
    except Exception as e:
        print('draco failed, exporting plain', e)
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_yup=True, export_apply=True, export_texcoords=False)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTDIR, f'car_{key}.blend'))
    print('EXPORTED', glb, os.path.getsize(glb))
    return C

for key, C in CARS.items():
    if ONLY and key not in ONLY[0][5:].split(','): continue
    build(key, C)
