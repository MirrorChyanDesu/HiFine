#include <windows.h>
#include <shobjidl.h>
#include <thumbcache.h>
#include <wrl/client.h>
#include <libheif/heif.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <memory>
#include <new>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {
// {85E522D8-EC6F-4163-9F28-96B13B918743}
constexpr CLSID provider_id = {0x85e522d8, 0xec6f, 0x4163, {0x9f,0x28,0x96,0xb1,0x3b,0x91,0x87,0x43}};
HMODULE provider_module;
std::atomic<long> active_objects{0};

// The bundled wheel gives its DLLs content-specific names. Resolve them relative
// to our installed DLL, including dependencies, independent of Explorer's PATH.
#define HEIF_SYMBOLS(X) \
    X(heif_init) X(heif_deinit) X(heif_context_alloc) X(heif_context_free) \
    X(heif_context_read_from_memory_without_copy) X(heif_context_get_primary_image_handle) \
    X(heif_image_handle_get_width) X(heif_image_handle_get_height) X(heif_image_handle_release) \
    X(heif_image_handle_get_list_of_thumbnail_IDs) X(heif_image_handle_get_thumbnail) \
    X(heif_decode_image) X(heif_image_release) X(heif_image_get_plane_readonly) \
    X(heif_image_get_primary_width) X(heif_image_get_primary_height) X(heif_image_scale_image)

struct Decoder {
    HMODULE library = nullptr;
    bool initialized = false;
#define DECLARE(name) decltype(&::name) name = nullptr;
    HEIF_SYMBOLS(DECLARE)
#undef DECLARE

    bool load() {
        std::wstring path(32768, L'\0');
        DWORD length = GetModuleFileNameW(provider_module, path.data(), static_cast<DWORD>(path.size()));
        if (!length || length >= path.size()) return false;
        path.resize(length);
        path.resize(path.find_last_of(L"\\/") + 1);
        path += L"_internal\\" HIFINE_HEIF_DLL;
        library = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!library) return false;
#define LOAD(name) name = reinterpret_cast<decltype(name)>(GetProcAddress(library, #name)); if (!name) return false;
        HEIF_SYMBOLS(LOAD)
#undef LOAD
        initialized = heif_init(nullptr).code == heif_error_Ok;
        return initialized;
    }

    ~Decoder() {
        if (initialized) heif_deinit();
        if (library) FreeLibrary(library);
    }
};

HRESULT decode_thumbnail(IStream* stream, UINT size, HBITMAP* result, WTS_ALPHATYPE* alpha) {
    STATSTG stat{};
    HRESULT hr = stream->Stat(&stat, STATFLAG_NONAME);
    if (FAILED(hr)) return hr;
    constexpr ULONG max_input = 128 * 1024 * 1024;
    if (!stat.cbSize.QuadPart || stat.cbSize.QuadPart > max_input) return E_INVALIDARG;
    hr = stream->Seek({}, STREAM_SEEK_SET, nullptr);
    if (FAILED(hr)) return hr;
    std::vector<unsigned char> data(stat.cbSize.LowPart);
    ULONG read = 0;
    hr = stream->Read(data.data(), stat.cbSize.LowPart, &read);
    if (FAILED(hr) || read != data.size()) return STG_E_READFAULT;

    Decoder api;
    if (!api.load()) return E_FAIL;
    std::unique_ptr<heif_context, decltype(api.heif_context_free)> context(api.heif_context_alloc(), api.heif_context_free);
    if (!context) return E_OUTOFMEMORY;
    if (api.heif_context_read_from_memory_without_copy(context.get(), data.data(), data.size(), nullptr).code)
        return WINCODEC_ERR_BADIMAGE;
    heif_image_handle* handle = nullptr;
    if (api.heif_context_get_primary_image_handle(context.get(), &handle).code) return WINCODEC_ERR_BADIMAGE;
    using Handle = std::unique_ptr<heif_image_handle, decltype(api.heif_image_handle_release)>;
    Handle source(handle, api.heif_image_handle_release);
    Handle embedded(nullptr, api.heif_image_handle_release);
    heif_item_id thumbnail_id;
    if (api.heif_image_handle_get_list_of_thumbnail_IDs(source.get(), &thumbnail_id, 1) == 1 &&
        !api.heif_image_handle_get_thumbnail(source.get(), thumbnail_id, &handle).code) {
        embedded.reset(handle);
    }
    heif_image* pixels = nullptr;
    auto decode = [&](const Handle& input) {
        if (!input) return false;
        int w = api.heif_image_handle_get_width(input.get());
        int h = api.heif_image_handle_get_height(input.get());
        if (w <= 0 || h <= 0 || int64_t(w) * h > 120'000'000) return false;
        return api.heif_decode_image(input.get(), &pixels, heif_colorspace_RGB, heif_chroma_interleaved_RGBA, nullptr).code == heif_error_Ok;
    };
    // Some Sony HIF files contain a thumbnail whose advertised dimensions are
    // incorrect while the full-resolution primary image is perfectly decodable.
    if (!decode(embedded) && !decode(source)) return WINCODEC_ERR_BADIMAGE;
    std::unique_ptr<heif_image, decltype(api.heif_image_release)> image(pixels, api.heif_image_release);
    int width = api.heif_image_get_primary_width(image.get());
    int height = api.heif_image_get_primary_height(image.get());
    if (width <= 0 || height <= 0) return WINCODEC_ERR_BADIMAGE;
    int longest = std::max(width, height);
    if (longest > static_cast<int>(size)) {
        width = std::max(1, MulDiv(width, size, longest));
        height = std::max(1, MulDiv(height, size, longest));
        if (api.heif_image_scale_image(image.get(), &pixels, width, height, nullptr).code) return E_FAIL;
        image.reset(pixels);
    }
    int stride = 0;
    const auto* rgba = api.heif_image_get_plane_readonly(image.get(), heif_channel_interleaved, &stride);
    if (!rgba || stride < width * 4) return WINCODEC_ERR_BADIMAGE;
    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = width;
    info.bmiHeader.biHeight = -height;  // top-down DIB
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* dest = nullptr;
    HBITMAP bitmap = CreateDIBSection(nullptr, &info, DIB_RGB_COLORS, &dest, nullptr, 0);
    if (!bitmap) return E_OUTOFMEMORY;
    auto* bgra = static_cast<unsigned char*>(dest);
    for (int y = 0; y < height; ++y) {
        const auto* row = rgba + static_cast<size_t>(y) * stride;
        for (int x = 0; x < width; ++x, row += 4, bgra += 4) {
            const unsigned int a = row[3];
            bgra[0] = (row[2] * a + 127) / 255;
            bgra[1] = (row[1] * a + 127) / 255;
            bgra[2] = (row[0] * a + 127) / 255;
            bgra[3] = static_cast<unsigned char>(a);
        }
    }
    *result = bitmap;
    *alpha = WTSAT_ARGB;
    return S_OK;
}

