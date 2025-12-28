import bpy
import re
import math

from mathutils import Vector

UI_CATEGORY = "CONVERTERS"

# --- HELPERS ---

def nearest_quarter(ang):
    """Calculates the nearest quarter circle (90, 180, 270, 360) of an angle."""
    return (((round((ang / math.pi) / 0.5)) / 4) * (2 * math.pi)) % (2 * math.pi)

def get_active_camera(context):
    """Returns the active camera object (active object first, then scene camera)."""
    cam_obj = context.active_object
    if not cam_obj or cam_obj.type != 'CAMERA':
        cam_obj = context.scene.camera
    
    if cam_obj and cam_obj.type == 'CAMERA':
        return cam_obj
    return None

# --- LOGIC ---

def convert_max_empties_logic(context):
    """
    Detects 3ds Max style 'Parent' and '.Target' Empty pairs and converts 
    them into Blender Cameras with tracking.
    """
    selected_objects = context.selected_objects
    # Filter for base empties (avoiding .Target objects as bases)
    base_empties = [obj for obj in selected_objects if not obj.name.endswith(".Target") and obj.type == 'EMPTY']
    
    if not base_empties:
        return 0

    # Ensure camera collection exists
    coll_name = "Converted_Cameras"
    cam_collection = bpy.data.collections.get(coll_name)
    if not cam_collection:
        cam_collection = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(cam_collection)

    created_count = 0
    for old_empty in base_empties:
        target_name = f"{old_empty.name}.Target"
        old_target = bpy.data.objects.get(target_name)
        
        if old_target:
            cam_pos = old_empty.matrix_world.to_translation()
            target_pos = old_target.matrix_world.to_translation()

            # 1. Create and position the Target object (Empty)
            new_target = bpy.data.objects.new(f"P_Target_{old_empty.name}", None)
            new_target.empty_display_type = 'PLAIN_AXES'
            new_target.location = target_pos
            cam_collection.objects.link(new_target)

            # 2. Create the Camera
            cam_data = bpy.data.cameras.new(name=old_empty.name)
            
            # Auto-extract focal length if name contains pattern like _20mm
            focal_match = re.search(r'_(\d+)mm', old_empty.name)
            if focal_match:
                try:
                    cam_data.lens = float(focal_match.group(1))
                except ValueError:
                    pass 

            cam_data.show_passepartout = True
            cam_data.passepartout_alpha = 1.0
            
            cam_obj = bpy.data.objects.new(f"P_Cam_{old_empty.name}", cam_data)
            cam_obj.location = cam_pos
            cam_collection.objects.link(cam_obj)

            # 3. Add Constraints
            # Track To constraint for targeting
            tt = cam_obj.constraints.new(type='TRACK_TO')
            tt.target = new_target
            tt.track_axis = 'TRACK_NEGATIVE_Z'
            tt.up_axis = 'UP_Y'
            
            # NOTE: Limit Rotation is omitted to allow modular Two-Point Perspective tool usage.
            
            # Set the first created camera as active for the scene
            if created_count == 0:
                context.scene.camera = cam_obj
            
            created_count += 1
            
    return created_count

def apply_two_point_perspective_logic(context):
    """
    Aligns camera to exactly vertical (90deg X) while maintaining the visual 
    composition using shift_y. Uses reference core.py math.
    """
    cam_obj = get_active_camera(context)
    if not cam_obj:
        return False, "No camera selected"
    
    scene = context.scene
    cam = cam_obj.data
    
    # Preserve active object state while baking
    old_active = context.view_layer.objects.active
    context.view_layer.objects.active = cam_obj
    
    # Bake constraints (Track To) into the actual location/rotation
    bpy.ops.object.visual_transform_apply()
    
    # Temporarily mute constraints so they don't override manual alignment
    for const in cam_obj.constraints:
        if const.type in {'TRACK_TO', 'LIMIT_ROTATION'}:
            const.mute = True

    # --- Perspective Math ---
    cam_obj.rotation_mode = "XYZ"
    cam_rotation = cam_obj.rotation_euler.copy()
    cam_position = cam_obj.location.copy()
    orig_shift_y = cam.shift_y

    # Save original state for reset
    cam_obj["pm_perspective_orig_loc"] = cam_position
    cam_obj["pm_perspective_orig_rot"] = cam_rotation
    cam_obj["pm_perspective_orig_shift_y"] = orig_shift_y
    cam_obj["pm_perspective_applied"] = True

    focal_length = cam.lens
    ratio = scene.render.resolution_x / scene.render.resolution_y
    
    if cam.sensor_fit == "HORIZONTAL" or (cam.sensor_fit == "AUTO" and ratio >= 1):
        sensor_size = cam.sensor_width
    else:
        sensor_size = cam.sensor_height

    # Correct rotation to the nearest 90deg horizontal axis
    corrected_rotation = nearest_quarter(cam_rotation[0])
    
    # Trigonometry for shift and pivot compensation
    angle = corrected_rotation - cam_rotation[0]
    if abs(math.cos(angle)) < 0.001:
        return False, "Camera angle too extreme"
        
    adjacent_side = focal_length / sensor_size
    opposite_side = -math.tan(angle) * adjacent_side
    offset = (adjacent_side / math.cos(angle)) - adjacent_side
    
    # Transform local Z-offset to world space using reference logic (Row-Vector @ Inv Matrix)
    offset_vec = Vector((0, 0, offset))
    inv_world_matrix = cam_obj.matrix_world.copy().inverted()
    rotated_offset_vec = offset_vec @ inv_world_matrix
    
    # Apply changes directly to object transform and camera data
    cam_obj.location = cam_position + rotated_offset_vec
    cam_obj.rotation_euler[0] = corrected_rotation
    cam.shift_y += opposite_side
    
    # Restore viewport context
    context.view_layer.objects.active = old_active
    return True, ""

