import bpy

UI_CATEGORY = "SCENE_OPTIMIZATION"

# --- LOGIC ---

def link_instances_by_vertex_count_logic(context):
    """
    Groups selected mesh objects by vertex count and links those 
    with identical counts to share the same mesh data (master instance).
    """
    selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj.data]
    
    if len(selected_meshes) < 2:
        return None, "Please select at least two mesh objects"

    # Group by number of vertices
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

# --- OPERATORS ---

class PM_OT_LinkByVCount(bpy.types.Operator):
    """Finds objects with the exact same vertex count among selection 
    and links them to share the same mesh data (creates instances)"""
    bl_idname = "pm.link_by_vcount"
    bl_label = "Link Instances (by Verts)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Requires at least two mesh objects
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return len(meshes) >= 2

    def execute(self, context):
        count, error = link_instances_by_vertex_count_logic(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
            
        self.report({'INFO'}, f"Successfully linked {count} instances")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    box = layout.box()
    box.label(text="Mesh Tools", icon='MESH_DATA')
    # Refined button icon for linking focus
    box.operator("pm.link_by_vcount", text="Link Instances (Verts)", icon='LINKED')

# --- REGISTRATION ---

classes = (
    PM_OT_LinkByVCount,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
