"""FlightPrint CLI — Run the pipeline from the command line.

Usage:
    python -m pipeline.cli --video path/to/video.mp4 --metadata path/to/metadata.json --output output_dir
    python -m pipeline.cli --video path/to/video.mp4 --metadata path/to/metadata.json --output output_dir --stages 1 2 3 4
"""

import argparse
import sys
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="FlightPrint — 3D reconstruction from drone video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Operating Modes (auto-detected):
  FULL            Video + GPS + IMU  → metric georeferenced output
  SCALE_ASSISTED  Video + GPS only   → approximate metric output
                  Video + altitude   → approximate metric (local frame)
  VISION_ONLY     Video only         → relative/unscaled local output
        """,
    )
    parser.add_argument("--video", required=True, help="Path to drone video (MP4)")
    parser.add_argument("--metadata", default=None,
                       help="Path to metadata JSON (optional — omit for vision-only mode)")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--stages", nargs="*", type=int, default=None,
                       help="Stages to run (1-9). Default: all")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to pipeline config JSON (optional)")
    parser.add_argument("--altitude", type=float, default=None,
                       help="Approximate flight altitude in meters (enables scale-assisted mode)")

    args = parser.parse_args()

    # Validate inputs
    video = Path(args.video)

    if not video.exists():
        print(f"Error: Video file not found: {video}")
        sys.exit(1)

    metadata = None
    if args.metadata:
        metadata = Path(args.metadata)
        if not metadata.exists():
            print(f"Error: Metadata file not found: {metadata}")
            sys.exit(1)
        metadata = str(metadata)

    config = {}
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    # Pass altitude hint through config if provided
    if args.altitude is not None:
        config["user_altitude_m"] = args.altitude

    # Run pipeline
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline.runner import run_pipeline
    ctx = run_pipeline(
        video_path=str(video),
        metadata_path=metadata,
        output_dir=args.output,
        config=config,
        stages=args.stages,
    )

    # Summary
    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print(f"  Mode:             {ctx.reconstruction_mode}")
    print(f"  Scale:            {ctx.scale_status}")
    print(f"  Frames extracted: {len(ctx.frame_paths)}")
    print(f"  Poses estimated:  {sum(1 for p in ctx.poses if p is not None)}")
    if ctx.sparse_cloud is not None:
        print(f"  Sparse points:    {len(ctx.sparse_cloud)}")
    if ctx.dense_cloud is not None:
        print(f"  Dense points:     {len(ctx.dense_cloud)}")
    print(f"  Anomalies found:  {len(ctx.anomalies)}")
    print(f"  Output dir:       {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
