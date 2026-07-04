from __future__ import annotations

import configparser
import ctypes
import logging
import re
import sys
from ctypes import WinDLL
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pywintypes
import win32api
import win32con
import win32gui


PROFILE_FILE = "profiles.ini"
PRESET_FILE = "presets.ini"
WINDOW_TITLE = "Borderless Window Utility"
user32: WinDLL = ctypes.windll.user32

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
class WindowSnapshot:
    hwnd: int
    title: str
    style: int
    exstyle: int
    class_name: str = ""


BROWSER_CLASS_PREFIXES = ("chrome", "mozilla", "edge")


def profile_file_path(script_path: str | Path | None = None) -> Path:
    argv0 = Path(script_path) if script_path is not None else Path(sys.argv[0])
    return argv0.parent.joinpath(PROFILE_FILE)


def preset_file_path(script_path: str | Path | None = None) -> Path:
    argv0 = Path(script_path) if script_path is not None else Path(sys.argv[0])
    return argv0.parent.joinpath(PRESET_FILE)


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


def read_profiles(profile_path: Path | None = None) -> dict[str, WindowBounds]:
    path = profile_path or profile_file_path()
    return _read_bounds_map(path, "profiles")


def read_presets(preset_path: Path | None = None) -> dict[str, WindowBounds]:
    path = preset_path or preset_file_path()
    return _read_bounds_map(path, "presets")


def _read_bounds_map(path: Path, source_name: str) -> dict[str, WindowBounds]:
    if not path.exists():
        return {}

    config = configparser.ConfigParser()
    try:
        with path.open("r", encoding="utf-8") as profile_file:
            config.read_file(profile_file)
    except (configparser.Error, OSError) as exc:
        raise BorderlessError(f"Failed to read profiles from '{path}': {exc}") from exc

    profiles: dict[str, WindowBounds] = {}
    for section in config.sections():
        try:
            profiles[section] = parse_window_bounds(
                config[section].get("x", "0"),
                config[section].get("y", "0"),
                config[section].get("width", "800"),
                config[section].get("height", "600"),
            )
        except BorderlessError as exc:
            log.warning("Skipping invalid %s '%s': %s", source_name, section, exc)

    return profiles


def save_window_profile(
    title: str,
    bounds: WindowBounds,
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
    config[normalized_title]["x"] = str(bounds.x)
    config[normalized_title]["y"] = str(bounds.y)
    config[normalized_title]["width"] = str(bounds.width)
    config[normalized_title]["height"] = str(bounds.height)

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
    profiles: Mapping[str, WindowBounds],
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
    profiles: Mapping[str, WindowBounds],
    title: str,
) -> WindowBounds | None:
    matching_profile = get_matching_profile_name(profiles, title)
    if matching_profile is None:
        return None

    return profiles[matching_profile]


def get_matching_profile_name(
    profiles: Mapping[str, WindowBounds],
    title: str,
) -> str | None:
    matching_profiles = iter_matching_profile_names(profiles, title)
    if not matching_profiles:
        return None

    return matching_profiles[0]


def _is_browser_window(window: WindowSnapshot) -> bool:
    class_lower = window.class_name.lower()
    return any(class_lower.startswith(prefix) for prefix in BROWSER_CLASS_PREFIXES)


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
        )

    win32gui.EnumWindows(win_enum_handler, None)
    return visible_windows


def sort_window_titles(
    windows: Mapping[str, WindowSnapshot],
    profiles: Mapping[str, WindowBounds],
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


def get_window_bounds(
    title: str,
    hwnd: int | None,
    profiles: Mapping[str, WindowBounds],
) -> WindowBounds:
    profile = load_profile(profiles, title)
    if profile is not None:
        return profile

    return get_window_rect_bounds(hwnd)


def move_window(hwnd: int | None, bounds: WindowBounds) -> None:
    if not is_valid_hwnd(hwnd):
        raise BorderlessError("Please select a valid window.")

    if not user32.MoveWindow(hwnd, bounds.x, bounds.y, bounds.width, bounds.height, True):
        raise BorderlessError("Failed to move the selected window.")


def set_window_long_ptr(hwnd: int, index: int, new_long: int) -> int:
    if ctypes.sizeof(ctypes.c_void_p) == 8 and hasattr(user32, "SetWindowLongPtrW"):
        return user32.SetWindowLongPtrW(hwnd, index, new_long)

    return user32.SetWindowLongW(hwnd, index, new_long)


def apply_borderless_window(hwnd: int | None, bounds: WindowBounds) -> None:
    if not is_valid_hwnd(hwnd):
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


def try_auto_borderless(preferred_title: str | None = None) -> bool:
    profiles = read_profiles()
    windows = enumerate_visible_windows()

    if preferred_title:
        needle = preferred_title.casefold()
        for title, window in windows.items():
            if needle in title.casefold():
                log.info("Applying settings to target title: '%s'", title)
                bounds = get_window_bounds(title, window.hwnd, profiles)
                apply_borderless_window(window.hwnd, bounds)
                return True

        log.warning("No window matching target title: '%s' found.", preferred_title)

    matched_windows = [
        window
        for title, window in windows.items()
        if load_profile(profiles, title) is not None
        and not _is_browser_window(window)
    ]

    if len(matched_windows) > 1:
        log.info("Multiple profile matches found; refusing to auto-apply. Matches:")
        for window in matched_windows:
            log.info("  - %s", window.title)
        return False

    if len(matched_windows) == 1:
        selected_window = matched_windows[0]
        log.info("Found the only matching profile: '%s', applying settings", selected_window.title)
        bounds = get_window_bounds(selected_window.title, selected_window.hwnd, profiles)
        apply_borderless_window(selected_window.hwnd, bounds)
        return True

    log.info("No matching profiles found to auto-apply.")
    return False
