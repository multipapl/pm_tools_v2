import bpy

UI_CATEGORY = "SCENE_MANAGEMENT"

# --- LOGIC ---

def arrange_objects_logic(context, selected_objects, sort_method):
    """Arranges selected objects in a row based on polycount or size."""
    if len(selected_objects) < 2:
        return False, "Please select at least two objects"

    # Find the maximum width to determine spacing
    max_x_dimension = 0.0
    for obj in selected_objects:
        if obj.dimensions.x > max_x_dimension:
            max_x_dimension = obj.dimensions.x

    spacing = max_x_dimension
    if spacing == 0.0:
        return False, "Could not determine object width"

    # Define sorting keys
    def get_polycount(obj):
        if obj.type == 'MESH' and obj.data:
            return len(obj.data.polygons)
        return 0

    def get_size(obj):
        dims = obj.dimensions
        return dims.x * dims.y * dims.z

    # Sort objects
    if sort_method == 'POLYCOUNT':
        sorted_objects = sorted(selected_objects, key=get_polycount)
    else:  # 'SIZE'
        sorted_objects = sorted(selected_objects, key=get_size)

    # Position objects in a row
    for index, obj in enumerate(sorted_objects):
        obj.location.x = spacing * index
        obj.location.y = 0
        obj.location.z = 0

    return True, f"Successfully arranged {len(sorted_objects)} objects"

# --- OPERATORS ---

class PM_OT_ArrangeAssets(bpy.types.Operator):
    """Arranges selected objects in a neat row, sorting them either 
    by their polygon count or their bounding box size (volume)"""
    bl_idname = "pm.arrange_assets"
    bl_label = "Arrange Assets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        sort_method = context.scene.pm_sort_method
        success, message = arrange_objects_logic(context, context.selected_objects, sort_method)
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'WARNING'}, message)
            
        return {'FINISHED'}

# --- UI DRAWING ---

def draw_ui(layout):
    scene = bpy.context.scene
    box = layout.box()
    box.label(text="Arrange Tools", icon='SORTSIZE')
    
    row = box.row(align=True)
    row.prop(scene, "pm_sort_method", text="")
    row.operator("pm.arrange_assets", text="Arrange", icon='PLAY')

# --- REGISTRATION ---

classes = (
    PM_OT_ArrangeAssets,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register the property on the Scene
    bpy.types.Scene.pm_sort_method = bpy.props.EnumProperty(
        name="Sort Method",
        items=[
            ('POLYCOUNT', "By Polycount", "Sort by vertex/polygon count"),
            ('SIZE', "By Size", "Sort by bounding box volume"),
        ],
        default='POLYCOUNT'
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pm_sort_method
