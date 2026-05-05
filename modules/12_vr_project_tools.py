import math
import os
import re

import bpy

from ..selection_targets import get_selected_target_objects

UI_CATEGORY = "VR_PROJECT"

PRIMARY_UV_NAME = "UVMap"
SIMPLE_BAKE_UV_NAME = "SimpleBake"
BLENDER_DUPLICATE_SUFFIX_PATTERN = re.compile(r"^(.*)\.(\d{3})$")
PASCAL_CASE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RESERVED_KEYWORDS = {
    "Glass": ("glass", "window", "windows", "lens", "lenses"),
    "Foliage": ("leaf",),
    "Stitching": ("stitch", "stitches", "stitching", "seam", "thread"),
    "Blackout": ("blackout", "blackoff", "black_out", "black_off", "blackscreen", "black_screen"),
    "Metal": ("metal",),
}


def iter_scope_objects(context, scope):
    if scope == 'SELECTED':
        return [obj for obj in get_selected_target_objects(context) if obj.type == 'MESH']

    return [obj for obj in bpy.data.objects if obj.type == 'MESH']


def count_material_object_users(material):
    if not material:
        return 0

    users = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not obj.data:
            continue
        if any(slot.material == material for slot in obj.material_slots):
            users += 1
    return users


def strip_blender_duplicate_suffix(name):
    match = BLENDER_DUPLICATE_SUFFIX_PATTERN.match(name or "")
    if match:
        return match.group(1), match.group(2)
    return name or "", None


def is_pascal_case_name(name):
    return bool(PASCAL_CASE_PATTERN.fullmatch(name or ""))


def remove_empty_material_slots(obj):
    removed = 0
    mesh = obj.data
    for index in reversed(range(len(mesh.materials))):
        if mesh.materials[index] is None:
            mesh.materials.pop(index=index)
            removed += 1
    return removed


def get_non_empty_materials(obj):
    return [slot.material for slot in obj.material_slots if slot.material]


def iter_object_materials(obj):
    seen = set()
    for material in get_non_empty_materials(obj):
        key = material.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        yield material


def iter_material_image_nodes(material):
    if not material or not material.use_nodes or not material.node_tree:
        return

    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and getattr(node, "image", None):
            yield node, node.image


def image_path_missing(image):
    if not image or image.packed_file:
        return False
    if getattr(image, "source", None) not in {'FILE', 'SEQUENCE', 'MOVIE', 'TILED'}:
        return False
    if not image.filepath:
        return False

    filepath = bpy.path.abspath(image.filepath, library=getattr(image, "library", None))
    return not os.path.exists(filepath)


def get_objects_with_missing_textures(objects):
    problem_objects = []
    for obj in objects:
        found = False
        for material in iter_object_materials(obj):
            for _node, image in iter_material_image_nodes(material):
                if image_path_missing(image):
                    found = True
                    break
            if found:
                break
        if found:
            problem_objects.append(obj)
    return problem_objects


def get_reserved_keyword_matches(obj):
    search_names = [obj.name]
    search_names.extend(material.name for material in iter_object_materials(obj))
    joined = " ".join(search_names).lower()

    matches = []
    for category, keywords in RESERVED_KEYWORDS.items():
        matched_keywords = [keyword for keyword in keywords if keyword in joined]
        if matched_keywords:
            matches.append(f"{category}: {', '.join(matched_keywords)}")
    return matches


def get_objects_with_reserved_keywords(objects):
    matches = []
    for obj in objects:
        categories = get_reserved_keyword_matches(obj)
        if categories:
            matches.append((obj, categories))
    return matches


