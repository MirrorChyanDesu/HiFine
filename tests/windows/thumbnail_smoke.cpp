#include <windows.h>
#include <shobjidl.h>
#include <shlwapi.h>
#include <thumbcache.h>
#include <wrl/client.h>
#include <cstdio>
#include <cwchar>

using Microsoft::WRL::ComPtr;

// Exercise the COM interfaces used by Explorer with no registry or default-app changes.
int wmain(int argc, wchar_t** argv) {
    if (argc < 3 || argc > 4) {
        std::fwprintf(stderr, L"thumbnail_smoke <installed DLL path> <input image> [invalid]\n");
        return 2;
    }
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) return 3;
    HMODULE library = LoadLibraryW(argv[1]);
    if (!library) return 4;
    auto get_factory = reinterpret_cast<decltype(&DllGetClassObject)>(GetProcAddress(library, "DllGetClassObject"));
    auto can_unload = reinterpret_cast<decltype(&DllCanUnloadNow)>(GetProcAddress(library, "DllCanUnloadNow"));
    if (!get_factory || !can_unload || can_unload() != S_OK) return 5;
    const CLSID clsid = {0x85e522d8, 0xec6f, 0x4163, {0x9f,0x28,0x96,0xb1,0x3b,0x91,0x87,0x43}};
    ComPtr<IClassFactory> factory;
    if (FAILED(get_factory(clsid, IID_PPV_ARGS(&factory)))) return 6;
    ComPtr<IInitializeWithStream> setup;
    if (FAILED(factory->CreateInstance(nullptr, IID_PPV_ARGS(&setup)))) return 7;
    ComPtr<IStream> stream;
    if (FAILED(SHCreateStreamOnFileEx(argv[2], STGM_READ | STGM_SHARE_DENY_NONE, 0, FALSE, nullptr, &stream))) return 8;
    if (FAILED(setup->Initialize(stream.Get(), STGM_READ))) return 9;
    if (setup->Initialize(stream.Get(), STGM_READ) != HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED)) return 10;
    ComPtr<IThumbnailProvider> provider;
    if (FAILED(setup.As(&provider))) return 11;
    HBITMAP bitmap{};
    WTS_ALPHATYPE type{};
    HRESULT hr = provider->GetThumbnail(256, &bitmap, &type);
    if (argc == 4 && wcscmp(argv[3], L"invalid") == 0) {
        if (SUCCEEDED(hr) || bitmap) return 12;
    } else {
        BITMAP desc{};
        if (FAILED(hr) || !bitmap || type != WTSAT_ARGB || !GetObjectW(bitmap, sizeof(desc), &desc)
            || !desc.bmBits || desc.bmWidth < 1 || desc.bmWidth > 256 || desc.bmHeight < 1 || desc.bmHeight > 256) {
            std::fwprintf(stderr, L"Missing/invalid thumbnail, HRESULT 0x%08lx\n", static_cast<unsigned long>(hr));
            return 13;
        }
        std::wprintf(L"Decoded %ld x %ld, %u bpp\n", desc.bmWidth, desc.bmHeight, desc.bmBitsPixel);
        DeleteObject(bitmap);
    }
    if (can_unload() != S_FALSE) return 14;
    provider.Reset();
    setup.Reset();
    factory.Reset();
    stream.Reset();
    if (can_unload() != S_OK) return 15;
    FreeLibrary(library);
    CoUninitialize();
    return 0;
}
