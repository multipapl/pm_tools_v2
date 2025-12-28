import bpy
import os
import mathutils

UI_CATEGORY = "SCENE_OPTIMIZATION"

# --- SYNC LOGIC ---

def get_socket_identifier(node_group, socket_name):
    """
    Retrieve the internal identifier for a node group socket by its display name.
    Supports Blender 4.0+ interface API and older inputs/outputs lists.
    """
    if hasattr(node_group, "interface"):
        for item in node_group.interface.items:
            if item.item_type == 'INPUT' and item.name == socket_name:
                return item.identifier
    elif hasattr(node_group, "inputs"):
        for input_socket in node_group.inputs:
            if input_socket.name == socket_name:
                return input_socket.identifier
    return None

def sync_proxy_param(settings, context, socket_name, prop_name, forced_id=None):
    """
    Synchronizes a PropertyGroup property with Geometry Nodes modifier inputs.
    Updates all selected mesh objects containing a 'Proxy' modifier.
    Only proceeds if there is a valid selection.
    """
    if not context or not context.selected_objects or getattr(settings, "is_fetching", False):
        return
        
    prop_value = getattr(settings, prop_name)

    for obj in context.selected_objects:
        if obj.type == 'MESH' and "Proxy" in obj.modifiers:
            mod = obj.modifiers["Proxy"]
            if mod.type == 'NODES' and mod.node_group:
                target_id = forced_id or get_socket_identifier(mod.node_group, socket_name)
                
                if target_id and target_id in mod:
                    try:
                        mod[target_id] = prop_value
                        obj.update_tag()
                    except:
                        pass

def sync_proxy_color_all_channels(settings, context):
    """
    Synchronizes the proxy color across Material, Object, and Geometry Nodes.
    Only proceeds if there is a valid selection to prevent inconsistent global state.
    """
    if not context or not context.selected_objects or getattr(settings, "is_fetching", False):
        return
        
    color = settings.proxy_color
    color_rgba = (color[0], color[1], color[2], 1.0)
    
    # 1. Sync Shared Material (papl_ProxyColor)
    mat = bpy.data.materials.get("papl_ProxyColor")
    if mat:
        mat.diffuse_color = color_rgba
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if "Base Color" in node.inputs:
                    node.inputs["Base Color"].default_value = color_rgba

    # 2. Sync Selected Objects (Object Color + GN Input)
    for obj in context.selected_objects:
        if obj.type == 'MESH' and "Proxy" in obj.modifiers:
            # Update Object Viewport Color
            obj.color = color_rgba
            
            # Update GN Input
            mod = obj.modifiers["Proxy"]
            if mod.type == 'NODES' and mod.node_group:
                target_id = "Input_12"
                if target_id not in mod:
                    target_id = get_socket_identifier(mod.node_group, "Proxy color")
                
                if target_id and target_id in mod:
                    try:
                        mod[target_id] = color_rgba
                    except:
                        pass
            
            obj.update_tag()

# --- UPDATE CALLBACKS ---

def update_density(self, context): 
    sync_proxy_param(self, context, "Point density", "point_density", "Input_15")

def update_radius(self, context): 
    sync_proxy_param(self, context, "Point radius", "point_radius", "Input_17")

def update_color(self, context): 
    sync_proxy_color_all_channels(self, context)

# --- PROPERTY GROUP ---

class PM_ProxySettings(bpy.types.PropertyGroup):
    """Scene-level settings for batch-controlling Proxy modifiers and materials."""
    
    is_fetching: bpy.props.BoolProperty(
        name="Fetching State",
        description="Internal flag to prevent recursion during setting synchronization",
        default=False
    )
    
    point_density: bpy.props.FloatProperty(
        name="Density", 
        description="Controls the density of points in the proxy view",
        default=10.0, 
        min=0.0, 
        update=update_density
    )
    
    point_radius: bpy.props.FloatProperty(
        name="Size", 
        description="Controls the display size of proxy points",
        default=0.02, 
        min=0.0, 
        unit='LENGTH', 
        update=update_radius
    )
    
    proxy_color: bpy.props.FloatVectorProperty(
        name="Main Color", 
        description="Synchronized color for materials, object viewport, and proxy geometry",
        subtype='COLOR', 
        default=(0.129420, 0.186190, 0.087890), 
        size=3, 
        update=update_color
    )

# --- HELPERS ---

def get_proxy_node_group():
    """Returns the 'papl_proxy' node group, appending it from assets if necessary."""
    group_name = "papl_proxy"
    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]
    
    addon_dir = os.path.dirname(os.path.dirname(__file__))
    blend_path = os.path.join(addon_dir, "assets", "node_library.blend")
    
    if not os.path.exists(blend_path):
        return None
    
    try:
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            if group_name in data_from.node_groups:
                data_to.node_groups = [group_name]
        return bpy.data.node_groups.get(group_name)
    except:
        return None

# --- OPERATORS ---

