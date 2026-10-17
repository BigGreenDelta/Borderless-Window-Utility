from __future__ import annotations

import configparser
import ctypes
import fnmatch
import logging
import re
import sys
import uuid
from ctypes import WinDLL, wintypes
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Mapping

import pywintypes
import win32api
import win32con
import win32gui
import win32process


PROFILE_FILE = "profiles.ini"
PRESET_FILE = "presets.ini"
SETTINGS_FILE = "settings.ini"
WINDOW_TITLE = "Borderless Window Utility"
DEFAULT_WATCHDOG_TOLERANCE_PX = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
user32: WinDLL = ctypes.windll.user32
kernel32: WinDLL = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
ole32: WinDLL = ctypes.WinDLL("ole32")
ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoCreateInstance.argtypes = (
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
)
ole32.CoCreateInstance.restype = ctypes.c_long
ole32.CoUninitialize.argtypes = ()
ole32.CoUninitialize.restype = None

COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
CLSID_TASKBAR_LIST = uuid.UUID("56FDF344-FD6D-11d0-958A-006097C9A090")
IID_ITASKBAR_LIST2 = uuid.UUID("602D4995-B13A-429b-A66E-1935E44F4317")
# ITaskbarList2 vtable slots: IUnknown (0-2), ITaskbarList (3-7), ITaskbarList2 (8).
_RELEASE_SLOT = 2
_HR_INIT_SLOT = 3
_MARK_FULLSCREEN_WINDOW_SLOT = 8
_ReleaseFn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_HrInitFn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
_MarkFullscreenWindowFn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, wintypes.BOOL)

log = logging.getLogger(__name__)


