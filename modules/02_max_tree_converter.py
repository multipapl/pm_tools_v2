import bpy
import os
import re

UI_CATEGORY = "CONVERTERS"

# --- CONSTANTS ---

LEAF_SHADER_INFO = {
    'node_group_name': 'PAPL_LeafShader',
    'socket_map': {
        'BASE_COLOR': 'Base Color', 
        'ALPHA': 'Opacity',
        'NORMAL': 'Normal', 
        'TRANSLUCENCY': 'Translusency',
    }
}

TEXTURE_SUFFIXES = {
    'BASE_COLOR': ['_d', '_diff', '_albedo', '_col'],
    'ALPHA': ['_a', '_alpha', '_mask', '_opacity'],
    'ROUGHNESS': ['_r', '_rough', '_roughness'],
    'NORMAL': ['_n', '_nrm', '_normal'],
    'TRANSLUCENCY': ['_trans', '_sss', '_transl', '_translucency'],
    'GLOSS': ['_g', '_gloss', '_glossiness']
}

# --- LOGIC ---

def ensure_leaf_shader_logic():
    """Checks if the leaf shader node group exists, and if not, attempts to append it from assets."""
    group_name = LEAF_SHADER_INFO['node_group_name']
    if group_name in bpy.data.node_groups:
        return True, ""

    # Path to assets/node_library.blend in the addon folder
    addon_dir = os.path.dirname(os.path.dirname(__file__))
    blend_path = os.path.join(addon_dir, "assets", "node_library.blend")

    if not os.path.exists(blend_path):
        return False, f"Asset library not found at: {blend_path}"

    try:
        with bpy.data.libraries.load(blend_path) as (data_from, data_to):
            if group_name in data_from.node_groups:
                data_to.node_groups.append(group_name)
            else:
                return False, f"Node Group '{group_name}' not found in library file."
        return True, ""
    except Exception as e:
        return False, f"Failed to append node group: {str(e)}"

def find_asset_keyword(material_name, keywords):
    """Finds a matching keyword in the material name to determine its type."""
    mat_name_lower = material_name.lower().replace(" ", "_")
    for keyword in keywords:
        if keyword in mat_name_lower:
            return keyword
    return None

def find_texture_path(material_name, tex_type, texture_folder, texture_files):
    """Searches for a texture file matching the material name and texture type."""
    base_name = material_name.lower().replace(" ", "_")
    suffixes = TEXTURE_SUFFIXES.get(tex_type, [])
    for filename in texture_files:
        fn_lower = filename.lower().replace(" ", "_")
        if fn_lower.startswith(base_name):
            remaining_part = fn_lower[len(base_name):]
            for suffix in suffixes:
                pattern = f"{re.escape(suffix)}([_\\.]|$)"
                if re.search(pattern, remaining_part):
                    return os.path.join(texture_folder, filename)
    return None

def create_texture_node(nodes, path, tex_type, y_pos):
    """Creates an image texture node and sets the correct color space."""
    tex_node = nodes.new('ShaderNodeTexImage')
    try:
        tex_node.image = bpy.data.images.load(path, check_existing=True)
    except Exception:
        return None
        
    tex_node.location = (-650, y_pos)
    if tex_type in ['BASE_COLOR', 'TRANSLUCENCY']:
        tex_node.image.colorspace_settings.name = 'sRGB'
    else:
        tex_node.image.colorspace_settings.name = 'Non-Color'
    return tex_node

