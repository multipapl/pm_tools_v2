import bpy
import importlib
import pkgutil
import os

bl_info = {
    "name": "PM Tools v2.0",
    "author": "User",
    "version": (2, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > N-Panel > PM Tools",
    "description": "Modular tools for Archviz with single UI panel",
    "category": "Interface",
}

# Global list to keep track of loaded sub-modules
loaded_modules = []

class PM_PT_MainPanel(bpy.types.Panel):
    """The only main container in the N-panel tab"""
    bl_label = "PM TOOLS"
    bl_idname = "PM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PM Tools'

    def draw(self, context):
        layout = self.layout
        # Iterate through loaded modules and call their UI functions
        for module in loaded_modules:
            if hasattr(module, "draw_ui"):
                module.draw_ui(layout)

def register():
    loaded_modules.clear()
    
    # Register the main panel class
    bpy.utils.register_class(PM_PT_MainPanel)
    
    # Discovery of modules inside the 'modules' folder
    modules_path = os.path.join(os.path.dirname(__file__), "modules")
    module_names = sorted([name for _, name, _ in pkgutil.iter_modules([modules_path])])
    
    for name in module_names:
        try:
            # Dynamic import
            full_name = f"{__package__}.modules.{name}"
            module = importlib.import_module(full_name)
            
            # Register classes defined within the module
            if hasattr(module, "register"):
                module.register()
                
            loaded_modules.append(module)
        except Exception as e:
            print(f"[PM Tools] Error loading module '{name}': {e}")

def unregister():
    # Unregister modules in reverse order
    for module in reversed(loaded_modules):
        try:
            if hasattr(module, "unregister"):
                module.unregister()
        except Exception as e:
            print(f"[PM Tools] Error unloading module: {e}")
            
    # Unregister the main panel
    bpy.utils.unregister_class(PM_PT_MainPanel)
    loaded_modules.clear()