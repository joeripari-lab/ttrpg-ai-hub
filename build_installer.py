"""
Build a standalone Windows distribution of TTRPG AI Hub using PyInstaller.
Excludes copyrighted rulebook PDFs (users provide their own via the Setup Wizard).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA_ARGS = [
    f"--add-data={ROOT / 'dcc_assets' / 'templates'};dcc_assets/templates",
    f"--add-data={ROOT / 'sw5e_assets' / 'templates'};sw5e_assets/templates",
    f"--add-data={ROOT / 'dnd5e_assets' / 'templates'};dnd5e_assets/templates",
]

CMD = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--collect-all=webview",
    "--hidden-import=clr",
    "--workpath",
    str(ROOT / "build_win"),
    "--distpath",
    str(ROOT / "dist_win"),
    "--name=TTRPG_AI_Hub",
    *DATA_ARGS,
    str(ROOT / "desktop_launcher.py"),
]

if __name__ == "__main__":
    print("Running:", " ".join(CMD))
    subprocess.check_call(CMD, cwd=str(ROOT))
    print("\nBuild complete! Output in dist/TTRPG_AI_Hub/TTRPG_AI_Hub.exe")
    print("Next: Compile installer.iss with Inno Setup to produce TTRPG_AI_Hub_Setup.exe")
