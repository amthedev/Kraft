"""
Script de exemplo para Blender Python API (bpy).
Este arquivo é usado como template pela plataforma Kraft.
O Blender Fabricator gera scripts dinâmicos baseados neste padrão.

Uso:
  blender --background --python create_asset.py
"""

import bpy
import sys


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def setup_material(obj, color=(0.5, 0.3, 0.1, 1.0)):
    mat = bpy.data.materials.new(name="KraftMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.8
        bsdf.inputs["Metallic"].default_value = 0.0
    obj.data.materials.append(mat)


def create_low_poly_character():
    """Exemplo: personagem low-poly básico."""
    clear_scene()

    # Corpo
    bpy.ops.mesh.primitive_cube_add(size=0.8, location=(0, 0, 0.4))
    body = bpy.context.active_object
    body.name = "Body"
    setup_material(body, (0.2, 0.5, 0.8, 1.0))

    # Cabeça
    bpy.ops.mesh.primitive_uvsphere_add(radius=0.35, location=(0, 0, 1.15), segments=8, ring_count=6)
    head = bpy.context.active_object
    head.name = "Head"
    setup_material(head, (0.9, 0.7, 0.5, 1.0))

    # Parenta cabeça ao corpo
    head.parent = body

    # Agrupa tudo
    bpy.ops.object.select_all(action="SELECT")


def export_glb(output_path: str):
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        export_apply=True,
        export_materials="EXPORT",
        export_animations=True,
    )


if __name__ == "__main__":
    output = "/tmp/kraft_output.glb"
    # Pega path de saída dos argumentos se fornecido
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args:
            output = args[0]

    create_low_poly_character()
    export_glb(output)
    print(f"[Kraft] Asset exportado para: {output}")
