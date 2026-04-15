from vasp.core.serialization import serialize_element_json
from vasp.media_reader.pipeline import detect_media_type, generate_input_json
from vasp.media_reader.probe import probe_media


def test_detect_media_type() -> None:
    assert detect_media_type("clip.mp4") == "video"
    assert detect_media_type("clip.gif") == "gif"
    assert detect_media_type("clip.jpg") == "image"
    assert detect_media_type("clip.mp3") == "audio"


def test_probe_media_shape() -> None:
    info = probe_media("nonexistent_file.mp4")
    assert info.duration is None
    assert info.width is None
    assert info.height is None


def test_generate_input_json() -> None:
    payload = generate_input_json(
        instruction="make this dramatic",
        media_paths=["input/clip.mp4", "input/audio.mp3"],
        output_path="output/test.mp4",
    )
    assert "elements" in payload
    assert "media_context" in payload
    assert payload["video"]["output_path"] == "output/test.mp4"


def test_integration_into_serializer() -> None:
    payload = generate_input_json(
        instruction="simple edit",
        media_paths=["input/clip.mp4"],
        output_path="output/test.mp4",
    )
    actions_json, props_json = serialize_element_json(payload)
    assert actions_json["elements"]
    assert props_json["elements"]


def test_prep_stage_shapes() -> None:
    payload = generate_input_json(
        instruction="prep test",
        media_paths=["input/clip.mp4"],
        output_path="output/test.mp4",
    )
    elements_json, props_json = serialize_element_json(payload)
    assert "elements" in elements_json
    assert "elements" in props_json


def test_generate_input_json_attaches_transcript_for_audio_video(monkeypatch) -> None:
    def _fake_transcribe(path: str, model_size: str = "small"):  # type: ignore[no-untyped-def]
        _ = path, model_size
        return {
            "full_text": "hello world",
            "words": [
                {"text": "hello", "start": 0.0, "end": 0.4},
                {"text": "world", "start": 0.45, "end": 0.8},
            ],
            "segments": [{"id": 0, "start": 0.0, "end": 0.4, "text": "hello"}],
            "language": "en",
            "word_stats": {"word_count": 2, "important_count": 0, "warnings": []},
        }

    monkeypatch.setattr("vasp.media_reader.pipeline.transcribe_media_with_features", _fake_transcribe)
    payload = generate_input_json(
        instruction="caption this",
        media_paths=["input/clip.mp4", "input/audio.mp3"],
        output_path="output/test.mp4",
        options={"asr_enabled": True, "asr_model_size": "small"},
    )
    analysis = payload["media_context"]["analysis"]
    assert isinstance(analysis["media_1"]["transcript"], dict)
    assert isinstance(analysis["media_2"]["transcript"], dict)
    assert analysis["media_1"]["transcript"]["full_text"] == "hello world"

    actions_json, props_json = serialize_element_json(payload)
    caption_ids = {entry["element_id"] for entry in actions_json["elements"] if str(entry["element_id"]).startswith("asr_caption_")}
    assert caption_ids
    caption_props = [e for e in props_json["elements"] if str(e["element_id"]).startswith("asr_caption_")]
    assert caption_props


def test_generate_input_json_does_not_attach_transcript_for_images(monkeypatch) -> None:
    def _fake_transcribe(path: str, model_size: str = "small"):  # type: ignore[no-untyped-def]
        _ = path, model_size
        return {"full_text": "should_not_be_used", "words": [], "segments": [], "language": "en", "word_stats": {}}

    monkeypatch.setattr("vasp.media_reader.pipeline.transcribe_media_with_features", _fake_transcribe)
    payload = generate_input_json(
        instruction="image only",
        media_paths=["input/image.jpg"],
        output_path="output/test.mp4",
    )
    analysis = payload["media_context"]["analysis"]
    assert analysis["media_1"]["transcript"] is None
