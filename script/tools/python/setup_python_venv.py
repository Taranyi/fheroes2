#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path


def get_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv(root: Path) -> Path:
    venv_dir = root / "venv"
    py_path = get_python_path(venv_dir)
    if not py_path.exists():
        print(f"Creating virtual environment in {venv_dir}")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        subprocess.check_call(
            [
                str(get_python_path(venv_dir)),
                "-m",
                "pip",
                "install",
                "-r",
                str(root / "requirements.txt"),
            ]
        )
    return py_path


def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    py_path = ensure_venv(root)
    if "--print-python" in sys.argv:
        print(py_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)