def process_materials_logic(context, materials_to_process, opaque_maps_to_use, transparent_maps_to_use):
    """Processes materials by connecting textures to appropriate shaders."""
    props = context.scene.pm_maxtree_converter_props
    texture_folder = bpy.path.abspath(props.texture_folder_path)
    
    if not os.path.isdir(texture_folder): 
        return 0, "Texture folder not found"

    # Pre-parse keywords
    transparent_keywords = [k.strip().lower() for k in props.transparent_keywords.split(',') if k.strip()]
    opaque_keywords = [k.strip().lower() for k in props.opaque_keywords.split(',') if k.strip()]
    all_keywords = transparent_keywords + opaque_keywords
    
    try:
        texture_files = os.listdir(texture_folder)
    except Exception as e:
        return 0, f"Error reading texture folder: {str(e)}"

    # Attempt to load the leaf shader if it might be needed
    shader_ready, shader_error = ensure_leaf_shader_logic()
    if not shader_ready:
        print(f"[PM Tools] Warning: {shader_error}")

    processed_count = 0
    for mat in materials_to_process:
        if not mat or not mat.use_nodes: 
            continue
            
        asset_keyword = find_asset_keyword(mat.name, all_keywords)
        if not asset_keyword: 
            continue

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clear existing nodes except for the Output
        for node in nodes:
            if node.type != 'OUTPUT_MATERIAL': 
                nodes.remove(node)
        
        output_node = nodes.get('Material Output') or nodes.new('ShaderNodeOutputMaterial')
        
        y_pos = 0
        y_offset = -350
        is_transparent = asset_keyword in transparent_keywords
        is_opaque = asset_keyword in opaque_keywords

        # 1. Setup the main shader node
        if is_transparent:
            group_name = LEAF_SHADER_INFO['node_group_name']
            if group_name in bpy.data.node_groups:
                shader = nodes.new('ShaderNodeGroup')
                shader.node_tree = bpy.data.node_groups[group_name]
                shader.location = (-250, 0)
                links.new(shader.outputs[0], output_node.inputs['Surface'])
                
                socket_map = LEAF_SHADER_INFO['socket_map']
                base_color_node = None
                
                # Connection logic for transparent materials
                if transparent_maps_to_use.get('BASE_COLOR'):
                    path = find_texture_path(mat.name, 'BASE_COLOR', texture_folder, texture_files)
                    if path:
                        base_color_node = create_texture_node(nodes, path, 'BASE_COLOR', y_pos)
                        if base_color_node:
                            links.new(base_color_node.outputs['Color'], shader.inputs[socket_map['BASE_COLOR']])
                            y_pos += y_offset
                
                if transparent_maps_to_use.get('ALPHA'):
                    path = find_texture_path(mat.name, 'ALPHA', texture_folder, texture_files)
                    if path:
                        tex_node = create_texture_node(nodes, path, 'ALPHA', y_pos)
                        if tex_node:
                            links.new(tex_node.outputs['Color'], shader.inputs[socket_map['ALPHA']])
                            y_pos += y_offset
                    elif base_color_node:
                        links.new(base_color_node.outputs['Alpha'], shader.inputs[socket_map['ALPHA']])
                
                if transparent_maps_to_use.get('NORMAL'):
                    path = find_texture_path(mat.name, 'NORMAL', texture_folder, texture_files)
                    if path:
                        tex_node = create_texture_node(nodes, path, 'NORMAL', y_pos)
                        if tex_node:
                            links.new(tex_node.outputs['Color'], shader.inputs[socket_map['NORMAL']])
                            y_pos += y_offset
                
                if transparent_maps_to_use.get('TRANSLUCENCY'):
                    path = find_texture_path(mat.name, 'TRANSLUCENCY', texture_folder, texture_files)
                    if path:
                        tex_node = create_texture_node(nodes, path, 'TRANSLUCENCY', y_pos)
                        if tex_node:
                            links.new(tex_node.outputs['Color'], shader.inputs[socket_map['TRANSLUCENCY']])
                            y_pos += y_offset
        
        elif is_opaque:
            shader = nodes.new('ShaderNodeBsdfPrincipled')
            shader.location = (-250, 0)
            links.new(shader.outputs[0], output_node.inputs['Surface'])
            
            # Connection logic for opaque materials
            if opaque_maps_to_use.get('BASE_COLOR'):
                path = find_texture_path(mat.name, 'BASE_COLOR', texture_folder, texture_files)
                if path:
                    tex_node = create_texture_node(nodes, path, 'BASE_COLOR', y_pos)
                    if tex_node:
                        links.new(tex_node.outputs['Color'], shader.inputs['Base Color'])
                        y_pos += y_offset
            
            if opaque_maps_to_use.get('NORMAL'):
                path = find_texture_path(mat.name, 'NORMAL', texture_folder, texture_files)
                if path:
                    tex_node = create_texture_node(nodes, path, 'NORMAL', y_pos)
                    if tex_node:
                        normal_map_node = nodes.new('ShaderNodeNormalMap')
                        normal_map_node.location = (-400, y_pos)
                        links.new(tex_node.outputs['Color'], normal_map_node.inputs['Color'])
                        links.new(normal_map_node.outputs['Normal'], shader.inputs['Normal'])
                        y_pos += y_offset
            
            if opaque_maps_to_use.get('ROUGHNESS'):
                rough_path = find_texture_path(mat.name, 'ROUGHNESS', texture_folder, texture_files)
                if rough_path:
                    tex_node = create_texture_node(nodes, rough_path, 'ROUGHNESS', y_pos)
                    if tex_node:
                        links.new(tex_node.outputs['Color'], shader.inputs['Roughness'])
                else:
                    gloss_path = find_texture_path(mat.name, 'GLOSS', texture_folder, texture_files)
                    if gloss_path:
                        tex_node = create_texture_node(nodes, gloss_path, 'GLOSS', y_pos)
                        if tex_node:
                            invert_node = nodes.new('ShaderNodeInvert')
                            invert_node.location = (-400, y_pos)
                            links.new(tex_node.outputs['Color'], invert_node.inputs['Color'])
                            links.new(invert_node.outputs['Color'], shader.inputs['Roughness'])
        
        # Set viewport colors for better organization
        if is_transparent: 
            mat.diffuse_color = (0.095, 0.185, 0.036, 1.0) # Greenish
        elif is_opaque: 
            mat.diffuse_color = (0.163, 0.116, 0.058, 1.0) # Brownish
            
        processed_count += 1
        
    return processed_count, None

