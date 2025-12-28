import bpy
import re
import math

UI_CATEGORY = "CONVERTERS"

# --- LOGIC ---

def convert_max_empties_logic(context):
    """
    Finds 3ds Max style Parent-Target Empty hierarchies and converts them 
    to Blender Cameras with Track To and Limit Rotation constraints.
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

            # Limit Rotation to fix vertical tilt (Archviz style)
            lr = cam_obj.constraints.new(type='LIMIT_ROTATION')
            lr.name = "P_ARCH_Vertical_Fix"
            lr.use_limit_x = True
            lr.min_x = math.radians(90)
            lr.max_x = math.radians(90)
            lr.use_limit_y = True
            lr.min_y = 0
            lr.max_y = 0
            lr.owner_space = 'WORLD'
            
            # Set the first created camera as active for the scene
            if created_count == 0:
                context.scene.camera = cam_obj
            
            created_count += 1
            
    return created_count

# --- OPERATORS ---

class PM_OT_ConvertMaxEmpties(bpy.types.Operator):
    """Detects 3ds Max style 'Parent' and '.Target' Empty pairs and converts 
    them into Blender Cameras with tracking and vertical tilt fixes"""
    bl_idname = "pm.convert_max_empties"
    bl_label = "Max Empties to Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Only active if Empties are selected
        return any(obj.type == 'EMPTY' for obj in context.selected_objects)

    def execute(self, context):
        count = convert_max_empties_logic(context)
        if count == 0:
            self.report({'WARNING'}, "No suitable Empties selected (Parent-Target pairs)")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Successfully created {count} cameras")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    box = layout.box()
    box.label(text="MaxCamera Converter", icon='CAMERA_DATA')
    # Refined icon to CAMERA_STEREO for 'pair' conversion feel
    box.operator("pm.convert_max_empties", text="Convert Selected Empties", icon='CAMERA_STEREO')

# --- REGISTRATION ---

classes = (
    PM_OT_ConvertMaxEmpties,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
