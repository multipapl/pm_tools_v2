import bpy
import math
import re

class PM_OT_ConvertMaxEmpties(bpy.types.Operator):
    """Convert 3ds Max Empties to Cameras with targets and rotation limits"""
    bl_idname = "pm.convert_max_empties"
    bl_label = "Convert Empties to Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        # Filter only base empties, excluding their targets
        base_empties = [obj for obj in selected_objects if not obj.name.endswith(".Target") and obj.type == 'EMPTY']
        
        if not base_empties:
            self.report({'WARNING'}, "No valid Empties selected")
            return {'CANCELLED'}

        # Ensure target collection exists
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
            
            # Basic positions
            cam_pos = old_empty.matrix_world.to_translation()
            
            # Handle Target creation
            if old_target:
                target_pos = old_target.matrix_world.to_translation()
                new_target = bpy.data.objects.new(f"P_Target_{old_empty.name}", None)
                new_target.empty_display_type = 'PLAIN_AXES'
                new_target.location = target_pos
                cam_collection.objects.link(new_target)

                # Camera data setup
                cam_data = bpy.data.cameras.new(name=old_empty.name)
                
                # Extract Focal Length (pattern: _20mm)
                focal_match = re.search(r'_(\d+)mm', old_empty.name)
                if focal_match:
                    try:
                        cam_data.lens = float(focal_match.group(1))
                    except ValueError:
                        pass 

                cam_data.show_passepartout = True
                cam_data.passepartout_alpha = 1.0
                
                # Create Camera Object
                cam_obj = bpy.data.objects.new(f"P_Cam_{old_empty.name}", cam_data)
                cam_obj.location = cam_pos
                cam_collection.objects.link(cam_obj)

                # Add Track To constraint
                tt = cam_obj.constraints.new(type='TRACK_TO')
                tt.target = new_target
                tt.track_axis = 'TRACK_NEGATIVE_Z'
                tt.up_axis = 'UP_Y'

                # Add Architectural vertical fix (Limit Rotation)
                lr = cam_obj.constraints.new(type='LIMIT_ROTATION')
                lr.name = "P_ARCH_Vertical_Fix"
                lr.use_limit_x = True
                lr.min_x = math.radians(90)
                lr.max_x = math.radians(90)
                lr.use_limit_y = True
                lr.min_y = 0
                lr.max_y = 0
                lr.owner_space = 'WORLD'
                
                # Set first camera as active scene camera
                if created_count == 0:
                    context.scene.camera = cam_obj
                    
                created_count += 1
                
        self.report({'INFO'}, f"Successfully converted {created_count} cameras")
        return {'FINISHED'}

class PM_PT_CameraConverterPanel(bpy.types.Panel):
    """Standalone panel for camera conversion tools"""
    bl_label = "Camera Converter"
    bl_idname = "PM_PT_camera_converter_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PM Tools'
    bl_options = set() # Open by default

    def draw(self, context):
        layout = self.layout
        layout.operator("pm.convert_max_empties", icon='CAMERA_DATA', text="Convert Max Empties")

# Register/Unregister
classes = (PM_OT_ConvertMaxEmpties, PM_PT_CameraConverterPanel)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)