# --- CLASSES ---

class PM_MaxTreeConverterProps(bpy.types.PropertyGroup):
    """Properties for the MaxTree Converter tool"""
    texture_folder_path: bpy.props.StringProperty(name="Texture Folder", subtype='DIR_PATH')
    transparent_keywords: bpy.props.StringProperty(name="Transparent Keywords", default="leaf,leaves,needle,flower")
    opaque_keywords: bpy.props.StringProperty(name="Opaque Keywords", default="bark,trunk,branch,mesh,stem,fruit")
    
    # Opaque toggles
    use_opaque_base_color: bpy.props.BoolProperty(name="Base Color", default=True)
    use_opaque_roughness: bpy.props.BoolProperty(name="Roughness", default=True)
    use_opaque_normal: bpy.props.BoolProperty(name="Normal Map", default=True)
    
    # Transparent toggles
    use_transparent_base_color: bpy.props.BoolProperty(name="Base Color", default=True)
    use_transparent_opacity: bpy.props.BoolProperty(name="Opacity", default=True)
    use_transparent_normal: bpy.props.BoolProperty(name="Normal Map", default=False)
    use_transparent_translucency: bpy.props.BoolProperty(name="Translucency", default=False)

class PM_OT_MaxTreeConverter(bpy.types.Operator):
    """Automates material setup for vegetation: loads textures based on 
    keywords and connects them to the PAPL_LeafShader or Principled BSDF"""
    bl_idname = "pm.maxtree_converter"
    bl_label = "Process Plant Materials"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        props = context.scene.pm_maxtree_converter_props
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "Please select at least one Mesh object")
            return {'CANCELLED'}
            
        # Collect all materials from selected objects
        materials = set()
        for obj in selected_objects:
            for slot in obj.material_slots:
                if slot.material: 
                    materials.add(slot.material)
        
        if not materials:
            self.report({'WARNING'}, "No materials found on selected objects")
            return {'CANCELLED'}

        opaque_maps = {
            'BASE_COLOR': props.use_opaque_base_color, 
            'ROUGHNESS': props.use_opaque_roughness, 
            'NORMAL': props.use_opaque_normal
        }
        transparent_maps = {
            'BASE_COLOR': props.use_transparent_base_color, 
            'ALPHA': props.use_transparent_opacity, 
            'NORMAL': props.use_transparent_normal, 
            'TRANSLUCENCY': props.use_transparent_translucency
        }

        count, error = process_materials_logic(context, list(materials), opaque_maps, transparent_maps)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Successfully processed {count} materials")
        return {'FINISHED'}

# --- UI DRAWING ---

class PM_PT_MaxTreeSettings(bpy.types.Panel):
    """Sub-panel drawing in a popover for MaxTree settings"""
    bl_label = "MaxTree Settings"
    bl_idname = "PM_PT_maxtree_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Removing bl_category and adding HIDE_HEADER to keep it out of the N-Panel list
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.pm_maxtree_converter_props
        
        col = layout.column(align=True)
        col.label(text="Keywords:")
        col.prop(props, "opaque_keywords", text="Opaque")
        col.prop(props, "transparent_keywords", text="Trans")
        
        layout.separator()
        
        split = layout.split(factor=0.5)
        col1 = split.column(align=True)
        col1.label(text="Opaque Maps:")
        col1.prop(props, "use_opaque_base_color")
        col1.prop(props, "use_opaque_roughness")
        col1.prop(props, "use_opaque_normal")

        col2 = split.column(align=True)
        col2.label(text="Trans Maps:")
        col2.prop(props, "use_transparent_base_color")
        col2.prop(props, "use_transparent_opacity")
        col2.prop(props, "use_transparent_normal")
        col2.prop(props, "use_transparent_translucency")

def draw_ui(layout):
    scene = bpy.context.scene
    props = scene.pm_maxtree_converter_props
    
    box = layout.box()
    box.label(text="MaxTree Converter", icon='NODE_MATERIAL')
    
    row = box.row(align=True)
    row.prop(props, "texture_folder_path", text="")
    # Settings Popover
    row.popover(panel="PM_PT_maxtree_settings", icon='SETTINGS', text="")
    
    box.operator("pm.maxtree_converter", text="Process Materials", icon='FORWARD')

# --- REGISTRATION ---

classes = (
    PM_MaxTreeConverterProps,
    PM_OT_MaxTreeConverter,
    PM_PT_MaxTreeSettings,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pm_maxtree_converter_props = bpy.props.PointerProperty(type=PM_MaxTreeConverterProps)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pm_maxtree_converter_props