def ensure_single_material_from_object(obj):
    removed_empty = remove_empty_material_slots(obj)
    materials = get_non_empty_materials(obj)

    if len(materials) > 1:
        return False, "multiple_materials", removed_empty

    if not materials:
        material = bpy.data.materials.new(name=obj.name)
        obj.data.materials.append(material)
        return True, "created", removed_empty

    material = materials[0]
    if count_material_object_users(material) > 1:
        material = material.copy()
        obj.material_slots[0].material = material

    blocker = bpy.data.materials.get(obj.name)
    if blocker and blocker != material:
        return False, "material_name_collision", removed_empty

    material.name = obj.name
    return True, "synced", removed_empty


def sync_names_from_objects(objects):
    made_mesh_single_user = 0
    synced_meshes = 0
    synced_materials = 0
    skipped_multiple_materials = []
    skipped_name_collisions = []
    removed_empty_slots = 0

    for obj in objects:
        if obj.data and obj.data.users > 1:
            obj.data = obj.data.copy()
            made_mesh_single_user += 1

        if obj.data and obj.data.name != obj.name:
            blocker = bpy.data.meshes.get(obj.name)
            if blocker and blocker != obj.data:
                skipped_name_collisions.append(obj.name)
                continue
            obj.data.name = obj.name
            synced_meshes += 1

        ok, _status, removed = ensure_single_material_from_object(obj)
        removed_empty_slots += removed
        if not ok:
            if _status == "multiple_materials":
                skipped_multiple_materials.append(obj.name)
            elif _status == "material_name_collision":
                skipped_name_collisions.append(obj.name)
            continue

        synced_materials += 1

    return {
        "made_mesh_single_user": made_mesh_single_user,
        "synced_meshes": synced_meshes,
        "synced_materials": synced_materials,
        "skipped_multiple_materials": skipped_multiple_materials,
        "skipped_name_collisions": skipped_name_collisions,
        "removed_empty_slots": removed_empty_slots,
    }


def ensure_uv_channels(mesh):
    layers = mesh.uv_layers
    if len(layers) == 0:
        primary = layers.new(name=PRIMARY_UV_NAME, do_init=True)
    else:
        primary = layers[0]

    if len(layers) == 1:
        simple_bake = layers.new(name=SIMPLE_BAKE_UV_NAME, do_init=True)
    else:
        simple_bake = layers[1]

    for index in reversed(range(2, len(layers))):
        layers.remove(layers[index])

    primary.name = "__PM_TMP_PRIMARY_UV__"
    simple_bake.name = "__PM_TMP_SIMPLE_BAKE_UV__"
    primary.name = PRIMARY_UV_NAME
    simple_bake.name = SIMPLE_BAKE_UV_NAME

    for source_data, target_data in zip(primary.data, simple_bake.data):
        target_data.uv = source_data.uv

    layers.active = primary
    for layer in layers:
        layer.active_render = layer == simple_bake
    return primary, simple_bake


def ensure_uv_channels_for_objects(objects):
    checked = 0
    changed_meshes = 0
    seen_meshes = set()

    for obj in objects:
        mesh = obj.data
        if not mesh:
            continue

        mesh_key = mesh.as_pointer()
        if mesh_key in seen_meshes:
            continue
        seen_meshes.add(mesh_key)

        before = [layer.name for layer in mesh.uv_layers]
        ensure_uv_channels(mesh)
        after = [layer.name for layer in mesh.uv_layers]
        checked += 1
        if before != after:
            changed_meshes += 1

    return checked, changed_meshes


