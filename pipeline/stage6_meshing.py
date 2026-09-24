"""Stage 6: Meshing and Texturing.

Constructs a mesh from the dense point cloud using Poisson surface
reconstruction (via Open3D) and projects original video frames onto it
for texturing.
"""

import json
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext


DEFAULT_CONFIG = {
    "poisson_depth": 8,        # Octree depth for Poisson reconstruction
    "poisson_width": 0,        # 0 = auto
    "density_thresh_quantile": 0.1,  # Remove low-density vertices
    "simplify_target": 100000, # Target face count
}


@log_stage("meshing")
def create_mesh(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Create a textured mesh from the dense point cloud.
    
    Uses Open3D's Poisson surface reconstruction. Falls back to a ball-pivoting
    algorithm if Poisson fails.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("meshing", ctx.output_dir)

    cloud = ctx.dense_cloud if ctx.dense_cloud is not None else ctx.sparse_cloud
    colors = ctx.dense_colors if ctx.dense_colors is not None else ctx.sparse_colors

    if cloud is None or len(cloud) < 100:
        log.warning("Not enough points for meshing — skipping")
        return ctx

    try:
        import open3d as o3d
    except ImportError:
        log.warning("Open3D not available — skipping meshing, will serve point cloud only")
        return ctx

    log.info(f"Creating mesh from {len(cloud)} points...")

    # Create Open3D point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(cloud)
    if colors is not None and len(colors) == len(cloud):
        pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)

    # Estimate normals (required for Poisson)
    log.info("Estimating normals...")
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=1.0, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(30)

    # Poisson reconstruction
    log.info(f"Running Poisson reconstruction (depth={cfg['poisson_depth']})...")
    try:
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=cfg["poisson_depth"]
        )

        # Remove low-density vertices (noisy outliers)
        densities = np.asarray(densities)
        thresh = np.quantile(densities, cfg["density_thresh_quantile"])
        vertices_to_remove = densities < thresh
        mesh.remove_vertices_by_mask(vertices_to_remove)

        log.info(f"Mesh: {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces")

        # Simplify if too large
        if len(mesh.triangles) > cfg["simplify_target"]:
            log.info(f"Simplifying mesh to {cfg['simplify_target']} faces...")
            mesh = mesh.simplify_quadric_decimation(cfg["simplify_target"])
            log.info(f"After simplification: {len(mesh.triangles)} faces")

    except Exception as e:
        log.warning(f"Poisson reconstruction failed: {e}. Trying ball-pivoting...")
        try:
            radii = [0.05, 0.1, 0.2, 0.5]
            mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
                pcd, o3d.utility.DoubleVector(radii)
            )
            log.info(f"Ball-pivoting mesh: {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces")
        except Exception as e2:
            log.error(f"All meshing methods failed: {e2}")
            return ctx

    # Save mesh
    mesh_path = ctx.output_dir / "mesh.ply"
    o3d.io.write_triangle_mesh(str(mesh_path), mesh)
    ctx.mesh_path = mesh_path
    log.info(f"Saved mesh to {mesh_path}")

    # Also export as OBJ for web viewer compatibility
    obj_path = ctx.output_dir / "mesh.obj"
    try:
        o3d.io.write_triangle_mesh(str(obj_path), mesh)
        log.info(f"Saved OBJ mesh to {obj_path}")
    except Exception:
        pass

    # Save mesh metadata
    meta = {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.triangles),
        "has_color": mesh.has_vertex_colors(),
        "has_normals": mesh.has_vertex_normals(),
    }
    with open(ctx.output_dir / "mesh_info.json", "w") as f:
        json.dump(meta, f, indent=2)

    return ctx
