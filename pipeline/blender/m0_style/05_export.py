"""M0.1 step 5: export the three style variants as GLBs for the Babylon style viewer.

  public/m0/S1.glb   all vertex color: geometric brows, lips and lid line as face colors; no textures
  public/m0/S2.glb   geometry + painted face: face.png on the body, iris.png on the eyes; no brow mesh
  public/m0/S3.glb   S2 + greyscale detail_*.png on top / bottom / shoes / hair

COLOR_0 = palette albedo (rgb) with baked ambient occlusion in alpha. A per-node glTF
extra `texMode` ("albedo" | "detail") tells the viewer how to apply a texture. Normals
are exported smooth; the viewer derives flat facets in the shader.
Run after step 04.
"""
import os

import bpy

OUT = "/home/david/projects/low-poly-character-system/public/m0"
TEX = os.path.join(OUT, "tex")
SKIN_REGIONS_FOR_TEXTURED_FACE = {1, 13}  # lips + lash line move into face.png in S2/S3
SKIN_SRGB = (0xD9 / 255, 0xA0 / 255, 0x7E / 255)

PARTS = ["LP_body", "LP_brows", "LP_eye_l", "LP_eye_r", "LP_hair", "LP_top", "LP_bottom", "LP_shoes"]
STYLES = {
    "S1": {"skip": set(), "tex": {}},
    "S2": {"skip": {"LP_brows"}, "tex": {"LP_body": ("face.png", "albedo"), "LP_eye_l": ("iris.png", "albedo"),
                                         "LP_eye_r": ("iris.png", "albedo")}},
    "S3": {"skip": {"LP_brows"}, "tex": {"LP_body": ("face.png", "albedo"), "LP_eye_l": ("iris.png", "albedo"),
                                         "LP_eye_r": ("iris.png", "albedo"),
                                         "LP_top": ("detail_top.png", "detail"), "LP_bottom": ("detail_bottom.png", "detail"),
                                         "LP_shoes": ("detail_shoes.png", "detail"), "LP_hair": ("detail_hair.png", "detail")}},
}


def material(name, image_file):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.9
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    vc = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    if image_file:
        t = nt.nodes.new("ShaderNodeTexImage")
        img = bpy.data.images.load(os.path.join(TEX, image_file), check_existing=True)
        t.image = img
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def pack_ao(me):
    """Col.a = AO (linear grey from the AO bake) so one COLOR_0 carries both."""
    col = me.color_attributes["Col"]; ao = me.color_attributes["AO"]
    for i in range(len(col.data)):
        r, g, b, _ = col.data[i].color
        col.data[i].color = (r, g, b, ao.data[i].color[0])


written = {}
for style, cfg in STYLES.items():
    objs = []
    for name in PARTS:
        if name in cfg["skip"]:
            continue
        src = bpy.data.objects[name]
        ob = src.copy(); ob.data = src.data.copy(); ob.name = "{}_{}".format(style, name[3:])
        bpy.context.scene.collection.objects.link(ob)
        me = ob.data
        tex = cfg["tex"].get(name)
        if tex and name == "LP_body":  # face.png carries skin + features: vertex color must be white,
            col = me.color_attributes["Col"]   # or skin × skin-texture comes out orange (first view)
            for i in range(len(col.data)):
                col.data[i].color = (1.0, 1.0, 1.0, 1.0)
        if tex and name.startswith("LP_eye"):  # the iris texture carries all eye color
            col = me.color_attributes["Col"]
            for i in range(len(col.data)):
                col.data[i].color = (1.0, 1.0, 1.0, 1.0)
        pack_ao(me)
        # The exporter writes the *render* color attribute as COLOR_0. After the AO bake that
        # was "AO", so the first export shipped grey AO instead of palette colors.
        names = [a.name for a in me.color_attributes]
        me.color_attributes.active_color_index = names.index("Col")
        me.color_attributes.render_color_index = names.index("Col")
        me.color_attributes.remove(me.color_attributes["AO"])
        for p in me.polygons:
            p.use_smooth = True
        me.materials.clear()
        me.materials.append(material("M_{}_{}".format(style, tex[0] if tex else "vc"), tex[0] if tex else None))
        ob["texMode"] = tex[1] if tex else "none"
        ob["part"] = name[3:]
        objs.append(ob)
    path = os.path.join(OUT, style + ".glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    with bpy.context.temp_override(selected_objects=objs, active_object=objs[0]):
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_extras=True,
                                  export_vertex_color="ACTIVE", export_normals=True, export_texcoords=True,
                                  export_materials="EXPORT", export_image_format="AUTO", export_apply=False,
                                  export_attributes=False, export_skins=False, export_animations=False,
                                  export_morph=False)
    written[style] = {"bytes": os.path.getsize(path), "parts": [o.name for o in objs],
                      "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
result = written