def audit_objects(objects):
    issues = {
        "bad_object_names": [],
        "shared_mesh_data": [],
        "mesh_name_mismatch": [],
        "material_count": [],
        "material_name_mismatch": [],
        "shared_materials": [],
        "uv_channels": [],
    }

    for obj in objects:
        if not is_pascal_case_name(obj.name) or BLENDER_DUPLICATE_SUFFIX_PATTERN.match(obj.name):
            issues["bad_object_names"].append(obj.name)

        if obj.data and obj.data.users > 1:
            issues["shared_mesh_data"].append(obj.name)

        if obj.data and obj.data.name != obj.name:
            issues["mesh_name_mismatch"].append(obj.name)

        materials = get_non_empty_materials(obj)
        if len(materials) != 1 or any(slot.material is None for slot in obj.material_slots):
            issues["material_count"].append(obj.name)
        else:
            material = materials[0]
            if material.name != obj.name:
                issues["material_name_mismatch"].append(obj.name)
            if count_material_object_users(material) > 1:
                issues["shared_materials"].append(obj.name)

        if obj.data:
            uv_names = [layer.name for layer in obj.data.uv_layers]
            if uv_names != [PRIMARY_UV_NAME, SIMPLE_BAKE_UV_NAME]:
                issues["uv_channels"].append(obj.name)

    return issues


def get_objects_from_issue_names(issue_names):
    objects = []
    for name in issue_names:
        obj = bpy.data.objects.get(name)
        if obj:
            objects.append(obj)
    return objects


def get_problem_objects(issues):
    names = set()
    for issue_names in issues.values():
        names.update(issue_names)
    return get_objects_from_issue_names(sorted(names))


def get_issue_filter_objects(issues, filter_key):
    if filter_key == 'BAD_NAMES':
        names = issues["bad_object_names"]
    elif filter_key == 'NAME_SYNC':
        names = set(issues["shared_mesh_data"])
        names.update(issues["mesh_name_mismatch"])
        names.update(issues["material_name_mismatch"])
        names = sorted(names)
    elif filter_key == 'MATERIAL_COUNT':
        names = issues["material_count"]
    elif filter_key == 'SHARED_MATERIALS':
        names = issues["shared_materials"]
    elif filter_key == 'UV_CHANNELS':
        names = issues["uv_channels"]
    else:
        names = []

    return get_objects_from_issue_names(names)


def select_scene_objects(context, objects):
    view_objects = {obj.as_pointer(): obj for obj in context.view_layer.objects}
    selectable = [view_objects[obj.as_pointer()] for obj in objects if obj.as_pointer() in view_objects]

    if context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    bpy.ops.object.select_all(action='DESELECT')
    for obj in selectable:
        obj.select_set(True)

    if selectable:
        context.view_layer.objects.active = selectable[0]

    return len(selectable), len(objects) - len(selectable)


def format_issue_sample(names):
    if len(names) <= 6:
        return ", ".join(names)
    return f"{', '.join(names[:6])}, ..."


class PM_OT_VR_AuditObjectPrep(bpy.types.Operator):
    bl_idname = "pm_vr.audit_object_prep"
    bl_label = "Audit Object Prep"
    bl_description = "Check object-based Scale Immersive naming, material, and UV requirements"
    bl_options = {'REGISTER'}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ('SELECTED', "Selected", "Only selected mesh targets"),
            ('ALL', "All Meshes", "All mesh objects in the file"),
        ),
        default='ALL',
    )

    def execute(self, context):
        objects = iter_scope_objects(context, self.scope)
        if not objects:
            self.report({'WARNING'}, "No mesh objects found in scope")
            return {'CANCELLED'}

        issues = audit_objects(objects)
        total_issues = sum(len(names) for names in issues.values())
        if total_issues == 0:
            self.report({'INFO'}, f"Audit passed for {len(objects)} object(s)")
            return {'FINISHED'}

        print("[PM Tools][VR Project] Scale Immersive audit:")
        for issue_name, names in issues.items():
            if names:
                print(f"  {issue_name}: {len(names)} ({format_issue_sample(names)})")

        selected, hidden = select_scene_objects(context, get_problem_objects(issues))
        hidden_note = f", {hidden} not visible in current view layer" if hidden else ""
        self.report({'WARNING'}, f"Audit found {total_issues} issue(s); selected {selected} object(s){hidden_note}")
        return {'FINISHED'}


