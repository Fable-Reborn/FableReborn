"""The Moonlight Lantern night, built and rendered in Blender (Cycles). Run by scripts/render_moonlantern.py:

    blender -b -P scripts/moonlantern_scene_blender.py -- <out.png> [percent] [samples]

A midnight lake under a full moon. Two old sakura stand close on the bank, in full blossom,
their boughs framing the moon; paper lanterns hang in them and drift on the water; a stone
lantern burns at the shore; the lake holds the moon's light and a glow of its own; mountains
stand in the mist beyond. cogs/profile/themes.py lays the player's card over the picture: their
portrait goes in the moon, their name on the dark air under it, and their records on glass over
the meadow. So the moon is placed to the pixel, and nothing blooms where the card writes
(written_on()).

Nothing here is painted flat. Paper is translucent and lit by a flame or a lamp inside it, wood,
bark and stone are textured and bumped, the water is a real reflecting surface with waves, the
ground is lit by the moon and by the lanterns, and there is mist in the air. The picture is
tone-mapped with AgX, so strengths below are light, not colours.

The camera is level and looks down +Y with its lens shifted, so the horizon sits on row HORIZON
and a point d metres away lands on the picture by plain similar triangles (see at()). MOON and
the rows the card writes on are the ones in themes.py (_MOON_*); change them in both places.
"""
import math
import random
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector, noise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "//moonlantern_render.png"
PERCENT = int(argv[1]) if len(argv) > 1 else 100
SAMPLES = int(argv[2]) if len(argv) > 2 else 600

W = H = 2000
FOCAL_MM, SENSOR_MM = 28.0, 36.0
F = W * FOCAL_MM / SENSOR_MM            # focal length in pixels
HORIZON = 1040                          # the row the horizon sits on
EYE = 1.2                               # the camera's height above the grass, metres
SHORE_ROW = 1215                        # where the bank meets the lake, on the picture
MOON = (1000, 400, 300, 9000.0)         # centre x, centre y, radius in pixels; distance in metres

rng = random.Random(598004694)


def at(u: float, v: float, d: float) -> Vector:
    """The point d metres in front of the camera that lands on pixel (u, v)."""
    return Vector(((u - W / 2) * d / F, d, EYE + (HORIZON - v) * d / F))


def pixel(point: Vector) -> tuple[float, float]:
    """Where a point lands on the picture."""
    return W / 2 + point.x * F / point.y, HORIZON - (point.z - EYE) * F / point.y


def shore(x: float) -> float:
    """How far away the bank ends and the lake begins, at x metres across."""
    return EYE * F / (SHORE_ROW - HORIZON) + 0.45 * math.sin(x * 0.55 + 0.6) + 0.22 * math.sin(x * 1.7 + 2.0)


def written_on(u: float, v: float, margin: float = 0.0) -> bool:
    """Whether a pixel is where the card writes: the moon with the portrait in it, and the band
    of dark air under it that carries the name, the level and the power."""
    mu, mv, radius, _far = MOON
    if (u - mu) ** 2 + (v - mv) ** 2 < (radius + 44 + margin) ** 2:
        return True
    return 104 - margin < u < W - 104 + margin and 726 - margin < v < 1004 + margin


# ---- node helpers --------------------------------------------------------------------------------

def material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    return mat, tree


def node(tree, kind, **values):
    n = tree.nodes.new(kind)
    for key, value in values.items():
        if key in n.inputs:
            n.inputs[key].default_value = value
        else:
            setattr(n, key, value)
    return n


def math_node(tree, operation, a, b=None, clamp=False):
    n = tree.nodes.new("ShaderNodeMath")
    n.operation = operation
    n.use_clamp = clamp
    for index, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            n.inputs[index].default_value = value
        else:
            tree.links.new(value, n.inputs[index])
    return n.outputs[0]


def ramp(tree, factor, stops):
    n = tree.nodes.new("ShaderNodeValToRGB")
    elements = n.color_ramp.elements
    while len(elements) < len(stops):
        elements.new(0.5)
    for element, (position, colour) in zip(elements, stops):
        element.position = position
        element.color = (*colour, 1.0)
    tree.links.new(factor, n.inputs["Fac"])
    return n.outputs["Color"]


def finish(tree, surface):
    out = node(tree, "ShaderNodeOutputMaterial")
    tree.links.new(surface, out.inputs["Surface"])


def bumped(tree, height, strength, distance=0.02, onto=None):
    bump = node(tree, "ShaderNodeBump", Strength=strength, Distance=distance)
    tree.links.new(height, bump.inputs["Height"])
    if onto is not None:
        tree.links.new(onto, bump.inputs["Normal"])
    return bump.outputs["Normal"]


def thin(tree, colour, normal=None, through=0.6):
    """Something thin that light passes through (paper, petals, blades of grass): part of the
    light that falls on one side shows on the other."""
    solid = node(tree, "ShaderNodeBsdfDiffuse")
    passed = node(tree, "ShaderNodeBsdfTranslucent")
    for shader in (solid, passed):
        tree.links.new(colour, shader.inputs["Color"])
        if normal is not None:
            tree.links.new(normal, shader.inputs["Normal"])
    both = node(tree, "ShaderNodeMixShader")
    both.inputs[0].default_value = through
    tree.links.new(solid.outputs[0], both.inputs[1])
    tree.links.new(passed.outputs[0], both.inputs[2])
    return both.outputs[0]


# ---- materials -----------------------------------------------------------------------------------

def lantern_paper(name, warm, cool, fibre=38.0):
    """Paper lit from inside. It has no light of its own: what shows is the flame's light coming
    through it, so it is brightest near the flame and deepens toward the crown. Fibres and creases
    catch the light; eight glued seams show as slightly thicker paper."""
    mat, tree = material(name)
    coords = node(tree, "ShaderNodeTexCoord")
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Object"], split.inputs[0])
    fibres = node(tree, "ShaderNodeTexNoise", Scale=fibre, Detail=6.0, Roughness=0.7)
    creases = node(tree, "ShaderNodeTexNoise", Scale=4.5, Detail=3.0)
    for tex in (fibres, creases):
        tree.links.new(coords.outputs["Object"], tex.inputs["Vector"])
    angle = math_node(tree, "ARCTAN2", split.outputs["X"], split.outputs["Y"])
    seam = math_node(tree, "ABSOLUTE", math_node(tree, "SUBTRACT", math_node(tree, "FRACT", math_node(tree, "MULTIPLY", angle, 8 / math.tau)), 0.5))
    seam = math_node(tree, "GREATER_THAN", seam, 0.487)
    info = node(tree, "ShaderNodeObjectInfo")
    blend = math_node(tree, "ADD", math_node(tree, "MULTIPLY", fibres.outputs["Fac"], 0.5), math_node(tree, "MULTIPLY", info.outputs["Random"], 0.5), clamp=True)
    colour = ramp(tree, blend, ((0.2, warm), (0.85, cool)))
    darker = node(tree, "ShaderNodeMixRGB", blend_type="MULTIPLY")
    tree.links.new(math_node(tree, "MULTIPLY", seam, 0.45), darker.inputs["Fac"])
    tree.links.new(colour, darker.inputs["Color1"])
    darker.inputs["Color2"].default_value = (0.55, 0.30, 0.16, 1.0)
    relief = math_node(tree, "ADD", math_node(tree, "MULTIPLY", fibres.outputs["Fac"], 0.35), creases.outputs["Fac"])
    finish(tree, thin(tree, darker.outputs["Color"], bumped(tree, relief, 0.5, 0.012), through=0.72))
    return mat


