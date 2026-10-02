"""Unit tests for the filament fields a pipeline run puts on each copy's queue item.

Without filament overrides the scheduler maps a sliced plate's filaments to AMS slots by
type alone, so an all-PLA plate prints in whatever colours sit in the matching slots.
``force_color_match`` runs carry every filament as a forced override instead.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from backend.app.api.routes.pipeline_runs import _queue_filament_fields


def _sliced_3mf(path: Path, filaments: list[dict]) -> Path:
    body = "".join(
        f'<filament id="{f["id"]}" type="{f["type"]}" color="{f["color"]}" used_g="{f.get("used_g", "5")}" '
        f'tray_info_idx="{f.get("tray_info_idx", "")}"/>'
        for f in filaments
    )
    config = f'<?xml version="1.0" encoding="utf-8"?><config><plate><metadata key="index" value="1"/>{body}</plate></config>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Metadata/slice_info.config", config)
    return path


NAME_TAG = [
    {"id": "1", "type": "PLA", "color": "#00AE42", "tray_info_idx": "GFA00"},
    {"id": "2", "type": "PLA", "color": "#FFFFFF", "tray_info_idx": "GFA00"},
    {"id": "3", "type": "PLA", "color": "#FEC600", "tray_info_idx": "GFA00"},
]


class TestQueueFilamentFields:
    def test_forced_run_carries_every_filament_as_a_forced_override(self, tmp_path: Path):
        types_json, overrides_json = _queue_filament_fields(_sliced_3mf(tmp_path / "plate.3mf", NAME_TAG), True)

        assert json.loads(types_json) == ["PLA"]
        overrides = json.loads(overrides_json)
        assert [o["slot_id"] for o in overrides] == [1, 2, 3]
        assert [o["color"].upper()[:7] for o in overrides] == ["#00AE42", "#FFFFFF", "#FEC600"]
        assert all(o["force_color_match"] is True for o in overrides)
        assert all(o["type"] == "PLA" and o["tray_info_idx"] == "GFA00" for o in overrides)

    def test_unforced_run_records_types_but_no_overrides(self, tmp_path: Path):
        types_json, overrides_json = _queue_filament_fields(_sliced_3mf(tmp_path / "plate.3mf", NAME_TAG), False)

        assert json.loads(types_json) == ["PLA"]
        assert overrides_json is None

    def test_missing_or_unreadable_file_adds_nothing(self, tmp_path: Path):
        assert _queue_filament_fields(None, True) == (None, None)
        assert _queue_filament_fields(tmp_path / "gone.3mf", True) == (None, None)
        bad = tmp_path / "bad.3mf"
        bad.write_bytes(b"not a zip")
        assert _queue_filament_fields(bad, True) == (None, None)

    def test_only_the_printed_plates_filaments_are_forced(self, tmp_path: Path):
        f = tmp_path / "two_plates.3mf"
        plate = '<plate><metadata key="index" value="{n}"/><filament id="{i}" type="PLA" color="{c}" used_g="5" tray_info_idx="GFA00"/></plate>'
        config = '<?xml version="1.0" encoding="utf-8"?><config>' + plate.format(n=1, i=1, c="#C12E1F") + plate.format(n=2, i=2, c="#0086D6") + "</config>"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("Metadata/slice_info.config", config)

        _, overrides_json = _queue_filament_fields(f, True)

        assert [(o["slot_id"], o["color"].upper()[:7]) for o in json.loads(overrides_json)] == [(1, "#C12E1F")]

    def test_filaments_without_a_colour_are_not_forced(self, tmp_path: Path):
        f = _sliced_3mf(tmp_path / "plate.3mf", [{"id": "1", "type": "PLA", "color": ""}])

        types_json, overrides_json = _queue_filament_fields(f, True)

        assert json.loads(types_json) == ["PLA"]
        assert overrides_json is None
