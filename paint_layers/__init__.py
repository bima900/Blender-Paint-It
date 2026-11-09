"""
Paint Layers (MVP)
Layer stack untuk Texture Paint ala Substance Painter.

Setiap layer = 1 Image (RGBA, transparan) + mask opsional (Image grayscale).
Layer digabung otomatis lewat node di material aktif dan dihubungkan ke
Base Color pada Principled BSDF. Urutan di list: atas = layer paling atas.
"""

import uuid

import bpy
import numpy as np
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList

PREFIX = "PL_"
_suspend = False  # matikan callback selama operator bekerja

BLEND_ITEMS = [
    ("MIX", "Normal", ""),
    ("DARKEN", "Darken", ""),
    ("MULTIPLY", "Multiply", ""),
    ("BURN", "Color Burn", ""),
    ("LIGHTEN", "Lighten", ""),
    ("SCREEN", "Screen", ""),
    ("DODGE", "Color Dodge", ""),
    ("ADD", "Add", ""),
    ("OVERLAY", "Overlay", ""),
    ("SOFT_LIGHT", "Soft Light", ""),
    ("LINEAR_LIGHT", "Linear Light", ""),
    ("DIFFERENCE", "Difference", ""),
    ("EXCLUSION", "Exclusion", ""),
    ("SUBTRACT", "Subtract", ""),
    ("DIVIDE", "Divide", ""),
    ("HUE", "Hue", ""),
    ("SATURATION", "Saturation", ""),
    ("COLOR", "Color", ""),
    ("VALUE", "Value", ""),
]


# --------------------------------------------------------------------------
# Node building
# --------------------------------------------------------------------------

def _ensure_tree(mat):
    if not mat.use_nodes or mat.node_tree is None:
        try:
            mat.use_nodes = True
        except Exception:
            pass
    return mat.node_tree


def _ensure_principled(tree):
    for n in tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    out = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        out.location = (bsdf.location.x + 300, bsdf.location.y)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return bsdf


def _rgba(sockets):
    return [s for s in sockets if s.type == "RGBA"]


def rebuild(mat):
    """Bangun ulang seluruh node layer pada material."""
    if mat is None:
        return
    tree = _ensure_tree(mat)
    if tree is None:
        return
    nodes, links = tree.nodes, tree.links

    for n in [n for n in nodes if n.name.startswith(PREFIX)]:
        nodes.remove(n)

    layers = mat.pl_layers
    if len(layers) == 0:
        return

    bsdf = _ensure_principled(tree)
    bx, by = bsdf.location.x, bsdf.location.y
    count = len(layers)

    base = nodes.new("ShaderNodeRGB")
    base.name = PREFIX + "base"
    base.label = "Paint Base"
    base.outputs[0].default_value = (0.8, 0.8, 0.8, 1.0)
    base.location = (bx - 1500, by)
    prev = base.outputs[0]

    # index 0 = layer paling atas -> proses dari bawah (index terakhir)
    for step, i in enumerate(reversed(range(count))):
        L = layers[i]
        if L.image is None:
            continue
        y = by - step * 700

        tex = nodes.new("ShaderNodeTexImage")
        tex.name = f"{PREFIX}tex_{L.uid}"
        tex.label = L.name
        tex.image = L.image
        tex.location = (bx - 1250, y)

        op = nodes.new("ShaderNodeMath")
        op.name = f"{PREFIX}op_{L.uid}"
        op.label = "Opacity"
        op.operation = "MULTIPLY"
        op.inputs[1].default_value = L.opacity if L.visible else 0.0
        op.location = (bx - 950, y)
        links.new(tex.outputs["Alpha"], op.inputs[0])
        fac = op.outputs[0]

        if L.use_mask and L.mask_image is not None:
            mtex = nodes.new("ShaderNodeTexImage")
            mtex.name = f"{PREFIX}mask_{L.uid}"
            mtex.label = L.name + " (Mask)"
            mtex.image = L.mask_image
            mtex.location = (bx - 1250, y - 330)
            mm = nodes.new("ShaderNodeMath")
            mm.name = f"{PREFIX}maskmul_{L.uid}"
            mm.label = "Mask"
            mm.operation = "MULTIPLY"
            mm.location = (bx - 780, y)
            links.new(fac, mm.inputs[0])
            links.new(mtex.outputs["Color"], mm.inputs[1])
            fac = mm.outputs[0]

        mix = nodes.new("ShaderNodeMix")
        mix.name = f"{PREFIX}mix_{L.uid}"
        mix.label = L.name
        mix.data_type = "RGBA"
        mix.blend_type = L.blend_type
        mix.clamp_factor = True
        mix.location = (bx - 600 + step * 40, y)
        links.new(fac, mix.inputs[0])
        a, b = _rgba(mix.inputs)[:2]
        links.new(prev, a)
        links.new(tex.outputs["Color"], b)
        prev = _rgba(mix.outputs)[0]

    links.new(prev, bsdf.inputs["Base Color"])


