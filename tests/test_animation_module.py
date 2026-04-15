from vasp.animation import BasicAnimationEngine, list_animation_presets
from vasp.animation.primitives import AnimationSpec, AnimationType
from vasp.core.elements import Image, Timing


def test_animation_presets_exposed() -> None:
    presets = list_animation_presets()
    assert "subtle_zoom" in presets
    assert "pop" in presets
    assert "slide_up" in presets


def test_engine_transform_at_zoom_changes_scale() -> None:
    engine = BasicAnimationEngine()
    element = Image(id="img1", timing=Timing(start=0.0, duration=5.0), source_uri="x.png")
    spec = AnimationSpec(
        id="subtle_zoom",
        target_element_id="img1",
        type=AnimationType.ZOOM_IN,
        start=0.0,
        duration=4.0,
        params={"from_scale": 1.0, "to_scale": 1.1},
    )
    tf = engine.transform_at(element, [spec], t=2.0)
    assert tf.scale_x > 1.0
    assert tf.scale_y > 1.0


def test_engine_transform_at_slide_changes_position() -> None:
    engine = BasicAnimationEngine()
    element = Image(id="img2", timing=Timing(start=0.0, duration=5.0), source_uri="x.png")
    spec = AnimationSpec(
        id="slide_up",
        target_element_id="img2",
        type=AnimationType.SLIDE_UP,
        start=0.0,
        duration=2.0,
        params={"distance_px": 100.0},
    )
    tf = engine.transform_at(element, [spec], t=1.0)
    assert tf.y > 0.0
