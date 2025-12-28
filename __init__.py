import bpy
import importlib
import pkgutil
import os

bl_info = {
    "name": "PM Tools v2.0",
    "author": "User",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > PM Tools",
    "description": "Modular tools for Archviz with single UI panel",
    "category": "Interface",
}

# --- GLOBAL STATE ---
loaded_modules = []

class PM_UI_State(bpy.types.PropertyGroup):
    """Property group for tracking UI state (expanded/collapsed)"""
    show_converters: bpy.props.BoolProperty(name="Converters", default=True)
    show_management: bpy.props.BoolProperty(name="Scene Management", default=True)
    show_optimization: bpy.props.BoolProperty(name="Scene Optimization", default=True)
    show_other: bpy.props.BoolProperty(name="Other Tools", default=False)

# --- UI PANEL ---

class PM_PT_MainPanel(bpy.types.Panel):
    """The only main container in the N-panel tab"""
    bl_label = "PM TOOLS"
    bl_idname = "PM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PM Tools'

    def draw(self, context):
        layout = self.layout
        ui_state = context.scene.pm_ui_state
        
        # Categorize modules (optimized grouping)
        categories = {
            "CONVERTERS": [],
            "SCENE_MANAGEMENT": [],
            "SCENE_OPTIMIZATION": [],
            "OTHER": []
        }
        
        for module in loaded_modules:
            cat = getattr(module, "UI_CATEGORY", "OTHER")
            if cat in categories:
                categories[cat].append(module)
            else:
                categories["OTHER"].append(module)
        
        # Mapping category IDs to (Title, Property Name)
        category_map = {
            "CONVERTERS": ("CONVERTERS", "show_converters"),
            "SCENE_MANAGEMENT": ("SCENE MANAGEMENT", "show_management"),
            "SCENE_OPTIMIZATION": ("SCENE OPTIMIZATION", "show_optimization"),
            "OTHER": ("OTHER TOOLS", "show_other")
        }
        
        for cat_id, modules in categories.items():
            if not modules:
                continue
            
            title, prop_name = category_map[cat_id]
            is_expanded = getattr(ui_state, prop_name)
            
            # Box container for each category
            box = layout.box()
            row = box.row(align=True)
            
            # Customizing the header with a toggle
            icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
            row.prop(ui_state, prop_name, text="", icon=icon, emboss=False)
            row.label(text=title, icon='PREFERENCES')
            
            if is_expanded:
                for module in modules:
                    if hasattr(module, "draw_ui"):
                        module.draw_ui(box)

# --- REGISTRATION ---

def register():
    """Register all addon components and sub-modules"""
    loaded_modules.clear()
    
    # 1. Register main UI state and panel
    bpy.utils.register_class(PM_UI_State)
    bpy.types.Scene.pm_ui_state = bpy.props.PointerProperty(type=PM_UI_State)
    bpy.utils.register_class(PM_PT_MainPanel)
    
    # 2. Discover and register sub-modules in /modules folder
    modules_path = os.path.join(os.path.dirname(__file__), "modules")
    module_names = sorted([name for _, name, _ in pkgutil.iter_modules([modules_path])])
    
    for name in module_names:
        try:
            full_name = f"{__package__}.modules.{name}"
            module = importlib.import_module(full_name)
            
            # Ensure fresh code is loaded (development-friendly)
            importlib.reload(module)
            
            if hasattr(module, "register"):
                module.register()
                
            loaded_modules.append(module)
        except Exception as e:
            print(f"[PM Tools] CRITICAL: Failed to load module '{name}': {e}")

def unregister():
    """Clean up all addon components and sub-modules"""
    # 1. Unregister sub-modules (reverse order for safety)
    for module in reversed(loaded_modules):
        try:
            if hasattr(module, "unregister"):
                module.unregister()
        except Exception as e:
            print(f"[PM Tools] Error unregistering sub-module: {e}")
            
    # 2. Unregister main components
    bpy.utils.unregister_class(PM_PT_MainPanel)
    del bpy.types.Scene.pm_ui_state
    bpy.utils.unregister_class(PM_UI_State)
    
    loaded_modules.clear()