def sync_params(mat):
    """Update ringan (opacity/blend/visibility) tanpa membangun ulang node."""
    tree = mat.node_tree
    if tree is None:
        return
    nodes = tree.nodes
    for L in mat.pl_layers:
        if L.image is None:
            continue
        op = nodes.get(f"{PREFIX}op_{L.uid}")
        mix = nodes.get(f"{PREFIX}mix_{L.uid}")
        if op is None or mix is None:
            rebuild(mat)
            activate(mat)
            return
        op.inputs[1].default_value = L.opacity if L.visible else 0.0
        mix.blend_type = L.blend_type


def activate(mat):
    """Jadikan image layer aktif sebagai kanvas Texture Paint."""
    layers = mat.pl_layers
    idx = mat.pl_active
    if not (0 <= idx < len(layers)) or mat.node_tree is None:
        return
    L = layers[idx]
    use_mask = L.edit_target == "MASK" and L.use_mask and L.mask_image
    img = L.mask_image if use_mask else L.image
    name = f"{PREFIX}{'mask' if use_mask else 'tex'}_{L.uid}"
    nodes = mat.node_tree.nodes
    node = nodes.get(name)
    if node is not None:
        for n in nodes:
            n.select = False
        node.select = True
        nodes.active = node
    try:
        ts = bpy.context.scene.tool_settings
        if ts.image_paint.mode == "IMAGE" and img is not None:
            ts.image_paint.canvas = img
    except Exception:
        pass


# --------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------

def _params_update(self, context):
    if _suspend:
        return
    sync_params(self.id_data)


def _struct_update(self, context):
    if _suspend:
        return
    mat = self.id_data
    rebuild(mat)
    activate(mat)


def _target_update(self, context):
    if _suspend:
        return
    activate(self.id_data)


def _active_update(self, context):
    if _suspend:
        return
    activate(self)


