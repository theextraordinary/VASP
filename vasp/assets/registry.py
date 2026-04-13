from __future__ import annotations

from typing import Dict, Iterable, Optional

from vasp.assets.media import MediaAsset


class AssetRegistry:
    """Simple registry for known assets."""

    def __init__(self) -> None:
        self._items: Dict[str, MediaAsset] = {}

    def add(self, asset: MediaAsset) -> None:
        self._items[asset.id] = asset

    def get(self, asset_id: str) -> Optional[MediaAsset]:
        return self._items.get(asset_id)

    def list(self) -> Iterable[MediaAsset]:
        return self._items.values()
