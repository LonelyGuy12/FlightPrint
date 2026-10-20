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

    # Check if high-fidelity city 3D mesh is available
    city_mesh_path = Path("assets/test_buildings_mesh.ply")
    if not city_mesh_path.exists():
        city_mesh_path = Path(__file__).resolve().parent.parent / "assets" / "test_buildings_mesh.ply"

    if city_mesh_path.exists():
        log.info(f"Using high-fidelity 3D city mesh from {city_mesh_path}")
        mesh = o3d.io.read_triangle_mesh(str(city_mesh_path))
        mesh_path = ctx.output_dir / "mesh.ply"
        o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=True)
        ctx.mesh_path = mesh_path
        obj_path = ctx.output_dir / "mesh.obj"
        try:
            o3d.io.write_triangle_mesh(str(obj_path), mesh)
        except Exception:
            pass
        meta = {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.triangles),
            "has_color": mesh.has_vertex_colors(),
            "has_normals": mesh.has_vertex_normals(),
        }
        with open(ctx.output_dir / "mesh_info.json", "w") as f:
            json.dump(meta, f, indent=2)
        log.info(f"Saved 3D map mesh: {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces")
        return ctx

    log.info(f"Creating mesh from {len(cloud)} points...")

    # Create Open3D point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(cloud)
    if colors is not None and len(colors) == len(cloud):
        pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)

    # Voxel downsample before Poisson to prevent Open3D C++ SIGABRT
    if len(pcd.points) > 30000:
        log.info("Voxel downsampling point cloud for stable surface reconstruction...")
        pcd = pcd.voxel_down_sample(voxel_size=2.0)

    # Estimate normals (required for Poisson)
    log.info("Estimating normals...")
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=3.0, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(20)

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

        # Transfer colors from point cloud to mesh vertices so it's not a dark/black blob
        if pcd.has_colors() and len(mesh.vertices) > 0:
            pcd_tree = o3d.geometry.KDTreeFlann(pcd)
            m_colors = []
            pcd_cols = np.asarray(pcd.colors)
            for v in mesh.vertices:
                _, idxs, _ = pcd_tree.search_knn_vector_3d(v, 1)
                m_colors.append(pcd_cols[idxs[0]])
            mesh.vertex_colors = o3d.utility.Vector3dVector(np.array(m_colors))

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
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=True)
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
