import bpy
import json
import os

UI_CATEGORY = "SCENE_MANAGEMENT"

# --- HELPERS ---

def get_presets_path():
    """Returns absolute path to layer_presets.json."""
    addon_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(addon_dir, "assets", "layer_presets.json")

def load_layer_presets():
    """Loads presets from JSON file."""
    path = get_presets_path()
    if not os.path.exists(path):
        return {"defaults": {}, "user": {}}
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "defaults" not in data:
                data["defaults"] = {}
            if "user" not in data:
                data["user"] = {}
            return data
    except Exception as e:
        print(f"Error loading layer presets: {e}")
        return {"defaults": {}, "user": {}}

def get_next_preset_name(base_name="User_Preset"):
    """Finds a unique incremented name for a new preset."""
    presets = load_layer_presets()
    user_presets = presets.get("user", {})
    
    if base_name not in user_presets:
        return base_name
        
    i = 1
    while f"{base_name}_{i:02d}" in user_presets:
        i += 1
    return f"{base_name}_{i:02d}"

# --- LOGIC ---

def create_collection_logic(context, name, parent=None, color_tag='DEFAULT', disable_in_render=False):
    """Helper to create or get a collection and link it to a parent."""
    collection = bpy.data.collections.get(name)
    if not collection:
        collection = bpy.data.collections.new(name)
        if parent:
            parent.children.link(collection)
        else:
            context.scene.collection.children.link(collection)
            
    collection.color_tag = color_tag
    if disable_in_render:
        collection.hide_render = True
        
    return collection

def create_nested_structure_logic(context, structure_dict, project_name, parent_coll=None):
    """Recursively creates a nested collection structure from a dictionary."""
    for raw_name, value in structure_dict.items():
        # Skip reserved technical keys
        if raw_name in ("color", "disable_in_render"):
            continue

        # Replace placeholder in names
        name = raw_name.replace("{PROJECT_NAME}", project_name)
        
        if isinstance(value, dict):
            color = value.get("color", "DEFAULT")
            disable_in_render = value.get("disable_in_render", False)
            new_parent = create_collection_logic(context, name, parent_coll, color, disable_in_render)
            
            sub_structure = {k: v for k, v in value.items() if k not in ("color", "disable_in_render")}
            if sub_structure:
                create_nested_structure_logic(context, sub_structure, project_name, new_parent)
        else:
            create_collection_logic(context, name, parent_coll, value, False)

def create_preset_logic(context, preset_key, project_name):
    """Entry point for creating a preset structure from JSON."""
    presets_data = load_layer_presets()
    
    # Search in defaults then users
    structure = presets_data.get("defaults", {}).get(preset_key)
    if not structure:
        structure = presets_data.get("user", {}).get(preset_key)
        
    if not structure:
        return f"Preset '{preset_key}' not found in assets/layer_presets.json"
    
    create_nested_structure_logic(context, structure, project_name)
    return None

def collection_to_dict(collection, project_name=None):
    """
    Converts a collection and its children to a dictionary structure.
    This captures the FULL tree including the collection itself.
    """
    data = {}
    
    # Add collection properties
    if collection.color_tag != 'DEFAULT':
        data["color"] = collection.color_tag
    if collection.hide_render:
        data["disable_in_render"] = True
    
    # Recursively add children
    for child in collection.children:
        child_name = child.name
        if project_name and child_name == project_name:
            child_name = "{PROJECT_NAME}"
        
        data[child_name] = collection_to_dict(child, project_name)
    
    return data

def save_preset_logic(context, preset_name, project_name, col_names_list=None):
    """
    Saves the specified collections into JSON.
    Returns None on success, error message string on failure.
    """
    selected_cols = []
    
    if col_names_list:
        # Resolve names to actual collection objects
        for name in col_names_list:
            if name in bpy.data.collections:
                selected_cols.append(bpy.data.collections[name])
    
    # Fallback to active layer collection if nothing selected
    if not selected_cols and context.view_layer.active_layer_collection:
        active_col = context.view_layer.active_layer_collection.collection
        if active_col != context.scene.collection:
            selected_cols = [active_col]

    if not selected_cols:
        return "Please select at least one collection in the Outliner to save as a preset."

    # Build the preset structure
    if len(selected_cols) == 1:
        col = selected_cols[0]
        root_name = col.name
        if project_name and root_name == project_name:
            root_name = "{PROJECT_NAME}"
        full_structure = {root_name: collection_to_dict(col, project_name)}
    else:
        # Multiple collections selected
        full_structure = {}
        for col in selected_cols:
            name = col.name
            if project_name and name == project_name:
                name = "{PROJECT_NAME}"
            full_structure[name] = collection_to_dict(col, project_name)
    
    # Save to file under 'user' section
    presets_data = load_layer_presets()
    if "user" not in presets_data:
        presets_data["user"] = {}
    
    presets_data["user"][preset_name] = full_structure
    
    path = get_presets_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(presets_data, f, indent=4)
        return None
    except Exception as e:
        return str(e)

def delete_preset_logic(preset_name):
    """
    Deletes a user preset from JSON.
    Returns None on success, error message string on failure.
    """
    presets_data = load_layer_presets()
    
    if preset_name not in presets_data.get("user", {}):
        return f"Preset '{preset_name}' not found in user presets"
    
    del presets_data["user"][preset_name]
    
    path = get_presets_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(presets_data, f, indent=4)
        return None
    except Exception as e:
        return str(e)

