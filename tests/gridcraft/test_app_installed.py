"""Real installed app/core contracts and candidate bytes; no browser/export claim."""

import json
import os
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import openpyxl
import pytest
from craftreport_gridcraft.app_values import BrowserTarget
from craftreport_gridcraft.codecs import target_codec

from craftreport.adapters.binding_codecs import BindingResultCodec
from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.report_codecs import prepared_codec, quality_codec
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins
from tests.kernel.fixture_packaging import (
    ROOT,
    InstalledFixture,
    install_locked_dependencies,
)
from tests.kernel.fixture_packaging import (
    run as packaging_run,
)

APP = ROOT / "packages/craftreport-gridcraft"
PACKAGE = APP / "src/craftreport_gridcraft"
FILES = {
    "__init__.py",
    "app_values.py",
    "codecs.py",
    "values.py",
    "workbook.py",
    "py.typed",
    "resources/support.json",
}


def test_task4_package_source_manifest() -> None:
    """Future control-panel resources and runtime implementations are separate tasks."""
    actual = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert actual == FILES


def install_app(directory: Path) -> InstalledFixture:
    """Compose the repository's offline packaging helpers for the two real wheels."""
    uv = shutil.which("uv")
    assert uv is not None
    wheels = directory / "wheels"
    wheels.mkdir()
    for source in (ROOT, APP):
        packaging_run(
            [
                uv,
                "build",
                "--wheel",
                "--offline",
                "--no-build-isolation",
                "--python",
                sys.executable,
                "--out-dir",
                str(wheels),
                str(source),
            ],
            directory,
        )
    environment = directory / "env"
    packaging_run([uv, "venv", "--python", sys.executable, str(environment)], directory)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    constraints = install_locked_dependencies(uv, python, directory)
    built = tuple(sorted(wheels.glob("*.whl")))
    assert len(built) == 2
    packaging_run(
        [
            uv,
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "--constraint",
            str(constraints),
            *(str(wheel) for wheel in built),
        ],
        directory,
    )
    packaging_run([uv, "pip", "check", "--python", str(python)], directory)
    return InstalledFixture(python, directory, built)


def assert_wheel_manifest(installed: InstalledFixture) -> None:
    wheel = next(
        path for path in installed.wheels if path.name.startswith("craftreport_gridcraft-")
    )
    with ZipFile(wheel) as archive:
        package_files = {
            name.removeprefix("craftreport_gridcraft/")
            for name in archive.namelist()
            if name.startswith("craftreport_gridcraft/")
        }
        assert package_files == FILES
        for name in FILES:
            assert archive.read(f"craftreport_gridcraft/{name}") == (PACKAGE / name).read_bytes()


