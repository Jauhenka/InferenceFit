"""Install a built artifact into a clean virtual environment and smoke-test it."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path


def venv_python_path(environment: Path, os_name: str = os.name) -> Path:
    return environment / ("Scripts/python.exe" if os_name == "nt" else "bin/python")


def main(artifact: Path, expected_version: str, source_root: Path) -> int:
    artifact = artifact.resolve()
    source_root = source_root.resolve()
    smoke_script = Path(__file__).with_name("installed_distribution_smoke.py")
    with tempfile.TemporaryDirectory(prefix="inferencefit-artifact-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        interpreter = venv_python_path(environment)
        subprocess.run(
            [str(interpreter), "-m", "pip", "install", str(artifact)],
            check=True,
            text=True,
            capture_output=True,
        )
        copied_smoke = directory / "installed_distribution_smoke.py"
        shutil.copy2(smoke_script, copied_smoke)
        environment_variables = os.environ.copy()
        environment_variables.pop("PYTHONPATH", None)
        subprocess.run(
            [str(interpreter), str(copied_smoke), expected_version, str(source_root)],
            cwd=directory,
            env=environment_variables,
            check=True,
            text=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("expected_version")
    parser.add_argument("source_root", type=Path)
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.artifact, arguments.expected_version, arguments.source_root))