class PM_OT_VR_SyncNamesFromObjects(bpy.types.Operator):
    bl_idname = "pm_vr.sync_names_from_objects"
    bl_label = "Sync Names From Objects"
    bl_description = "Copy each object name to its mesh data-block and single material"
    bl_options = {'REGISTER', 'UNDO'}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ('SELECTED', "Selected", "Only selected mesh targets"),
            ('ALL', "All Meshes", "All mesh objects in the file"),
        ),
        default='ALL',
    )

    def execute(self, context):
        objects = iter_scope_objects(context, self.scope)
        if not objects:
            self.report({'WARNING'}, "No mesh objects found in scope")
            return {'CANCELLED'}

        result = sync_names_from_objects(objects)
        skipped = result["skipped_multiple_materials"]
        if skipped:
            print("[PM Tools][VR Project] Skipped objects with multiple material slots:")
            print(f"  {format_issue_sample(skipped)}")

        collisions = result["skipped_name_collisions"]
        if collisions:
            print("[PM Tools][VR Project] Skipped objects with occupied mesh/material names:")
            print(f"  {format_issue_sample(collisions)}")

        message = (
            f"Single-user meshes {result['made_mesh_single_user']}, "
            f"synced {result['synced_meshes']} mesh names, "
            f"{result['synced_materials']} materials"
        )
        skipped_total = len(skipped) + len(collisions)
        if skipped_total:
            self.report({'WARNING'}, f"{message}; skipped {skipped_total} object(s)")
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


class PM_OT_VR_CheckUVChannels(bpy.types.Operator):
    bl_idname = "pm_vr.ensure_uv_channels"
    bl_label = "Check UV Channels"
    bl_description = "Force exact UVMap and SimpleBake channels, copying UVMap coordinates to SimpleBake"
    bl_options = {'REGISTER', 'UNDO'}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=(
            ('SELECTED', "Selected", "Only selected mesh targets"),
            ('ALL', "All Meshes", "All mesh objects in the file"),
        ),
        default='ALL',
    )

    def execute(self, context):
        objects = iter_scope_objects(context, self.scope)
        if not objects:
            self.report({'WARNING'}, "No mesh objects found in scope")
            return {'CANCELLED'}

        checked, changed = ensure_uv_channels_for_objects(objects)
        self.report({'INFO'}, f"UV channels ready: processed {checked}, renamed/trimmed {changed} mesh data-block(s)")
        return {'FINISHED'}


class PM_OT_VR_SelectAuditIssue(bpy.types.Operator):
    bl_idname = "pm_vr.select_audit_issue"
    bl_label = "Select Audit Issue"
    bl_description = "Select objects that match one Scale Immersive audit issue"
    bl_options = {'REGISTER'}

    issue: bpy.props.EnumProperty(
        name="Issue",
        items=(
            ('BAD_NAMES', "Bad Names", "Object names that are not PascalCase or still have .001 suffixes"),
            ('NAME_SYNC', "Name Sync", "Mesh data or material names do not match object names"),
            ('MATERIAL_COUNT', "Material Count", "Objects do not have exactly one filled material slot"),
            ('SHARED_MATERIALS', "Shared Materials", "Materials are used by more than one object"),
            ('UV_CHANNELS', "UV Channels", "UV layers are not exactly UVMap and SimpleBake"),
        ),
        default='UV_CHANNELS',
    )

    def execute(self, context):
        objects = iter_scope_objects(context, 'ALL')
        if not objects:
            self.report({'WARNING'}, "No mesh objects found in scope")
            return {'CANCELLED'}

        issues = audit_objects(objects)
        issue_objects = get_issue_filter_objects(issues, self.issue)
        if not issue_objects:
            self.report({'INFO'}, "No objects found for this issue")
            return {'FINISHED'}

        selected, hidden = select_scene_objects(context, issue_objects)
        hidden_note = f", {hidden} not visible in current view layer" if hidden else ""
        self.report({'INFO'}, f"Selected {selected} object(s){hidden_note}")
        return {'FINISHED'}


