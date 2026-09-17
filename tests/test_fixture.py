from pathlib import Path

import pytest

from step_explorer.step.parser import StepDocument


def test_slot1_fixture_smoke():
    candidates = (
        Path("slot1.STEP"),
        Path("tests/fixtures/slot1.STEP"),
        Path("fixtures/slot1.STEP"),
        Path("examples/stepAP203/slot1.STEP"),
    )
    fixture = next((path for path in candidates if path.exists()), None)
    if fixture is None:
        pytest.skip("slot1.STEP is an external development fixture")
    document = StepDocument.from_file(fixture)
    assert document.entities
    assert len(document.entities) == len(document.by_id)
    assert all(entity.raw.endswith(";") for entity in document.entities)
