import bpy
import os

# --- 1. CONSTANTS & CONFIGURATION ---
UI_CATEGORY = "MATERIAL_OVERRIDE"
UI_HIDDEN = True
NODE_GROUP_NAME = "PAPL_MaterialOverride"
ASSET_FILENAME = "node_library.blend"
OVERRIDE_NODE_NAME = "PAPL_Override_Instance"

# Input Socket Constants (Must match Asset)
SOCK_SHADER = "Shader"
SOCK_ON_OFF = "On_Off"

# --- 2. DATA STRUCTURES ---

class PM_ExcludeItem(bpy.types.PropertyGroup):
    """Item for the manual exclusion list."""
    name: bpy.props.StringProperty(name="Material Name")

class PM_UL_ExcludeList(bpy.types.UIList):
    """UI List definition for exclusions."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name, icon='MATERIAL')

# --- 3. MANAGER CLASS ---

class MaterialOverrideManager:
    """
    Core logic handler for Material Override system.
    Implements optimized global updates and robust node handling.
    """
    
    @staticmethod
    def get_assets_path():
        """Get absolute path to asset blend file."""
        modules_dir = os.path.dirname(os.path.abspath(__file__))
        addon_root = os.path.dirname(modules_dir)
        return os.path.join(addon_root, "assets", ASSET_FILENAME)

    @staticmethod
    def get_or_load_node_group():
        """
        Get the node group datablock, appending if missing.
        Returns bpy.types.NodeTree or None.
        """
        if NODE_GROUP_NAME in bpy.data.node_groups:
            return bpy.data.node_groups[NODE_GROUP_NAME]
        
        filepath = MaterialOverrideManager.get_assets_path()
        if not os.path.exists(filepath):
            print(f"[PM Tools] ERROR: Asset file missing: {filepath}")
            return None

        # Only print loading message if actually loading
        print(f"[PM Tools] Loading Asset '{NODE_GROUP_NAME}' from disk...")
        try:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                if NODE_GROUP_NAME in data_from.node_groups:
                    data_to.node_groups = [NODE_GROUP_NAME]
            
            if data_to.node_groups:
                return data_to.node_groups[0]
        except Exception as e:
            print(f"[PM Tools] ERROR Loading Asset: {e}")
            
        return None

    @staticmethod
    def update_internal_shader_value(ng, input_type, value):
        """
        Updates the internal 'Principled BSDF' node inside the node group.
        input_type: 'COLOR' or 'ROUGHNESS'
        """
        if not ng: return

        # Find the Principled BSDF node
        bsdf = None
        for node in ng.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        
        if not bsdf:
            bsdf = ng.nodes.get("Principled BSDF")

        if bsdf:
            if input_type == 'COLOR':
                if len(bsdf.inputs) > 0:
                     bsdf.inputs[0].default_value = value
            elif input_type == 'ROUGHNESS':
                sock = bsdf.inputs.get("Roughness")
                if sock:
                    sock.default_value = value

    @staticmethod
    def _update_socket_value(node, target_val):
        """Helper to safely set On_Off socket on an instance node."""
        socket = node.inputs.get(SOCK_ON_OFF)
        if not socket: socket = node.inputs.get("on_off")
        if not socket: socket = node.inputs.get("Enable")
        
        if socket and socket.default_value != target_val:
            try:
                socket.default_value = int(target_val)
            except TypeError:
                socket.default_value = target_val

    @staticmethod
    def update_material(mat, ng_data, global_enabled, auto_keywords, manual_exclude_set, create_if_missing):
        """
        Update a single material's override state.
        create_if_missing: If False, skips material if override node not found.
        """
        if not mat or not mat.use_nodes:
            return

        tree = mat.node_tree
        if not tree: return

        # --- Exclusion Logic ---
        is_excluded = False
        name_lower = mat.name.lower()
        
        if name_lower in manual_exclude_set:
            is_excluded = True
        
        if not is_excluded and auto_keywords:
            for key in auto_keywords:
                if key in name_lower:
                    is_excluded = True
                    break
        
        should_be_active = global_enabled and not is_excluded
        target_val = 1 if should_be_active else 0

        # --- Node Insertion/Update Logic ---
        outputs = [n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL']
        
        for output_node in outputs:
            surface_socket = output_node.inputs.get("Surface")
            if not surface_socket:
                continue
                
            # Check for existing override
            existing_override = None
            if surface_socket.is_linked:
                link = surface_socket.links[0]
                from_node = link.from_node
                if from_node.type == 'GROUP' and from_node.node_tree == ng_data:
                    existing_override = from_node
            
            # --- DECISION POINT ---
            if existing_override:
                # Always update if exists
                MaterialOverrideManager._update_socket_value(existing_override, target_val)
            else:
                # Does not exist. Create?
                if not create_if_missing:
                    # Skip creation
                    continue
                
                # Create and Link
                override_node = tree.nodes.new('ShaderNodeGroup')
                override_node.node_tree = ng_data
                override_node.name = OVERRIDE_NODE_NAME
                override_node.location = (output_node.location.x - 300, output_node.location.y)
                
                MaterialOverrideManager._update_socket_value(override_node, target_val)
                
                if surface_socket.is_linked:
                    # Insert
                    link = surface_socket.links[0]
                    orig_socket = link.from_socket
                    tree.links.remove(link)
                    
                    if len(override_node.inputs) > 0:
                        tree.links.new(orig_socket, override_node.inputs[0])
                    tree.links.new(override_node.outputs[0], surface_socket)
                else:
                    # Just Connect
                    tree.links.new(override_node.outputs[0], surface_socket)

    @staticmethod
    def update_all(scene, create_if_missing=False):
        """
        Smart/Optimized Refresh Loop.
        create_if_missing: Controls aggressive node creation.
        """
        if not scene: return
        
        ng_data = MaterialOverrideManager.get_or_load_node_group()
        if not ng_data: return

        # --- Pre-calculation ---
        global_enabled = scene.pm_override_enabled
        
        auto_keywords = []
        if scene.pm_override_use_keywords:
            raw_str = scene.pm_override_auto_list
            if raw_str:
                auto_keywords = [k.strip().lower() for k in raw_str.split(",") if k.strip()]
        
        manual_exclude_set = {item.name.lower() for item in scene.pm_override_exclude_list}
        
        # --- Iteration ---
        for mat in bpy.data.materials:
            MaterialOverrideManager.update_material(mat, ng_data, global_enabled, auto_keywords, manual_exclude_set, create_if_missing)

    @staticmethod
    def remove_all_overrides(context):
        """Clean removal of all override instances."""
        ng_data = MaterialOverrideManager.get_or_load_node_group()
        if not ng_data: return 0
        
        count = 0
        for mat in bpy.data.materials:
            if not mat.use_nodes: continue
            tree = mat.node_tree
            if not tree: continue
            
            to_remove = [n for n in tree.nodes if n.type == 'GROUP' and n.node_tree == ng_data]
            
            for node in to_remove:
                input_link = None
                if len(node.inputs) > 0 and node.inputs[0].is_linked:
                    input_link = node.inputs[0].links[0]
                
                output_link = None
                if len(node.outputs) > 0 and node.outputs[0].is_linked:
                    output_link = node.outputs[0].links[0]
                    
                if input_link and output_link:
                    tree.links.new(input_link.from_socket, output_link.to_socket)
                    
                tree.nodes.remove(node)
                count += 1
                
        return count

# --- 4. PROPERTY CALLBACKS ---

def update_override_enable(self, context):
    """Callback for MAIN enable toggle. Creates nodes if missing."""
    MaterialOverrideManager.update_all(self, create_if_missing=True)

def update_override_settings(self, context):
    """Callback for customization settings. Only updates EXISTING nodes."""
    MaterialOverrideManager.update_all(self, create_if_missing=False)

def update_override_color(self, context):
    """Updates internal Principled BSDF color."""
    ng = MaterialOverrideManager.get_or_load_node_group()
    if ng:
        MaterialOverrideManager.update_internal_shader_value(ng, 'COLOR', self.pm_override_color)

def update_override_roughness(self, context):
    """Updates internal Principled BSDF roughness."""
    ng = MaterialOverrideManager.get_or_load_node_group()
    if ng:
        MaterialOverrideManager.update_internal_shader_value(ng, 'ROUGHNESS', self.pm_override_roughness)

# --- 5. OPERATORS ---

class PM_OT_SetupOverride(bpy.types.Operator):
    bl_idname = "pm.setup_material_override"
    bl_label = "Refresh / Setup"
    bl_description = "Force re-check of all materials and create override nodes if missing"
    
    def execute(self, context):
        # Manual Setup -> Create Nodes
        MaterialOverrideManager.update_all(context.scene, create_if_missing=True)
        self.report({'INFO'}, "Material Override Refreshed")
        return {'FINISHED'}

class PM_OT_ExcludeActive(bpy.types.Operator):
    bl_idname = "pm.exclude_active_material"
    bl_label = "Exclude Active"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.active_material

    def execute(self, context):
        mat = context.active_object.active_material
        scene = context.scene
        
        target_name = mat.name.lower()
        exists = any(item.name.lower() == target_name for item in scene.pm_override_exclude_list)
        
        if not exists:
            item = scene.pm_override_exclude_list.add()
            item.name = mat.name
            self.report({'INFO'}, f"Excluded '{mat.name}'")
            # Only update existing nodes, don't force create on others
            MaterialOverrideManager.update_all(scene, create_if_missing=False)
            
        return {'FINISHED'}

class PM_OT_IncludeActive(bpy.types.Operator):
    bl_idname = "pm.include_active_material"
    bl_label = "Include Active"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.active_material

    def execute(self, context):
        mat = context.active_object.active_material
        scene = context.scene
        
        target_name = mat.name.lower()
        idx = -1
        for i, item in enumerate(scene.pm_override_exclude_list):
            if item.name.lower() == target_name:
                idx = i
                break
        
        if idx != -1:
            scene.pm_override_exclude_list.remove(idx)
            self.report({'INFO'}, f"Included '{mat.name}'")
            # Only update existing nodes
            MaterialOverrideManager.update_all(scene, create_if_missing=False)
        else:
            self.report({'WARNING'}, f"'{mat.name}' not in exclusion list")

        return {'FINISHED'}

class PM_OT_RemoveExcludeItem(bpy.types.Operator):
    bl_idname = "pm.remove_exclude_item"
    bl_label = "Remove Selected"
    
    @classmethod
    def poll(cls, context):
        return len(context.scene.pm_override_exclude_list) > 0
        
    def execute(self, context):
        scene = context.scene
        idx = scene.pm_override_exclude_index
        if 0 <= idx < len(scene.pm_override_exclude_list):
            scene.pm_override_exclude_list.remove(idx)
            if scene.pm_override_exclude_index >= len(scene.pm_override_exclude_list):
                scene.pm_override_exclude_index = max(0, len(scene.pm_override_exclude_list) - 1)
            # Only update existing
            MaterialOverrideManager.update_all(scene, create_if_missing=False)
        return {'FINISHED'}

class PM_OT_ClearManualExclusions(bpy.types.Operator):
    bl_idname = "pm.clear_manual_exclusions"
    bl_label = "Clear List"
    
    def execute(self, context):
        context.scene.pm_override_exclude_list.clear()
        MaterialOverrideManager.update_all(context.scene, create_if_missing=False)
        return {'FINISHED'}

class PM_OT_RemoveOverride(bpy.types.Operator):
    bl_idname = "pm.remove_material_override"
    bl_label = "Remove All Overrides"
    bl_description = "Remove override nodes and restore original links"
    
    def execute(self, context):
        count = MaterialOverrideManager.remove_all_overrides(context)
        self.report({'INFO'}, f"Removed override from {count} materials")
        return {'FINISHED'}

# --- 6. UI DRAWING ---

def draw_ui(layout, context):
    scene = context.scene
    
    box = layout.box()
    row = box.row()
    row.alignment = 'CENTER'
    row.label(text="Material Override", icon='SHADING_RENDERED')
    
    col = box.column(align=True)
    
    row = col.row()
    row.scale_y = 1.5
    row.prop(scene, "pm_override_enabled", text="Enable Override", toggle=True)
    
    col.separator()
    
    col.label(text="Global Settings:")
    sub = col.column(align=True)
    sub.prop(scene, "pm_override_color", text="")
    sub.prop(scene, "pm_override_roughness", text="Roughness", slider=True)
    
    col.separator()
    
    col.label(text="Auto-Exclude:")
    sub = col.column(align=True)
    sub.prop(scene, "pm_override_use_keywords", text="By Keywords")
    if scene.pm_override_use_keywords:
        sub.prop(scene, "pm_override_auto_list", text="")

    col.separator()

    col.label(text="Manual Exclusion:")
    row = col.row()
    row.template_list("PM_UL_ExcludeList", "", scene, "pm_override_exclude_list", scene, "pm_override_exclude_index", rows=4)
    
    c = row.column(align=True)
    c.operator(PM_OT_RemoveExcludeItem.bl_idname, text="", icon='REMOVE')
    c.operator(PM_OT_ClearManualExclusions.bl_idname, text="", icon='TRASH')
    
    row = col.row(align=True)
    row.operator(PM_OT_ExcludeActive.bl_idname, icon='HIDE_ON', text="Exclude Active")
    row.operator(PM_OT_IncludeActive.bl_idname, icon='HIDE_OFF', text="Include Active")
    
    col.separator()
    
    row = col.row(align=True)
    row.operator(PM_OT_SetupOverride.bl_idname, text="Force Refresh", icon='FILE_REFRESH')
    row.operator(PM_OT_RemoveOverride.bl_idname, text="Remove All", icon='X')

# --- 7. REGISTRATION ---

classes = (
    PM_ExcludeItem,
    PM_UL_ExcludeList,
    PM_OT_SetupOverride,
    PM_OT_ExcludeActive,
    PM_OT_IncludeActive,
    PM_OT_RemoveExcludeItem,
    PM_OT_ClearManualExclusions,
    PM_OT_RemoveOverride,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.pm_override_enabled = bpy.props.BoolProperty(
        name="Enable Override", default=False, update=update_override_enable # USES ENABLE CALLBACK (True)
    )
    bpy.types.Scene.pm_override_color = bpy.props.FloatVectorProperty(
        name="Override Color", subtype='COLOR', size=4, 
        default=(0.5, 0.5, 0.5, 1.0), min=0.0, max=1.0, 
        update=update_override_color
    )
    bpy.types.Scene.pm_override_roughness = bpy.props.FloatProperty(
        name="Override Roughness", default=0.5, min=0.0, max=1.0, 
        update=update_override_roughness
    )
    
    bpy.types.Scene.pm_override_use_keywords = bpy.props.BoolProperty(
        name="Use Keywords", default=True, update=update_override_settings # USES SETTINGS CALLBACK (False)
    )
    bpy.types.Scene.pm_override_auto_list = bpy.props.StringProperty(
        name="Keywords", default="glass, mirror, led", update=update_override_settings # USES SETTINGS CALLBACK (False)
    )
    
    bpy.types.Scene.pm_override_exclude_list = bpy.props.CollectionProperty(type=PM_ExcludeItem)
    bpy.types.Scene.pm_override_exclude_index = bpy.props.IntProperty()
    # Note: CollectionProperty doesn't have an update arg on the property itself, 
    # but the Operators manipulating it call update_all(False).

def unregister():
    del bpy.types.Scene.pm_override_enabled
    del bpy.types.Scene.pm_override_color
    del bpy.types.Scene.pm_override_roughness
    del bpy.types.Scene.pm_override_use_keywords
    del bpy.types.Scene.pm_override_auto_list
    del bpy.types.Scene.pm_override_exclude_list
    del bpy.types.Scene.pm_override_exclude_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
