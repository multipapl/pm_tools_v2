import bpy
import re

UI_CATEGORY = "SCENE_OPTIMIZATION"

# --- LOGIC ---

def mesh_to_ic_logic(context):
    """
    Converts selected meshes to collection instances (IC).
    Uses the collection from the active object (expected to be an instance collection).
    """
    active_obj = context.active_object
    if not active_obj or active_obj.instance_type != 'COLLECTION' or not active_obj.instance_collection:
        return "Active object must be a Collection Instance"

    ic_collection = active_obj.instance_collection
    
    # Filter meshes to replace, excluding the active object itself
    selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj != active_obj]
    
    if not selected_meshes:
        return "No mesh objects selected to replace"

    for obj in selected_meshes:
        instance = bpy.data.objects.new(f"Inst_{obj.name}", None)
        instance.instance_type = 'COLLECTION'
        instance.instance_collection = ic_collection
        instance.matrix_world = obj.matrix_world.copy()
        
        # Link to the same collection as the original object
        for col in obj.users_collection:
            col.objects.link(instance)
            
        bpy.data.objects.remove(obj, do_unlink=True)
        
    return None

def link_instances_by_vertex_count_logic(context):
    """
    Groups selected mesh objects by vertex count and links those 
    with identical counts to share the same mesh data (master instance).
    """
    selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj.data]
    
    if len(selected_meshes) < 2:
        return None, "Please select at least two mesh objects"

    groups = {}
    for obj in selected_meshes:
        v_count = len(obj.data.vertices)
        if v_count not in groups:
            groups[v_count] = []
        groups[v_count].append(obj)

    linked_count = 0
    for v_count, obs in groups.items():
        if len(obs) > 1:
            master_data = obs[0].data
            for i in range(1, len(obs)):
                if obs[i].data != master_data:
                    obs[i].data = master_data
                    linked_count += 1
                
    return linked_count, None

def defuck_lights_logic(context):
    """Adjusts custom distance of lights (legacy fix for imported scenes)."""
    count = 0
    for obj in context.selected_objects:
        if obj.type == 'LIGHT' and hasattr(obj.data, "cutoff_distance"):
            obj.data.cutoff_distance /= 100
            count += 1
    return count

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
    """Converts classic mesh objects into Collection Instances"""
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

class PM_OT_LinkByVCount(bpy.types.Operator):
    """Links objects with identical vertex counts to share mesh data"""
    bl_idname = "pm.link_by_vcount"
    bl_label = "Link Instances (by Verts)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return len(meshes) >= 2

    def execute(self, context):
        count, error = link_instances_by_vertex_count_logic(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
            
        self.report({'INFO'}, f"Linked {count} instances")
        return {'FINISHED'}

class PM_OT_DeFuckLights(bpy.types.Operator):
    """Fixes overblown lighting from imported scenes by scaling cutoff 100x"""
    bl_idname = "pm.defuck_lights"
    bl_label = "Fix Lights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'LIGHT' for obj in context.selected_objects)

    def execute(self, context):
        count = defuck_lights_logic(context)
        self.report({'INFO'}, f"Fixed {count} lights")
        return {'FINISHED'}

class PM_OT_CleanupMaterialDuplicates(bpy.types.Operator):
    """Merges material duplicates (.001, .002, etc.)"""
    bl_idname = "pm.cleanup_material_duplicates"
    bl_label = "Cleanup Material Duplicates"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        count = cleanup_material_duplicates_logic(context)
        self.report({'INFO'}, f"Cleaned up {count} slots")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout, context):
    box = layout.box()
    box.label(text="Optimization", icon='MODIFIER')
    
    # 1. Instancing Tools
    col = box.column(align=True)
    col.label(text="Instancing:")
    row = col.row(align=True)
    row.operator("pm.mesh_to_ic", text="Mesh to IC", icon='OUTLINER_OB_GROUP_INSTANCE')
    row.operator("pm.link_by_vcount", text="Link (Verts)", icon='LINKED')
    
    # 2. Scene Refinement Tools
    col = box.column(align=True)
    col.label(text="Refinement:")
    row = col.row(align=True)
    row.operator("pm.defuck_lights", text="Fix Lights", icon='OUTLINER_OB_LIGHT')
    row.operator("pm.cleanup_material_duplicates", text="Materials", icon='MATERIAL')

# --- REGISTRATION ---

classes = (
    PM_OT_MeshToIC,
    PM_OT_LinkByVCount,
    PM_OT_DeFuckLights,
    PM_OT_CleanupMaterialDuplicates,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
