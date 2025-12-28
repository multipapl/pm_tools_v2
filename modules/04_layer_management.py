import bpy

UI_CATEGORY = "SCENE_MANAGEMENT"

# --- LOGIC ---

def create_collection(context, name, parent=None, color_tag='DEFAULT', disable_in_render=False):
    """Helper to create or get a collection and link it to a parent."""
    collection = bpy.data.collections.get(name)
    if not collection:
        collection = bpy.data.collections.new(name)
        if parent:
            parent.children.link(collection)
        else:
            context.scene.collection.children.link(collection)
            
    collection.color_tag = color_tag
    if disable_in_render:
        collection.hide_render = True
        
    return collection

def create_nested_structure_logic(context, structure_dict, parent_coll=None):
    """Recursively creates a nested collection structure from a dictionary."""
    for name, value in structure_dict.items():
        if isinstance(value, dict):
            color = value.get("color", "DEFAULT")
            disable_in_render = value.get("disable_in_render", False)
            new_parent = create_collection(context, name, parent_coll, color, disable_in_render)
            sub_structure = {k: v for k, v in value.items() if k not in ("color", "disable_in_render")}
            if sub_structure:
                create_nested_structure_logic(context, sub_structure, new_parent)
        else:
            create_collection(context, name, parent_coll, value, False)

def create_set_1_logic(context, project_name):
    """Standard Archviz structure (Set 1)."""
    structure = {
        project_name: {
            "color": "COLOR_05",
            "###_COMP": {
                "color": "COLOR_07",
                "CC_Cam01": "COLOR_07", "CC_Cam02": "COLOR_07", "CC_Cam03": "COLOR_07", 
                "CC_Cam04": "COLOR_07", "CC_Cam05": "COLOR_07"
            },
            "##_Cameras": {"color": "COLOR_06"},
            "#_ASSETS": {
                "color": "COLOR_06", "disable_in_render": True,
                "Trees": "COLOR_04", "Bushes": "COLOR_04", "Grass": "COLOR_04", "Props": "COLOR_03",
            },
            "#_HELPERS": {"color": "COLOR_07", "disable_in_render": True},
            "01_BLD": {
                "color": "COLOR_05", "Blocking": "COLOR_05", "Walls": "COLOR_05", "Floor": "COLOR_05", 
                "Ceiling": "COLOR_05", "Windows": "COLOR_05", "Doors": "COLOR_05", "Structure": "COLOR_05", "Facade": "COLOR_05"
            },
            "02_LANDSCAPE": {"color": "COLOR_02", "Grass_Plane": "COLOR_02"},
            "03_PLANTS": {"color": "COLOR_04", "Manual": "COLOR_04"},
            "04_PROPS": {"color": "COLOR_03", "Exterior_Props": "COLOR_03", "Interior_Props": "COLOR_03"},
            "99_HIDE": {"color": "COLOR_07", "disable_in_render": True}
        },
        "Garbage": {"color": "COLOR_08", "disable_in_render": True}
    }
    create_nested_structure_logic(context, structure)

def create_set_2_logic(context, project_name):
    """Standard Interior structure (Set 2)."""
    structure = {
        project_name: {
            "color": "COLOR_05",
            "###_COMP": {
                "color": "COLOR_07",
                "CC_Cam01": "COLOR_07", "CC_Cam02": "COLOR_07", "CC_Cam03": "COLOR_07", 
                "CC_Cam04": "COLOR_07", "CC_Cam05": "COLOR_07"
            },
            "##_Cameras": {"color": "COLOR_06"},
            ",-_PLANS": {
                "color": "COLOR_06", "Floor_Plan": "COLOR_06", "Elevation_Plan": "COLOR_06", "Detail_Drawings": "COLOR_06"
                },
            "01_FURNITURE": {
                "color": "COLOR_01", "Sofas": "COLOR_01", "Tables": "COLOR_01", "Chairs": "COLOR_01", 
                "Cabinets": "COLOR_01", "Shelves": "COLOR_01"
            },
            "02_LIGHTING": {
                "color": "COLOR_02", "Ceiling_Lights": "COLOR_02", "Floor_Lamps": "COLOR_02", 
                "Wall_Lights": "COLOR_02", "Table_Lamps": "COLOR_02"
            },
            "03_DECOR": {
                "color": "COLOR_03", "Rugs": "COLOR_03", "Curtains": "COLOR_03", "Wall_Art": "COLOR_03", 
                "Decorative_Objects": "COLOR_03"
            },
            "04_STRUCTURE": {
                "color": "COLOR_04", "Walls": "COLOR_04", "Floors": "COLOR_04", "Ceilings": "COLOR_04", 
                "Doors": "COLOR_04", "Windows": "COLOR_04"
            },
            "07_UTILITIES": {
                "color": "COLOR_05", "Electrical": "COLOR_05", "Plumbing": "COLOR_05", "HVAC": "COLOR_05"
            },
            "10_HIDE": {"color": "COLOR_08", "disable_in_render": True}
        }
    }
    create_nested_structure_logic(context, structure)

# --- OPERATORS ---

class PM_OT_CreateSet1(bpy.types.Operator):
    """Generates a comprehensive collection structure for Architectural 
    External/Landscape projects (Buildings, Plants, Props, etc.)"""
    bl_idname = "pm.create_set1"
    bl_label = "Create Set 1 (Archviz)"
    bl_options = {'REGISTER', 'UNDO'}

    main_collection_name: bpy.props.StringProperty(name="Project Name", default="ProjectName")

    def execute(self, context):
        create_set_1_logic(context, self.main_collection_name)
        self.report({'INFO'}, f"Set 1 structure created: {self.main_collection_name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class PM_OT_CreateSet2(bpy.types.Operator):
    """Generates a clean collection structure tailored for Interior 
    design projects (Furniture, Decor, Lighting, Plans, etc.)"""
    bl_idname = "pm.create_set2"
    bl_label = "Create Set 2 (Interior)"
    bl_options = {'REGISTER', 'UNDO'}

    main_collection_name: bpy.props.StringProperty(name="Project Name", default="ProjectName")

    def execute(self, context):
        create_set_2_logic(context, self.main_collection_name)
        self.report({'INFO'}, f"Set 2 structure created: {self.main_collection_name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# --- UI DRAWING ---

def draw_ui(layout, context):
    box = layout.box()
    box.label(text="Layer Management", icon='OUTLINER_OB_GROUP_INSTANCE')
    row = box.row(align=True)
    row.operator("pm.create_set1", text="Archviz Set", icon='WORLD_DATA')
    row.operator("pm.create_set2", text="Interior Set", icon='HOME')

# --- REGISTRATION ---

classes = (
    PM_OT_CreateSet1,
    PM_OT_CreateSet2,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
