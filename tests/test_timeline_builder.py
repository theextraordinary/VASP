from vasp.core import TimelineBuilder, TrackType
from vasp.core.elements import Caption, Timing
from vasp.core.validation import validate_timeline


def test_builder_basic() -> None:
    builder = TimelineBuilder()
    track_id = builder.add_track(TrackType.CAPTION, name="captions")
    caption_id = builder.add_element(
        Caption(id="cap_1", timing=Timing(start=0.0, duration=1.0), text="Hi")
    )
    builder.place(caption_id, track_id, start=0.0, duration=1.0, layer=0)
    timeline, _ = builder.build()
    validate_timeline(timeline)
    assert timeline.duration == 1.0
