# Blender Paint It

Substance Painter-style **paint layers and masks** for Blender's Texture Paint mode.

Blender has no built-in paint layer stack. Blender Paint It builds one on top of
image textures and material nodes, so you can paint non-destructively.

> Status: **v0.1.0 (MVP)**. Base Color channel only.

## Features

- Layer stack per material (top of the list = top layer)
- Add transparent or solid fill layers (512 / 1024 / 2048 / 4096)
- Remove, reorder, duplicate, show/hide layers
- 19 blend modes and per-layer opacity
- Per-layer masks (reveal / hide) with a Layer/Mask paint target switch
- Nodes are generated automatically and connected to the Principled BSDF Base Color
- The selected layer becomes the active Texture Paint canvas
- Save all layer images to `//textures` (or pack them if the .blend is unsaved)

## Requirements

- Blender 4.2 or newer
- A mesh with UVs

## Install

1. Zip the **contents** of the `paint_layers/` folder
   (`__init__.py` and `blender_manifest.toml` must be at the zip root), or run
   `blender --command extension build` inside `paint_layers/`.
2. In Blender: *Edit > Preferences > Get Extensions > (arrow, top right) > Install from Disk*.
3. Enable the add-on. The panel is in the 3D Viewport sidebar (`N`), tab **Paint Layers**.

## Usage

1. Select a mesh with UVs.
2. Click **Add Layer** (or **Add Fill**).
3. Enter **Texture Paint Mode** and paint.
4. Use blend mode **Erase Alpha** on the brush to erase on a transparent layer.
5. Click **Save Layer Images** before closing Blender.

## Roadmap

- Merge down
- Layer folders
- Full PBR channels (Roughness, Metallic, Normal, Height) and export
- Fill layers with procedural content, mask generators (curvature, AO)

## License

GPL-3.0-or-later.
