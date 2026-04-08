import bpy
import os
import re
import uuid

from ..selection_targets import (
    get_selected_target_objects,
    is_collection_instance,
    resolve_operable_mesh_targets,
)

UI_CATEGORY = "MATERIAL_OVERRIDE_LOOKDEV"

ASSET_FILENAME = "node_library.blend"
NODE_GROUP_NAME = "P_GN_MaterialOverride"
MATERIAL_SOCKET_NAME = "Material"
MATERIAL_SOCKET_IDENTIFIER = "Socket_2"
MODIFIER_NAME = "PM_MaterialOverride"
MATERIAL_PREFIX = "P_MO_"
DEFAULT_GROUP_NAME = "Default"
DEFAULT_GROUP_COLOR = (0.6, 0.6, 0.6, 1.0)
DEFAULT_GROUP_ROUGHNESS = 0.5


def sanitize_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value or "").strip("_")
    return cleaned or "Group"


class PM_MOG_Manager:
    @staticmethod
    def iter_all_mesh_objects():
        return [obj for obj in bpy.data.objects if obj and obj.type == 'MESH']

    @staticmethod
    def get_assets_path():
        modules_dir = os.path.dirname(os.path.abspath(__file__))
        addon_root = os.path.dirname(modules_dir)
        return os.path.join(addon_root, "assets", ASSET_FILENAME)

    @staticmethod
    def get_or_load_node_group():
        if NODE_GROUP_NAME in bpy.data.node_groups:
            return bpy.data.node_groups[NODE_GROUP_NAME]

        filepath = PM_MOG_Manager.get_assets_path()
        if not os.path.exists(filepath):
            print(f"[PM Tools] ERROR: Asset file missing: {filepath}")
            return None

        try:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                if NODE_GROUP_NAME in data_from.node_groups:
                    data_to.node_groups = [NODE_GROUP_NAME]
        except Exception as exc:
            print(f"[PM Tools] ERROR: Failed to load node group '{NODE_GROUP_NAME}': {exc}")
            return None

        return bpy.data.node_groups.get(NODE_GROUP_NAME)

    @staticmethod
    def get_socket_identifier(node_group, socket_name=MATERIAL_SOCKET_NAME):
        if not node_group:
            return None

        interface = getattr(node_group, "interface", None)
        items = getattr(interface, "items_tree", None) or getattr(interface, "items", None)
        if items:
            for item in items:
                if getattr(item, "item_type", None) not in {'SOCKET', 'INPUT'}:
                    continue
                if getattr(item, "in_out", 'INPUT') != 'INPUT':
                    continue
                if item.name == socket_name:
                    return getattr(item, "identifier", None)

        inputs = getattr(node_group, "inputs", None)
        if inputs:
            for socket in inputs:
                if socket.name == socket_name:
                    return getattr(socket, "identifier", None) or socket.name

        return MATERIAL_SOCKET_IDENTIFIER

    @staticmethod
    def get_active_group(scene):
        groups = getattr(scene, "pm_mog_groups", None)
        if not groups:
            return None

        index = getattr(scene, "pm_mog_group_index", -1)
        if 0 <= index < len(groups):
            return groups[index]
        return None

    @staticmethod
    def next_group_name(scene):
        existing = {group.name for group in scene.pm_mog_groups}
        index = 1
        while True:
            candidate = f"Group {index:02d}"
            if candidate not in existing:
                return candidate
            index += 1

    @staticmethod
    def get_group_by_uid(scene, group_uid):
        if not scene or not group_uid:
            return None
        for group in scene.pm_mog_groups:
            if group.uid == group_uid:
                return group
        return None

    @staticmethod
    def get_group_by_name(scene, group_name):
        if not scene or not group_name:
            return None
        for group in scene.pm_mog_groups:
            if group.name == group_name:
                return group
        return None

    @staticmethod
    def get_group_material(group):
        if not group:
            return None
        material_name = getattr(group, "material_name", "")
        if not material_name:
            return None
        return bpy.data.materials.get(material_name)

    @staticmethod
    def ensure_material_nodes(material):
        material.use_nodes = True
        tree = material.node_tree
        if not tree:
            return None, None

        nodes = tree.nodes
        links = tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)

        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)

        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        return tree, bsdf

    @staticmethod
    def update_material_from_group(group):
        material = PM_MOG_Manager.get_group_material(group)
        if not material:
            return None

        _, bsdf = PM_MOG_Manager.ensure_material_nodes(material)
        if not bsdf:
            return material

        color_socket = bsdf.inputs.get("Base Color") or bsdf.inputs[0]
        roughness_socket = bsdf.inputs.get("Roughness")

        if color_socket:
            color_socket.default_value = tuple(group.base_color)
        if roughness_socket:
            roughness_socket.default_value = group.roughness

        material.diffuse_color = tuple(group.base_color)
        return material

    @staticmethod
    def make_material_name(group):
        slug = sanitize_name(group.name)
        return f"{MATERIAL_PREFIX}{slug}"

    @staticmethod
    def sync_group_material_name(group):
        material = PM_MOG_Manager.get_group_material(group)
        if not material:
            return None

        desired_name = PM_MOG_Manager.make_material_name(group)
        material.name = desired_name
        group.material_name = material.name
        return material

    @staticmethod
    def ensure_group_material(group):
        material = PM_MOG_Manager.get_group_material(group)
        if material:
            PM_MOG_Manager.sync_group_material_name(group)
            PM_MOG_Manager.update_material_from_group(group)
            return material

        material_name = PM_MOG_Manager.make_material_name(group)
        material = bpy.data.materials.new(name=material_name)
        material.use_fake_user = True
        group.material_name = material.name
        PM_MOG_Manager.update_material_from_group(group)
        return material

    @staticmethod
    def get_override_modifier(obj):
        if not obj or obj.type != 'MESH':
            return None
        modifier = obj.modifiers.get(MODIFIER_NAME)
        if modifier and modifier.type == 'NODES':
            return modifier
        return None

    @staticmethod
    def ensure_override_modifier(obj, node_group):
        if not obj or obj.type != 'MESH' or not node_group:
            return None

        modifier = obj.modifiers.get(MODIFIER_NAME)
        if modifier and modifier.type != 'NODES':
            obj.modifiers.remove(modifier)
            modifier = None

        created = False
        if modifier is None:
            modifier = obj.modifiers.new(name=MODIFIER_NAME, type='NODES')
            created = True

        modifier.node_group = node_group

        if created:
            modifier.show_viewport = True
            modifier.show_render = False

        current_index = obj.modifiers.find(modifier.name)
        if current_index > 0:
            try:
                obj.modifiers.move(current_index, 0)
            except Exception:
                pass

        return modifier

    @staticmethod
    def apply_group_to_object(obj, group, node_group=None):
        if not obj or obj.type != 'MESH' or not group:
            return False

        node_group = node_group or PM_MOG_Manager.get_or_load_node_group()
        if not node_group:
            return False

        material = PM_MOG_Manager.ensure_group_material(group)
        modifier = PM_MOG_Manager.ensure_override_modifier(obj, node_group)
        if not modifier or not material:
            return False

        socket_identifier = PM_MOG_Manager.get_socket_identifier(node_group, MATERIAL_SOCKET_NAME)
        if socket_identifier and socket_identifier in modifier:
            modifier[socket_identifier] = material
        elif MATERIAL_SOCKET_IDENTIFIER in modifier:
            modifier[MATERIAL_SOCKET_IDENTIFIER] = material
        else:
            return False

        obj.pm_mog_group_uid = group.uid
        obj.update_tag()
        return True

    @staticmethod
    def clear_override_from_object(obj):
        if not obj or obj.type != 'MESH':
            return False

        modifier = PM_MOG_Manager.get_override_modifier(obj)
        if modifier:
            obj.modifiers.remove(modifier)

        if getattr(obj, "pm_mog_group_uid", ""):
            obj.pm_mog_group_uid = ""

        obj.update_tag()
        return True

    @staticmethod
    def iter_group_objects(scene, group_uid):
        if not group_uid:
            return []
        return [obj for obj in bpy.data.objects if obj.type == 'MESH' and getattr(obj, "pm_mog_group_uid", "") == group_uid]

    @staticmethod
    def count_group_objects(scene, group_uid):
        return len(PM_MOG_Manager.iter_group_objects(scene, group_uid))

    @staticmethod
    def get_scope_managed_objects(context):
        selected_targets = get_selected_target_objects(context)
        if selected_targets:
            return [obj for obj in selected_targets if PM_MOG_Manager.get_override_modifier(obj)]

        return [obj for obj in PM_MOG_Manager.iter_all_mesh_objects() if PM_MOG_Manager.get_override_modifier(obj)]

    @staticmethod
    def get_scope_label(context):
        selected_targets = get_selected_target_objects(context)
        if selected_targets:
            return f"Scope: Selected Targets ({len(selected_targets)})"

        managed_count = len([obj for obj in PM_MOG_Manager.iter_all_mesh_objects() if PM_MOG_Manager.get_override_modifier(obj)])
        return f"Scope: All Managed Objects ({managed_count})"

    @staticmethod
    def get_related_group_instances(scene, group_uid):
        if not scene or not group_uid:
            return []

        group_targets = {obj.as_pointer() for obj in PM_MOG_Manager.iter_group_objects(scene, group_uid)}
        if not group_targets:
            return []

        related = []
        seen_instances = set()

        for obj in scene.objects:
            if not is_collection_instance(obj):
                continue

            resolved_targets = resolve_operable_mesh_targets([obj])
            if not resolved_targets:
                continue

            if not any(target.as_pointer() in group_targets for target in resolved_targets):
                continue

            instance_key = obj.as_pointer()
            if instance_key in seen_instances:
                continue

            seen_instances.add(instance_key)
            related.append(obj)

        return related

    @staticmethod
    def get_selectable_group_objects(context, group_uid):
        if not context or not group_uid:
            return []

        selectable = []
        seen = set()

        view_layer_objects = {obj.as_pointer(): obj for obj in context.view_layer.objects}
        for obj in PM_MOG_Manager.iter_group_objects(context.scene, group_uid):
            object_key = obj.as_pointer()
            if object_key in view_layer_objects and object_key not in seen:
                seen.add(object_key)
                selectable.append(view_layer_objects[object_key])

        for inst in PM_MOG_Manager.get_related_group_instances(context.scene, group_uid):
            inst_key = inst.as_pointer()
            if inst_key not in seen:
                seen.add(inst_key)
                selectable.append(inst)

        return selectable

    @staticmethod
    def describe_group_toggle_state(scene, group_uid, attribute_name):
        objects = PM_MOG_Manager.iter_group_objects(scene, group_uid)
        if not objects:
            return "No Objects"

        values = []
        for obj in objects:
            modifier = PM_MOG_Manager.get_override_modifier(obj)
            if modifier:
                values.append(bool(getattr(modifier, attribute_name)))

        if not values:
            return "No Modifier"
        if all(values):
            return "On"
        if not any(values):
            return "Off"
        return "Mixed"

    @staticmethod
    def sync_group_to_objects(scene, group):
        node_group = PM_MOG_Manager.get_or_load_node_group()
        if not node_group or not group:
            return 0

        PM_MOG_Manager.ensure_group_material(group)

        count = 0
        for obj in PM_MOG_Manager.iter_group_objects(scene, group.uid):
            if PM_MOG_Manager.apply_group_to_object(obj, group, node_group=node_group):
                count += 1
        return count

    @staticmethod
    def refresh_scene(scene):
        if not scene:
            return 0, 0

        node_group = PM_MOG_Manager.get_or_load_node_group()
        if not node_group:
            return 0, 0

        group_lookup = {group.uid: group for group in scene.pm_mog_groups}
        repaired = 0
        removed = 0

        for group in scene.pm_mog_groups:
            PM_MOG_Manager.ensure_group_material(group)

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            group_uid = getattr(obj, "pm_mog_group_uid", "")
            modifier = PM_MOG_Manager.get_override_modifier(obj)

            if group_uid and group_uid in group_lookup:
                if PM_MOG_Manager.apply_group_to_object(obj, group_lookup[group_uid], node_group=node_group):
                    repaired += 1
                continue

            cleaned = False
            if modifier:
                obj.modifiers.remove(modifier)
                cleaned = True
            if group_uid:
                obj.pm_mog_group_uid = ""
                cleaned = True
            if cleaned:
                removed += 1

        return repaired, removed

    @staticmethod
    def remove_group_material(group):
        material = PM_MOG_Manager.get_group_material(group)
        if material:
            group.material_name = ""
            bpy.data.materials.remove(material, do_unlink=True)

    @staticmethod
    def ensure_default_group(scene):
        group = PM_MOG_Manager.get_group_by_name(scene, DEFAULT_GROUP_NAME)
        created = False
        if group is None:
            group = scene.pm_mog_groups.add()
            group.uid = uuid.uuid4().hex
            group.name = DEFAULT_GROUP_NAME
            group.material_name = ""
            group.base_color = DEFAULT_GROUP_COLOR
            group.roughness = DEFAULT_GROUP_ROUGHNESS
            created = True
        PM_MOG_Manager.ensure_group_material(group)
        return group, created

    @staticmethod
    def get_scene_default_fill_candidates(scene):
        if not scene:
            return [], []

        targets = []
        seen_targets = set()
        source_objects = []
        seen_sources = set()

        for obj in scene.objects:
            resolved_targets = []

            if obj.type == 'MESH':
                resolved_targets = [obj]
            elif is_collection_instance(obj):
                resolved_targets = resolve_operable_mesh_targets([obj])

            missing_targets = []
            for target in resolved_targets:
                target_key = target.as_pointer()
                if target_key in seen_targets:
                    continue
                if getattr(target, "pm_mog_group_uid", ""):
                    continue
                seen_targets.add(target_key)
                missing_targets.append(target)
                targets.append(target)

            if missing_targets:
                source_key = obj.as_pointer()
                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    source_objects.append(obj)

        return targets, source_objects