class PL_Layer(PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    uid: StringProperty(default="")
    image: PointerProperty(type=bpy.types.Image, update=_struct_update)
    mask_image: PointerProperty(type=bpy.types.Image, update=_struct_update)
    use_mask: BoolProperty(name="Use Mask", default=False, update=_struct_update)
    visible: BoolProperty(name="Visible", default=True, update=_params_update)
    opacity: FloatProperty(
        name="Opacity", default=1.0, min=0.0, max=1.0,
        subtype="FACTOR", update=_params_update,
    )
    blend_type: EnumProperty(
        name="Blend", items=BLEND_ITEMS, default="MIX", update=_params_update
    )
    edit_target: EnumProperty(
        name="Paint On",
        items=[
            ("LAYER", "Layer", "Paint on layer color"),
            ("MASK", "Mask", "Paint on layer mask"),
        ],
        default="LAYER",
        update=_target_update,
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _active_mat(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj.active_material


def _new_image(name, size, color, alpha=True, non_color=False):
    img = bpy.data.images.new(name, size, size, alpha=alpha)
    img.generated_color = color
    img.alpha_mode = "STRAIGHT"
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    img.use_fake_user = True
    return img


def _copy_image(src, name, alpha=True, non_color=False):
    w, h = src.size
    img = bpy.data.images.new(name, w, h, alpha=alpha)
    img.alpha_mode = "STRAIGHT"
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    buf = np.empty(w * h * 4, dtype=np.float32)
    src.pixels.foreach_get(buf)
    img.pixels.foreach_set(buf)
    img.update()
    img.use_fake_user = True
    return img


class _Suspend:
    def __enter__(self):
        global _suspend
        _suspend = True

    def __exit__(self, *exc):
        global _suspend
        _suspend = False


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class PL_OT_add_layer(Operator):
    bl_idname = "paint_layers.add_layer"
    bl_label = "Add Layer"
    bl_description = "Tambah layer paint baru di atas layer aktif"
    bl_options = {"REGISTER", "UNDO"}

    fill_color: FloatVectorProperty(
        name="Fill", size=4, subtype="COLOR", min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0, 0.0),
    )

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        mat = obj.active_material
        if mat is None:
            mat = bpy.data.materials.new(f"{obj.name}_Paint")
            if obj.material_slots:
                obj.active_material = mat
            else:
                obj.data.materials.append(mat)
        _ensure_tree(mat)

        size = int(context.scene.pl_resolution)
        layers = mat.pl_layers
        target = mat.pl_active if len(layers) else 0
        target = max(0, min(target, len(layers)))

        with _Suspend():
            n = len(layers) + 1
            name = f"Layer {n}"
            img = _new_image(f"{mat.name}_{name}", size, tuple(self.fill_color))
            L = layers.add()
            L.uid = uuid.uuid4().hex[:8]
            L.name = name
            L.image = img
            layers.move(len(layers) - 1, target)
            mat.pl_active = target

        rebuild(mat)
        activate(mat)
        return {"FINISHED"}


class PL_OT_remove_layer(Operator):
    bl_idname = "paint_layers.remove_layer"
    bl_label = "Remove Layer"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        return m is not None and len(m.pl_layers) > 0

    def execute(self, context):
        mat = _active_mat(context)
        layers = mat.pl_layers
        idx = mat.pl_active
        if not (0 <= idx < len(layers)):
            return {"CANCELLED"}
        imgs = [layers[idx].image, layers[idx].mask_image]
        with _Suspend():
            layers.remove(idx)
            mat.pl_active = max(0, min(idx, len(layers) - 1))
        rebuild(mat)
        for img in imgs:
            if img is not None:
                bpy.data.images.remove(img)
        activate(mat)
        return {"FINISHED"}


class PL_OT_move_layer(Operator):
    bl_idname = "paint_layers.move_layer"
    bl_label = "Move Layer"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        return m is not None and len(m.pl_layers) > 1

    def execute(self, context):
        mat = _active_mat(context)
        layers = mat.pl_layers
        idx = mat.pl_active
        new = idx - 1 if self.direction == "UP" else idx + 1
        if not (0 <= new < len(layers)):
            return {"CANCELLED"}
        with _Suspend():
            layers.move(idx, new)
            mat.pl_active = new
        rebuild(mat)
        activate(mat)
        return {"FINISHED"}


class PL_OT_duplicate_layer(Operator):
    bl_idname = "paint_layers.duplicate_layer"
    bl_label = "Duplicate Layer"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        return m is not None and len(m.pl_layers) > 0

    def execute(self, context):
        mat = _active_mat(context)
        layers = mat.pl_layers
        idx = mat.pl_active
        if not (0 <= idx < len(layers)):
            return {"CANCELLED"}
        s = layers[idx]
        if s.image is None:
            return {"CANCELLED"}
        data = dict(
            name=s.name + " Copy", blend=s.blend_type, opacity=s.opacity,
            visible=s.visible, img=s.image,
            mask=s.mask_image if s.use_mask else None,
        )
        with _Suspend():
            img = _copy_image(data["img"], f"{mat.name}_{data['name']}")
            mask = None
            if data["mask"] is not None:
                mask = _copy_image(
                    data["mask"], f"{mat.name}_{data['name']}_mask",
                    alpha=False, non_color=True,
                )
            L = layers.add()
            L.uid = uuid.uuid4().hex[:8]
            L.name = data["name"]
            L.blend_type = data["blend"]
            L.opacity = data["opacity"]
            L.visible = data["visible"]
            L.image = img
            if mask is not None:
                L.mask_image = mask
                L.use_mask = True
            layers.move(len(layers) - 1, idx)
            mat.pl_active = idx
        rebuild(mat)
        activate(mat)
        return {"FINISHED"}


class PL_OT_add_mask(Operator):
    bl_idname = "paint_layers.add_mask"
    bl_label = "Add Mask"
    bl_options = {"REGISTER", "UNDO"}

    fill: EnumProperty(
        name="Fill",
        items=[
            ("WHITE", "Reveal All", "Putih: layer terlihat penuh"),
            ("BLACK", "Hide All", "Hitam: layer tersembunyi"),
        ],
        default="WHITE",
    )

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        if m is None or not (0 <= m.pl_active < len(m.pl_layers)):
            return False
        return not m.pl_layers[m.pl_active].use_mask

    def execute(self, context):
        mat = _active_mat(context)
        L = mat.pl_layers[mat.pl_active]
        if L.image is None:
            return {"CANCELLED"}
        size = max(L.image.size[0], L.image.size[1])
        v = 1.0 if self.fill == "WHITE" else 0.0
        with _Suspend():
            L.mask_image = _new_image(
                f"{mat.name}_{L.name}_mask", size, (v, v, v, 1.0),
                alpha=False, non_color=True,
            )
            L.use_mask = True
            L.edit_target = "MASK"
        rebuild(mat)
        activate(mat)
        return {"FINISHED"}


class PL_OT_remove_mask(Operator):
    bl_idname = "paint_layers.remove_mask"
    bl_label = "Remove Mask"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        if m is None or not (0 <= m.pl_active < len(m.pl_layers)):
            return False
        return m.pl_layers[m.pl_active].use_mask

    def execute(self, context):
        mat = _active_mat(context)
        L = mat.pl_layers[mat.pl_active]
        img = L.mask_image
        with _Suspend():
            L.edit_target = "LAYER"
            L.use_mask = False
            L.mask_image = None
        rebuild(mat)
        if img is not None:
            bpy.data.images.remove(img)
        activate(mat)
        return {"FINISHED"}


class PL_OT_save_images(Operator):
    bl_idname = "paint_layers.save_images"
    bl_label = "Save Layer Images"
    bl_description = (
        "Simpan semua image layer ke folder //textures (atau pack jika "
        ".blend belum disimpan)"
    )

    @classmethod
    def poll(cls, context):
        m = _active_mat(context)
        return m is not None and len(m.pl_layers) > 0

    def execute(self, context):
        import os

        mat = _active_mat(context)
        imgs = []
        for L in mat.pl_layers:
            for im in (L.image, L.mask_image):
                if im is not None and im not in imgs:
                    imgs.append(im)

        saved, failed = 0, 0
        if not bpy.data.filepath:
            for im in imgs:
                try:
                    im.pack()
                    saved += 1
                except Exception:
                    failed += 1
            self.report({"INFO"}, f"Blend belum disimpan: {saved} image di-pack")
            return {"FINISHED"}

        folder = bpy.path.abspath("//textures")
        os.makedirs(folder, exist_ok=True)
        for im in imgs:
            try:
                if im.packed_file:
                    im.unpack(method="REMOVE")
                path = os.path.join(folder, bpy.path.clean_name(im.name) + ".png")
                im.filepath_raw = path
                im.file_format = "PNG"
                im.save()
                im.source = "FILE"
                saved += 1
            except Exception as e:
                failed += 1
                print("[Paint Layers] gagal simpan", im.name, e)
        msg = f"{saved} image disimpan ke {folder}"
        if failed:
            msg += f" ({failed} gagal, cek System Console)"
        self.report({"WARNING" if failed else "INFO"}, msg)
        return {"FINISHED"}


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

class PL_UL_layers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "visible", text="", emboss=False,
                 icon="HIDE_OFF" if item.visible else "HIDE_ON")
        row.prop(item, "name", text="", emboss=False)
        if item.use_mask:
            row.label(text="", icon="MOD_MASK")


class PL_PT_main(Panel):
    bl_label = "Paint Layers"
    bl_idname = "PL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paint Layers"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == "MESH"

    def draw(self, context):
        layout = self.layout
        mat = _active_mat(context)

        if context.mode == "PAINT_TEXTURE":
            layout.operator("object.mode_set", text="Back to Object Mode",
                            icon="OBJECT_DATAMODE").mode = "OBJECT"
        else:
            layout.operator("object.mode_set", text="Texture Paint Mode",
                            icon="TPAINT_HLT").mode = "TEXTURE_PAINT"

        layout.prop(context.scene, "pl_resolution", text="Resolution")
        row = layout.row(align=True)
        row.operator("paint_layers.add_layer", text="Add Layer", icon="ADD")
        fill = row.operator("paint_layers.add_layer", text="Add Fill",
                            icon="IMAGE_RGB")
        fill.fill_color = (0.5, 0.5, 0.5, 1.0)

        if mat is None:
            return

        row = layout.row()
        row.template_list("PL_UL_layers", "", mat, "pl_layers",
                          mat, "pl_active", rows=6)
        col = row.column(align=True)
        col.operator("paint_layers.remove_layer", text="", icon="REMOVE")
        col.separator()
        col.operator("paint_layers.move_layer", text="",
                     icon="TRIA_UP").direction = "UP"
        col.operator("paint_layers.move_layer", text="",
                     icon="TRIA_DOWN").direction = "DOWN"
        col.separator()
        col.operator("paint_layers.duplicate_layer", text="", icon="DUPLICATE")

        idx = mat.pl_active
        if not (0 <= idx < len(mat.pl_layers)):
            return
        L = mat.pl_layers[idx]

        box = layout.box()
        box.prop(L, "blend_type", text="Blend")
        box.prop(L, "opacity", slider=True)

        mbox = layout.box()
        if L.use_mask:
            mbox.row().prop(L, "edit_target", expand=True)
            mbox.operator("paint_layers.remove_mask", icon="X")
        else:
            r = mbox.row(align=True)
            r.operator("paint_layers.add_mask", text="Mask: Reveal",
                       icon="MOD_MASK").fill = "WHITE"
            r.operator("paint_layers.add_mask", text="Mask: Hide",
                       icon="MOD_MASK").fill = "BLACK"

        layout.operator("paint_layers.save_images", icon="FILE_TICK")


# --------------------------------------------------------------------------
# Register
# --------------------------------------------------------------------------

classes = (
    PL_Layer,
    PL_OT_add_layer,
    PL_OT_remove_layer,
    PL_OT_move_layer,
    PL_OT_duplicate_layer,
    PL_OT_add_mask,
    PL_OT_remove_mask,
    PL_OT_save_images,
    PL_UL_layers,
    PL_PT_main,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Material.pl_layers = CollectionProperty(type=PL_Layer)
    bpy.types.Material.pl_active = IntProperty(default=0, update=_active_update)
    bpy.types.Scene.pl_resolution = EnumProperty(
        name="Resolution",
        items=[
            ("512", "512", ""),
            ("1024", "1024", ""),
            ("2048", "2048", ""),
            ("4096", "4096", ""),
        ],
        default="2048",
    )


def unregister():
    del bpy.types.Scene.pl_resolution
    del bpy.types.Material.pl_active
    del bpy.types.Material.pl_layers
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
