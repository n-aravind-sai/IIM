"""Public OS metadata APIs only. No window text, process arguments or images."""
import ctypes
import os
import platform
import subprocess
from pathlib import Path


def get_pe_metadata(filepath):
    if platform.system() != "Windows" or not filepath:
        return {}
    try:
        from ctypes import wintypes as w
        v = ctypes.WinDLL("version", use_last_error=True)
        handle = w.DWORD()
        size = v.GetFileVersionInfoSizeW(filepath, ctypes.byref(handle))
        if not size:
            return {}
        buf = ctypes.create_string_buffer(size)
        if not v.GetFileVersionInfoW(filepath, 0, size, buf):
            return {}
        trans_ptr = ctypes.c_void_p()
        trans_len = w.UINT()
        res = {}
        if v.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)):
            if trans_len.value >= 4:
                trans_data = ctypes.cast(trans_ptr, ctypes.POINTER(w.WORD))
                lang, cp = trans_data[0], trans_data[1]
                sub = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\"
                for prop in ("FileDescription", "ProductName", "OriginalFilename", "CompanyName"):
                    ptr = ctypes.c_void_p()
                    plen = w.UINT()
                    if v.VerQueryValueW(buf, sub + prop, ctypes.byref(ptr), ctypes.byref(plen)) and plen.value > 0:
                        val = ctypes.wstring_at(ptr.value)
                        if val.strip():
                            res[prop] = val.strip()
        return res
    except Exception:
        return {}


def processes():
    system = platform.system()
    if system == "Windows":
        from ctypes import wintypes as w

        class Entry(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                        ("heap", ctypes.c_size_t), ("module", w.DWORD),
                        ("threads", w.DWORD), ("parent", w.DWORD),
                        ("priority", w.LONG), ("flags", w.DWORD),
                        ("name", w.WCHAR * 260)]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
        k.CreateToolhelp32Snapshot.restype = w.HANDLE
        k.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
        k.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
        k.CloseHandle.argtypes = [w.HANDLE]
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.OpenProcess.restype = w.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        k.QueryFullProcessImageNameW.restype = w.BOOL
        handle = k.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError("Process snapshot unavailable")
        out = []
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(entry)
            ok = k.Process32FirstW(handle, ctypes.byref(entry))
            if not ok:
                raise OSError("Process enumeration unavailable")
            while ok:
                meta = {}
                if entry.pid > 4:
                    h_proc = k.OpenProcess(0x1000, False, entry.pid)
                    if h_proc:
                        try:
                            img_buf = ctypes.create_unicode_buffer(1024)
                            img_size = w.DWORD(1024)
                            if k.QueryFullProcessImageNameW(h_proc, 0, img_buf, ctypes.byref(img_size)):
                                meta = get_pe_metadata(img_buf.value)
                        except Exception:
                            pass
                        finally:
                            k.CloseHandle(h_proc)
                out.append({"pid": entry.pid, "name": entry.name, "metadata": meta})
                ok = k.Process32NextW(handle, ctypes.byref(entry))
        finally:
            k.CloseHandle(handle)
        return out
    if system == "Darwin":
        output = subprocess.run(["/bin/ps", "-axo", "pid=,comm="], capture_output=True,
                                text=True, timeout=3, check=True).stdout
        return [{"pid": int(parts[0]), "name": Path(parts[1]).name, "metadata": {}}
                for line in output.splitlines() if len(parts := line.strip().split(None, 1)) == 2]
    # Linux is a development fallback, not a supported desktop release target.
    out = []
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                out.append({"pid": int(p.name), "name": (p / "comm").read_text().strip(), "metadata": {}})
            except (OSError, UnicodeError):
                pass
    return out


def windows():
    system = platform.system()
    if system == "Windows":
        from ctypes import wintypes as w
        u = ctypes.WinDLL("user32", use_last_error=True)
        cbtype = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        u.EnumWindows.argtypes = [cbtype, w.LPARAM]
        u.IsWindowVisible.argtypes = [w.HWND]
        u.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = w.LONG
        u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.GetWindowDisplayAffinity.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.GetLayeredWindowAttributes.argtypes = [w.HWND, ctypes.POINTER(w.DWORD),
                                                ctypes.POINTER(w.BYTE), ctypes.POINTER(w.DWORD)]
        out = []

        @cbtype
        def callback(hwnd, _):
            if not u.IsWindowVisible(hwnd):
                return True
            pid, affinity = w.DWORD(), w.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid():
                return True
            style = u.GetWindowLongW(hwnd, -20)
            color, alpha, flags = w.DWORD(), w.BYTE(255), w.DWORD()
            alpha_ok = u.GetLayeredWindowAttributes(hwnd, ctypes.byref(color),
                                                     ctypes.byref(alpha), ctypes.byref(flags))
            affinity_ok = u.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity))
            out.append({"id": str(hwnd), "pid": pid.value, "topmost": bool(style & 8),
                        "layered": bool(style & 0x80000), "clickthrough": bool(style & 0x20),
                        "alpha": alpha.value / 255 if alpha_ok and flags.value & 2 else None,
                        "affinity": affinity.value if affinity_ok else None})
            return True
        if not u.EnumWindows(callback, 0):
            raise OSError("Window enumeration unavailable")
        return out
    if system == "Darwin":
        import Quartz as q
        rows = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly |
                                           q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID)
        if rows is None:
            raise PermissionError("Window metadata unavailable")
        return [{"id": str(row.get(q.kCGWindowNumber)), "pid": row.get(q.kCGWindowOwnerPID),
                 "topmost": row.get(q.kCGWindowLayer, 0) > 0,
                 "layered": row.get(q.kCGWindowAlpha, 1) < 1,
                 "clickthrough": False, "alpha": row.get(q.kCGWindowAlpha),
                 "affinity": None} for row in rows if row.get(q.kCGWindowOwnerPID) != os.getpid()]
    raise NotImplementedError("Native window metadata requires Windows or macOS")


def displays():
    if platform.system() == "Windows":
        from ctypes import wintypes as w

        class Device(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("name", w.WCHAR * 32), ("label", w.WCHAR * 128),
                        ("flags", w.DWORD), ("id", w.WCHAR * 128), ("key", w.WCHAR * 128)]
        u = ctypes.WinDLL("user32")
        u.EnumDisplayDevicesW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(Device), w.DWORD]
        devices = []
        for i in range(64):
            d = Device()
            d.cb = ctypes.sizeof(d)
            if not u.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
                break
            if d.flags & 1:
                devices.append({"label": d.label, "virtual_hint": bool(d.flags & 8) or
                                any(x in d.label.lower() for x in ("virtual", "indirect", "remote"))})
        return devices
    if platform.system() == "Darwin":
        import Quartz as q
        error, ids, count = q.CGGetActiveDisplayList(32, None, None)
        if error:
            raise OSError("Display enumeration unavailable")
        return [{"label": "Built-in display" if q.CGDisplayIsBuiltin(i) else "External display",
                 "virtual_hint": None} for i in list(ids)[:count]]
    raise NotImplementedError("Display metadata requires Windows or macOS")


def audio_devices():
    # PortAudio device inventory only: does not open audio or identify listeners.
    import sounddevice
    return [{"name": d["name"], "inputs": d["max_input_channels"]}
            for d in sounddevice.query_devices() if d["max_input_channels"] > 0]
