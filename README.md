# PM Tools v2.0

Personal Blender addon for architectural visualization and CG production. Optimized for Blender 5.0+.

## Core Concept
A complete modular refactor of the previous toolset. The architecture is designed for absolute flexibility: each feature is a standalone file within the `modules/` directory, automatically discovered and registered by the core system.

## Features (In Progress)
- **Advanced Camera Converter**: Transform Empties into cameras with architectural rotation constraints.
- **Mesh Instance Linker**: Scene optimization via Shared Data based on vertex counts.
- **Backplate Tool**: Mathematically accurate plane alignment for AI Matte Painting workflows.
- **Dynamic UI**: Modular N-panel that builds itself based on active modules.

## Technical Specs
- **IDE**: VS Code
- **Language**: Python 3.11+
- **Blender Version**: 5.0.1+