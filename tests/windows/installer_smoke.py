"""Exercise the NSIS install and uninstall without changing the user's associations.

Run after packaging/windows/build_installer.py, passing a path to makensis.exe.
"""

import ctypes
from ctypes import wintypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
import winreg


REPO = Path(__file__).resolve().parents[2]
IID = "{E357FCCD-A995-4576-B01F-234630154E96}"
CLSID = "{85E522D8-EC6F-4163-9F28-96B13B918743}"


def value(key, name=""):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
        return winreg.QueryValueEx(handle, name)[0]


def write(key, data, name=""):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
        winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, data)


def verify_shell(user_root, classes, app, sample):
    # Give this process private HKCR / HKCU views before loading the Shell APIs.
    advapi = ctypes.WinDLL("advapi32")
    redirect = advapi.RegOverridePredefKey
    redirect.argtypes = [wintypes.HKEY, wintypes.HKEY]
    redirect.restype = wintypes.LONG
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, classes) as private_classes, \
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_root) as private_user:
        assert redirect(winreg.HKEY_CLASSES_ROOT, int(private_classes)) == 0
        assert redirect(winreg.HKEY_CURRENT_USER, int(private_user)) == 0
        try:
            query = ctypes.WinDLL("shlwapi").AssocQueryStringW
            query.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                              wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            for kind, extra, expected in ((1, "open", f'"{app}" "%1"'), (16, IID, CLSID)):
                output = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(output))
                hr = query(0x10, kind, ".hif", extra, output, ctypes.byref(size))
                assert hr == 0 and output.value.lower() == expected.lower(), (kind, hex(hr), output.value)
            print("Windows resolved the .hif open command and IThumbnailProvider CLSID.")
        finally:
            redirect(winreg.HKEY_CURRENT_USER, None)
            redirect(winreg.HKEY_CLASSES_ROOT, None)

    # Give ShellExecuteEx the private association's class key so the live user's
    # preferred application cannot be launched by this test.
    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    kernel = ctypes.WinDLL("kernel32")
    user = ctypes.WinDLL("user32")
    kernel.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, classes + "\\" + value(classes + r"\.hif")) as progid:
        info = ShellExecuteInfo(cbSize=ctypes.sizeof(ShellExecuteInfo), fMask=0x3 | 0x40 | 0x400,
                                lpVerb="open", lpFile=str(sample), nShow=0, hkeyClass=int(progid))
        assert ctypes.WinDLL("shell32").ShellExecuteExW(ctypes.byref(info)) and info.hProcess
    process_id = kernel.GetProcessId(info.hProcess)
    found = []
    seen = set()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(window, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value == process_id:
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(window, title, len(title))
            seen.add(title.value)
            if title.value == f"{sample.name} — HiFine":
                found.append(window)
        return True

    try:
        for _ in range(150):
            user.EnumWindows(visit, 0)
            if found or kernel.WaitForSingleObject(info.hProcess, 0) != 258:
                break
            time.sleep(0.1)
        assert found, f"HiFine did not display the requested document: {seen}"
        user.PostMessageW(found[0], 0x10, 0, 0)
        assert kernel.WaitForSingleObject(info.hProcess, 5000) == 0
        print("ShellExecute opened the selected image in the installed viewer, which closed normally.")
    finally:
        if kernel.WaitForSingleObject(info.hProcess, 0) == 258:
            kernel.TerminateProcess(info.hProcess, 1)
            kernel.WaitForSingleObject(info.hProcess, 5000)
        kernel.CloseHandle(info.hProcess)


def main():
    nsis = sys.argv[1] if len(sys.argv) > 1 else shutil.which("makensis")
    if not nsis:
        raise SystemExit("Pass a path to makensis.exe")
    root = rf"Software\HiFine-Installer-QA-{uuid.uuid4()}"
    software = root + r"\Software"
    classes = software + r"\Classes"
    bundle = REPO / "dist/HiFine"
    with (REPO / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    try:
        with tempfile.TemporaryDirectory(prefix="HiFine integration ") as work:
            directory = Path(work)
            setup = directory / "HiFine-install-check.exe"
            target = directory / "HiFine"
            subprocess.run([
                nsis, "/V2", "/INPUTCHARSET", "UTF8", "/XSetCompressor /FINAL zlib",
                f"/DAPP_VERSION={version}", f"/DSOFTWARE_ROOT={software}", f"/DSHORTCUT_DIR={directory}",
                f"/DBUNDLE={bundle}", f"/DMANIFEST={REPO / 'build/windows/uninstall-files.nsh'}",
                f"/DOUTPUT={setup}", REPO / "packaging/windows/installer.nsi",
            ], check=True)
            # Start with an unclaimed .hif and a pre-existing .heic thumbnail handler.
            retained = classes + rf"\.heic\shellex\{IID}"
            write(retained, "{00000001-0000-0000-0000-000000000000}")
            subprocess.run(f'"{setup}" /S /D={target}', check=True, timeout=90)
            app = target / "HiFine.exe"
            assert app.is_file() and (directory / "HiFine.lnk").is_file()
            assert value(software + r"\Microsoft\Windows\CurrentVersion\Uninstall\HiFine", "DisplayVersion") == version
            assert value(classes + r"\.hif") == "HiFine.Heif"
            assert value(software + r"\RegisteredApplications", "HiFine") == software + r"\HiFine\Capabilities"
            assert value(classes + rf"\CLSID\{CLSID}\InprocServer32") == str(target / "HiFineThumbnail.dll")
            assert value(classes + r"\.jpg\OpenWithProgids", "HiFine.Image") == ""
            assert value(retained).startswith("{00000001")
            sample = directory / "open file 测试.HIF"
            shutil.copyfile(next((bundle / "_internal/hifine/assets/samples").glob("*.hif")), sample)
            provider = value(classes + rf"\CLSID\{CLSID}\InprocServer32")
            subprocess.run([REPO / "build/windows/thumbnail/Release/thumbnail_smoke.exe",
                            provider, sample], check=True)
            gui_error = None
            try:
                verify_shell(root, classes, app, sample)
            except AssertionError as exc:
                gui_error = exc
            # Windows can store the user's default in UserChoice alone. A repair
            # installation must leave that choice and the empty extension default intact.
            choice = software + r"\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.hif\UserChoice"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, classes + r"\.hif", 0, winreg.KEY_SET_VALUE) as ext:
                winreg.DeleteValue(ext, "")
            write(choice, "AnotherViewer.Hif", "ProgId")
            subprocess.run(f'"{setup}" /S /D={target}', check=True, timeout=90)
            try:
                value(classes + r"\.hif")
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("Repair claimed an extension with an existing UserChoice")
            assert value(choice, "ProgId") == "AnotherViewer.Hif"
            # Run a copy in place so the test can wait while it removes the installed uninstaller.
            uninstall = directory / "HiFine-uninstall-check.exe"
            shutil.copy2(target / "Uninstall.exe", uninstall)
            sentinel = target / "user-created.txt"
            sentinel.touch()
            subprocess.run(f'"{uninstall}" /S _?={target}', check=True, timeout=90)
            assert value(retained).startswith("{00000001")
            assert value(choice, "ProgId") == "AnotherViewer.Hif"
            for removed in (software + r"\HiFine\Capabilities", classes + r"\HiFine.Heif",
                            classes + rf"\CLSID\{CLSID}", classes + rf"\.hif\shellex\{IID}"):
                try:
                    winreg.OpenKey(winreg.HKEY_CURRENT_USER, removed).Close()
                except FileNotFoundError:
                    continue
                raise AssertionError(f"Uninstall left {removed}")
            assert sentinel.exists() and not app.exists() and not (directory / "HiFine.lnk").exists()
            print("Uninstall removed HiFine and preserved other handlers and user-created files.")
            if gui_error is not None:
                raise gui_error
    finally:
        # This UUID-named key belongs exclusively to this test.
        subprocess.run(["reg.exe", "delete", "HKCU\\" + root, "/f"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
