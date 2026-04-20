from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Any

from vasp.a2v.v2.optional_media_collector import MODES as OPTIONAL_MEDIA_MODES
from vasp.a2v.v2.optional_media_collector import OPTIONAL_MEDIA_MAX_COUNT, OPTIONAL_MEDIA_MIN_COUNT
from vasp.a2v.v3.new_flow_pipeline_v3 import run_new_flow_pipeline_v3
from vasp.a2v.v3.utils import safe_name


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
GIF_EXTS = {".gif"}


def _import_gradio() -> Any:
    try:
        import gradio as gr  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised only when optional dep missing.
        raise RuntimeError(
            "Gradio is required for the VASP UI. Install it with `pip install gradio` "
            "or use the CLI: `python -m vasp.a2v.v3.new_flow_pipeline_v3 ...`."
        ) from exc
    return gr


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique filename for {path}")


def _copy_uploads(uploaded_files: list[Any] | None, edit_name: str) -> list[Path]:
    input_dir = Path("assets") / "inputs" / safe_name(edit_name)
    input_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for item in uploaded_files or []:
        src_text = getattr(item, "name", None) or str(item or "")
        if not src_text:
            continue
        src = Path(src_text)
        if not src.exists() or not src.is_file():
            continue
        dst = _unique_path(input_dir / src.name)
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def _default_aim_for(path: Path, index: int) -> str:
    suffix = path.suffix.lower()
    if suffix in AUDIO_EXTS:
        return "extract speech captions"
    if suffix in VIDEO_EXTS and index == 0:
        return "extract speech captions"
    return "use with appropriate captions"


def _default_about_for(path: Path) -> str:
    name = path.stem.replace("_", " ").replace("-", " ").strip()
    return name or "uploaded media"


def _looks_like_captions_file(text: str) -> bool:
    first = (text or "").strip().splitlines()[0].lower() if (text or "").strip() else ""
    return "file" in first and "about" in first


def _write_captions_file(edit_name: str, copied_files: list[Path], captions_text: str) -> Path:
    input_dir = Path("assets") / "inputs" / safe_name(edit_name)
    input_dir.mkdir(parents=True, exist_ok=True)
    captions_path = input_dir / "captions.txt"
    text = (captions_text or "").strip()

    if text and _looks_like_captions_file(text):
        captions_path.write_text(text + "\n", encoding="utf-8")
        return captions_path

    if text and not copied_files:
        captions_path.write_text(text + "\n", encoding="utf-8")
        return captions_path

    rows: list[dict[str, str]] = []
    for idx, path in enumerate(copied_files):
        rows.append(
            {
                "file": path.name,
                "about": _default_about_for(path),
                "aim": _default_aim_for(path, idx),
            }
        )
    if not rows:
        raise ValueError("Upload at least one media file, or paste a transcript/captions file.")

    with captions_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "about", "aim"])
        writer.writeheader()
        writer.writerows(rows)
    return captions_path


def _run_from_ui(
    edit_name: str,
    instruction: str,
    planner_endpoint: str,
    refiner_endpoint: str,
    base_planner_endpoint: str,
    uploaded_files: list[Any] | None,
    captions_text: str,
    creativity: int,
    media_collection_mode: str,
    optional_media_count: int,
    asset_library_dir: str,
    no_caption: bool,
    aim_refinement: bool,
    dynamic_prompts: bool,
    use_preset_backgrounds: bool,
) -> tuple[str | None, str, str | None]:
    if not edit_name.strip():
        raise ValueError("Edit name is required.")
    if not instruction.strip():
        raise ValueError("Instruction is required.")
    if not planner_endpoint.strip():
        raise ValueError("Planner endpoint is required.")
    if not refiner_endpoint.strip():
        raise ValueError("Refiner endpoint is required.")

    copied = _copy_uploads(uploaded_files, edit_name)
    captions_path = _write_captions_file(edit_name, copied, captions_text)
    result = run_new_flow_pipeline_v3(
        captions_path=captions_path,
        user_instruction=instruction,
        planner_endpoint=planner_endpoint.strip(),
        refiner_endpoint=refiner_endpoint.strip(),
        edit_name=edit_name.strip(),
        creativity=int(creativity),
        media_collection_mode=media_collection_mode,
        asset_library_dir=asset_library_dir.strip() or "assets/library",
        optional_media_count=int(optional_media_count),
        base_planner_endpoint=base_planner_endpoint.strip() or None,
        use_preset_backgrounds=bool(use_preset_backgrounds),
        aim_refinement=bool(aim_refinement),
        dynamic_prompts=bool(dynamic_prompts),
        render_captions=not bool(no_caption),
    )
    video = result.get("video") or None
    run_dir = result.get("run_dir") or ""
    summary = "\n".join(
        [
            "A2V V3 render complete.",
            f"Run dir: {run_dir}",
            f"captions.txt: {captions_path}",
            f"planner_output: {result.get('planner_output', '')}",
            f"inter_json: {result.get('inter_json', '')}",
            f"video: {video or ''}",
        ]
    )
    return video, summary, run_dir