class BorderlessError(RuntimeError):
    """Raised when a window or profile operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class WindowBounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class WindowProfile:
    bounds: WindowBounds
    # Drop the taskbar behind this window while it is active (see mark_fullscreen_window).
    hide_taskbar: bool = False


@dataclass(frozen=True, slots=True)
class WindowSnapshot:
    hwnd: int
    title: str
    style: int
    exstyle: int
    class_name: str = ""
    process_name: str = ""


@dataclass(frozen=True, slots=True)
class AutoApplyExclusions:
    """Windows that automatic triggers (headless auto-apply, watchdog) must never touch.

    Lists come only from settings.ini; there are no built-in defaults. Patterns are
    case-insensitive and support `*` / `?` wildcards. Manual apply from the TUI and an
    explicit target title ignore these lists.
    """

    processes: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()

    def matches(self, window: WindowSnapshot) -> bool:
        return _matches_any(window.process_name, self.processes) or _matches_any(window.class_name, self.classes)


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    if not value:
        return False
    normalized_value = value.casefold()
    return any(fnmatch.fnmatchcase(normalized_value, pattern.casefold()) for pattern in patterns)


def profile_file_path(script_path: str | Path | None = None) -> Path:
    argv0 = Path(script_path) if script_path is not None else Path(sys.argv[0])
    return argv0.parent.joinpath(PROFILE_FILE)


def preset_file_path(script_path: str | Path | None = None) -> Path:
    argv0 = Path(script_path) if script_path is not None else Path(sys.argv[0])
    return argv0.parent.joinpath(PRESET_FILE)


def settings_file_path(script_path: str | Path | None = None) -> Path:
    argv0 = Path(script_path) if script_path is not None else Path(sys.argv[0])
    return argv0.parent.joinpath(SETTINGS_FILE)


def parse_window_bounds(x: str | int, y: str | int, width: str | int, height: str | int) -> WindowBounds:
    try:
        bounds = WindowBounds(
            x=int(x),
            y=int(y),
            width=int(width),
            height=int(height),
        )
    except ValueError as exc:
        raise BorderlessError("Position and size fields must be valid integers.") from exc

    if bounds.width <= 0 or bounds.height <= 0:
        raise BorderlessError("Width and height must be greater than zero.")

    return bounds


def _read_settings(settings_path: Path | None = None) -> configparser.ConfigParser:
    path = settings_path or settings_file_path()
    config = configparser.ConfigParser()
    if not path.exists():
        return config

    try:
        with path.open("r", encoding="utf-8") as settings_file:
            config.read_file(settings_file)
    except (configparser.Error, OSError) as exc:
        raise BorderlessError(f"Failed to read settings from '{path}': {exc}") from exc

    return config


def _parse_pattern_list(raw_value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[,\n]", raw_value) if item.strip())


def read_auto_apply_exclusions(settings_path: Path | None = None) -> AutoApplyExclusions:
    config = _read_settings(settings_path)
    return AutoApplyExclusions(
        processes=_parse_pattern_list(config.get("auto_apply", "exclude_processes", fallback="")),
        classes=_parse_pattern_list(config.get("auto_apply", "exclude_classes", fallback="")),
    )


def read_watchdog_tolerance_px(settings_path: Path | None = None) -> int:
    config = _read_settings(settings_path)
    raw_value = config.get("watchdog", "tolerance_px", fallback=str(DEFAULT_WATCHDOG_TOLERANCE_PX))
    try:
        tolerance = int(raw_value)
    except ValueError:
        return DEFAULT_WATCHDOG_TOLERANCE_PX

    return max(0, tolerance)


def save_watchdog_tolerance_px(tolerance_px: int, settings_path: Path | None = None) -> None:
    if tolerance_px < 0:
        raise BorderlessError("Watchdog delta must be zero or greater.")

    _write_setting("watchdog", "tolerance_px", str(tolerance_px), settings_path)


def _write_setting(section: str, key: str, value: str, settings_path: Path | None = None) -> None:
    path = settings_path or settings_file_path()
    config = _read_settings(path)

    if not config.has_section(section):
        config.add_section(section)
    config[section][key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as output_file:
            config.write(output_file)
    except OSError as exc:
        raise BorderlessError(f"Failed to write settings to '{path}': {exc}") from exc


def read_profiles(profile_path: Path | None = None) -> dict[str, WindowProfile]:
    path = profile_path or profile_file_path()
    config = _read_bounds_config(path)

    profiles: dict[str, WindowProfile] = {}
    for section, bounds in _parse_bounds_sections(config, "profiles").items():
        try:
            hide_taskbar = config[section].getboolean("hide_taskbar", fallback=False)
        except ValueError:
            log.warning("Ignoring invalid hide_taskbar value in profile '%s'.", section)
            hide_taskbar = False
        profiles[section] = WindowProfile(bounds=bounds, hide_taskbar=hide_taskbar)

    return profiles


def read_presets(preset_path: Path | None = None) -> dict[str, WindowBounds]:
    path = preset_path or preset_file_path()
    return _parse_bounds_sections(_read_bounds_config(path), "presets")


def _read_bounds_config(path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not path.exists():
        return config

    try:
        with path.open("r", encoding="utf-8") as profile_file:
            config.read_file(profile_file)
    except (configparser.Error, OSError) as exc:
        raise BorderlessError(f"Failed to read profiles from '{path}': {exc}") from exc

    return config


def _parse_bounds_sections(config: configparser.ConfigParser, source_name: str) -> dict[str, WindowBounds]:
    bounds_map: dict[str, WindowBounds] = {}
    for section in config.sections():
        try:
            bounds_map[section] = parse_window_bounds(
                config[section].get("x", "0"),
                config[section].get("y", "0"),
                config[section].get("width", "800"),
                config[section].get("height", "600"),
            )
        except BorderlessError as exc:
            log.warning("Skipping invalid %s '%s': %s", source_name, section, exc)

    return bounds_map


def save_window_profile(
    title: str,
    profile: WindowProfile,
    profile_path: Path | None = None,
    original_title: str | None = None,
) -> None:
    normalized_title = title.strip()
    if not normalized_title:
        raise BorderlessError("Profile name cannot be empty.")

    path = profile_path or profile_file_path()
    config = configparser.ConfigParser()

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as profile_file:
                config.read_file(profile_file)
        except (configparser.Error, OSError) as exc:
            raise BorderlessError(f"Failed to read profiles from '{path}': {exc}") from exc

    if original_title and original_title != normalized_title:
        config.remove_section(original_title)

    config.remove_section(normalized_title)
    config.add_section(normalized_title)
    config[normalized_title]["x"] = str(profile.bounds.x)
    config[normalized_title]["y"] = str(profile.bounds.y)
    config[normalized_title]["width"] = str(profile.bounds.width)
    config[normalized_title]["height"] = str(profile.bounds.height)
    config[normalized_title]["hide_taskbar"] = "true" if profile.hide_taskbar else "false"

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as output_file:
            config.write(output_file)
    except OSError as exc:
        raise BorderlessError(f"Failed to write profiles to '{path}': {exc}") from exc


def delete_window_profile(title: str, profile_path: Path | None = None) -> None:
    if not title:
        raise BorderlessError("Please select a window first.")

    path = profile_path or profile_file_path()
    config = configparser.ConfigParser()

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as profile_file:
                config.read_file(profile_file)
        except (configparser.Error, OSError) as exc:
            raise BorderlessError(f"Failed to read profiles from '{path}': {exc}") from exc

    config.remove_section(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as output_file:
            config.write(output_file)
    except OSError as exc:
        raise BorderlessError(f"Failed to write profiles to '{path}': {exc}") from exc


def iter_matching_profile_names(
    profiles: Mapping[str, WindowProfile],
    title: str,
) -> list[str]:
    exact_matches: list[str] = []
    wildcard_matches: list[str] = []

    for profile_name in profiles:
        if title_matches_profile_pattern(profile_name, title):
            if profile_name == title:
                exact_matches.append(profile_name)
            else:
                wildcard_matches.append(profile_name)

    return exact_matches + wildcard_matches


def title_matches_profile_pattern(pattern: str, title: str) -> bool:
    if pattern == title:
        return True
    if "*" not in pattern:
        return False

    normalized_title = title.casefold()
    profile_pattern = re.escape(pattern.casefold()).replace(r"\*", ".*")
    return re.fullmatch(profile_pattern, normalized_title) is not None


def load_profile(
    profiles: Mapping[str, WindowProfile],
    title: str,
) -> WindowProfile | None:
    matching_profile = get_matching_profile_name(profiles, title)
    if matching_profile is None:
        return None

    return profiles[matching_profile]


def get_matching_profile_name(
    profiles: Mapping[str, WindowProfile],
    title: str,
) -> str | None:
    matching_profiles = iter_matching_profile_names(profiles, title)
    if not matching_profiles:
        return None

    return matching_profiles[0]


def get_window_process_name(hwnd: int) -> str:
    try:
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
    except pywintypes.error:
        return ""

    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not process_handle:
        return ""

    try:
        buffer_size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(buffer_size.value)
        if not kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(buffer_size)):
            return ""
    finally:
        kernel32.CloseHandle(process_handle)

    return PureWindowsPath(buffer.value).name


def enumerate_visible_windows() -> dict[str, WindowSnapshot]:
    visible_windows: dict[str, WindowSnapshot] = {}

    def win_enum_handler(hwnd: int, _context: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd)
        if not title or title == WINDOW_TITLE:
            return

        try:
            style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
            exstyle = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            class_name = win32gui.GetClassName(hwnd)
        except pywintypes.error:
            return

        visible_windows[title] = WindowSnapshot(
            hwnd=hwnd,
            title=title,
            style=style,
            exstyle=exstyle,
            class_name=class_name,
            process_name=get_window_process_name(hwnd),
        )

    win32gui.EnumWindows(win_enum_handler, None)
    return visible_windows


def sort_window_titles(
    windows: Mapping[str, WindowSnapshot],
    profiles: Mapping[str, WindowProfile],
) -> list[str]:
    return sorted(
        windows,
        key=lambda title: (not bool(iter_matching_profile_names(profiles, title)), title.casefold()),
    )


def is_valid_hwnd(hwnd: int | None) -> bool:
    if hwnd is None:
        return False

    try:
        return bool(win32gui.IsWindow(hwnd))
    except pywintypes.error:
        return False


def get_window_rect_bounds(hwnd: int | None) -> WindowBounds:
    if not is_valid_hwnd(hwnd):
        raise BorderlessError("Please select a valid window.")

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except pywintypes.error as exc:
        raise BorderlessError("Window not found. Refresh the list and try again.") from exc

    return WindowBounds(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
    )


def get_window_profile(
    title: str,
    hwnd: int | None,
    profiles: Mapping[str, WindowProfile],
) -> WindowProfile:
    profile = load_profile(profiles, title)
    if profile is not None:
        return profile

    return WindowProfile(bounds=get_window_rect_bounds(hwnd))


def move_window(hwnd: int | None, bounds: WindowBounds) -> None:
    if not is_valid_hwnd(hwnd):
        raise BorderlessError("Please select a valid window.")

    if not user32.MoveWindow(hwnd, bounds.x, bounds.y, bounds.width, bounds.height, True):
        raise BorderlessError("Failed to move the selected window.")


def set_window_long_ptr(hwnd: int, index: int, new_long: int) -> int:
    if ctypes.sizeof(ctypes.c_void_p) == 8 and hasattr(user32, "SetWindowLongPtrW"):
        return user32.SetWindowLongPtrW(hwnd, index, new_long)

    return user32.SetWindowLongW(hwnd, index, new_long)


def mark_fullscreen_window(hwnd: int, fullscreen: bool) -> None:
    """Tell the shell to drop the taskbar below `hwnd` while that window is active.

    Uses ITaskbarList2::MarkFullscreenWindow. Unlike HWND_TOPMOST, the window stays in
    the normal z-order band: the taskbar returns above it as soon as another window is
    activated. The mark is held by the shell, so it outlives this process.
    """
    clsid = (ctypes.c_byte * 16).from_buffer_copy(CLSID_TASKBAR_LIST.bytes_le)
    iid = (ctypes.c_byte * 16).from_buffer_copy(IID_ITASKBAR_LIST2.bytes_le)

    init_hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    try:
        taskbar_list = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER, ctypes.byref(iid), ctypes.byref(taskbar_list)
        )
        if hr < 0 or not taskbar_list.value:
            raise BorderlessError(f"Failed to reach the taskbar (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")

        vtable = ctypes.cast(taskbar_list, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        try:
            hr = _HrInitFn(vtable[_HR_INIT_SLOT])(taskbar_list)
            if hr >= 0:
                hr = _MarkFullscreenWindowFn(vtable[_MARK_FULLSCREEN_WINDOW_SLOT])(taskbar_list, hwnd, fullscreen)
        finally:
            _ReleaseFn(vtable[_RELEASE_SLOT])(taskbar_list)

        if hr < 0:
            raise BorderlessError(f"Failed to update hide taskbar mode (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")
    finally:
        # RPC_E_CHANGED_MODE (negative) means COM was already set up differently on this thread.
        if init_hr >= 0:
            ole32.CoUninitialize()


def apply_borderless_window(hwnd: int | None, bounds: WindowBounds, hide_taskbar: bool = False) -> None:
    if hwnd is None or not is_valid_hwnd(hwnd):
        raise BorderlessError("Please select a valid window.")

    get_window_rect_bounds(hwnd)

    set_window_long_ptr(hwnd, win32con.GWL_STYLE, win32con.WS_VISIBLE | win32con.WS_CLIPCHILDREN)
    set_window_long_ptr(hwnd, win32con.GWL_EXSTYLE, 0)

    move_window(hwnd, bounds)

    win32gui.SetWindowPos(
        hwnd,
        None,
        bounds.x,
        bounds.y,
        bounds.width + 1,
        bounds.height + 1,
        win32con.SWP_FRAMECHANGED | win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER,
    )

    # Always sync the mark so turning the setting off also releases previously marked windows.
    mark_fullscreen_window(hwnd, hide_taskbar)


def find_auto_apply_windows(
    profiles: Mapping[str, WindowProfile],
    windows: Mapping[str, WindowSnapshot],
    exclusions: AutoApplyExclusions,
) -> list[WindowSnapshot]:
    return [
        window
        for title, window in windows.items()
        if load_profile(profiles, title) is not None and not exclusions.matches(window)
    ]


def _bounds_within_tolerance(current: WindowBounds, target: WindowBounds, tolerance_px: int) -> bool:
    return (
        abs(current.x - target.x) <= tolerance_px
        and abs(current.y - target.y) <= tolerance_px
        and abs(current.width - target.width) <= tolerance_px
        and abs(current.height - target.height) <= tolerance_px
    )


def run_watchdog_pass(
    profiles: Mapping[str, WindowProfile] | None = None,
    tolerance_px: int = DEFAULT_WATCHDOG_TOLERANCE_PX,
    exclusions: AutoApplyExclusions | None = None,
) -> list[str]:
    """Reapply saved profiles to auto-apply-eligible windows whose bounds drifted from them.

    Polled from the TUI when "Watchdog Mode" is enabled, so a window that changes
    resolution (e.g. a game switching modes) or gets moved off its saved position
    gets its template reapplied automatically.

    `tolerance_px` absorbs the 1px repaint nudge that apply_borderless_window's
    SetWindowPos call applies on top of the saved bounds (see below) plus any other
    minor drift the user wants to ignore, so watchdog doesn't reapply every poll.
    """
    active_profiles = profiles if profiles is not None else read_profiles()
    active_exclusions = exclusions if exclusions is not None else read_auto_apply_exclusions()
    windows = enumerate_visible_windows()

    reapplied_titles: list[str] = []
    for window in find_auto_apply_windows(active_profiles, windows, active_exclusions):
        profile = load_profile(active_profiles, window.title)
        if profile is None:
            continue

        try:
            current_bounds = get_window_rect_bounds(window.hwnd)
        except BorderlessError:
            continue

        if _bounds_within_tolerance(current_bounds, profile.bounds, tolerance_px):
            continue

        try:
            apply_borderless_window(window.hwnd, profile.bounds, profile.hide_taskbar)
        except BorderlessError as exc:
            log.warning("Watchdog failed to reapply profile for '%s': %s", window.title, exc)
            continue

        log.info("Watchdog reapplied profile for '%s' after resolution change.", window.title)
        reapplied_titles.append(window.title)

    return reapplied_titles


def try_auto_borderless(preferred_title: str | None = None) -> bool:
    profiles = read_profiles()
    windows = enumerate_visible_windows()

    if preferred_title:
        needle = preferred_title.casefold()
        for title, window in windows.items():
            if needle in title.casefold():
                log.info("Applying settings to target title: '%s'", title)
                profile = get_window_profile(title, window.hwnd, profiles)
                apply_borderless_window(window.hwnd, profile.bounds, profile.hide_taskbar)
                return True

        log.warning("No window matching target title: '%s' found.", preferred_title)

    matched_windows = find_auto_apply_windows(profiles, windows, read_auto_apply_exclusions())

    if len(matched_windows) > 1:
        log.info("Multiple profile matches found; refusing to auto-apply. Matches:")
        for window in matched_windows:
            log.info("  - %s", window.title)
        return False

    if len(matched_windows) == 1:
        selected_window = matched_windows[0]
        log.info("Found the only matching profile: '%s', applying settings", selected_window.title)
        profile = get_window_profile(selected_window.title, selected_window.hwnd, profiles)
        apply_borderless_window(selected_window.hwnd, profile.bounds, profile.hide_taskbar)
        return True

    log.info("No matching profiles found to auto-apply.")
    return False
