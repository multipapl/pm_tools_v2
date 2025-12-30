import bpy
import os

UI_CATEGORY = "SCENE_MANAGEMENT"

# --- DATA ---

# Hardcoded resolutions based on RESOLUTIONS_4K docs
RESOLUTION_DATA = [
    {"ratio": "1:1", "w": 4096, "h": 4096},
    {"ratio": "16:9", "w": 5504, "h": 3072},
    {"ratio": "9:16", "w": 3072, "h": 5504},
    {"ratio": "4:3", "w": 4800, "h": 3584},
    {"ratio": "3:4", "w": 3584, "h": 4800},
    {"ratio": "3:2", "w": 5056, "h": 3392},
    {"ratio": "2:3", "w": 3392, "h": 5056},
    {"ratio": "5:4", "w": 4608, "h": 3712},
    {"ratio": "4:5", "w": 3712, "h": 4608},
    {"ratio": "21:9", "w": 6336, "h": 2688},
]

# --- LOGIC ---

def create_output_presets_logic(context):
    """
    Core logic to create render presets.
    Returns the number of presets created.
    """
    # Get the directory where Blender stores render presets
    presets_dir = os.path.join(bpy.utils.user_resource('SCRIPTS'), "presets", "render")
    
    # Ensure directory exists
    if not os.path.exists(presets_dir):
        os.makedirs(presets_dir, exist_ok=True)

    # Store current scene settings to restore later
    render = context.scene.render
    old_settings = {
        'res_x': render.resolution_x,
        'res_y': render.resolution_y,
        'perc': render.resolution_percentage,
        'asp_x': render.pixel_aspect_x,
        'asp_y': render.pixel_aspect_y
    }

    created_count = 0
    
    for res in RESOLUTION_DATA:
        preset_name = f"PM_{res['ratio']} - {res['w']}x{res['h']}"

        # Set resolution for the preset
        render.resolution_x = res['w']
        render.resolution_y = res['h']
        render.resolution_percentage = 100
        render.pixel_aspect_x = 1.0
        render.pixel_aspect_y = 1.0
        
        # Save as preset (Blender operator handles file creation)
        bpy.ops.render.preset_add(name=preset_name, remove_active=False)
        created_count += 1

    # Restore original settings
    render.resolution_x = old_settings['res_x']
    render.resolution_y = old_settings['res_y']
    render.resolution_percentage = old_settings['perc']
    render.pixel_aspect_x = old_settings['asp_x']
    render.pixel_aspect_y = old_settings['asp_y']

    return created_count

# --- OPERATORS ---

class PM_OT_CreateResolutionPresets(bpy.types.Operator):
    """Generates standard PM resolution presets for render output"""
    bl_idname = "pm.create_resolution_presets"
    bl_label = "Create PM Output Presets"
    bl_description = "Create standard PM resolution presets"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        create_output_presets_logic(context)
        self.report({'INFO'}, "Done")
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout, context):
    """Draws the presets generator button in the panel"""
    layout.operator("pm.create_resolution_presets", icon='RENDER_STILL')

# --- REGISTRATION ---

classes = (
    PM_OT_CreateResolutionPresets,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
