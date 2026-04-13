from vasp.core.elements import Caption, ElementType, Timing


def test_element_defaults() -> None:
    caption = Caption(
        id="cap_1",
        timing=Timing(start=0.0, duration=2.0),
        text="Hello",
    )
    assert caption.type == ElementType.CAPTION
    assert caption.transform.x == 0.0
    assert caption.layer == 0
    assert caption.visible is True
