"""Owned offline wheel builds; no fixture install into the developer environment."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/fixtures/kernel_plugin"
ENVIRONMENT_PROBE = """
import json, platform
from hashlib import sha256
from pathlib import Path
import craftreport
from importlib.metadata import distributions
from craftreport_kernel_fixture import factory
from craftreport.contracts.capabilities import CORE_CONTRACT_VERSION
manifest = factory().describe()
kernel_root = Path(craftreport.__file__).parent
kernel_digest = sha256()
for source in sorted(kernel_root.rglob("*.py")):
    kernel_digest.update(source.relative_to(kernel_root).as_posix().encode())
    kernel_digest.update(source.read_bytes())
print(json.dumps({"python": platform.python_version(), "packages":
    {d.metadata["Name"]: d.version for d in distributions()},
    "core_contract_version": CORE_CONTRACT_VERSION,
    "kernel_implementation_digest": kernel_digest.hexdigest(),
    "capability": {"identity": manifest.identity, "package": manifest.package,
        "version": manifest.version, "implementation_digest": manifest.implementation_digest,
        "operations": [{"name": op.key.name, "version": op.key.contract_version,
                        "kind": op.kind.value} for op in manifest.operations]}}))
"""


def activation_variant(content: str, variant: str) -> str:
    dependencies = {
        "dependent": ("synthetic", ">=1,<2"),
        "wrongrange": ("synthetic", ">=2"),
        "cyclea": ("cycleb", ">=1"),
        "cycleb": ("cyclea", ">=1"),
    }
    if variant in dependencies:
        identity, version = dependencies[variant]
        content = content.replace(
            "            (),\n            SETTINGS.schema(),",
            f"            (CapabilityRequirement({identity!r}, {version!r}),),\n"
            "            SETTINGS.schema(),",
        ).replace(
            "CapabilityManifest, CapabilityVersion",
            "CapabilityManifest, CapabilityVersion, CapabilityRequirement",
        )
    replacements = {
        "provideddup": (
            'CapabilityVersion(IDENTITY, "1.0.0")',
            'CapabilityVersion("synthetic", "1.0.0")',
        ),
        "tooldup": ('NAMESPACE = "tooldup"', 'NAMESPACE = "synthetic"'),
        "reserved": ('NAMESPACE = "reserved"', 'NAMESPACE = "craftreport.private"'),
        "badversion": ("distribution(PACKAGE).version", '"9.0.0"'),
        "badpackage": ("            PACKAGE,", '            "wrong-package",'),
        "mismatch": (
            "Operations(NAMESPACE, settings.resource_kind)",
            'Operations("different", settings.resource_kind)',
        ),
    }
    if variant in replacements:
        content = content.replace(*replacements[variant])
    return content


def variant_source(directory: Path, variant: str) -> Path:
    """Build negative cases from owned copies; never mutate the canonical fixture."""
    source = directory / variant
    shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    old_module = "craftreport_kernel_fixture"
    module = f"{old_module}_{variant}"
    package = f"craftreport-kernel-fixture-{variant}"
    original = source / "src" / old_module
    original.rename(source / "src" / module)
    metadata = source / "pyproject.toml"
    metadata.write_text(
        metadata.read_text()
        .replace("craftreport-kernel-fixture", package)
        .replace(old_module, module)
        .replace("synthetic =", f"{variant} =")
    )
    init = source / "src" / module / "__init__.py"
    content = init.read_text().replace(
        'PACKAGE = "craftreport-kernel-fixture"', f'PACKAGE = "{package}"'
    )
    if variant != "collision":
        content = content.replace('IDENTITY = "synthetic"', f'IDENTITY = "{variant}"')
        content = content.replace('NAMESPACE = "synthetic"', f'NAMESPACE = "{variant}"')
    if variant == "incompatible":
        content = content.replace('CORE_RANGE = ">=1.0,<2.0"', 'CORE_RANGE = ">=9.0,<10.0"')
    if variant == "unselected":
        content += '\nraise RuntimeError("Unselected fixture was imported")\n'
    init.write_text(activation_variant(content, variant))
    if variant in ("tool128", "tool129"):
        operations = source / "src" / module / "operations.py"
        version = "1" * (int(variant[4:]) - len(variant + ".write.v"))
        operations.write_text(
            operations.read_text().replace(
                'OperationKey(f"{namespace}.write", "1")',
                f'OperationKey(f"{{namespace}}.write", "{version}")',
            )
        )
    return source


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@dataclass(frozen=True)
class InstalledFixture:
    python: Path
    directory: Path
    wheels: tuple[Path, ...]

    def probe(self, script: str) -> str:
        return run([str(self.python), "-I", "-c", script], self.directory)

    def record_identity(self) -> None:
        environment = self.probe(ENVIRONMENT_PROBE)
        identity = {
            "scope": "synthetic packaging and author contract; no activation or durability claim",
            "requirements": ["1.1", "1.2", "1.4", "2.5", "7.1", "7.4"],
            "fixture_suite": "kernel-fixture-packaging-v1",
            "lock_sha256": sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "wheels": {wheel.name: sha256(wheel.read_bytes()).hexdigest() for wheel in self.wheels},
            "environment": json.loads(environment),
        }
        (self.directory / "inventory.json").write_text(json.dumps(identity, indent=2))


def build_fixture(directory: Path, extra_variants: tuple[str, ...] = ()) -> InstalledFixture:
    uv = shutil.which("uv")
    assert uv is not None
    wheels = directory / "wheels"
    wheels.mkdir()
    variants = tuple(
        variant_source(directory, v)
        for v in ("unselected", "incompatible", "collision", *extra_variants)
    )
    for source in (ROOT, SOURCE, *variants):
        run(
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
    env = directory / "env"
    run([uv, "venv", "--python", sys.executable, str(env)], directory)
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    built = tuple(sorted(wheels.glob("*.whl")))
    constraints = directory / "locked-requirements.txt"
    run(
        [
            uv,
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--project",
            str(ROOT),
            "--output-file",
            str(constraints),
        ],
        directory,
    )
    run(
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
    installed = InstalledFixture(python, directory, built)
    installed.record_identity()
    return installed