def build_demo() -> Any:
    gr = _import_gradio()
    css = """
    .vasp-hero {
        border-radius: 24px;
        padding: 24px;
        background:
          radial-gradient(circle at 20% 0%, rgba(251, 191, 36, 0.22), transparent 28%),
          linear-gradient(135deg, #071014 0%, #101820 48%, #1f2937 100%);
        color: #f8fafc;
        border: 1px solid rgba(255,255,255,0.12);
    }
    .vasp-hero h1 { font-family: Georgia, serif; letter-spacing: -0.04em; margin-bottom: 6px; }
    """
    with gr.Blocks(title="VASP A2V Studio", css=css) as demo:
        gr.HTML(
            """
            <section class="vasp-hero">
              <h1>VASP A2V Studio</h1>
              <p>Upload media, describe the edit, and render an MVP short-form video through the V3 pipeline.</p>
            </section>
            """
        )
        with gr.Row():
            with gr.Column(scale=1):
                edit_name = gr.Textbox(label="Edit name", value="edit_ui", placeholder="edit8")
                instruction = gr.Textbox(
                    label="User instruction",
                    lines=4,
                    value="Create a clean, creative video.",
                    placeholder="Create a cinematic documentary edit with synced captions.",
                )
                uploaded_files = gr.File(
                    label="Media files",
                    file_count="multiple",
                    type="filepath",
                    file_types=["video", "audio", "image", ".gif", ".webp", ".txt", ".csv"],
                )
                captions_text = gr.Textbox(
                    label="Optional captions.txt / transcript override",
                    lines=8,
                    placeholder=(
                        "Either paste file,about,aim rows here, or leave empty and the UI will "
                        "create captions.txt from uploaded media filenames."
                    ),
                )
            with gr.Column(scale=1):
                planner_endpoint = gr.Textbox(label="Planner endpoint", placeholder="https://.../planner-v3/generate")
                refiner_endpoint = gr.Textbox(label="Refiner endpoint", placeholder="https://.../refiner-v3-preset/generate")
                base_planner_endpoint = gr.Textbox(label="Base planner endpoint (optional)", placeholder="https://.../planner/generate")
                creativity = gr.Slider(0, 5, value=2, step=1, label="Creativity")
                media_collection_mode = gr.Dropdown(
                    choices=sorted(OPTIONAL_MEDIA_MODES),
                    value="none",
                    label="Optional media mode",
                )
                optional_media_count = gr.Slider(
                    OPTIONAL_MEDIA_MIN_COUNT,
                    OPTIONAL_MEDIA_MAX_COUNT,
                    value=10,
                    step=1,
                    label="Optional media count",
                )
                asset_library_dir = gr.Textbox(label="Asset library dir", value="assets/library")
                with gr.Row():
                    no_caption = gr.Checkbox(label="No-caption mode", value=False)
                    aim_refinement = gr.Checkbox(label="Aim refinement", value=False)
                with gr.Row():
                    dynamic_prompts = gr.Checkbox(label="Dynamic prompts", value=False)
                    use_preset_backgrounds = gr.Checkbox(label="Preset backgrounds", value=True)

        run_btn = gr.Button("Generate video", variant="primary")
        with gr.Row():
            output_video = gr.Video(label="Final video", format="mp4")
            output_summary = gr.Textbox(label="Run summary", lines=8)
        run_dir = gr.Textbox(label="Run directory", visible=False)

        run_btn.click(
            fn=_run_from_ui,
            inputs=[
                edit_name,
                instruction,
                planner_endpoint,
                refiner_endpoint,
                base_planner_endpoint,
                uploaded_files,
                captions_text,
                creativity,
                media_collection_mode,
                optional_media_count,
                asset_library_dir,
                no_caption,
                aim_refinement,
                dynamic_prompts,
                use_preset_backgrounds,
            ],
            outputs=[output_video, output_summary, run_dir],
            show_progress="full",
        )
    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch VASP A2V V3 Gradio UI.")
    parser.add_argument("--server-name", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()
    demo = build_demo()
    demo.queue().launch(server_name=args.server_name, server_port=args.server_port, share=args.share)


if __name__ == "__main__":
    main()
