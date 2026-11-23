"""Package an existing PyInstaller onedir build and its native Explorer handler."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tomllib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def nsis_path(path: Path) -> str:
    return str(path).replace("$", "$$")


def uninstall_manifest(bundle: Path, destination: Path) -> None:
    # Delete only payload files and empty directories owned by this release.
    entries = sorted(bundle.rglob("*"), key=lambda path: (-len(path.parts), str(path)))
    lines = []
    for entry in entries:
        if entry.is_symlink():
            raise ValueError(f"Unexpected symbolic link in Windows bundle: {entry}")
        command = "RMDir" if entry.is_dir() else "Delete /REBOOTOK"
        lines.append(f'{command} "$INSTDIR\\{nsis_path(entry.relative_to(bundle))}"')
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--makensis", default=shutil.which("makensis"))
    parser.add_argument("--bundle", type=Path, default=ROOT / "dist" / "HiFine")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build" / "windows")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    build = args.build_dir.resolve()
    nsis = args.makensis or Path(os.environ["ProgramFiles(x86)"]) / "NSIS" / "makensis.exe"
    if not Path(nsis).is_file():
        parser.error("Install NSIS 3 or pass --makensis with the path to makensis.exe")
    if not (bundle / "HiFine.exe").is_file():
        parser.error(f"Build packaging/HiFine.spec before packaging {bundle}")
    libraries = list((bundle / "_internal").glob("libheif-*.dll"))
    if len(libraries) != 1:
        parser.error(f"Expected exactly one pillow-heif libheif DLL in {bundle / '_internal'}")

    native = build / "thumbnail"
    subprocess.run([
        "cmake", "-S", HERE / "thumbnail", "-B", native, "-A", "x64",
        f"-DHIFINE_HEIF_DLL={libraries[0].name}", "-DHIFINE_THUMBNAIL_TEST=ON",
    ], check=True)
    subprocess.run(["cmake", "--build", native, "--config", "Release", "--parallel"], check=True)
    provider = bundle / "HiFineThumbnail.dll"
    shutil.copy2(native / "Release" / provider.name, provider)
    specimen = next((bundle / "_internal/hifine/assets/samples").glob("*.hif"))
    smoke = native / "Release/thumbnail_smoke.exe"
    subprocess.run([smoke, provider, specimen], check=True)
    subprocess.run([smoke, provider, HERE / "thumbnail/provider.def", "invalid"], check=True)

    manifest = build / "uninstall-files.nsh"
    uninstall_manifest(bundle, manifest)
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve() / f"HiFine-{version}-windows-x64-setup.exe"
    subprocess.run([
        nsis, "/V2", "/INPUTCHARSET", "UTF8", f"/DAPP_VERSION={version}",
        f"/DBUNDLE={bundle}", f"/DMANIFEST={manifest}", f"/DOUTPUT={output}", HERE / "installer.nsi",
    ], check=True)
    print(output)


if __name__ == "__main__":
    main()
