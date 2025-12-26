import bpy
import math
import re

# --- OPERATORS ---

class PM_OT_ConvertMaxEmpties(bpy.types.Operator):
    """Convert 3ds Max Empties to Cameras with focal length and limits"""
    bl_idname = "pm.convert_max_empties"
    bl_label = "Convert Max Empties"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        # Filter base empties (avoiding target helpers)
        base_empties = [obj for obj in selected_objects if not obj.name.endswith(".Target") and obj.type == 'EMPTY']
        
        if not base_empties:
            self.report({'WARNING'}, "No valid Empties selected")
            return {'CANCELLED'}

        # Ensure camera collection exists
        coll_name = "Converted_Cameras"
        if coll_name not in bpy.data.collections:
            cam_collection = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(cam_collection)
        else:
            cam_collection = bpy.data.collections[coll_name]

        created_count = 0
        
        for old_empty in base_empties:
            target_name = f"{old_empty.name}.Target"
            old_target = bpy.data.objects.get(target_name)
            cam_pos = old_empty.matrix_world.to_translation()
            
            # Create Camera Data and Object
            cam_data = bpy.data.cameras.new(name=old_empty.name)
            
            # Extract Focal Length (pattern _20mm)
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

            # Handle Target if it exists
            if old_target:
                target_pos = old_target.matrix_world.to_translation()
                new_target = bpy.data.objects.new(f"P_Target_{old_empty.name}", None)
                new_target.empty_display_type = 'PLAIN_AXES'
                new_target.location = target_pos
                cam_collection.objects.link(new_target)

                # Track To constraint
                tt = cam_obj.constraints.new(type='TRACK_TO')
                tt.target = new_target
                tt.track_axis = 'TRACK_NEGATIVE_Z'
                tt.up_axis = 'UP_Y'

            # Architectural Vertical Fix (90 degrees X)
            lr = cam_obj.constraints.new(type='LIMIT_ROTATION')
            lr.name = "P_ARCH_Vertical_Fix"
            lr.use_limit_x = True
            lr.min_x = math.radians(90)
            lr.max_x = math.radians(90)
            lr.use_limit_y = True
            lr.min_y = 0
            lr.max_y = 0
            lr.owner_space = 'WORLD'
            
            if created_count == 0:
                context.scene.camera = cam_obj
                
            created_count += 1
                
        self.report({'INFO'}, f"Converted {created_count} cameras")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    """Function called by the main __init__.py to render UI elements"""
    box = layout.box()
    box.label(text="Camera Tools", icon='CAMERA_DATA')
    # Button to call our operator
    box.operator("pm.convert_max_empties", icon='FORWARD', text="Max Empties to Cams")

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