def reset_perspective_logic(context):
    """Undoes perspective correction by zeroing shift and re-enabling tracking."""
    cam_obj = get_active_camera(context)
    if not cam_obj:
        return False, "No camera selected"
    
    # Try to restore from saved state first
    if cam_obj.get("pm_perspective_applied"):
        if "pm_perspective_orig_loc" in cam_obj:
            cam_obj.location = cam_obj["pm_perspective_orig_loc"]
        if "pm_perspective_orig_rot" in cam_obj:
            cam_obj.rotation_euler = cam_obj["pm_perspective_orig_rot"]
        if "pm_perspective_orig_shift_y" in cam_obj:
            cam_obj.data.shift_y = cam_obj["pm_perspective_orig_shift_y"]
        
        # Cleanup
        del cam_obj["pm_perspective_applied"]
        for prop in ["pm_perspective_orig_loc", "pm_perspective_orig_rot", "pm_perspective_orig_shift_y"]:
            if prop in cam_obj:
                del cam_obj[prop]
    else:
        # Fallback for old sessions/external cameras: just zero shift
        cam_obj.data.shift_y = 0
    
    # Restore constraints (like Track To)
    for const in cam_obj.constraints:
        if const.type in {'TRACK_TO', 'LIMIT_ROTATION'}:
            const.mute = False
            
    return True, ""

# --- OPERATORS ---

class PM_OT_ConvertMaxEmpties(bpy.types.Operator):
    """Converts 3ds Max style Empty targets to Blender Cameras"""
    bl_idname = "pm.convert_max_empties"
    bl_label = "Max Empties to Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'EMPTY' for obj in context.selected_objects)

    def execute(self, context):
        count = convert_max_empties_logic(context)
        if count == 0:
            self.report({'WARNING'}, "No suitable Empties selected")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Created {count} cameras")
        return {'FINISHED'}

class PM_OT_ApplyTwoPointPerspective(bpy.types.Operator):
    """Calculates shift_y for vertical alignment (Archviz 2-point perspective)"""
    bl_idname = "pm.apply_two_point_perspective"
    bl_label = "Two-Point Perspective"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_active_camera(context) is not None

    def execute(self, context):
        success, message = apply_two_point_perspective_logic(context)
        if success:
            self.report({'INFO'}, "Applied Two-Point Perspective")
            return {'FINISHED'}
        
        self.report({'ERROR'}, message if message else "Failed to apply correction")
        return {'CANCELLED'}

class PM_OT_ResetPerspective(bpy.types.Operator):
    """Zeros shift and restores constraint tracking"""
    bl_idname = "pm.reset_perspective"
    bl_label = "Reset Perspective"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cam_obj = get_active_camera(context)
        # Only active if shift_y is not zero (has perspective correction applied)
        return cam_obj is not None and abs(cam_obj.data.shift_y) > 0.00001

    def execute(self, context):
        success, message = reset_perspective_logic(context)
        if success:
            self.report({'INFO'}, "Perspective Reset")
            return {'FINISHED'}
            
        self.report({'ERROR'}, message if message else "Failed to reset")
        return {'CANCELLED'}

# --- UI DRAWING ---

def draw_ui(layout, context):
    box = layout.box()
    box.label(text="MaxCamera Converter", icon='CAMERA_DATA')
    
    box.operator("pm.convert_max_empties", text="Convert Selected Empties", icon='CAMERA_STEREO')
    
    row = box.row(align=True)
    row.operator("pm.apply_two_point_perspective", text="Two-Point", icon='ORIENTATION_VIEW')
    row.operator("pm.reset_perspective", text="Reset", icon='X')

# --- REGISTRATION ---

classes = (
    PM_OT_ConvertMaxEmpties,
    PM_OT_ApplyTwoPointPerspective,
    PM_OT_ResetPerspective,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
