"""Sidecar Preparation and Verification Script for Tauri Desktop Shell.

Assists with:
1. Validating local Python environment prerequisites and dependencies.
2. Staging local virtual environment (.venv) into `src-tauri/binaries/python` for development/testing.
3. Providing release instructions for indygreg/python-build-standalone portable bundling.
4. Verifying standalone worker execution.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARIES_DIR = ROOT / "src-tauri" / "binaries" / "python"
VENV_DIR = ROOT / ".venv"


def check_dependencies(python_path: Path) -> bool:
    """Verify that the target Python environment has all required packages."""
    print(f"[*] Checking Python environment at: {python_path}")
    if not python_path.exists():
        print(f"[-] Python executable not found: {python_path}")
        return False

    # Check version
    ver_cmd = [str(python_path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"]
    try:
        ver_str = subprocess.check_output(ver_cmd, text=True).strip()
        print(f"[+] Python version: {ver_str}")
    except Exception as e:
        print(f"[-] Failed to execute Python: {e}")
        return False

    # Check modules
    modules = ["cv2", "reportlab", "cryptography"]
    missing = []
    for mod in modules:
        try:
            subprocess.check_call(
                [str(python_path), "-c", f"import {mod}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  [+] Module '{mod}': Available")
        except Exception:
            print(f"  [-] Module '{mod}': MISSING")
            missing.append(mod)

    # Optional modules
    for opt in ["mediapipe"]:
        try:
            subprocess.check_call(
                [str(python_path), "-c", f"import {opt}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  [+] Optional '{opt}': Available")
        except Exception:
            print(f"  [i] Optional '{opt}': Not installed (heuristic fallback active)")

    if missing:
        print(f"[-] Missing required dependencies: {missing}")
        print("    Install them via: pip install -r requirements.txt")
        return False

    print("[+] All core dependencies are present.")
    return True


def stage_local_venv(force: bool = False) -> bool:
    """Stage the local .venv into src-tauri/binaries/python for desktop testing."""
    if not VENV_DIR.exists():
        print(f"[-] Local virtual environment not found at {VENV_DIR}")
        print("    Create one using: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt")
        return False

    BINARIES_DIR.parent.mkdir(parents=True, exist_ok=True)

    if BINARIES_DIR.exists():
        if not force:
            print(f"[i] Staging target already exists at {BINARIES_DIR}")
            print("    Use --force to overwrite/re-link.")
            return True
        print(f"[*] Removing existing staging directory: {BINARIES_DIR}")
        if os.name == "nt" and BINARIES_DIR.is_symlink():
            os.rmdir(BINARIES_DIR)
        else:
            shutil.rmtree(BINARIES_DIR, ignore_errors=True)

    print(f"[*] Staging {VENV_DIR} -> {BINARIES_DIR}...")
    try:
        # On Windows, try junction first (does not require admin privileges)
        if os.name == "nt":
            try:
                subprocess.check_call(
                    ["cmd", "/c", "mklink", "/J", str(BINARIES_DIR), str(VENV_DIR)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                print("[+] Successfully created directory junction.")
                return True
            except subprocess.CalledProcessError:
                pass
        # Fallback to symlink or directory copy
        try:
            BINARIES_DIR.symlink_to(VENV_DIR, target_is_directory=True)
            print("[+] Successfully created directory symlink.")
            return True
        except (OSError, NotImplementedError):
            print("[*] Symlink not permitted; copying environment tree (this may take a moment)...")
            shutil.copytree(VENV_DIR, BINARIES_DIR, symlinks=True)
            print("[+] Environment copied successfully.")
            return True
    except Exception as e:
        print(f"[-] Staging failed: {e}")
        return False


def verify_sidecar() -> bool:
    """Verify that the staged sidecar or .venv can run worker commands."""
    if os.name == "nt":
        target_py = BINARIES_DIR / "Scripts" / "python.exe"
        if not target_py.exists():
            target_py = BINARIES_DIR / "python.exe"
    else:
        target_py = BINARIES_DIR / "bin" / "python"
        if not target_py.exists():
            target_py = BINARIES_DIR / "python3"

    if not target_py.exists():
        # Check if root .venv exists
        if os.name == "nt":
            target_py = VENV_DIR / "Scripts" / "python.exe"
        else:
            target_py = VENV_DIR / "bin" / "python"

    if not target_py.exists():
        print("[-] No Python runtime found in src-tauri/binaries/python or .venv")
        return False

    print(f"[*] Verifying runtime: {target_py}")
    if not check_dependencies(target_py):
        return False

    # Test importing worker
    try:
        test_cmd = [
            str(target_py),
            "-c",
            "import worker.engine; import worker.server; import worker.audit; import worker.report; print('All worker modules imported successfully.')",
        ]
        out = subprocess.check_output(test_cmd, cwd=str(ROOT), text=True).strip()
        print(f"[+] {out}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[-] Worker verification failed: {e}")
        return False


def print_release_guide():
    """Print instructions for creating standalone zero-dependency packages."""
    print("""
================================================================================
Standalone Packaging Guide (indygreg / astral-sh python-build-standalone)
================================================================================
For production distribution where end-users do not have Python installed:

1. Download a standalone Python release from:
   https://github.com/astral-sh/python-build-standalone/releases
   Example for Windows x86_64:
   cpython-3.12.*+*-x86_64-pc-windows-msvc-install_only.tar.gz

2. Extract the archive into:
   interview-integrity-monitor/src-tauri/binaries/python/

3. Install production dependencies into the standalone Python:
   Windows:
     src-tauri/binaries/python/python.exe -m pip install -r requirements.txt
   macOS/Linux:
     src-tauri/binaries/python/bin/python3 -m pip install -r requirements.txt

4. Configure tauri.conf.json resources:
   In `bundle.resources`, include:
     "binaries/python/": "binaries/python/"

5. Build the desktop installer:
   npm run desktop:build
================================================================================
""")


def main():
    parser = argparse.ArgumentParser(description="Interview Integrity Monitor Sidecar Preparation")
    parser.add_argument("--stage", action="store_true", help="Stage local .venv into src-tauri/binaries/python")
    parser.add_argument("--force", action="store_true", help="Force overwrite when staging")
    parser.add_argument("--verify", action="store_true", help="Verify runtime and dependencies")
    parser.add_argument("--guide", action="store_true", help="Show standalone release packaging guide")
    args = parser.parse_args()

    if len(sys.argv) == 1:
        # Default workflow: verify and report status
        args.verify = True

    if args.guide:
        print_release_guide()

    if args.stage:
        success = stage_local_venv(force=args.force)
        if not success:
            sys.exit(1)

    if args.verify:
        success = verify_sidecar()
        if not success:
            sys.exit(1)
        print("[+] Sidecar environment is ready and verified.")


if __name__ == "__main__":
    main()