def far_paper():
    """The lanterns too far off to light one by one: the same paper, glowing as it would."""
    mat, tree = material("FarPaper")
    coords = node(tree, "ShaderNodeTexCoord")
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Object"], split.inputs[0])
    height = math_node(tree, "ADD", math_node(tree, "MULTIPLY", split.outputs["Z"], 1 / 0.97), 0.485, clamp=True)
    colour = ramp(tree, height, ((0.0, (1.0, 0.70, 0.34)), (0.4, (1.0, 0.42, 0.14)), (1.0, (0.62, 0.13, 0.04))))
    info = node(tree, "ShaderNodeObjectInfo")
    facing = node(tree, "ShaderNodeLayerWeight", Blend=0.5)
    strength = math_node(tree, "ADD", math_node(tree, "MULTIPLY", math_node(tree, "POWER", math_node(tree, "SUBTRACT", 1.0, height), 1.6), 2.0), 0.5)
    strength = math_node(tree, "MULTIPLY", strength, math_node(tree, "SUBTRACT", 1.0, math_node(tree, "MULTIPLY", math_node(tree, "POWER", facing.outputs["Facing"], 1.8), 0.55)))
    strength = math_node(tree, "MULTIPLY", strength, math_node(tree, "ADD", math_node(tree, "MULTIPLY", info.outputs["Random"], 0.7), 0.65))
    emit = node(tree, "ShaderNodeEmission")
    tree.links.new(colour, emit.inputs["Color"])
    tree.links.new(strength, emit.inputs["Strength"])
    finish(tree, emit.outputs[0])
    return mat


def emission(name, colour, strength):
    mat, tree = material(name)
    emit = node(tree, "ShaderNodeEmission", Strength=strength)
    emit.inputs["Color"].default_value = (*colour, 1.0)
    finish(tree, emit.outputs[0])
    return mat


