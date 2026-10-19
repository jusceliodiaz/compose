import bpy
import os

output_dir = r"c:\Users\saant\Desktop\meu-configurador-zytro"

# Clear all objects
bpy.ops.wm.read_factory_settings(use_empty=True)

# 1. Setup Scene and Engine
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.film_transparent = False

# Enable View Layer Passes
view_layer = scene.view_layers[0]
view_layer.use_pass_uv = True
view_layer.use_pass_shadow = True
view_layer.use_pass_ambient_occlusion = True
view_layer.use_pass_material_index = True

# 2. Create Geometry
# Floor (Chão)
bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "Floor"
floor.pass_index = 1  # ID 1

# Wall (Parede de fundo)
bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 5, 5), rotation=(1.5708, 0, 0))
wall = bpy.context.active_object
wall.name = "Wall"
wall.pass_index = 2

# Hero Object (Móvel / Cubo central para projetar sombra no piso)
bpy.ops.mesh.primitive_cube_add(size=1.6, location=(0, 1.5, 0.8))
cube = bpy.context.active_object
cube.name = "CenterFurniture"
cube.pass_index = 3

# 3. Materials
mat_floor = bpy.data.materials.new(name="Mat_Floor")
mat_floor.use_nodes = True
mat_floor.pass_index = 1
bsdf_floor = mat_floor.node_tree.nodes.get("Principled BSDF")
bsdf_floor.inputs['Base Color'].default_value = (0.7, 0.65, 0.6, 1.0)
bsdf_floor.inputs['Roughness'].default_value = 0.3
floor.data.materials.append(mat_floor)

mat_wall = bpy.data.materials.new(name="Mat_Wall")
mat_wall.use_nodes = True
mat_wall.pass_index = 2
bsdf_wall = mat_wall.node_tree.nodes.get("Principled BSDF")
bsdf_wall.inputs['Base Color'].default_value = (0.9, 0.9, 0.92, 1.0)
wall.data.materials.append(mat_wall)

mat_cube = bpy.data.materials.new(name="Mat_Cube")
mat_cube.use_nodes = True
mat_cube.pass_index = 3
bsdf_cube = mat_cube.node_tree.nodes.get("Principled BSDF")
bsdf_cube.inputs['Base Color'].default_value = (0.2, 0.25, 0.35, 1.0)
cube.data.materials.append(mat_cube)

# 4. Lighting & Camera
# Sun light
bpy.ops.object.light_add(type='SUN', location=(3, -3, 6), rotation=(0.785, 0.4, -0.6))
sun = bpy.context.active_object
sun.data.energy = 3.5

# Camera
bpy.ops.object.camera_add(location=(0, -6.5, 3.2), rotation=(1.25, 0, 0))
cam = bpy.context.active_object
scene.camera = cam

# 5. Compositor Nodes to Output Passes
scene.use_nodes = True
if hasattr(scene, "node_tree") and scene.node_tree:
    tree = scene.node_tree
else:
    tree = bpy.data.node_groups.new(name="Compositing", type="CompositorNodeTree")
    scene.compositing_node_group = tree

for node in list(tree.nodes):
    tree.nodes.remove(node)

rlayers = tree.nodes.new(type="CompositorNodeRLayers")
rlayers.location = (0, 0)

# Output node for beauty
comp = tree.nodes.new(type="NodeGroupOutput")
comp.location = (400, 100)
# Create input socket if needed
if len(comp.inputs) == 0:
    tree.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
if 'Image' in comp.inputs and 'Image' in rlayers.outputs:
    tree.links.new(rlayers.outputs['Image'], comp.inputs['Image'])

# File Output for UV Pass & Masks
file_out = tree.nodes.new(type="CompositorNodeOutputFile")
file_out.location = (400, -100)
file_out.base_path = output_dir

# Slot 0: UV Pass (PNG 16-bit)
file_out.file_slots[0].path = "pass_uv"
file_out.format.file_format = 'PNG'
file_out.format.color_depth = '16'
file_out.format.color_mode = 'RGB'
tree.links.new(rlayers.outputs['UV'], file_out.inputs['pass_uv'])

# Slot 1: Material Index / Mask (Piso tem ID 1)
id_mask = tree.nodes.new(type="CompositorNodeIDMask")
id_mask.location = (200, -250)
id_mask.index = 1
tree.links.new(rlayers.outputs['IndexMA'], id_mask.inputs['ID value'])

slot_mask = file_out.file_slots.new("pass_mask_floor")
tree.links.new(id_mask.outputs['Alpha'], file_out.inputs['pass_mask_floor'])

# Slot 2: Shadow / AO
slot_ao = file_out.file_slots.new("pass_ao")
tree.links.new(rlayers.outputs['AO'], file_out.inputs['pass_ao'])

# Render setup
scene.render.filepath = os.path.join(output_dir, "render_beauty.png")
print("Rendering test scene passes...")
bpy.ops.render.render(write_still=True)
print("Render finished successfully!")