# --- SETTINGS / PROPERTIES ---

def get_preset_items(self, context):
    """Dynamic Enum items from JSON keys, organized by Default and User."""
    presets_data = load_layer_presets()
    
    items = [("NONE", "Select Preset...", "Choose a structure to create", 'NONE', 0)]
    index = 1
    
    if not presets_data:
        return items
    
    # Default presets
    defaults = presets_data.get("defaults", {})
    for k in sorted(defaults.keys()):
        label = k.replace("_", " ").title()
        items.append((k, f"Default: {label}", f"Standard preset: {k}", 'BOOKMARKS', index))
        index += 1
        
    # User presets
    user = presets_data.get("user", {})
    if user:
        for k in sorted(user.keys()):
            label = k.replace("_", " ").title()
            items.append((k, f"User: {label}", f"Custom user preset: {k}", 'USER', index))
            index += 1
            
    return items

class PM_LayerManagementSettings(bpy.types.PropertyGroup):
    active_preset: bpy.props.EnumProperty(
        name="Preset",
        description="Select a collection structure preset",
        items=get_preset_items
    )

# --- OPERATORS ---

class PM_OT_CreateLayerSet(bpy.types.Operator):
    """Generates the selected collection structure from presets"""
    bl_idname = "pm.create_layer_set"
    bl_label = "Create Layers Set"
    bl_options = {'REGISTER', 'UNDO'}

    main_collection_name: bpy.props.StringProperty(
        name="Project Name",
        default="ProjectName"
    )

    def execute(self, context):
        settings = context.scene.pm_layer_mgmt
        if settings.active_preset == "NONE":
            self.report({'ERROR'}, "No presets available")
            return {'CANCELLED'}
            
        error = create_preset_logic(context, settings.active_preset, self.main_collection_name)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
            
        self.report({'INFO'}, f"Layers created: {settings.active_preset}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class PM_OT_SaveCurrentAsPreset(bpy.types.Operator):
    """Saves the current collection hierarchy as a new preset in assets/layer_presets.json"""
    bl_idname = "pm.save_current_as_preset"
    bl_label = "Add Current as Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty(
        name="New Preset Name",
        default="My_Preset"
    )
    project_name_in_scene: bpy.props.StringProperty(
        name="Project Name to Replace",
        default="ProjectName"
    )
    
    # Hidden property to store selection from Outliner (captured in invoke)
    selected_cols_csv: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        col_names = self.selected_cols_csv.split(",") if self.selected_cols_csv else []
        error = save_preset_logic(context, self.preset_name, self.project_name_in_scene, col_names)
        
        if error:
            self.report({'ERROR'}, f"Failed to save preset: {error}")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Preset '{self.preset_name}' saved to JSON")
        return {'FINISHED'}

    def invoke(self, context, event):
        # Capture selection while we are still in the Outliner interaction context
        selected_ids = getattr(context, "selected_ids", ())
        sel_cols = [item.name for item in selected_ids if isinstance(item, bpy.types.Collection)]
        
        if not sel_cols and context.view_layer.active_layer_collection:
            active_col = context.view_layer.active_layer_collection.collection
            if active_col != context.scene.collection:
                sel_cols = [active_col.name]
        
        if not sel_cols:
            self.report({'WARNING'}, "No collections selected in Outliner!")
            return {'CANCELLED'}
            
        self.selected_cols_csv = ",".join(sel_cols)
        self.preset_name = get_next_preset_name("User_Preset")
        return context.window_manager.invoke_props_dialog(self)

class PM_OT_DeleteLayerPreset(bpy.types.Operator):
    """Deletes the selected user layout preset"""
    bl_idname = "pm.delete_layer_preset"
    bl_label = "Delete Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        settings = context.scene.pm_layer_mgmt
        presets_data = load_layer_presets()
        return settings.active_preset in presets_data.get("user", {})

    def execute(self, context):
        error = delete_preset_logic(self.preset_name)
        
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        # Reset active preset to avoid pointing to deleted one
        context.scene.pm_layer_mgmt.active_preset = "NONE"
        
        self.report({'INFO'}, f"Preset '{self.preset_name}' deleted")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

# --- UI DRAWING ---

def draw_ui(layout, context):
    box = layout.box()
    box.label(text="Layer Management", icon='OUTLINER_OB_GROUP_INSTANCE')
    
    settings = context.scene.pm_layer_mgmt
    
    col = box.column(align=True)
    row = col.row(align=True)
    row.prop(settings, "active_preset", text="")
    
    # Only show delete button if it's a user preset
    presets_data = load_layer_presets()
    if settings.active_preset in presets_data.get("user", {}):
        del_op = row.operator("pm.delete_layer_preset", text="", icon='TRASH')
        del_op.preset_name = settings.active_preset
        
    row.operator("pm.create_layer_set", text="Create Set", icon='PLAY')
    
    col.separator()
    box.operator("pm.save_current_as_preset", text="Save Current to JSON", icon='ADD')

# --- REGISTRATION ---

classes = (
    PM_LayerManagementSettings,
    PM_OT_CreateLayerSet,
    PM_OT_SaveCurrentAsPreset,
    PM_OT_DeleteLayerPreset,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pm_layer_mgmt = bpy.props.PointerProperty(type=PM_LayerManagementSettings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pm_layer_mgmt