def timber(name, dark, light, grain=34.0, rough=0.5):
    """Wood: streaked along its grain, a little worn, bumped so the light rakes across it."""
    mat, tree = material(name)
    coords = node(tree, "ShaderNodeTexCoord")
    stretch = node(tree, "ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (1.0, 1.0, 0.06)
    tree.links.new(coords.outputs["Object"], stretch.inputs["Vector"])
    streak = node(tree, "ShaderNodeTexNoise", Scale=grain, Detail=6.0, Roughness=0.65)
    tree.links.new(stretch.outputs[0], streak.inputs["Vector"])
    worn = node(tree, "ShaderNodeTexNoise", Scale=5.0, Detail=4.0)
    tree.links.new(coords.outputs["Object"], worn.inputs["Vector"])
    colour = ramp(tree, streak.outputs["Fac"], ((0.3, dark), (0.72, light)))
    shader = node(tree, "ShaderNodeBsdfPrincipled")
    tree.links.new(colour, shader.inputs["Base Color"])
    tree.links.new(math_node(tree, "ADD", math_node(tree, "MULTIPLY", worn.outputs["Fac"], 0.35), rough - 0.15), shader.inputs["Roughness"])
    tree.links.new(bumped(tree, streak.outputs["Fac"], 0.55, 0.004), shader.inputs["Normal"])
    finish(tree, shader.outputs[0])
    return mat


def tile():
    """The lantern roofs: dark glazed tile in courses, catching the moon."""
    mat, tree = material("Tile")
    coords = node(tree, "ShaderNodeTexCoord")
    courses = node(tree, "ShaderNodeTexWave", Scale=70.0, Distortion=0.4)
    courses.bands_direction = "Z"
    tree.links.new(coords.outputs["Object"], courses.inputs["Vector"])
    speck = node(tree, "ShaderNodeTexNoise", Scale=90.0, Detail=3.0)
    tree.links.new(coords.outputs["Object"], speck.inputs["Vector"])
    colour = ramp(tree, speck.outputs["Fac"], ((0.3, (0.012, 0.014, 0.022)), (0.8, (0.05, 0.055, 0.075))))
    shader = node(tree, "ShaderNodeBsdfPrincipled", Roughness=0.42)
    tree.links.new(colour, shader.inputs["Base Color"])
    tree.links.new(bumped(tree, courses.outputs["Fac"], 0.3, 0.004), shader.inputs["Normal"])
    finish(tree, shader.outputs[0])
    return mat


def lake():
    """Water: dark and clear, reflecting by Fresnel like the real thing, so the far lake mirrors
    the sky and the near water shows its depth. Waves at three scales break every reflection into
    glitter and draw the moon into a path."""
    mat, tree = material("Lake")
    place = node(tree, "ShaderNodeNewGeometry")
    stretch = node(tree, "ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (0.3, 1.0, 1.0)
    tree.links.new(place.outputs["Position"], stretch.inputs["Vector"])
    normal = None
    for scale, strength, distance in ((0.35, 0.25, 0.4), (2.6, 0.45, 0.08), (11.0, 0.5, 0.02)):
        wave = node(tree, "ShaderNodeTexNoise", Scale=scale, Detail=4.0, Roughness=0.62)
        tree.links.new(stretch.outputs[0], wave.inputs["Vector"])
        normal = bumped(tree, wave.outputs["Fac"], strength, distance, normal)
    shader = node(tree, "ShaderNodeBsdfPrincipled", Roughness=0.02, IOR=1.333)
    shader.inputs["Base Color"].default_value = (0.0, 0.010, 0.030, 1.0)
    tree.links.new(normal, shader.inputs["Normal"])
    # the lake holds a light of its own: a cyan glow that gathers along the wave crests
    shimmer = node(tree, "ShaderNodeTexNoise", Scale=3.4, Detail=5.0, Roughness=0.7)
    tree.links.new(stretch.outputs[0], shimmer.inputs["Vector"])
    shader.inputs["Emission Color"].default_value = (0.0, 0.34, 1.0, 1.0)
    tree.links.new(math_node(tree, "ADD", math_node(tree, "MULTIPLY", math_node(tree, "POWER", shimmer.outputs["Fac"], 4.0), 1.3), 0.035),
                   shader.inputs["Emission Strength"])
    finish(tree, shader.outputs[0])
    return mat


def rock():
    """The mountains: dark rock, paler and smoother where snow lies on the high, gentle ground."""
    mat, tree = material("Rock")
    place = node(tree, "ShaderNodeNewGeometry")
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(place.outputs["Position"], split.inputs[0])
    slope = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(place.outputs["Normal"], slope.inputs[0])
    strata = node(tree, "ShaderNodeTexNoise", Scale=0.012, Detail=8.0, Roughness=0.7)
    tree.links.new(place.outputs["Position"], strata.inputs["Vector"])
    snow = math_node(tree, "MULTIPLY", math_node(tree, "SUBTRACT", math_node(tree, "MULTIPLY", split.outputs["Z"], 1 / 260.0), 0.42),
                     math_node(tree, "MULTIPLY", slope.outputs["Z"], 2.2), clamp=True)
    stone = ramp(tree, strata.outputs["Fac"], ((0.3, (0.004, 0.008, 0.020)), (0.75, (0.016, 0.026, 0.055))))
    covered = node(tree, "ShaderNodeMixRGB")
    tree.links.new(math_node(tree, "MULTIPLY", snow, 1.6, clamp=True), covered.inputs["Fac"])
    tree.links.new(stone, covered.inputs["Color1"])
    covered.inputs["Color2"].default_value = (0.14, 0.26, 0.52, 1.0)
    shader = node(tree, "ShaderNodeBsdfPrincipled", Roughness=0.85)
    tree.links.new(covered.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(bumped(tree, strata.outputs["Fac"], 1.0, 6.0), shader.inputs["Normal"])
    finish(tree, shader.outputs[0])
    return mat


def moon_surface():
    """The full moon: bright highlands, grey seas, a scatter of craters, dimmer toward the limb."""
    mat, tree = material("Moon")
    coords = node(tree, "ShaderNodeTexCoord")
    seas = node(tree, "ShaderNodeTexNoise", Scale=1.7, Detail=9.0, Roughness=0.68)
    pits = node(tree, "ShaderNodeTexVoronoi", Scale=22.0)
    fine = node(tree, "ShaderNodeTexNoise", Scale=30.0, Detail=6.0)
    for tex in (seas, pits, fine):
        tree.links.new(coords.outputs["Generated"], tex.inputs["Vector"])
    colour = ramp(tree, seas.outputs["Fac"], ((0.36, (0.62, 0.84, 1.0)), (0.50, (0.36, 0.56, 0.90)), (0.62, (0.13, 0.26, 0.58))))
    crater = math_node(tree, "MULTIPLY", math_node(tree, "LESS_THAN", pits.outputs["Distance"], 0.16), 0.22)
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Generated"], split.inputs[0])
    dx = math_node(tree, "SUBTRACT", split.outputs["X"], 0.5)
    dy = math_node(tree, "SUBTRACT", split.outputs["Y"], 0.5)
    limb = math_node(tree, "MULTIPLY", math_node(tree, "ADD", math_node(tree, "MULTIPLY", dx, dx), math_node(tree, "MULTIPLY", dy, dy)), 4.0)
    strength = math_node(tree, "MULTIPLY", math_node(tree, "SUBTRACT", 1.5, math_node(tree, "MULTIPLY", limb, 0.6)),
                         math_node(tree, "ADD", math_node(tree, "SUBTRACT", 0.9, crater), math_node(tree, "MULTIPLY", fine.outputs["Fac"], 0.2)))
    emit = node(tree, "ShaderNodeEmission")
    tree.links.new(colour, emit.inputs["Color"])
    tree.links.new(strength, emit.inputs["Strength"])
    finish(tree, emit.outputs[0])
    return mat


def petal_material():
    """Sakura petals: thin, so light shines through them, and softly luminous, as blossom is under
    a moon. Each flower has its own pink, from nearly white to deep rose."""
    mat, tree = material("Petal")
    tint = node(tree, "ShaderNodeAttribute", attribute_name="tint")
    colour = ramp(tree, tint.outputs["Fac"], ((0.0, (1.0, 0.86, 0.93)), (0.45, (1.0, 0.56, 0.76)), (1.0, (0.80, 0.20, 0.46))))
    glow = node(tree, "ShaderNodeEmission", Strength=0.085)
    tree.links.new(colour, glow.inputs["Color"])
    lit = node(tree, "ShaderNodeAddShader")
    tree.links.new(thin(tree, colour, through=0.55), lit.inputs[0])
    tree.links.new(glow.outputs[0], lit.inputs[1])
    finish(tree, lit.outputs[0])
    return mat


def blade_material():
    """Grass: nearly black at the root, a living green at the tip, in patches of richer and drier."""
    mat, tree = material("Grass")
    place = node(tree, "ShaderNodeNewGeometry")
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(place.outputs["Position"], split.inputs[0])
    patches = node(tree, "ShaderNodeTexNoise", Scale=1.1, Detail=3.0)
    tree.links.new(place.outputs["Position"], patches.inputs["Vector"])
    tall = math_node(tree, "ADD", math_node(tree, "MULTIPLY", split.outputs["Z"], 6.5),
                     math_node(tree, "MULTIPLY", math_node(tree, "SUBTRACT", patches.outputs["Fac"], 0.5), 0.6), clamp=True)
    colour = ramp(tree, tall, ((0.0, (0.006, 0.03, 0.012)), (0.4, (0.035, 0.22, 0.07)), (1.0, (0.18, 0.62, 0.18))))
    sheen = node(tree, "ShaderNodeBsdfGlossy", Roughness=0.35)
    sheen.inputs["Color"].default_value = (0.5, 0.6, 0.5, 1.0)
    both = node(tree, "ShaderNodeMixShader")
    both.inputs[0].default_value = 0.10
    tree.links.new(thin(tree, colour, through=0.5), both.inputs[1])
    tree.links.new(sheen.outputs[0], both.inputs[2])
    finish(tree, both.outputs[0])
    return mat


def soil():
    mat, tree = material("Soil")
    place = node(tree, "ShaderNodeNewGeometry")
    clod = node(tree, "ShaderNodeTexNoise", Scale=14.0, Detail=5.0)
    tree.links.new(place.outputs["Position"], clod.inputs["Vector"])
    colour = ramp(tree, clod.outputs["Fac"], ((0.3, (0.006, 0.012, 0.006)), (0.8, (0.03, 0.035, 0.018))))
    shader = node(tree, "ShaderNodeBsdfPrincipled", Roughness=0.9)
    tree.links.new(colour, shader.inputs["Base Color"])
    tree.links.new(bumped(tree, clod.outputs["Fac"], 0.8, 0.03), shader.inputs["Normal"])
    finish(tree, shader.outputs[0])
    return mat


def mist(name, density, colour=(0.22, 0.50, 1.0)):
    """Air with a little water in it: it glows round every light and pales what is far away."""
    mat, tree = material(name)
    scatter = node(tree, "ShaderNodeVolumeScatter", Density=density, Anisotropy=0.55)
    scatter.inputs["Color"].default_value = (*colour, 1.0)
    out = node(tree, "ShaderNodeOutputMaterial")
    tree.links.new(scatter.outputs[0], out.inputs["Volume"])
    return mat


def night_sky(scene):
    """Midnight: near black overhead, deep blue toward the horizon, the moon's glow spreading
    through thin cloud, and stars."""
    world = bpy.data.worlds.new("Midnight")
    world.use_nodes = True
    tree = world.node_tree
    tree.nodes.clear()
    coords = node(tree, "ShaderNodeTexCoord")
    look = node(tree, "ShaderNodeVectorMath", operation="NORMALIZE")
    tree.links.new(coords.outputs["Generated"], look.inputs[0])
    split = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(look.outputs["Vector"], split.inputs[0])
    up = math_node(tree, "MAXIMUM", split.outputs["Z"], 0.0)
    colour = ramp(tree, up, ((0.0, (0.006, 0.034, 0.17)), (0.06, (0.0035, 0.019, 0.105)), (0.20, (0.0015, 0.0085, 0.055)),
                             (0.50, (0.0007, 0.0036, 0.027)), (1.0, (0.0003, 0.0014, 0.012))))
    sky = node(tree, "ShaderNodeBackground", Strength=1.0)
    tree.links.new(colour, sky.inputs["Color"])

    toward = node(tree, "ShaderNodeVectorMath", operation="DOT_PRODUCT")
    tree.links.new(look.outputs["Vector"], toward.inputs[0])
    toward.inputs[1].default_value = (at(MOON[0], MOON[1], MOON[3]) - Vector((0, 0, EYE))).normalized()
    near = math_node(tree, "MAXIMUM", toward.outputs["Value"], 0.0)
    wisps = node(tree, "ShaderNodeTexNoise", Scale=3.4, Detail=7.0, Roughness=0.62)
    spread = node(tree, "ShaderNodeMapping")
    spread.inputs["Scale"].default_value = (1.0, 1.0, 3.2)             # cloud lies in long bars
    tree.links.new(look.outputs["Vector"], spread.inputs["Vector"])
    tree.links.new(spread.outputs[0], wisps.inputs["Vector"])
    cloud = math_node(tree, "MULTIPLY", math_node(tree, "SUBTRACT", wisps.outputs["Fac"], 0.47), 3.2, clamp=True)
    halo = math_node(tree, "ADD", math_node(tree, "MULTIPLY", math_node(tree, "POWER", near, 60.0), 0.30),
                     math_node(tree, "MULTIPLY", math_node(tree, "MULTIPLY", math_node(tree, "POWER", near, 5.0), cloud), 0.30))
    halo = math_node(tree, "ADD", halo, math_node(tree, "MULTIPLY", math_node(tree, "POWER", near, 14.0), 0.045))
    halo = math_node(tree, "ADD", halo, math_node(tree, "MULTIPLY", cloud, 0.022))          # cloud all over the sky, faintly lit
    shine = node(tree, "ShaderNodeBackground")
    shine.inputs["Color"].default_value = (0.16, 0.42, 1.0, 1.0)
    tree.links.new(halo, shine.inputs["Strength"])

    cells = node(tree, "ShaderNodeTexVoronoi", Scale=300.0)
    tree.links.new(coords.outputs["Generated"], cells.inputs["Vector"])
    point = math_node(tree, "LESS_THAN", cells.outputs["Distance"], 0.04)
    bright = node(tree, "ShaderNodeSeparateXYZ")
    tree.links.new(cells.outputs["Color"], bright.inputs[0])
    clear = math_node(tree, "MULTIPLY", math_node(tree, "MINIMUM", math_node(tree, "MULTIPLY", math_node(tree, "MAXIMUM", math_node(tree, "SUBTRACT", up, 0.04), 0.0), 5.0), 1.0),
                      math_node(tree, "SUBTRACT", 1.0, math_node(tree, "MULTIPLY", cloud, 0.8)))
    twinkle = math_node(tree, "MULTIPLY", math_node(tree, "MULTIPLY", point, clear), math_node(tree, "POWER", bright.outputs["X"], 3.0))
    stars = node(tree, "ShaderNodeBackground")
    stars.inputs["Color"].default_value = (0.86, 0.92, 1.0, 1.0)
    tree.links.new(math_node(tree, "MULTIPLY", twinkle, 9.0), stars.inputs["Strength"])

    lit = node(tree, "ShaderNodeAddShader")
    tree.links.new(sky.outputs[0], lit.inputs[0])
    tree.links.new(shine.outputs[0], lit.inputs[1])
    both = node(tree, "ShaderNodeAddShader")
    tree.links.new(lit.outputs[0], both.inputs[0])
    tree.links.new(stars.outputs[0], both.inputs[1])
    out = node(tree, "ShaderNodeOutputWorld")
    tree.links.new(both.outputs[0], out.inputs["Surface"])
    scene.world = world


# ---- shapes --------------------------------------------------------------------------------------

def box(bm, low, high, index=0):
    made = bmesh.ops.create_cube(bm, size=1.0)
    size = Vector(high) - Vector(low)
    centre = (Vector(high) + Vector(low)) / 2
    for vert in made["verts"]:
        vert.co = Vector((vert.co.x * size.x, vert.co.y * size.y, vert.co.z * size.z)) + centre
        for face in vert.link_faces:
            face.material_index = index


def to_mesh(bm, name, *materials):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for mat in materials:
        mesh.materials.append(mat)
    return mesh


def link(scene, name, data, location=(0, 0, 0), scale=1.0, rotation=(0, 0, 0)):
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.scale = (scale, scale, scale)
    obj.rotation_euler = rotation
    scene.collection.objects.link(obj)
    return obj


def lamp(scene, name, location, watts, colour=(1.0, 0.56, 0.24), size=0.05):
    light = bpy.data.lights.new(name, "POINT")
    light.energy, light.color, light.shadow_soft_size = watts, colour, size
    return link(scene, name, light, location)


def lantern_mesh(name, ratio, segments, materials, creased=True):
    """A sky lantern one unit tall, centred on its origin: a paper shell open at the foot, never
    quite round; the bamboo ring that holds its mouth; the wire cross and the burner; the flame."""
    radius = ratio / 2
    rows = [i / 30 * 0.94 for i in range(31)] if creased else [0.0, 0.02, 0.06, 0.12, 0.2, 0.3, 0.37, 0.5, 0.65, 0.8, 0.94]

    def r(y):
        if y <= 0.37:
            return radius * math.sqrt(max(0.0, 1 - ((y - 0.37) / 0.37) ** 2))
        return radius * (1.0 + (0.56 - 1.0) * (y - 0.37) / 0.57)

    bm = bmesh.new()
    rings = []
    for y in rows:
        if y == 0.0:
            rings.append([bm.verts.new((0, 0, 0.5))])
            continue
        ring = []
        for i in range(segments):
            a = math.tau * i / segments
            out = r(y)
            if creased:   # the paper sags and bellies a little between its seams
                out *= 1 + 0.018 * noise.noise(Vector((math.cos(a) * 1.6, math.sin(a) * 1.6, y * 3.0 + ratio))) + 0.006 * math.cos(a * 8)
            ring.append(bm.verts.new((out * math.cos(a), out * math.sin(a), 0.5 - y)))
        rings.append(ring)
    for upper, lower in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            face = bm.faces.new((upper[0], lower[i], lower[j])) if len(upper) == 1 else bm.faces.new((upper[i], lower[i], lower[j], upper[j]))
            face.smooth = True
    mouth, thick = r(0.94) * 1.03, 0.014
    band = [[bm.verts.new((rad * math.cos(a), rad * math.sin(a), z)) for a in (math.tau * i / segments for i in range(segments))]
            for rad, z in ((mouth, -0.435), (mouth, -0.47), (mouth - thick, -0.47), (mouth - thick, -0.435))]
    for k in range(4):
        for i in range(segments):
            j = (i + 1) % segments
            face = bm.faces.new((band[k][i], band[(k + 1) % 4][i], band[(k + 1) % 4][j], band[k][j]))
            face.material_index = 1
            face.smooth = True
    wire = 0.004
    box(bm, (-mouth, -wire, -0.455), (mouth, wire, -0.447), 1)          # the wires that carry the burner
    box(bm, (-wire, -mouth, -0.455), (wire, mouth, -0.447), 1)
    box(bm, (-0.03, -0.03, -0.462), (0.03, 0.03, -0.44), 1)
    flame = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.03, matrix=Matrix.Translation((0, 0, -0.395)) @ Matrix.Diagonal((1, 1, 1.9, 1)))
    for vert in flame["verts"]:
        for face in vert.link_faces:
            face.material_index = 2
            face.smooth = True
    return to_mesh(bm, name, *materials)


def stone_lantern(scene, base: Vector, tall: float, stone, paper, core):
    """A stone lantern at the water's edge: plinth, post, a lamp chamber with paper windows, and a
    wide cap. Its lamp warms the grass and the shore round it."""
    w = tall * 0.2
    bm = bmesh.new()
    box(bm, (base.x - w * 1.5, base.y - w * 1.5, 0.0), (base.x + w * 1.5, base.y + w * 1.5, tall * 0.07))
    box(bm, (base.x - w * 0.45, base.y - w * 0.45, tall * 0.07), (base.x + w * 0.45, base.y + w * 0.45, tall * 0.52))
    box(bm, (base.x - w * 1.25, base.y - w * 1.25, tall * 0.52), (base.x + w * 1.25, base.y + w * 1.25, tall * 0.58))
    for sx in (-1, 1):
        for sy in (-1, 1):                                               # four corner posts round the lamp
            box(bm, (base.x + sx * w - w * 0.14, base.y + sy * w - w * 0.14, tall * 0.58), (base.x + sx * w + w * 0.14, base.y + sy * w + w * 0.14, tall * 0.80))
    box(bm, (base.x - w * 1.9, base.y - w * 1.9, tall * 0.80), (base.x + w * 1.9, base.y + w * 1.9, tall * 0.84))
    eave = [bm.verts.new((base.x + sx * w * 1.9, base.y + sy * w * 1.9, tall * 0.84)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    peak = bm.verts.new((base.x, base.y, tall * 0.97))
    for a, b in zip(eave, eave[1:] + eave[:1]):
        bm.faces.new((a, b, peak))
    box(bm, (base.x - w * 0.22, base.y - w * 0.22, tall * 0.95), (base.x + w * 0.22, base.y + w * 0.22, tall * 1.0))
    link(scene, "StoneLantern", to_mesh(bm, "StoneLantern", stone))
    bm = bmesh.new()
    box(bm, (base.x - w * 0.95, base.y - w * 0.95, tall * 0.585), (base.x + w * 0.95, base.y + w * 0.95, tall * 0.795))
    for face in list(bm.faces):
        if abs(face.normal.z) > 0.5:
            bm.faces.remove(face)
    link(scene, "StoneLanternPaper", to_mesh(bm, "StoneLanternPaper", paper))
    bm = bmesh.new()
    box(bm, (base.x - w * 0.4, base.y - w * 0.4, tall * 0.60), (base.x + w * 0.4, base.y + w * 0.4, tall * 0.76))
    link(scene, "StoneLanternLamp", to_mesh(bm, "StoneLanternLamp", core))
    lamp(scene, "StoneLanternGlow", base + Vector((0, -w * 2.6, tall * 0.62)), 16.0, size=0.25)


def granite():
    mat, tree = material("Granite")
    place = node(tree, "ShaderNodeNewGeometry")
    grit = node(tree, "ShaderNodeTexNoise", Scale=60.0, Detail=6.0, Roughness=0.7)
    moss = node(tree, "ShaderNodeTexNoise", Scale=5.0, Detail=4.0)
    for tex in (grit, moss):
        tree.links.new(place.outputs["Position"], tex.inputs["Vector"])
    stone = ramp(tree, grit.outputs["Fac"], ((0.3, (0.035, 0.04, 0.05)), (0.75, (0.16, 0.17, 0.19))))
    grown = node(tree, "ShaderNodeMixRGB")
    tree.links.new(math_node(tree, "MULTIPLY", math_node(tree, "SUBTRACT", moss.outputs["Fac"], 0.5), 2.4, clamp=True), grown.inputs["Fac"])
    tree.links.new(stone, grown.inputs["Color1"])
    grown.inputs["Color2"].default_value = (0.02, 0.07, 0.03, 1.0)
    shader = node(tree, "ShaderNodeBsdfPrincipled", Roughness=0.8)
    tree.links.new(grown.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(bumped(tree, grit.outputs["Fac"], 0.7, 0.006), shader.inputs["Normal"])
    finish(tree, shader.outputs[0])
    return mat


def mountains(scene, mat):
    """Real ground, not a backdrop: foothills at the far shore rising to snow peaks, with ridges
    and gullies for the moonlight and the mist to find."""
    nx, ny = 520, 150
    x0, x1, y0, y1 = -4600.0, 4600.0, 1250.0, 4200.0
    verts = []
    for j in range(ny):
        y = y0 + (y1 - y0) * j / (ny - 1)
        rise = min(1.0, (y - y0) / 1900.0)
        for i in range(nx):
            x = x0 + (x1 - x0) * i / (nx - 1)
            p = Vector((x / 1500.0, y / 1500.0, 4.2))
            crag = noise.ridged_multi_fractal(p, 1.0, 2.1, 7, 1.0, 2.0)
            lump = noise.fractal(p * 0.45, 1.0, 2.0, 4)
            verts.append((x, y, -8.0 + rise ** 1.5 * (70 + 240 * crag + 210 * max(0.0, lump + 0.25))))
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    mesh = bpy.data.meshes.new("Mountains")
    mesh.from_pydata(verts, [], faces)
    for poly in mesh.polygons:
        poly.use_smooth = True
    mesh.materials.append(mat)
    link(scene, "Mountains", mesh)


def quads(name, mat, items):
    """One mesh of many small flat shapes: items are (centre, size, rotation matrix, tint, outline)."""
    verts, faces, tints = [], [], []
    for centre, size, turn, tint, outline in items:
        start = len(verts)
        verts += [tuple(centre + turn @ Vector((px * size, py * size, 0.0))) for px, py in outline]
        faces.append(tuple(range(start, start + len(outline))))
        tints += [tint] * len(outline)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    layer = mesh.attributes.new("tint", "FLOAT", "POINT")
    layer.data.foreach_set("value", tints)
    mesh.materials.append(mat)
    return mesh


PETAL = ((0.0, -0.5), (0.34, -0.08), (0.20, 0.44), (0.0, 0.32), (-0.20, 0.44), (-0.34, -0.08))   # narrow at the heart, notched at the tip


def spin(r):
    return Matrix.Rotation(r.uniform(0, math.tau), 3, "Z") @ Matrix.Rotation(r.uniform(0, math.pi), 3, "X") @ Matrix.Rotation(r.uniform(0, math.tau), 3, "Y")


def sakura(scene, name, base: Vector, height: float, lean: float, seed: int, bark, petal, hung_mesh, hang_most=5, flowers=54000):
    """A cherry tree in full blossom: a twisting trunk and boughs, and on every twig a hundred
    separate petals, so the light comes through the blossom and it has depth. Nothing flowers
    where the card writes. A few paper lanterns hang in the boughs and warm the blossom round them."""
    r = random.Random(seed)
    boughs, twigs = [], []

    def grow(start, direction, length, radius, level):
        points = [(start.copy(), radius)]
        spot, heading = start.copy(), direction.normalized()
        steps = 6
        for i in range(1, steps + 1):
            wander = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.5, 0.8))) * (0.24 if level == 0 else 0.36)
            heading = (heading + wander + Vector((0, 0, 0.16 if level < 2 else -0.03))).normalized()
            spot = spot + heading * (length / steps)
            thick = radius * (1 - 0.45 * i / steps)
            points.append((spot.copy(), thick))
            if level >= 2:
                twigs.append(spot.copy())
            if level < 3 and i >= 2 and r.random() < (0.85 if level == 0 else 0.6):
                side = heading.cross(Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1)))).normalized()
                grow(spot, (heading * 0.5 + side * 0.9 + Vector((0, 0, 0.12))).normalized(), length * r.uniform(0.6, 0.85), thick * 0.72, level + 1)
        if level < 3:
            for _ in range(2):
                side = heading.cross(Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1)))).normalized()
                grow(spot, (heading * 0.75 + side * 0.65).normalized(), length * r.uniform(0.55, 0.8), points[-1][1] * 0.8, level + 1)
        boughs.append(points)

    grow(base, Vector((lean, 0.0, 1.0)), height * 0.42, height * 0.036, 0)
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions, curve.bevel_depth, curve.bevel_resolution, curve.use_fill_caps = "3D", 1.0, 4, True
    trunk = boughs[-1]
    for points in boughs:
        if points is not trunk:                    # a bough stops where the card writes; only the trunk may stand behind it
            keep = next((i for i, (co, _thick) in enumerate(points) if written_on(*pixel(co))), len(points))
            points = points[:keep]
            if len(points) < 2:
                continue
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, (co, thick) in zip(spline.points, points):
            point.co = (co.x, co.y, co.z, 1.0)
            point.radius = thick
    curve.materials.append(bark)
    link(scene, name, curve)

    per_twig = max(14, min(60, flowers // max(1, len(twigs))))
    fifth = [Matrix.Rotation(math.tau * k / 5, 3, "Z") @ Matrix.Rotation(math.radians(26), 3, "X") for k in range(5)]
    blossom, hung, glows = [], 0, 0
    for index, twig in enumerate(twigs):
        if twig.z < 0.5:
            continue
        shade = r.random()
        for _ in range(r.randint(per_twig * 3 // 4, per_twig * 5 // 4)):
            spot = twig + Vector((r.gauss(0, 0.16), r.gauss(0, 0.16), r.gauss(0, 0.13)))
            if written_on(*pixel(spot), 30):
                continue
            facing, size = spin(r), r.uniform(0.022, 0.034)
            tint = min(1.0, max(0.0, r.gauss(shade * 0.7, 0.2)))
            for turn in fifth:                                          # a whole flower: five cupped petals round a heart
                way = facing @ turn
                blossom.append((spot + way @ Vector((0.0, size * 0.5, 0.0)), size, way, tint, PETAL))
        if hung < hang_most and index % 23 == 7 and 1.5 < twig.z < 3.4 and pixel(twig)[1] > 60 and not written_on(*pixel(twig), 70):
            hang = twig - Vector((0, 0, 0.34))
            link(scene, "Hung", hung_mesh, hang, 0.34)
            lamp(scene, "HungLamp", hang - Vector((0, 0, 0.12)), 2.2, size=0.02)      # lights its own paper
            lamp(scene, "HungGlow", hang - Vector((0, 0, 0.26)), 5.0, size=0.1)       # and spills on the blossom below
            hung += 1
        elif glows < 5 and index % 53 == 11 and twig.z > 1.0:
            lamp(scene, "BlossomGlow", twig, 4.0, colour=(1.0, 0.45, 0.72), size=0.5)   # the blossom's own light, pooled in the canopy
            glows += 1
    print(f"TREE {name}: {len(twigs)} twigs, {len(blossom)} petals, {hung} lanterns")
    link(scene, name + "Blossom", quads(name + "Blossom", petal, blossom))


def grass(scene, stands, mat):
    """The bank, blade by blade, thick as a meadow. Blades are scattered evenly over the picture,
    so the grass is as dense far off as underfoot, and none stands in front of a lantern's paper.
    Returns places for fallen petals to lie."""
    verts, faces, resting = [], [], []
    for _ in range(300000):
        u, v = rng.uniform(-300, W + 300), rng.uniform(SHORE_ROW - 14, H + 130)
        d = EYE * F / (v - HORIZON)
        x = (u - W / 2) * d / F
        if d > shore(x):
            continue
        clump = 0.6 + 0.8 * noise.noise(Vector((x * 1.3, d * 1.3, 0.0))) ** 2
        tall = rng.uniform(0.06, 0.13) * (0.75 + 0.5 * rng.random()) * clump
        if rng.random() < 0.02:
            tall *= 1.8                                                 # the odd seed stalk standing above the rest
        inside = False
        for (x1, _y1, x2, y2), depth, left, right, deep in stands:
            if left - 0.07 < x < right + 0.07 and depth - 0.06 < d < depth + deep + 0.08:
                inside = True
                break
            if d < depth and x1 - 20 < u < x2 + 20:                     # in front of the paper: stay under its foot
                tall = min(tall, EYE - (y2 + 14 - HORIZON) * d / F)
        if inside or tall < 0.02:
            continue
        turn = rng.uniform(0, math.pi)
        half = tall * 0.035 + 0.0022
        wx, wy = math.cos(turn) * half, math.sin(turn) * half
        lx, ly = rng.gauss(0, 0.32) * tall, rng.gauss(0, 0.32) * tall
        i = len(verts)
        verts += [(x - wx, d - wy, 0.0), (x + wx, d + wy, 0.0),
                  (x - wx * 0.8 + lx * 0.2, d - wy * 0.8 + ly * 0.2, tall * 0.4), (x + wx * 0.8 + lx * 0.2, d + wy * 0.8 + ly * 0.2, tall * 0.4),
                  (x - wx * 0.5 + lx * 0.6, d - wy * 0.5 + ly * 0.6, tall * 0.75), (x + wx * 0.5 + lx * 0.6, d + wy * 0.5 + ly * 0.6, tall * 0.75),
                  (x + lx, d + ly, tall)]
        faces += [(i, i + 1, i + 3, i + 2), (i + 2, i + 3, i + 5, i + 4), (i + 4, i + 5, i + 6)]
        if rng.random() < 0.006:
            resting.append(Vector((x + lx, d + ly, tall * 0.85)))
    mesh = bpy.data.meshes.new("Grass")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    link(scene, "Grass", mesh)
    return resting


# ---- the scene -----------------------------------------------------------------------------------

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    camera.location = (0, 0, EYE)
    camera.rotation_euler = (math.radians(90), 0, 0)
    camera.data.lens, camera.data.sensor_width, camera.data.sensor_fit = FOCAL_MM, SENSOR_MM, "HORIZONTAL"
    camera.data.clip_start, camera.data.clip_end = 0.05, 30000
    camera.data.shift_y = (HORIZON - H / 2) / W
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = 4.4
    camera.data.dof.aperture_fstop = 2.0
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = W, H, PERCENT

    night_sky(scene)
    bamboo = timber("Bamboo", (0.05, 0.03, 0.012), (0.20, 0.13, 0.06), grain=18.0)
    flame = emission("Flame", (1.0, 0.50, 0.16), 90.0)
    paper = lantern_paper("SkyPaper", (1.0, 0.56, 0.26), (0.96, 0.36, 0.13))
    far_mesh = lantern_mesh("FarLantern", 0.74, 20, (far_paper(), bamboo, flame), creased=False)
    hung_mesh = lantern_mesh("HungLantern", 0.86, 64, (paper, bamboo, flame))

    # Wish lanterns far out over the lake: a scatter of warm lights, not a crowd.
    made = 0
    while made < 150:
        d = 160.0 * (1600.0 / 160.0) ** rng.random()
        u, v = rng.uniform(-700, W + 700), rng.uniform(-300, HORIZON - 30)
        if written_on(u, v, 20) or at(u, v, d).z < 6:
            continue
        link(scene, f"Far{made}", far_mesh, at(u, v, d), rng.uniform(1.0, 1.7),
             (math.radians(rng.uniform(-7, 7)), math.radians(rng.uniform(-7, 7)), rng.uniform(0, math.tau)))
        made += 1

    # Paper lanterns set adrift on the lake, each with its lamp.
    washi = lantern_paper("Washi", (1.0, 0.70, 0.40), (1.0, 0.56, 0.28), fibre=70.0)
    core = emission("Core", (1.0, 0.56, 0.24), 7.0)
    frame = timber("Frame", (0.016, 0.008, 0.005), (0.085, 0.04, 0.022))
    made = 0
    while made < 17:
        d = 13.5 * (120.0 / 13.5) ** rng.random()
        x = rng.uniform(-0.62, 0.62) * d
        if d < shore(x) + 1.5 or (abs(x) < d * 0.07 and d < 60):       # keep the moon's path on the water clear
            continue
        size = rng.uniform(0.26, 0.36)
        bm = bmesh.new()
        box(bm, (x - size / 2, d - size / 2, -0.04), (x + size / 2, d + size / 2, size * 1.05 - 0.04))
        for face in list(bm.faces):
            if abs(face.normal.z) > 0.5:
                bm.faces.remove(face)
        link(scene, "AdriftPaper", to_mesh(bm, "AdriftPaper", washi))
        bm = bmesh.new()
        box(bm, (x - size * 0.22, d - size * 0.22, 0.0), (x + size * 0.22, d + size * 0.22, size * 0.7))
        box(bm, (x - size * 0.62, d - size * 0.62, -0.07), (x + size * 0.62, d + size * 0.62, -0.035), 1)
        link(scene, "AdriftLamp", to_mesh(bm, "AdriftLamp", core, frame))
        made += 1

    water = bpy.data.meshes.new("Lake")
    water.from_pydata([(-9000, -60, -0.06), (9000, -60, -0.06), (9000, 9000, -0.06), (-9000, 9000, -0.06)], [], [(0, 1, 2, 3)])
    water.materials.append(lake())
    link(scene, "Lake", water)

    # The bank: soil out to a wandering shoreline, grass over it, fallen petals in the grass.
    edge = [(-20 + 0.25 * i, shore(-20 + 0.25 * i)) for i in range(161)]
    bank = bpy.data.meshes.new("Bank")
    bank.from_pydata([(-20, -4, 0.0), (20, -4, 0.0)] + [(x, y, 0.0) for x, y in reversed(edge)], [], [tuple(range(len(edge) + 2))])
    bank.materials.append(soil())
    link(scene, "Bank", bank)
    resting = grass(scene, [], blade_material())

    # The sakura. The near one is the heart of the picture: close enough to see every flower.
    petal = petal_material()
    bark = timber("Bark", (0.010, 0.006, 0.006), (0.075, 0.045, 0.038), grain=26.0, rough=0.85)
    sakura(scene, "SakuraNear", Vector((at(36, 1500, 3.4).x, 3.4, 0.0)), 4.9, 0.20, 11, bark, petal, hung_mesh, hang_most=5, flowers=62000)
    sakura(scene, "SakuraFar", Vector((at(1975, 1330, 5.6).x, 5.6, 0.0)), 5.2, -0.26, 29, bark, petal, hung_mesh, hang_most=4, flowers=52000)

    loose = [(spot, rng.uniform(0.02, 0.032), spin(rng), rng.random(), PETAL) for spot in resting]     # fallen, lying on the grass
    made = 0
    while made < 420:                                                                                 # and still falling
        d = 1.5 * (16.0 / 1.5) ** rng.random()
        u, v = rng.uniform(-100, W + 100), rng.uniform(20, 1230)
        if written_on(u, v, 10) or at(u, v, d).z < 0.2:
            continue
        loose.append((at(u, v, d), rng.uniform(0.018, 0.03), spin(rng), rng.random(), PETAL))
        made += 1
    link(scene, "LoosePetals", quads("LoosePetals", petal, loose))

    stone_lantern(scene, Vector((at(1585, HORIZON, 9.4).x, 9.4, 0.0)), 1.25, granite(), washi, emission("StoneCore", (1.0, 0.56, 0.24), 9.0))

    # Fireflies over the grass and along the shore.
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    fly = to_mesh(bm, "Firefly", emission("Firefly", (0.40, 0.86, 1.0), 45.0))
    made = 0
    while made < 200:
        d = rng.uniform(2.4, 11.5)
        u = rng.uniform(-40, W + 40)
        spot = Vector(((u - W / 2) * d / F, d, rng.uniform(0.1, 1.1)))
        if d > shore(spot.x) + 0.6 or written_on(*pixel(spot), 6):
            continue
        link(scene, "Firefly", fly, spot, rng.uniform(0.004, 0.008))
        made += 1

    mountains(scene, rock())

    # A town on the far shore, lit for the festival.
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    town = to_mesh(bm, "TownLamp", emission("TownLamp", (1.0, 0.56, 0.24), 30.0))
    for cluster in range(6):
        middle = rng.uniform(-1500, 1500)
        for _ in range(rng.randint(14, 40)):
            link(scene, "TownLamp", town, (middle + rng.gauss(0, 120), 1262 + rng.uniform(-12, 0), rng.uniform(1.0, 16) * rng.random()), rng.uniform(0.4, 0.9))

    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=160, radius=1.0)
    u, v, radius, far = MOON
    link(scene, "Moon", to_mesh(bm, "Moon", moon_surface()), at(u, v, far), radius * far / F, (math.radians(90), 0, 0))

    # The moon's path on the water. The moon stands too high for its mirror image to reach the
    # far lake, so a low glow that only the water can see lays the path where the eye expects it.
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=1.0)
    path = link(scene, "MoonPath", to_mesh(bm, "MoonPath", emission("MoonPath", (0.40, 0.66, 1.0), 2.4)),
                at(u, HORIZON - 150, far), 150 * far / F, (math.radians(90), 0, 0))
    path.scale.x *= 0.30
    path.visible_camera = False

    # Moonlight. The moon in the picture is its source, so it falls toward the camera from above:
    # it rims every petal and blade of grass and lies on the water.
    beam = bpy.data.lights.new("Moonlight", "SUN")
    beam.energy, beam.color, beam.angle = 4.5, (0.20, 0.46, 1.0), math.radians(2.5)
    link(scene, "Moonlight", beam, rotation=(Vector((0, 0, EYE)) - at(u, v - 380, far)).to_track_quat("-Z", "Y").to_euler())

    # The sky's own light, from behind the camera and high up: very little of it, deep blue, and
    # soft, so the meadow and the near sides of things are dark but not lost.
    fill = bpy.data.lights.new("Skylight", "SUN")
    fill.energy, fill.color, fill.angle = 0.5, (0.16, 0.42, 1.0), math.radians(40)
    link(scene, "Skylight", fill, rotation=(Vector((0.3, 1.0, -0.9))).to_track_quat("-Z", "Y").to_euler())

    # Mist: a thin haze through all the air, and a thicker one lying on the lake.
    bm = bmesh.new()
    box(bm, (-6000, -40, -1), (6000, 5200, 420))
    link(scene, "Haze", to_mesh(bm, "Haze", mist("Haze", 0.00003)))
    bm = bmesh.new()
    box(bm, (-3000, 12.5, -0.05), (3000, 2600, 7.0))
    link(scene, "LakeMist", to_mesh(bm, "LakeMist", mist("LakeMist", 0.0003)))

    scene.render.engine = "CYCLES"
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(dev.type == kind for dev in prefs.devices):
                for dev in prefs.devices:
                    dev.use = dev.type == kind
                scene.cycles.device = "GPU"
                break
        except Exception:
            continue
    scene.cycles.samples = SAMPLES
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.012
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 5
    scene.cycles.transmission_bounces = 8
    scene.cycles.volume_bounces = 1
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    scene.cycles.sample_clamp_indirect = 8.0
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = -0.35
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = OUT

    # Say where the moon landed, so a drift between this file and themes.py shows at once.
    bpy.context.view_layer.update()
    seen = world_to_camera_view(scene, camera, at(MOON[0], MOON[1], MOON[3]))
    print(f"LAYOUT moon: wanted ({MOON[0]}, {MOON[1]}) got ({seen.x * W:.1f}, {(1 - seen.y) * H:.1f})")
    return scene


if __name__ == "__main__":
    build()
    bpy.ops.render.render(write_still=True)
    print("RENDERED", OUT)
