import bpy

UI_CATEGORY = "SCENE_OPTIMIZATION"

# --- LOGIC ---

def get_instantiated_collections(context, skip_scene_name):
    """Returns a set of all collections used as instances in other scenes."""
    instantiated = set()
    for scene in bpy.data.scenes:
        if scene.name == skip_scene_name:
            continue
        for obj in scene.objects:
            if obj.instance_type == 'COLLECTION' and obj.instance_collection:
                instantiated.add(obj.instance_collection)
    return instantiated

def mark_unused_collections_logic(context, library_scene_name="Library", marker="[UNUSED] "):
    """Marks collections in the library scene that are not referenced elsewhere."""
    library_scene = bpy.data.scenes.get(library_scene_name)
    if not library_scene:
        return None, None, f"Library scene '{library_scene_name}' not found!"

    library_collections = set(library_scene.collection.children)
    instantiated_collections = get_instantiated_collections(context, library_scene_name)

    marked_count = 0
    revised_count = 0

    for col in library_collections:
        if col.name.startswith("GS"): 
            continue
            
        is_used = col in instantiated_collections
        is_marked = col.name.startswith(marker)

        if not is_used and not is_marked:
            col.name = marker + col.name
            marked_count += 1
        elif is_used and is_marked:
            col.name = col.name[len(marker):]
            revised_count += 1

    return marked_count, revised_count, None

def delete_unused_collections_logic(context, library_scene_name="Library", marker="[UNUSED] "):
    """Deletes all collections in the library scene marked with the unused prefix."""
    library_scene = bpy.data.scenes.get(library_scene_name)
    if not library_scene:
        return f"Library scene '{library_scene_name}' not found!", 0

    to_delete = [col for col in library_scene.collection.children if col.name.startswith(marker)]
    
    deleted_count = 0
    for col in to_delete:
        bpy.data.collections.remove(col)
        deleted_count += 1
        
    return None, deleted_count

# --- OPERATORS ---

class PM_OT_MarkUnusedCollections(bpy.types.Operator):
    """Scans the 'Library' scene and adds an '[UNUSED]' prefix to any 
    collection that isn't currently instanced in any other scene"""
    bl_idname = "pm.mark_unused_collections"
    bl_label = "Mark Unused"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return "Library" in bpy.data.scenes

    def execute(self, context):
        marked, revised, error = mark_unused_collections_logic(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        msg = f"Marked: {marked}, Revised: {revised}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

class PM_OT_DeleteUnusedCollections(bpy.types.Operator):
    """Permanently removes all collections from the 'Library' scene 
    that are marked with the '[UNUSED]' prefix"""
    bl_idname = "pm.delete_unused_collections"
    bl_label = "Delete Unused"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if "Library" not in bpy.data.scenes:
            return False
        lib_scene = bpy.data.scenes["Library"]
        return any(col.name.startswith("[UNUSED] ") for col in lib_scene.collection.children)

    def execute(self, context):
        error, count = delete_unused_collections_logic(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
            
        self.report({'INFO'}, f"Successfully deleted {count} collections")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout, context):
    box = layout.box()
    box.label(text="Collection Cleanup", icon='COLLECTION_NEW')
    
    row = box.row(align=True)
    row.operator("pm.mark_unused_collections", text="Mark Unused", icon='VIEWZOOM')
    row.operator("pm.delete_unused_collections", text="Delete Unused", icon='TRASH')

# --- REGISTRATION ---

classes = (
    PM_OT_MarkUnusedCollections,
    PM_OT_DeleteUnusedCollections,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
