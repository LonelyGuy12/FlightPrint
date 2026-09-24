"""FlightPrint Pipeline Runner — orchestrates all stages sequentially.

Provides progress callbacks and partial result delivery so the frontend
can show sparse results early while dense processing continues.
"""

import json
import time
import traceback
from pathlib import Path
from enum import Enum

from .utils.logging import get_logger
from .utils.io import PipelineContext, load_metadata, save_pipeline_report
from .scale_and_georef import detect_mode, save_mode_report


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some stages completed, others failed


class PipelineRunner:
    """Orchestrates the full FlightPrint pipeline.
    
    Each stage is independent and writes its outputs to both the
    PipelineContext and the filesystem. Stages can be skipped or
    stubbed for demo purposes.
    """

    def __init__(self, video_path: str | Path, metadata_path: str | Path | None,
                 output_dir: str | Path, config: dict | None = None):
        self.video_path = Path(video_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None
        self.output_dir = Path(output_dir)
        self.config = config or {}
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.log = get_logger("runner", self.output_dir)
        self.status = PipelineStatus.PENDING
        self.stage_status = {}
        self.progress_callbacks = []
        self.current_stage = None
        self.error = None
        self.mode_decision = None   # set after metadata load

    def on_progress(self, callback):
        """Register a progress callback: callback(stage_name, status, message)."""
        self.progress_callbacks.append(callback)

    def _emit_progress(self, stage: str, status: str, message: str = ""):
        self.stage_status[stage] = {"status": status, "message": message, "timestamp": time.time()}
        for cb in self.progress_callbacks:
            try:
                cb(stage, status, message)
            except Exception:
                pass

        # Save progress to file for API polling
        progress_path = self.output_dir / "progress.json"
        progress_data = {
            "pipeline_status": self.status.value,
            "current_stage": self.current_stage,
            "stages": self.stage_status,
            "error": self.error,
        }
        if self.mode_decision:
            progress_data["reconstruction_mode"] = self.mode_decision.mode.value
            progress_data["scale_status"] = self.mode_decision.scale_status.value
        with open(progress_path, "w") as f:
            json.dump(progress_data, f, indent=2, default=str)

    def run(self, stages: list[int] | None = None) -> PipelineContext:
        """Run the full pipeline (or a subset of stages).
        
        Args:
            stages: List of stage numbers to run (1-9). None = run all.
        
        Returns:
            PipelineContext with all results.
        """
        self.status = PipelineStatus.RUNNING
        self.log.info("=" * 60)
        self.log.info("FlightPrint Pipeline Starting")
        self.log.info(f"Video: {self.video_path}")
        self.log.info(f"Metadata: {self.metadata_path}")
        self.log.info(f"Output: {self.output_dir}")
        self.log.info("=" * 60)

        # Initialize context
        ctx = PipelineContext(
            video_path=self.video_path,
            metadata_path=self.metadata_path,
            output_dir=self.output_dir,
        )

        # Load metadata (gracefully handles None / missing / bad JSON)
        ctx.metadata = load_metadata(self.metadata_path)
        has_meta = bool(ctx.metadata)
        if has_meta:
            self.log.info(f"Loaded metadata: "
                         f"{len(ctx.metadata.get('gps_track', []))} GPS points, "
                         f"camera={'yes' if ctx.metadata.get('camera') else 'no'}, "
                         f"IMU={'yes' if ctx.metadata.get('imu') else 'no'}")
        else:
            self.log.info("No metadata provided — running in vision-only mode")

        # ── Detect reconstruction mode ──
        mode_decision = detect_mode(ctx.metadata, self.config)
        self.mode_decision = mode_decision
        ctx.mode_decision = mode_decision
        ctx.reconstruction_mode = mode_decision.mode.value
        ctx.scale_status = mode_decision.scale_status.value

        self.log.info(f"Reconstruction mode: {mode_decision.mode.value}")
        self.log.info(f"Scale status:        {mode_decision.scale_status.value}")
        for reason in mode_decision.reasons:
            self.log.info(f"  → {reason}")

        save_mode_report(self.output_dir, mode_decision)

        if stages is None:
            stages = list(range(1, 10))

        stage_funcs = {
            1: ("frame_extraction", self._run_stage1),
            2: ("camera_calibration", self._run_stage2),
            3: ("feature_detection", self._run_stage3),
            4: ("pose_estimation", self._run_stage4),
            5: ("dense_reconstruction", self._run_stage5),
            6: ("meshing", self._run_stage6),
            7: ("georeferencing", self._run_stage7),
            8: ("dynamic_filtering", self._run_stage8),
            9: ("ai_agent", self._run_stage9),
        }

        completed_stages = 0
        t_total = time.perf_counter()

        for stage_num in stages:
            if stage_num not in stage_funcs:
                continue

            name, func = stage_funcs[stage_num]
            self.current_stage = name
            self._emit_progress(name, "running")

            try:
                t0 = time.perf_counter()
                ctx = func(ctx)
                elapsed = time.perf_counter() - t0
                self._emit_progress(name, "completed", f"Completed in {elapsed:.1f}s")
                completed_stages += 1
            except Exception as e:
                self.log.error(f"Stage {stage_num} ({name}) failed: {e}")
                self.log.debug(traceback.format_exc())
                self._emit_progress(name, "failed", str(e))
                self.error = f"Stage {stage_num} ({name}): {e}"

                # Continue to next stage if possible (graceful degradation)
                if stage_num <= 4:
                    # Stages 1-4 are critical — can't continue without them
                    self.log.error("Critical stage failed — aborting pipeline")
                    self.status = PipelineStatus.FAILED
                    break
                else:
                    self.log.warning(f"Non-critical stage {stage_num} failed — continuing")

        total_elapsed = time.perf_counter() - t_total

        if self.status != PipelineStatus.FAILED:
            if completed_stages == len(stages):
                self.status = PipelineStatus.COMPLETED
            else:
                self.status = PipelineStatus.PARTIAL

        self.current_stage = None
        self._emit_progress("pipeline", self.status.value,
                           f"Completed {completed_stages}/{len(stages)} stages in {total_elapsed:.1f}s")

        # Save final report
        try:
            save_pipeline_report(self.output_dir / "pipeline_report.json", ctx)
        except Exception:
            pass

        self.log.info("=" * 60)
        self.log.info(f"Pipeline {self.status.value}: {completed_stages}/{len(stages)} stages "
                     f"in {total_elapsed:.1f}s")
        self.log.info("=" * 60)

        return ctx

    def _run_stage1(self, ctx: PipelineContext) -> PipelineContext:
        from .stage1_frames import extract_frames
        return extract_frames(ctx, self.config.get("stage1"))

    def _run_stage2(self, ctx: PipelineContext) -> PipelineContext:
        from .stage2_calibration import calibrate_camera
        return calibrate_camera(ctx)

    def _run_stage3(self, ctx: PipelineContext) -> PipelineContext:
        from .stage3_features import detect_and_match
        return detect_and_match(ctx, self.config.get("stage3"))

    def _run_stage4(self, ctx: PipelineContext) -> PipelineContext:
        from .stage4_poses import estimate_poses
        return estimate_poses(ctx, self.config.get("stage4"))

    def _run_stage5(self, ctx: PipelineContext) -> PipelineContext:
        from .stage5_reconstruction import densify
        return densify(ctx, self.config.get("stage5"))

    def _run_stage6(self, ctx: PipelineContext) -> PipelineContext:
        from .stage6_meshing import create_mesh
        return create_mesh(ctx, self.config.get("stage6"))

    def _run_stage7(self, ctx: PipelineContext) -> PipelineContext:
        from .stage7_georef import georeference
        return georeference(ctx, self.config.get("stage7"))

    def _run_stage8(self, ctx: PipelineContext) -> PipelineContext:
        from .stage8_filtering import filter_dynamic_objects
        return filter_dynamic_objects(ctx, self.config.get("stage8"))

    def _run_stage9(self, ctx: PipelineContext) -> PipelineContext:
        from .stage9_ai_agent import analyze_scene
        return analyze_scene(ctx, self.config.get("stage9"))


def run_pipeline(video_path: str, metadata_path: str | None, output_dir: str,
                 config: dict | None = None, stages: list[int] | None = None) -> PipelineContext:
    """Convenience function to run the full pipeline."""
    runner = PipelineRunner(video_path, metadata_path, output_dir, config)
    return runner.run(stages)