class PM_OT_VR_SelectReservedKeywords(bpy.types.Operator):
    bl_idname = "pm_vr.select_reserved_keywords"
    bl_label = "Select Reserved Words"
    bl_description = "Select objects whose object or material names contain Scale Immersive reserved keywords"
    bl_options = {'REGISTER'}

    def execute(self, context):
        objects = iter_scope_objects(context, 'ALL')
        matches = get_objects_with_reserved_keywords(objects)
        if not matches:
            self.report({'INFO'}, "No reserved keywords found")
            return {'FINISHED'}

        print("[PM Tools][VR Project] Reserved keyword matches:")
        for obj, categories in matches[:80]:
            print(f"  {obj.name}: {', '.join(categories)}")
        if len(matches) > 80:
            print(f"  ...and {len(matches) - 80} more")

        selected, hidden = select_scene_objects(context, [obj for obj, _categories in matches])
        hidden_note = f", {hidden} not visible in current view layer" if hidden else ""
        self.report({'INFO'}, f"Selected {selected} reserved-keyword object(s){hidden_note}")
        return {'FINISHED'}


class PM_OT_VR_SelectMissingTextures(bpy.types.Operator):
    bl_idname = "pm_vr.select_missing_textures"
    bl_label = "Select Missing Textures"
    bl_description = "Select objects using unpacked image textures whose source files cannot be found"
    bl_options = {'REGISTER'}

    def execute(self, context):
        objects = iter_scope_objects(context, 'ALL')
        problem_objects = get_objects_with_missing_textures(objects)
        if not problem_objects:
            self.report({'INFO'}, "No missing texture file references found")
            return {'FINISHED'}

        selected, hidden = select_scene_objects(context, problem_objects)
        hidden_note = f", {hidden} not visible in current view layer" if hidden else ""
        self.report({'WARNING'}, f"Selected {selected} object(s) with missing textures{hidden_note}")
        return {'FINISHED'}


TARGET_TD_PX_PER_CM = 10.0
TEXTURE_OPTIONS = {
    "1K": 1024,
    "2K": 2048,
    "4K": 4096,
}
CM_PER_BLEND_UNIT = 100.0

TD_SUFFIX_PATTERN = re.compile(r"_(1K|2K|4K)$")


def remove_td_suffix(name):
    return TD_SUFFIX_PATTERN.sub("", name)


def polygon_area_2d(points):
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def triangle_area_3d(a, b, c):
    return ((b - a).cross(c - a)).length * 0.5