class PM_OT_AddProxyModifier(bpy.types.Operator):
    """Applies the documentation-compliant Proxy modifier to selected meshes."""
    bl_idname = "pm.add_proxy_modifier"
    bl_label = "Add Proxy"
    bl_description = "Add a Geometry Nodes based Proxy modifier to selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        node_group = get_proxy_node_group()
        
        if not node_group:
            self.report({'ERROR'}, "Required asset 'papl_proxy' not found in library")
            return {'CANCELLED'}
        
        settings = context.scene.pm_proxy_settings
        color_rgba = (settings.proxy_color[0], settings.proxy_color[1], settings.proxy_color[2], 1.0)
        
        for obj in selected_meshes:
            if "Proxy" not in obj.modifiers:
                mod = obj.modifiers.new(name="Proxy", type='NODES')
                mod.node_group = node_group
                mod.show_viewport = True
                mod.show_render = False
                
                # Apply initial synchronization
                obj.color = color_rgba
                target_id = "Input_12"
                if target_id not in mod:
                    target_id = get_socket_identifier(node_group, "Proxy color")
                    
                if target_id and target_id in mod:
                    try: mod[target_id] = color_rgba
                    except: pass
                    
        return {'FINISHED'}

class PM_OT_ToggleProxy(bpy.types.Operator):
    """Toggles viewport visibility of the Proxy modifier for selected objects."""
    bl_idname = "pm.toggle_proxy"
    bl_label = "Toggle Proxy Visibility"
    bl_description = "Toggle viewport visibility for all modifiers named 'Proxy'"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("Proxy" in obj.modifiers for obj in context.selected_objects)

    def execute(self, context):
        for obj in context.selected_objects:
            if "Proxy" in obj.modifiers:
                mod = obj.modifiers["Proxy"]
                mod.show_viewport = not mod.show_viewport
        return {'FINISHED'}

class PM_OT_CopyProxySettings(bpy.types.Operator):
    """Copies settings from the active object's Proxy to all selected objects."""
    bl_idname = "pm.copy_proxy_settings"
    bl_label = "Copy from Active"
    bl_description = "Copy Density, Size, and Color from the active object and apply to all selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and "Proxy" in context.active_object.modifiers

    def execute(self, context):
        active_obj = context.active_object
        mod = active_obj.modifiers.get("Proxy")
        if not mod or not mod.node_group:
            self.report({'ERROR'}, "Active object has no 'Proxy' modifier")
            return {'CANCELLED'}
            
        settings = context.scene.pm_proxy_settings
        
        # We don't use is_fetching because we WANT update callbacks to fire
        # and distribute settings to all SELECTED objects.
        
        mapping = {
            "point_density": ("Point density", "Input_15"), 
            "point_radius": ("Point radius", "Input_17"),
            "proxy_color": ("Proxy color", "Input_12")
        }
        
        for prop_name, (socket_name, forced_id) in mapping.items():
            target_id = forced_id if forced_id in mod else get_socket_identifier(mod.node_group, socket_name)
            if target_id and target_id in mod:
                val = mod[target_id]
                if hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
                    if len(val) >= 3:
                        setattr(settings, prop_name, val[:3])
                else:
                    setattr(settings, prop_name, val)
        
        # Also sync material color explicitly from the active state
        mat = bpy.data.materials.get("papl_ProxyColor")
        if mat:
            settings.proxy_color = mat.diffuse_color[:3]
            
        self.report({'INFO'}, "Settings copied from active object to selection")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout, context):
    """Renders the Proxy Tools panel in the N-panel."""
    scene = context.scene
    if not hasattr(scene, "pm_proxy_settings"): 
        return
        
    settings = scene.pm_proxy_settings
    box = layout.box()
    
    # Title
    box.label(text="Proxy Tools", icon='NODETREE')
    
    # Main Actions
    row = box.row(align=True)
    row.operator("pm.add_proxy_modifier", text="Add Proxy", icon='ADD')
    row.operator("pm.toggle_proxy", text="On/Off", icon='HIDE_OFF')
    
    # Copy from Active
    box.operator("pm.copy_proxy_settings", text="Copy from Active", icon='PASTEDOWN')
    
    # Parameter Controls
    col = box.column(align=True)
    col.label(text="Parameters:")
    col.prop(settings, "point_density")
    col.prop(settings, "point_radius")
    
    # Material Style Control
    col.prop(settings, "proxy_color", text="Main Color")

# --- REGISTRATION ---

classes = (
    PM_ProxySettings,
    PM_OT_AddProxyModifier,
    PM_OT_ToggleProxy,
    PM_OT_CopyProxySettings,
)

def register():
    """Register classes and property group for the Proxy module."""
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except:
            pass
    bpy.types.Scene.pm_proxy_settings = bpy.props.PointerProperty(type=PM_ProxySettings)

def unregister():
    """Unregister classes and clean up scene properties."""
    if hasattr(bpy.types.Scene, "pm_proxy_settings"):
        del bpy.types.Scene.pm_proxy_settings
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass
