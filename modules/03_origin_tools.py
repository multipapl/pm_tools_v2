import bpy
from mathutils import Vector

UI_CATEGORY = "SCENE_MANAGEMENT"

# --- LOGIC ---

def center_origin_logic(context):
    """Sets origin to center of mass (median) for selected objects."""
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')

def center_bottom_origin_logic(context):
    """Sets origin to the bottom center of the bounding box for selected objects."""
    selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
    
    if not selected_objects:
        return

    # Store current cursor location to restore it later
    saved_cursor_location = context.scene.cursor.location.copy()
    
    for obj in selected_objects:
        # Get bounding box in world space
        bbox_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Calculate bottom center (min Z, average X and Y)
        min_z = min(v.z for v in bbox_world)
        avg_x = sum(v.x for v in bbox_world) / 8
        avg_y = sum(v.y for v in bbox_world) / 8
        
        bottom_center = Vector((avg_x, avg_y, min_z))
        
        # Temporarily move cursor to set origin
        context.scene.cursor.location = bottom_center
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        
    # Restore cursor
    context.scene.cursor.location = saved_cursor_location

# --- OPERATORS ---

class PM_OT_CenterOrigin(bpy.types.Operator):
    """Moves the object's origin point to the physical center (median) 
    of its geometry"""
    bl_idname = "pm.center_origin"
    bl_label = "Center Origin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        center_origin_logic(context)
        return {'FINISHED'}

class PM_OT_BottomOrigin(bpy.types.Operator):
    """Moves the object's origin point to the bottom-most center point 
    of its bounding box (perfect for placing objects on floors)"""
    bl_idname = "pm.bottom_origin"
    bl_label = "Bottom Origin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        center_bottom_origin_logic(context)
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    box = layout.box()
    box.label(text="Origin Tools", icon='OBJECT_ORIGIN')
    row = box.row(align=True)
    row.operator("pm.center_origin", text="Center", icon='CENTER_ONLY')
    row.operator("pm.bottom_origin", text="Bottom", icon='EMPTY_DATA')

# --- REGISTRATION ---

classes = (
    PM_OT_CenterOrigin,
    PM_OT_BottomOrigin,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