def get_mesh_areas(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()

    try:
        if not mesh.polygons:
            return 0.0, 0.0, "no polygons"

        uv_layer = mesh.uv_layers.get(SIMPLE_BAKE_UV_NAME)
        if uv_layer is None:
            return 0.0, 0.0, f'UV channel "{SIMPLE_BAKE_UV_NAME}" not found'

        world_area_bu2 = 0.0
        uv_area = 0.0
        mw = obj.matrix_world

        for poly in mesh.polygons:
            loop_indices = poly.loop_indices
            if len(loop_indices) < 3:
                continue

            verts_world = [
                mw @ mesh.vertices[mesh.loops[i].vertex_index].co
                for i in loop_indices
            ]
            v0 = verts_world[0]
            for i in range(1, len(verts_world) - 1):
                world_area_bu2 += triangle_area_3d(
                    v0, verts_world[i], verts_world[i + 1]
                )

            uvs = [uv_layer.data[i].uv.copy() for i in loop_indices]
            uv_area += polygon_area_2d(uvs)

        mesh_area_cm2 = world_area_bu2 * (CM_PER_BLEND_UNIT ** 2)
        return mesh_area_cm2, uv_area, None
    finally:
        obj_eval.to_mesh_clear()


def choose_texture_suffix(uv_area, mesh_area_cm2):
    if mesh_area_cm2 <= 0.0 or uv_area <= 0.0:
        return "4K", {}

    td_results = {}
    for suffix, size in TEXTURE_OPTIONS.items():
        td_results[suffix] = size * math.sqrt(uv_area / mesh_area_cm2)

    for suffix, size in sorted(TEXTURE_OPTIONS.items(), key=lambda item: item[1]):
        if td_results[suffix] >= TARGET_TD_PX_PER_CM:
            return suffix, td_results

    return "4K", td_results


class PM_OT_VR_AddTextureSuffix(bpy.types.Operator):
    bl_idname = "pm_vr.add_texture_suffix"
    bl_label = "Add Texture Suffix"
    bl_description = (
        "Append _1K/_2K/_4K suffix based on texel density target "
        f"({TARGET_TD_PX_PER_CM} px/cm, UV: {SIMPLE_BAKE_UV_NAME})"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [
            obj for obj in get_selected_target_objects(context)
            if obj.type == 'MESH'
        ]
        if not selected:
            self.report({'WARNING'}, "No selected mesh objects found")
            return {'CANCELLED'}

        renamed = 0
        skipped = 0

        for obj in selected:
            mesh_area_cm2, uv_area, error = get_mesh_areas(obj)
            if error:
                skipped += 1
                print(f"[PM Tools][VR Project] SKIPPED {obj.name}: {error}")
                continue

            suffix, td_results = choose_texture_suffix(uv_area, mesh_area_cm2)
            base_name = remove_td_suffix(obj.name)
            new_name = f"{base_name}_{suffix}"
            obj.name = new_name
            renamed += 1

            print(
                f"[PM Tools][VR Project] {base_name} -> {new_name} | "
                f"Area: {mesh_area_cm2:.1f} cm\u00b2 | "
                f"TD 1K: {td_results.get('1K', 0):.1f}  "
                f"2K: {td_results.get('2K', 0):.1f}  "
                f"4K: {td_results.get('4K', 0):.1f} px/cm"
            )

        msg = f"Renamed {renamed} object(s)"
        if skipped:
            msg += f", skipped {skipped}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PM_OT_VR_ActivateUVMap(bpy.types.Operator):
    bl_idname = "pm_vr.activate_uvmap"
    bl_label = "Activate UVMap"
    bl_description = "Set first UV layer (UVMap) as active and renderable on selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [
            obj for obj in get_selected_target_objects(context)
            if obj.type == 'MESH'
        ]
        if not selected:
            self.report({'WARNING'}, "No selected mesh objects found")
            return {'CANCELLED'}

        count = 0
        for obj in selected:
            if not obj.data or not obj.data.uv_layers:
                continue
            layers = obj.data.uv_layers
            target = layers.get(PRIMARY_UV_NAME) or layers[0]
            layers.active = target
            for layer in layers:
                layer.active_render = (layer == target)
            count += 1

        self.report({'INFO'}, f"Activated UVMap on {count} object(s)")
        return {'FINISHED'}


class PM_OT_VR_ActivateSimpleBake(bpy.types.Operator):
    bl_idname = "pm_vr.activate_simplebake"
    bl_label = "Activate SimpleBake"
    bl_description = "Set SimpleBake UV layer as active and renderable on selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [
            obj for obj in get_selected_target_objects(context)
            if obj.type == 'MESH'
        ]
        if not selected:
            self.report({'WARNING'}, "No selected mesh objects found")
            return {'CANCELLED'}

        count = 0
        missing = 0
        for obj in selected:
            if not obj.data or not obj.data.uv_layers:
                continue
            layers = obj.data.uv_layers
            target = layers.get(SIMPLE_BAKE_UV_NAME)
            if not target:
                missing += 1
                continue
            layers.active = target
            for layer in layers:
                layer.active_render = (layer == target)
            count += 1

        msg = f"Activated SimpleBake on {count} object(s)"
        if missing:
            msg += f", {missing} without SimpleBake layer"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def draw_ui(layout, context):
    box = layout.box()
    box.label(text="Scale Immersive Prep", icon='WORLD')

    audit_col = box.column(align=True)
    row = audit_col.row(align=True)
    op = row.operator(PM_OT_VR_AuditObjectPrep.bl_idname, text="Audit Selected", icon='CHECKMARK')
    op.scope = 'SELECTED'
    op = row.operator(PM_OT_VR_AuditObjectPrep.bl_idname, text="Audit All", icon='CHECKMARK')
    op.scope = 'ALL'

    row = audit_col.row(align=True)
    op = row.operator(PM_OT_VR_SelectAuditIssue.bl_idname, text="Bad Names", icon='SORTALPHA')
    op.issue = 'BAD_NAMES'
    op = row.operator(PM_OT_VR_SelectAuditIssue.bl_idname, text="Name Sync", icon='LINKED')
    op.issue = 'NAME_SYNC'

    row = audit_col.row(align=True)
    op = row.operator(PM_OT_VR_SelectAuditIssue.bl_idname, text="One Material Issues", icon='MATERIAL')
    op.issue = 'MATERIAL_COUNT'
    op = row.operator(PM_OT_VR_SelectAuditIssue.bl_idname, text="Shared Materials", icon='LINKED')
    op.issue = 'SHARED_MATERIALS'

    row = audit_col.row(align=True)
    op = row.operator(PM_OT_VR_SelectAuditIssue.bl_idname, text="UV Issues", icon='GROUP_UVS')
    op.issue = 'UV_CHANNELS'
    row.operator(PM_OT_VR_SelectReservedKeywords.bl_idname, text="Reserved Words", icon='VIEWZOOM')

    box.separator()

    name_col = box.column(align=True)
    name_col.label(text="Copy Object Names:")
    row = name_col.row(align=True)
    op = row.operator(PM_OT_VR_SyncNamesFromObjects.bl_idname, text="Sync Selected", icon='OUTLINER_OB_MESH')
    op.scope = 'SELECTED'
    op = row.operator(PM_OT_VR_SyncNamesFromObjects.bl_idname, text="Sync All", icon='OUTLINER_OB_MESH')
    op.scope = 'ALL'

    box.separator()

    uv_col = box.column(align=True)
    uv_col.label(text="UV Channels:")
    row = uv_col.row(align=True)
    op = row.operator(PM_OT_VR_CheckUVChannels.bl_idname, text="Check UV Selected", icon='GROUP_UVS')
    op.scope = 'SELECTED'
    op = row.operator(PM_OT_VR_CheckUVChannels.bl_idname, text="Check UV All", icon='GROUP_UVS')
    op.scope = 'ALL'
    row = uv_col.row(align=True)
    row.operator(PM_OT_VR_ActivateUVMap.bl_idname, text="Activate UVMap", icon='GROUP_UVS')
    row.operator(PM_OT_VR_ActivateSimpleBake.bl_idname, text="Activate SimpleBake", icon='GROUP_UVS')

    box.separator()

    texture_col = box.column(align=True)
    texture_col.label(text="Textures:")
    texture_col.operator(PM_OT_VR_SelectMissingTextures.bl_idname, text="Missing Textures", icon='ERROR')
    texture_col.operator(PM_OT_VR_AddTextureSuffix.bl_idname, text="Add Texel Suffix", icon='TEXTURE')


classes = (
    PM_OT_VR_AuditObjectPrep,
    PM_OT_VR_SyncNamesFromObjects,
    PM_OT_VR_CheckUVChannels,
    PM_OT_VR_SelectAuditIssue,
    PM_OT_VR_SelectReservedKeywords,
    PM_OT_VR_SelectMissingTextures,
    PM_OT_VR_AddTextureSuffix,
    PM_OT_VR_ActivateUVMap,
    PM_OT_VR_ActivateSimpleBake,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