struct RefCounted {
    std::atomic<ULONG> references{1};
    RefCounted() { ++active_objects; }
    virtual ~RefCounted() { --active_objects; }
    ULONG release() {
        ULONG count = --references;
        if (!count) delete this;
        return count;
    }
};

class Provider final : public RefCounted, public IInitializeWithStream, public IThumbnailProvider {
    ComPtr<IStream> stream_;
public:
    STDMETHODIMP QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IInitializeWithStream)) *out = static_cast<IInitializeWithStream*>(this);
        else if (iid == __uuidof(IThumbnailProvider)) *out = static_cast<IThumbnailProvider*>(this);
        else return E_NOINTERFACE;
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return ++references; }
    STDMETHODIMP_(ULONG) Release() override { return release(); }
    STDMETHODIMP Initialize(IStream* stream, DWORD) override {
        if (!stream) return E_POINTER;
        if (stream_) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        stream_ = stream;
        return S_OK;
    }
    STDMETHODIMP GetThumbnail(UINT size, HBITMAP* bitmap, WTS_ALPHATYPE* alpha) override {
        if (!bitmap || !alpha) return E_POINTER;
        *bitmap = nullptr;
        *alpha = WTSAT_UNKNOWN;
        if (!size || !stream_) return E_INVALIDARG;
        try {
            return decode_thumbnail(stream_.Get(), std::min(size, 2048U), bitmap, alpha);
        } catch (const std::bad_alloc&) {
            return E_OUTOFMEMORY;
        } catch (...) {
            return E_FAIL;
        }
    }
};

class Factory final : public RefCounted, public IClassFactory {
public:
    STDMETHODIMP QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid != IID_IUnknown && iid != IID_IClassFactory) return E_NOINTERFACE;
        *out = static_cast<IClassFactory*>(this);
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return ++references; }
    STDMETHODIMP_(ULONG) Release() override { return release(); }
    STDMETHODIMP CreateInstance(IUnknown* outer, REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* provider = new (std::nothrow) Provider;
        if (!provider) return E_OUTOFMEMORY;
        HRESULT hr = provider->QueryInterface(iid, out);
        provider->Release();
        return hr;
    }
    STDMETHODIMP LockServer(BOOL lock) override {
        if (lock) ++active_objects;
        else --active_objects;
        return S_OK;
    }
};
}

extern "C" BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, void*) {
    if (reason == DLL_PROCESS_ATTACH) {
        provider_module = module;
    }
    return TRUE;
}

STDAPI DllCanUnloadNow() { return active_objects == 0 ? S_OK : S_FALSE; }
STDAPI DllGetClassObject(REFCLSID id, REFIID iid, void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (id != provider_id) return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new (std::nothrow) Factory;
    if (!factory) return E_OUTOFMEMORY;
    HRESULT hr = factory->QueryInterface(iid, out);
    factory->Release();
    return hr;
}
