"""Render a 480x270 JPEG thumbnail (models/thumb_<car>.jpg) and, with full=1, two large previews per car.
Usage: python3 blender/render_cars.py [keys=hatch,coupe] [s=24] [full=1]"""
import bpy, math, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); MODELS = os.path.join(HERE, '..', 'models')
arg = lambda k, d: next((a.split('=', 1)[1] for a in sys.argv if a.startswith(k + '=')), d)
keys = arg('keys', 'hatch,supermini,coupe,crossover').split(','); samples = int(arg('s', '24')); full = arg('full', '0') == '1'
for key in keys:
    bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, f'car_{key}.blend'))
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=60); g = bpy.context.active_object
    gm = bpy.data.materials.new('G'); gm.use_nodes = True; b = gm.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.16, 0.11, 0.06, 1); b.inputs['Roughness'].default_value = .9; g.data.materials.append(gm)
    bpy.ops.object.light_add(type='SUN', rotation=(math.radians(48), 0, math.radians(-35)))
    bpy.context.active_object.data.energy = 4.2; bpy.context.active_object.data.angle = 0.15
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True; bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.6, 0.72, 0.85, 1); bg.inputs[1].default_value = 0.9
    sc.render.engine = 'CYCLES'; sc.cycles.samples = samples; sc.cycles.device = 'CPU'; sc.view_settings.view_transform = 'AgX'
    d = bpy.data.objects.new('t', None); sc.collection.objects.link(d); d.location = (0, 0, 0.65)
    shots = [((-4.6, -4.4, 1.55), (480, 270), os.path.join(MODELS, f'thumb_{key}.jpg'), 'JPEG')]
    if full:
        shots += [((-5.4, -5.2, 1.9), (960, 560), os.path.join(HERE, f'prev_{key}_0.png'), 'PNG'),
                  ((5.6, 4.6, 2.2), (960, 560), os.path.join(HERE, f'prev_{key}_1.png'), 'PNG')]
    for loc, res, path, fmt in shots:
        bpy.ops.object.camera_add(location=loc); cam = bpy.context.active_object; sc.camera = cam; cam.data.lens = 50
        cam.constraints.new('TRACK_TO').target = d
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.image_settings.file_format = fmt
        if fmt == 'JPEG': sc.render.image_settings.quality = 78
        sc.render.filepath = path; bpy.ops.render.render(write_still=True)
