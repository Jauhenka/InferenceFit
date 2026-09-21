"""Install a built artifact into a clean virtual environment and smoke-test it."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path


def venv_python_path(environment: Path, os_name: str = os.name) -> Path:
    return environment / ("Scripts/python.exe" if os_name == "nt" else "bin/python")


def venv_bin_path(environment: Path, os_name: str = os.name) -> Path:
    return environment / ("Scripts" if os_name == "nt" else "bin")


def run_checked(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, cwd=cwd, env=env, check=True, text=True, capture_output=True
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"command failed with exit code {error.returncode}: {shlex.join(command)}; "
            f"stdout={error.stdout!r}; stderr={error.stderr!r}"
        ) from error


def main(artifact: Path, expected_version: str, source_root: Path) -> int:
    artifact = artifact.resolve()
    source_root = source_root.resolve()
    smoke_script = Path(__file__).with_name("installed_distribution_smoke.py")
    with tempfile.TemporaryDirectory(prefix="inferencefit-artifact-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        interpreter = venv_python_path(environment)
        run_checked([str(interpreter), "-m", "pip", "install", str(artifact)], directory)
        copied_smoke = directory / "installed_distribution_smoke.py"
        shutil.copy2(smoke_script, copied_smoke)
        environment_variables = os.environ.copy()
        environment_variables.pop("PYTHONPATH", None)
        environment_variables["PATH"] = os.pathsep.join(
            filter(None, (str(venv_bin_path(environment)), environment_variables.get("PATH")))
        )
        run_checked(
            [str(interpreter), str(copied_smoke), expected_version, str(source_root)],
            directory,
            environment_variables,
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("expected_version")
    parser.add_argument("source_root", type=Path)
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.artifact, arguments.expected_version, arguments.source_root))
