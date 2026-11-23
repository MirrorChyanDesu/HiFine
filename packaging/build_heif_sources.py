"""Build or verify the source archive accompanying the distributed HEIF wheels."""

import argparse
import hashlib
import json
import shutil
import tempfile
import tomllib
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSYS = "https://raw.githubusercontent.com/msys2/MINGW-packages"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    sha256: str


# The Linux/macOS source releases are pinned by pillow-heif's libheif/build_libs.py.
# Windows uses the MSYS2 packages; include their recipes and the patch applied to x265.
SOURCES = (
    Source("pillow_heif-v1.8.1.tar.gz",
           "https://codeload.github.com/bigcat88/pillow_heif/tar.gz/0ed53791bef34eeda0182b7a26476f99445922de",
           "6c794d0d214a723dbe5fe1b7c2e6bf683c6180574e84893c9857399999d6be01"),
    Source("libheif-1.23.6.tar.gz",
           "https://github.com/strukturag/libheif/releases/download/v1.23.6/libheif-1.23.6.tar.gz",
           "4484346dc5995319dbc11e3a1c35d0a2ec46511ce370900869337fd2c7033125"),
    Source("libde265-1.1.3.tar.gz",
           "https://github.com/strukturag/libde265/releases/download/v1.1.3/libde265-1.1.3.tar.gz",
           "554228bd17788c99a7e63b37ab5634722190e6e2bf60c1dcb01cef328e133905"),
    Source("x265_4.3.tar.gz",
           "https://github.com/Multicorewareinc/x265/releases/download/4.3/x265_4.3.tar.gz",
           "83c53e4c8bbb8f1e33ed59e10a7d621d1d7801ca853910c3eb41f038b8ffb121"),
    Source("msys2/mingw-w64-x265/PKGBUILD",
           f"{MSYS}/f6ae36581d8dd1f6878442575cc8471830b863ed/mingw-w64-x265/PKGBUILD",
           "440ec07f857cc7490c91e95b27d1cc47adfbfd45305b95990ac95f46fd2fae6f"),
    Source("msys2/mingw-w64-x265/0001-missing-include.patch",
           f"{MSYS}/f6ae36581d8dd1f6878442575cc8471830b863ed/mingw-w64-x265/0001-missing-include.patch",
           "20e240c5365665e254b6030a458376fac16c1797903d607cae5863b280859a8f"),
    Source("msys2/mingw-w64-libde265/PKGBUILD",
           f"{MSYS}/c32cb4bc3e7de5dfc31415748daabe79c469d5fb/mingw-w64-libde265/PKGBUILD",
           "c6ce4da2f67ab13650fca6f7279b909557740912b385f9ad8c17dc120f8b047e"),
)

README = b"""HiFine HEIF component sources

Extract the component archives to obtain the upstream source trees and licenses.
The pillow-heif v1.8.1 tree contains .github/workflows/wheels.yml for all three
platforms, libheif/build_libs.py for macOS and Linux, and
libheif/windows/mingw-w64-libheif/PKGBUILD for Windows. The msys2 directory
contains the Windows codec package recipes and the x265 patch. The x265 source
release records revision e9b8812 in x265Version.txt (4.3+1-e9b8812).

sources.json records each original file's location and SHA-256 digest.
"""


def manifest() -> bytes:
    return (json.dumps([asdict(item) for item in SOURCES], indent=2) + "\n").encode()


def verify(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        expected = ["README.txt", "sources.json"] + [item.name for item in SOURCES]
        if sorted(archive.namelist()) != sorted(expected):
            raise ValueError("Unexpected source archive contents")
        if archive.read("README.txt") != README or archive.read("sources.json") != manifest():
            raise ValueError("Source archive metadata mismatch")
        for item in SOURCES:
            with archive.open(item.name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item.sha256:
                    raise ValueError(f"Incorrect SHA-256 for {item.name}")
    print(f"Verified {len(SOURCES)} pinned source files in {path}")


def member(name: str) -> zipfile.ZipInfo:
    # Fixed metadata makes the ZIP independent of the local clock and architecture.
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        candidate = Path(staging) / destination.name
        with zipfile.ZipFile(candidate, "w") as archive:
            archive.writestr(member("README.txt"), README)
            archive.writestr(member("sources.json"), manifest())
            for item in SOURCES:
                request = urllib.request.Request(item.url, headers={"User-Agent": "HiFine source packager"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    with archive.open(member(item.name), "w") as output:
                        shutil.copyfileobj(response, output)
        verify(candidate)
        candidate.replace(destination)
    print(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, metavar="ZIP", help="verify an existing archive offline")
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
    else:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        if "pillow-heif==1.8.1" not in project["dependencies"]:
            parser.error("Update the source pins to match the project's pillow-heif dependency")
        build(ROOT / "release" / f"HiFine-{project['version']}-heif-sources.zip")