PROBE = """
import json
from hashlib import sha256
from pathlib import Path
from importlib.metadata import distribution
from importlib.resources import files
import craftreport
import craftreport_gridcraft as app
from craftreport.adapters.binding_codecs import BindingResultCodec
from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.report_codecs import prepared_codec, quality_codec
from craftreport.runtime.values import RunPins
from craftreport_gridcraft.codecs import layout_codec, support_descriptor, target_codec
from craftreport_gridcraft.workbook import bootstrap, validate_mapping

assert {'PROFILE', 'AppIssue', 'MappingPlan', 'OwnedLayout', 'AppSettings',
        'BrowserTarget', 'TargetObservation', 'SavedCandidate', 'ArtifactRef',
        'support_descriptor'} <= set(app.__all__)
for public_name in app.__all__:
    assert getattr(app, public_name) is not None
payload = json.loads(Path('input.json').read_text(encoding='utf-8'))
prepared = prepared_codec().decode(payload['prepared'])
quality = quality_codec().decode(payload['quality'])
pins = BindingResultCodec().decode(payload['run'])
assert isinstance(pins, RunPins)
target = target_codec().decode(payload['target'])
layout = app.OwnedLayout(target, pins)
assert layout_codec().decode(layout_codec().encode(layout)) == layout
plan = validate_mapping(prepared, quality, layout)
assert isinstance(plan, app.MappingPlan), plan
assert plan.layout.run == pins
data = bootstrap(plan, target.document_marker)
assert isinstance(data, bytes), data
Path('candidate.xlsx').write_bytes(data)
descriptor = support_descriptor()
resource = files(app).joinpath('resources/support.json').read_text(encoding='utf-8')
disclosed = json.loads(canonical_bytes(descriptor))
resource_fields = json.loads(resource)
assert {key: disclosed[key] for key in resource_fields} == resource_fields
assert descriptor['operation_status'] == 'untested'
assert descriptor['mapping_status'] == 'supported'
assert descriptor['headed_status'] == 'MANUAL_VERIFY_REQUIRED'
assert descriptor['profile_pin']['identity'] == 'gridcraft/browser-fixed'
assert descriptor['profile_pin']['version'] == '1.0.0'
assert descriptor['profile_pin']['content_digest'] == app.PROFILE.pin.content_digest
declaration = json.dumps(disclosed['declaration'], sort_keys=True, separators=(',', ':')).encode()
assert sha256(declaration).hexdigest() == app.PROFILE.pin.content_digest
assert disclosed['declaration']['category_serialized_utf8_bytes'] == 16
assert disclosed['declaration']['literal_serialized_utf8_bytes'] == 32
assert disclosed['declaration']['shape'] == [4, 3, 4, 1]
assert len(descriptor['properties']) == 24
assert {item['name']: item['status'] for item in descriptor['properties']} == {
    'text.font_family': 'supported',
    'text.size_pt': 'supported',
    'text.bold': 'supported',
    'text.italic': 'supported',
    'text.color': 'supported',
    'text.fill': 'supported',
    'text.alignment': 'supported',
    'text.wrap': 'supported',
    'format.kind': 'supported',
    'format.decimal_places': 'supported',
    'format.negative_style': 'untested',
    'format.date_pattern': 'untested',
    'grid.show_gridlines': 'supported',
    'grid.header_height': 'supported',
    'grid.column_width': 'supported',
    'chart.series_colors': 'supported',
    'chart.line_width': 'supported',
    'chart.legend': 'supported',
    'chart.grid': 'supported',
    'chart.null_gaps': 'supported',
    'table.typed_null': 'untested',
    'table.null_marker': 'untested',
    'table.empty_headers': 'untested',
    'table.empty_note': 'untested',
}
dist = distribution('craftreport-gridcraft')
assert dist.version == '0.1.0'
assert dist.metadata['Name'] == 'craftreport-gridcraft'
assert 'craftreport==0.1.0' in dist.requires
assert 'xlsxwriter==3.2.9' in dist.requires
assert not dist.entry_points
environment = Path.cwd() / 'env'
for module in (craftreport, app):
    assert Path(module.__file__).is_relative_to(environment), module.__file__
assert files(app).joinpath('py.typed').is_file()
print(json.dumps({'core': craftreport.__file__, 'app': app.__file__,
                 'version': dist.version, 'profile': app.PROFILE.pin.content_digest,
                 'resource': json.loads(resource), 'public': app.__all__}))
"""


@pytest.mark.integration
def test_installed_app_contracts_and_candidate_bootstrap(
    prepared: PreparedReport,
    quality: QualityEvaluation,
    run: RunPins,
    browser_target: BrowserTarget,
) -> None:
    directory = ROOT / "artifacts/gridcraft/task-4/installed" / uuid4().hex
    directory.mkdir(parents=True)
    payload = {
        "prepared": prepared_codec().encode(prepared),
        "quality": quality_codec().encode(quality),
        "run": BindingResultCodec().encode(run),
        "target": target_codec().encode(browser_target),
    }
    (directory / "input.json").write_bytes(canonical_bytes(payload))
    installed = install_app(directory)
    assert_wheel_manifest(installed)
    result = json.loads(installed.probe(PROBE))
    book = openpyxl.load_workbook(directory / "candidate.xlsx")
    sheet = book["Report"]
    assert sheet["B7"].value == 15 and sheet["G7"].value is None
    assert sheet["C6"].value == "=1+1" and sheet["C6"].data_type == "s"
    assert sheet["C7"].value == "https://example.invalid/" and sheet["C7"].hyperlink is None
    assert sheet["M1"].value == "OUTSIDE-UNCHANGED"
    assert sheet["A1"].value == quality.draft_designation
    assert sheet["A3"].value == quality.validation_summary
    assert sheet["K1"].value == browser_target.document_marker
    assert sheet["K2"].value == run.run_id
    assert sheet["K3"].value == f"{run.snapshot.feed_id}@{run.snapshot.producer_version}"
    assert sheet["L3"].value == run.snapshot.content_digest
    assert sheet["K4"].value == run.prepared_digest
    book.close()
    (directory / "inventory.json").write_text(
        json.dumps(
            {
                "scope": "installed contracts and candidate bootstrap; no browser/export claim",
                "requirements": ["1.2", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "6.1"],
                "environment": result,
                "lock_sha256": sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
                "test_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "package_sources": {
                    name: sha256((PACKAGE / name).read_bytes()).hexdigest()
                    for name in sorted(FILES)
                },
                "wheels": {p.name: sha256(p.read_bytes()).hexdigest() for p in installed.wheels},
                "candidate_sha256": sha256((directory / "candidate.xlsx").read_bytes()).hexdigest(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