def update_group_material(self, context):
    PM_MOG_Manager.ensure_group_material(self)
    scene = getattr(context, "scene", None)
    if scene:
        PM_MOG_Manager.sync_group_to_objects(scene, self)


def update_group_name(self, context):
    PM_MOG_Manager.sync_group_material_name(self)
    PM_MOG_Manager.ensure_group_material(self)
    scene = getattr(context, "scene", None)
    if scene:
        PM_MOG_Manager.sync_group_to_objects(scene, self)


class PM_MOG_GroupItem(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty(name="UID")
    name: bpy.props.StringProperty(name="Name", default="Group", update=update_group_name)
    base_color: bpy.props.FloatVectorProperty(
        name="Base Color",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
        update=update_group_material,
    )
    roughness: bpy.props.FloatProperty(
        name="Roughness",
        min=0.0,
        max=1.0,
        default=0.5,
        update=update_group_material,
    )
    material_name: bpy.props.StringProperty(name="Material Name")


class PM_UL_MOG_GroupList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.name or "Unnamed Group", icon='MATERIAL')
            count = PM_MOG_Manager.count_group_objects(context.scene, item.uid)
            row.label(text=str(count), icon='MESH_DATA')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='MATERIAL')


class PM_OT_MOG_CreateGroupFromSelection(bpy.types.Operator):
    bl_idname = "pm_mog.create_group_from_selection"
    bl_label = "Create From Selection"
    bl_description = "Create a new override group and assign it to selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(get_selected_target_objects(context))

    def execute(self, context):
        scene = context.scene
        selected_meshes = get_selected_target_objects(context)
        node_group = PM_MOG_Manager.get_or_load_node_group()
        if not node_group:
            self.report({'ERROR'}, f"Asset node group '{NODE_GROUP_NAME}' was not found")
            return {'CANCELLED'}

        group = scene.pm_mog_groups.add()
        group.uid = uuid.uuid4().hex
        group.name = PM_MOG_Manager.next_group_name(scene)
        group.material_name = ""
        PM_MOG_Manager.ensure_group_material(group)
        scene.pm_mog_group_index = len(scene.pm_mog_groups) - 1

        assigned = 0
        for obj in selected_meshes:
            if PM_MOG_Manager.apply_group_to_object(obj, group, node_group=node_group):
                assigned += 1

        self.report({'INFO'}, f"Created '{group.name}' and assigned {assigned} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_AssignToActive(bpy.types.Operator):
    bl_idname = "pm_mog.assign_to_active"
    bl_label = "Assign To Active"
    bl_description = "Assign the active override group to selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(get_selected_target_objects(context)) and PM_MOG_Manager.get_active_group(context.scene) is not None

    def execute(self, context):
        scene = context.scene
        group = PM_MOG_Manager.get_active_group(scene)
        node_group = PM_MOG_Manager.get_or_load_node_group()
        if not group or not node_group:
            self.report({'ERROR'}, "Active group or asset node group is missing")
            return {'CANCELLED'}

        assigned = 0
        for obj in get_selected_target_objects(context):
            if PM_MOG_Manager.apply_group_to_object(obj, group, node_group=node_group):
                assigned += 1

        self.report({'INFO'}, f"Assigned '{group.name}' to {assigned} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_FillMissingWithDefault(bpy.types.Operator):
    bl_idname = "pm_mog.fill_missing_with_default"
    bl_label = "Fill Missing With Default"
    bl_description = "Create or reuse the Default group and assign it to all unassigned mesh and collection-instance targets in the current scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        targets, _ = PM_MOG_Manager.get_scene_default_fill_candidates(getattr(context, "scene", None))
        return bool(targets)

    def execute(self, context):
        scene = context.scene
        node_group = PM_MOG_Manager.get_or_load_node_group()
        if not node_group:
            self.report({'ERROR'}, f"Asset node group '{NODE_GROUP_NAME}' was not found")
            return {'CANCELLED'}

        targets, source_objects = PM_MOG_Manager.get_scene_default_fill_candidates(scene)
        if not targets:
            self.report({'WARNING'}, "No unassigned targets found in the current scene")
            return {'CANCELLED'}

        group, created = PM_MOG_Manager.ensure_default_group(scene)
        for index, item in enumerate(scene.pm_mog_groups):
            if item.uid == group.uid:
                scene.pm_mog_group_index = index
                break

        assigned = 0
        for obj in targets:
            if PM_MOG_Manager.apply_group_to_object(obj, group, node_group=node_group):
                assigned += 1

        if source_objects:
            selectable_objects = {obj.as_pointer(): obj for obj in context.view_layer.objects}
            bpy.ops.object.select_all(action='DESELECT')
            active_object = None
            for obj in source_objects:
                view_obj = selectable_objects.get(obj.as_pointer())
                if view_obj:
                    view_obj.select_set(True)
                    if active_object is None:
                        active_object = view_obj
            if active_object:
                context.view_layer.objects.active = active_object

        action = "Created" if created else "Updated"
        self.report({'INFO'}, f"{action} '{group.name}' and assigned {assigned} unassigned object(s)")
        return {'FINISHED'}


class PM_OT_MOG_SelectGroupObjects(bpy.types.Operator):
    bl_idname = "pm_mog.select_group_objects"
    bl_label = "Select Group Objects"
    bl_description = "Select all objects assigned to the active override group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return PM_MOG_Manager.get_active_group(context.scene) is not None

    def execute(self, context):
        group = PM_MOG_Manager.get_active_group(context.scene)
        objects = PM_MOG_Manager.get_selectable_group_objects(context, group.uid) if group else []
        if not objects:
            self.report({'WARNING'}, "Active group has no selectable objects in the current scene")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)

        context.view_layer.objects.active = objects[0]
        self.report({'INFO'}, f"Selected {len(objects)} object(s) from '{group.name}'")
        return {'FINISHED'}


class PM_OT_MOG_ToggleViewport(bpy.types.Operator):
    bl_idname = "pm_mog.toggle_viewport"
    bl_label = "Viewport On/Off"
    bl_description = "Toggle viewport visibility on selected override objects, or all managed objects if nothing is selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = PM_MOG_Manager.get_scope_managed_objects(context)
        if not objects:
            self.report({'WARNING'}, "No managed override objects found in scope")
            return {'CANCELLED'}

        target = not all(mod.show_viewport for mod in (PM_MOG_Manager.get_override_modifier(obj) for obj in objects) if mod)
        changed = 0
        for obj in objects:
            modifier = PM_MOG_Manager.get_override_modifier(obj)
            if modifier:
                modifier.show_viewport = target
                changed += 1

        state = "enabled" if target else "disabled"
        self.report({'INFO'}, f"Viewport {state} for {changed} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_ToggleRender(bpy.types.Operator):
    bl_idname = "pm_mog.toggle_render"
    bl_label = "Render On/Off"
    bl_description = "Toggle render visibility on selected override objects, or all managed objects if nothing is selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = PM_MOG_Manager.get_scope_managed_objects(context)
        if not objects:
            self.report({'WARNING'}, "No managed override objects found in scope")
            return {'CANCELLED'}

        target = not all(mod.show_render for mod in (PM_MOG_Manager.get_override_modifier(obj) for obj in objects) if mod)
        changed = 0
        for obj in objects:
            modifier = PM_MOG_Manager.get_override_modifier(obj)
            if modifier:
                modifier.show_render = target
                changed += 1

        state = "enabled" if target else "disabled"
        self.report({'INFO'}, f"Render {state} for {changed} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_RemoveOverride(bpy.types.Operator):
    bl_idname = "pm_mog.remove_override"
    bl_label = "Remove From Selected / All"
    bl_description = "Remove override modifiers from selected objects, or from all managed objects if nothing is selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = PM_MOG_Manager.get_scope_managed_objects(context)
        if not objects:
            self.report({'WARNING'}, "No managed override objects found in scope")
            return {'CANCELLED'}

        removed = 0
        for obj in objects:
            if PM_MOG_Manager.clear_override_from_object(obj):
                removed += 1

        self.report({'INFO'}, f"Removed override from {removed} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_DeleteActiveGroup(bpy.types.Operator):
    bl_idname = "pm_mog.delete_active_group"
    bl_label = "Delete Group"
    bl_description = "Delete the active group and remove it from all assigned objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return PM_MOG_Manager.get_active_group(context.scene) is not None

    def execute(self, context):
        scene = context.scene
        group = PM_MOG_Manager.get_active_group(scene)
        if not group:
            self.report({'WARNING'}, "No active group selected")
            return {'CANCELLED'}

        objects = PM_MOG_Manager.iter_group_objects(scene, group.uid)
        for obj in objects:
            PM_MOG_Manager.clear_override_from_object(obj)

        PM_MOG_Manager.remove_group_material(group)

        index = scene.pm_mog_group_index
        scene.pm_mog_groups.remove(index)
        if scene.pm_mog_groups:
            scene.pm_mog_group_index = min(index, len(scene.pm_mog_groups) - 1)
        else:
            scene.pm_mog_group_index = -1

        self.report({'INFO'}, f"Deleted group and cleared {len(objects)} object(s)")
        return {'FINISHED'}


class PM_OT_MOG_RefreshRepair(bpy.types.Operator):
    bl_idname = "pm_mog.refresh_repair"
    bl_label = "Refresh / Repair"
    bl_description = "Repair materials, modifiers, and group assignments for the current scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        repaired, removed = PM_MOG_Manager.refresh_scene(scene)
        self.report({'INFO'}, f"Repair complete: synced {repaired}, cleaned {removed}")
        return {'FINISHED'}


def draw_ui(layout, context):
    scene = context.scene
    if not hasattr(scene, "pm_mog_groups"):
        return

    box = layout.box()

    info_row = box.row()
    info_row.label(text=PM_MOG_Manager.get_scope_label(context), icon='RESTRICT_SELECT_OFF')

    action_row = box.row(align=True)
    action_row.operator(PM_OT_MOG_CreateGroupFromSelection.bl_idname, text="Create From Selection", icon='ADD')
    assign_row = action_row.row(align=True)
    assign_row.enabled = PM_MOG_Manager.get_active_group(scene) is not None and bool(get_selected_target_objects(context))
    assign_row.operator(PM_OT_MOG_AssignToActive.bl_idname, text="Assign To Active", icon='LINKED')

    default_row = box.row(align=True)
    default_row.operator(PM_OT_MOG_FillMissingWithDefault.bl_idname, text="Fill Missing With Default", icon='SHADING_SOLID')
    default_row.operator(PM_OT_MOG_RefreshRepair.bl_idname, text="Refresh / Repair", icon='FILE_REFRESH')

    utility_row = box.row(align=True)
    utility_row.operator(PM_OT_MOG_RemoveOverride.bl_idname, text="Remove From Selected / All", icon='X')

    toggle_row = box.row(align=True)
    toggle_row.operator(PM_OT_MOG_ToggleViewport.bl_idname, text="Viewport On/Off", icon='HIDE_OFF')
    toggle_row.operator(PM_OT_MOG_ToggleRender.bl_idname, text="Render On/Off", icon='RESTRICT_RENDER_OFF')

    if not scene.pm_mog_groups:
        box.separator()
        box.label(text="No override groups yet.", icon='INFO')
        box.label(text="Select mesh objects and create the first group.")
        return

    box.separator()
    box.label(text="Groups:")

    row = box.row()
    row.template_list(
        "PM_UL_MOG_GroupList",
        "",
        scene,
        "pm_mog_groups",
        scene,
        "pm_mog_group_index",
        rows=4,
    )

    active_group = PM_MOG_Manager.get_active_group(scene)
    if not active_group:
        return

    box.separator()
    box.label(text="Active Group:")
    props = box.column(align=True)
    props.prop(active_group, "name", text="Name")
    props.prop(active_group, "base_color", text="Base Color")
    props.prop(active_group, "roughness", text="Roughness", slider=True)

    count = PM_MOG_Manager.count_group_objects(scene, active_group.uid)
    box.label(text=f"Assigned Objects: {count}", icon='MESH_DATA')
    box.label(
        text=f"Viewport State: {PM_MOG_Manager.describe_group_toggle_state(scene, active_group.uid, 'show_viewport')}",
        icon='HIDE_OFF',
    )
    box.label(
        text=f"Render State: {PM_MOG_Manager.describe_group_toggle_state(scene, active_group.uid, 'show_render')}",
        icon='RESTRICT_RENDER_OFF',
    )

    action_row = box.row(align=True)
    action_row.operator(PM_OT_MOG_SelectGroupObjects.bl_idname, text="Select Group Objects", icon='RESTRICT_SELECT_OFF')
    action_row.operator(PM_OT_MOG_DeleteActiveGroup.bl_idname, text="Delete Group", icon='TRASH')


classes = (
    PM_MOG_GroupItem,
    PM_UL_MOG_GroupList,
    PM_OT_MOG_CreateGroupFromSelection,
    PM_OT_MOG_AssignToActive,
    PM_OT_MOG_FillMissingWithDefault,
    PM_OT_MOG_SelectGroupObjects,
    PM_OT_MOG_ToggleViewport,
    PM_OT_MOG_ToggleRender,
    PM_OT_MOG_RemoveOverride,
    PM_OT_MOG_DeleteActiveGroup,
    PM_OT_MOG_RefreshRepair,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.pm_mog_groups = bpy.props.CollectionProperty(type=PM_MOG_GroupItem)
    bpy.types.Scene.pm_mog_group_index = bpy.props.IntProperty(default=-1)
    bpy.types.Object.pm_mog_group_uid = bpy.props.StringProperty(name="PM MOG Group UID", default="")


def unregister():
    if hasattr(bpy.types.Object, "pm_mog_group_uid"):
        del bpy.types.Object.pm_mog_group_uid
    if hasattr(bpy.types.Scene, "pm_mog_group_index"):
        del bpy.types.Scene.pm_mog_group_index
    if hasattr(bpy.types.Scene, "pm_mog_groups"):
        del bpy.types.Scene.pm_mog_groups

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
