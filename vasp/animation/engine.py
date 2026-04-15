from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Iterable, List

from vasp.animation.catalog import get_animation_preset
from vasp.animation.primitives import AnimationSpec
from vasp.core.elements import Element, Transform
from vasp.core.timeline import Timeline


class AnimationEngine(ABC):
    """Applies animation specs to a timeline (pure transformations)."""

    @abstractmethod
    def apply(self, timeline: Timeline, animations: Iterable[AnimationSpec]) -> Timeline:
        raise NotImplementedError


class BasicAnimationEngine(AnimationEngine):
    """Minimal engine with transform evaluation helpers."""

    def apply(self, timeline: Timeline, animations: Iterable[AnimationSpec]) -> Timeline:
        _ = list(animations)
        return timeline

    def transform_at(self, element: Element, animations: Iterable[AnimationSpec], t: float) -> Transform:
        """Evaluate element transform at time `t` from animation specs."""
        tf = Transform(**element.transform.model_dump())
        for spec in animations:
            if spec.target_element_id != element.id:
                continue
            if t < spec.start or t > spec.start + spec.duration:
                continue
            local = 0.0 if spec.duration <= 0 else (t - spec.start) / spec.duration
            tf = _apply_spec_transform(tf, spec, local)
        return tf


def _apply_spec_transform(tf: Transform, spec: AnimationSpec, p: float) -> Transform:
    params = spec.params or {}
    preset = get_animation_preset(spec.id)
    preset_params = preset.default_params if preset is not None else {}
    merged = {**preset_params, **params}

    if spec.type.value in {"zoom", "zoom_in"}:
        from_scale = float(merged.get("from_scale", 1.0))
        to_scale = float(merged.get("to_scale", 1.08))
        s = _lerp(from_scale, to_scale, p)
        tf.scale_x *= s
        tf.scale_y *= s
    elif spec.type.value == "zoom_out":
        from_scale = float(merged.get("from_scale", 1.08))
        to_scale = float(merged.get("to_scale", 1.0))
        s = _lerp(from_scale, to_scale, p)
        tf.scale_x *= s
        tf.scale_y *= s
    elif spec.type.value in {"pulse", "breathe"}:
        min_s = float(merged.get("min_scale", 0.98))
        max_s = float(merged.get("max_scale", 1.06))
        s = _sin_range(p, min_s, max_s)
        tf.scale_x *= s
        tf.scale_y *= s
    elif spec.type.value == "pop":
        peak = float(merged.get("peak_scale", 1.15))
        if p < 0.2:
            s = _lerp(1.0, peak, p / 0.2)
        else:
            s = _lerp(peak, 1.0, min(1.0, (p - 0.2) / 0.8))
        tf.scale_x *= s
        tf.scale_y *= s
    elif spec.type.value == "bounce":
        amp = float(merged.get("amplitude_px", 36))
        tf.y -= abs(math.sin(p * math.pi * 2.0)) * amp
    elif spec.type.value == "shake":
        amp = float(merged.get("amplitude_px", 14))
        tf.x += math.sin(p * math.pi * 12.0) * amp
    elif spec.type.value == "wiggle":
        ang = float(merged.get("angle_deg", 6))
        tf.rotation_deg += math.sin(p * math.pi * 8.0) * ang
    elif spec.type.value == "spin":
        turns = float(merged.get("turns", 1))
        tf.rotation_deg += 360.0 * turns * p
    elif spec.type.value == "slide_up":
        d = float(merged.get("distance_px", 140))
        tf.y += _lerp(d, 0.0, p)
    elif spec.type.value == "slide_down":
        d = float(merged.get("distance_px", 140))
        tf.y += _lerp(-d, 0.0, p)
    elif spec.type.value == "slide_left":
        d = float(merged.get("distance_px", 180))
        tf.x += _lerp(d, 0.0, p)
    elif spec.type.value == "slide_right":
        d = float(merged.get("distance_px", 180))
        tf.x += _lerp(-d, 0.0, p)
    elif spec.type.value == "fade_in":
        from_op = float(merged.get("from_opacity", 0.0))
        to_op = float(merged.get("to_opacity", 1.0))
        tf.opacity = _clamp(_lerp(from_op, to_op, p), 0.0, 1.0)
    elif spec.type.value in {"fade_out", "fade"}:
        from_op = float(merged.get("from_opacity", 1.0))
        to_op = float(merged.get("to_opacity", 0.0))
        tf.opacity = _clamp(_lerp(from_op, to_op, p), 0.0, 1.0)
    elif spec.type.value == "stomp":
        d = float(merged.get("distance_px", 90))
        overshoot = float(merged.get("overshoot_scale", 1.08))
        if p < 0.3:
            phase = p / 0.3
            tf.y += _lerp(0.0, d, phase)
            tf.scale_x *= _lerp(1.0, overshoot, phase)
            tf.scale_y *= _lerp(1.0, 0.94, phase)
        else:
            phase = min(1.0, (p - 0.3) / 0.7)
            tf.y += _lerp(d, 0.0, phase)
            tf.scale_x *= _lerp(overshoot, 1.0, phase)
            tf.scale_y *= _lerp(0.94, 1.0, phase)

    # Keyframe overrides (explicit properties win).
    if spec.keyframes:
        ordered = sorted(spec.keyframes, key=lambda k: k.t)
        for idx in range(len(ordered) - 1):
            a = ordered[idx]
            b = ordered[idx + 1]
            if a.t <= p <= b.t:
                k = 0.0 if b.t == a.t else (p - a.t) / (b.t - a.t)
                for key, val in a.properties.items():
                    end_val = b.properties.get(key, val)
                    _set_transform_property(tf, key, _lerp(float(val), float(end_val), k))
                break
    return tf


def _set_transform_property(tf: Transform, key: str, value: float) -> None:
    if key == "x":
        tf.x = value
    elif key == "y":
        tf.y = value
    elif key == "scale_x":
        tf.scale_x = value
    elif key == "scale_y":
        tf.scale_y = value
    elif key == "rotation_deg":
        tf.rotation_deg = value
    elif key == "opacity":
        tf.opacity = _clamp(value, 0.0, 1.0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * _clamp(t, 0.0, 1.0)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sin_range(t: float, lo: float, hi: float) -> float:
    m = (lo + hi) / 2.0
    r = (hi - lo) / 2.0
    return m + math.sin(t * math.pi * 2.0) * r
