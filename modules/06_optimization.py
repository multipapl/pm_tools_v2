import bpy
import re

UI_CATEGORY = "SCENE_OPTIMIZATION"

# --- LOGIC ---

def mesh_to_ic_logic(context):
    """Converts selected meshes to collection instances (IC)."""
    selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not selected_objects:
        return "No mesh objects selected"

    for obj in selected_objects:
        mesh_data = obj.data
        col_name = f"IC_{mesh_data.name}"
        
        ic_collection = bpy.data.collections.get(col_name)
        if not ic_collection:
            ic_collection = bpy.data.collections.new(col_name)
            context.scene.collection.children.link(ic_collection)
            ic_collection.objects.link(bpy.data.objects.new(mesh_data.name, mesh_data))
        
        instance = bpy.data.objects.new(f"Inst_{obj.name}", None)
        instance.instance_type = 'COLLECTION'
        instance.instance_collection = ic_collection
        instance.matrix_world = obj.matrix_world
        
        context.collection.objects.link(instance)
        bpy.data.objects.remove(obj, do_unlink=True)
        
    return None

def defuck_lights_logic(context):
    """Adjusts custom distance of lights (legacy fix for imported scenes)."""
    count = 0
    for obj in context.selected_objects:
        if obj.type == 'LIGHT' and hasattr(obj.data, "cutoff_distance"):
            obj.data.cutoff_distance /= 100
            count += 1
    return count

def toggle_modifiers_logic(context, target_name="Optimization"):
    """Toggles visibility of modifiers with a specific name."""
    for obj in context.selected_objects:
        for mod in obj.modifiers:
            if target_name.lower() in mod.name.lower():
                mod.show_viewport = not mod.show_viewport
                mod.show_render = mod.show_viewport

def cleanup_material_duplicates_logic(context):
    """Finds and replaces material duplicates (e.g. Mat.001 -> Mat)."""
    pattern = re.compile(r"^(.*)\.(\d{3})$")
    replacements = {}
    
    selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
    
    for obj in selected_meshes:
        for mat in obj.data.materials:
            if mat:
                match = pattern.match(mat.name)
                if match:
                    base_name = match.group(1)
                    master_mat = bpy.data.materials.get(base_name)
                    if master_mat:
                        replacements[mat.name] = master_mat

    count = 0
    for obj in selected_meshes:
        for i, mat in enumerate(obj.data.materials):
            if mat and mat.name in replacements:
                obj.data.materials[i] = replacements[mat.name]
                count += 1
    return count

# --- OPERATORS ---

class PM_OT_MeshToIC(bpy.types.Operator):
    """Converts classic mesh objects into Collection Instances to 
    drastically reduce scene memory and file size"""
    bl_idname = "pm.mesh_to_ic"
    bl_label = "Mesh to IC"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        error = mesh_to_ic_logic(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}

class PM_OT_DeFuckLights(bpy.types.Operator):
    """Scales down light cutoff distance by 100x to fix overblown 
    lighting issues after importing scenes from other software"""
    bl_idname = "pm.defuck_lights"
    bl_label = "DeFuck Lights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'LIGHT' for obj in context.selected_objects)

    def execute(self, context):
        count = defuck_lights_logic(context)
        self.report({'INFO'}, f"Successfully fixed {count} lights")
        return {'FINISHED'}

class PM_OT_ToggleModifiers(bpy.types.Operator):
    """Quickly hide or show all modifiers named 'Optimization' across 
    selection (useful for disabling high-poly displacement/subdiv)"""
    bl_idname = "pm.toggle_modifiers"
    bl_label = "Toggle Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        toggle_modifiers_logic(context)
        return {'FINISHED'}

class PM_OT_CleanupMaterialDuplicates(bpy.types.Operator):
    """Merges materials with '.001', '.002' suffixes into their parent 
    material to keep the scene's material list clean"""
    bl_idname = "pm.cleanup_material_duplicates"
    bl_label = "Delete Material Duplicates"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        count = cleanup_material_duplicates_logic(context)
        self.report({'INFO'}, f"Cleaned up {count} material slots")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    box = layout.box()
    box.label(text="Optimization", icon='MODIFIER')
    
    row = box.row(align=True)
    row.operator("pm.mesh_to_ic", text="Mesh to IC", icon='OUTLINER_OB_GROUP_INSTANCE')
    row.operator("pm.defuck_lights", text="Fix Lights", icon='OUTLINER_OB_LIGHT')
    
    col = box.column(align=True)
    col.operator("pm.toggle_modifiers", text="Toggle 'Optimization' Mods", icon='HIDE_OFF')
    col.operator("pm.cleanup_material_duplicates", text="Cleanup Materials", icon='MATERIAL')

# --- REGISTRATION ---

classes = (
    PM_OT_MeshToIC,
    PM_OT_DeFuckLights,
    PM_OT_ToggleModifiers,
    PM_OT_CleanupMaterialDuplicates,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
