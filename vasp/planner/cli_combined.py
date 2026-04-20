from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
from vasp.planner.combined_prompt_builder import generate_combined_planner_input_prompt


def build_combined_prompt(
    *,
    system_prompt_path: Path,
    input_context_path: Path,
    expected_output_path: Path,
    combined_prompt_path: Path,
) -> Path:
    system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
    input_block = input_context_path.read_text(encoding="utf-8").strip()
    expected_block = expected_output_path.read_text(encoding="utf-8").strip()

    combined = (
        "### SYSTEM PROMPT (pass as system role)\n"
        + system_prompt
        + "\n\n### INPUT CONTEXT\n"
        + input_block
        + "\n\n### EXPECTED OUTPUT FORMAT\n"
        + expected_block
    )
    combined_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    combined_prompt_path.write_text(combined, encoding="utf-8")
    return combined_prompt_path


def call_planner_endpoint(
    *,
    endpoint: str,
    prompt_path: Path,
    output_text_path: Path,
    output_meta_path: Path,
    temperature: float = 0.1,
    max_tokens: int = 2200,
    timeout_s: float = 420.0,
) -> tuple[Path, Path]:
    prompt = prompt_path.read_text(encoding="utf-8")
    resp = httpx.post(
        endpoint,
        json={"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    payload = resp.json()
    text = payload.get("response", "") if isinstance(payload, dict) else str(payload)

    output_text_path.parent.mkdir(parents=True, exist_ok=True)
    output_text_path.write_text(text, encoding="utf-8")
    output_meta_path.write_text(
        json.dumps(
            {
                "endpoint": endpoint,
                "prompt_file": str(prompt_path),
                "output_file": str(output_text_path),
                "status_code": resp.status_code,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_text_path, output_meta_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build planner combined prompt and call planner endpoint in one command."
    )
    parser.add_argument("--system-prompt", default="output/planner_system_prompt_v1.txt")
    parser.add_argument("--input-context", default="output/element3.txt")
    parser.add_argument("--expected-output", default="output/planner_expected_output.md")
    parser.add_argument("--media-json", default="output/media.json")
    parser.add_argument("--transcript", default="", help="Transcript text to include in planner prompt.")
    parser.add_argument("--transcript-file", default="", help="Optional path to transcript text file.")
    parser.add_argument("--user-instruction", default="Create a clear, appealing short-form edit.")
    parser.add_argument(
        "--user-specific-instruction",
        default="",
        help="Optional theme/style instruction. If empty, plain default mode is used.",
    )
    parser.add_argument("--combined-prompt", default="output/planner_combined_prompt_v1.txt")
    parser.add_argument("--output", default="output/planner_output_combined_v1.txt")
    parser.add_argument("--meta", default="output/planner_output_combined_v1.meta.json")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("PLANNER_ENDPOINT", ""),
        help="Planner endpoint URL. Can also be set via PLANNER_ENDPOINT env var.",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--timeout-s", type=float, default=420.0)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip rebuilding combined prompt and use --combined-prompt as-is.",
    )
    args = parser.parse_args()

    system_prompt_path = Path(args.system_prompt)
    input_context_path = Path(args.input_context)
    expected_output_path = Path(args.expected_output)
    combined_prompt_path = Path(args.combined_prompt)
    output_text_path = Path(args.output)
    output_meta_path = Path(args.meta)

    if not args.skip_build:
        transcript_text = str(args.transcript or "").strip()
        if args.transcript_file:
            tfile = Path(args.transcript_file)
            if not tfile.exists():
                raise SystemExit(f"Transcript file not found: {tfile}")
            transcript_text = tfile.read_text(encoding="utf-8").strip()
        generate_combined_planner_input_prompt(
            system_prompt_path=system_prompt_path,
            transcript=transcript_text or None,
            user_instruction=str(args.user_instruction).strip(),
            user_specific_instruction=str(args.user_specific_instruction).strip() or None,
            element3_path=input_context_path,
            output_schema_path=expected_output_path,
            output_prompt_path=combined_prompt_path,
            media_json_path=Path(args.media_json),
        )

    if not args.endpoint.strip():
        raise SystemExit(
            "Missing endpoint. Pass --endpoint <url> or set PLANNER_ENDPOINT env var."
        )

    out_txt, out_meta = call_planner_endpoint(
        endpoint=args.endpoint.strip(),
        prompt_path=combined_prompt_path,
        output_text_path=output_text_path,
        output_meta_path=output_meta_path,
        temperature=float(args.temperature),
        max_tokens=int(args.max_tokens),
        timeout_s=float(args.timeout_s),
    )
    print(out_txt)
    print(out_meta)


if __name__ == "__main__":
    main()
