import bpy
import importlib
import pkgutil

bl_info = {
    "name": "PM Tools v2.0",
    "author": "User",
    "version": (2, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > N-Panel > PM Tools",
    "description": "Modular toolkit with collapsible panels",
    "category": "Interface",
}

loaded_modules = []

def register():
    
    # Dynamic discovery of modules
    import os
    modules_dir = os.path.join(os.path.dirname(__file__), "modules")
    
    # Sort for alphabetical/numeric order
    module_names = sorted([name for _, name, _ in pkgutil.iter_modules([modules_dir])])
    
    for name in module_names:
        try:
            full_name = f"{__package__}.modules.{name}"
            module = importlib.import_module(full_name)
            if hasattr(module, "register"):
                module.register()
            loaded_modules.append(module)
        except Exception as e:
            print(f"[PM Tools] Error loading '{name}': {e}")

def unregister():
    for module in reversed(loaded_modules):
        try:
            if hasattr(module, "unregister"):
                module.unregister()
        except Exception as e:
            print(f"[PM Tools] Error unloading module: {e}")
            
    loaded_modules.clear()