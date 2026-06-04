import argparse
import configparser
import ctypes
import logging
import re
import sys
from ctypes import WinDLL
from pathlib import Path

import FreeSimpleGUI as sg
import win32api
import win32con
import win32gui

# Basic logging setup
logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")
log = logging.getLogger(__name__)


PROFILE_FILE = "profiles.ini"


# UI entries
WINDOW_TITLE = "Borderless Window Utility"

# Generic Keys
X_KEY = "x"
Y_KEY = "y"
WIDTH_KEY = "width"
HEIGHT_KEY = "height"
H_RES_KEY = "HRes"
V_RES_KEY = "VRes"
HWND_KEY = "hwnd"

# Event Keys
EXIT_EVENT = "exit"
RESIZE_EVENT = "Apply"
BORDERLESS_WINDOW_EVENT = "Borderless Window"
REVERT_CHANGES_EVENT = "Normal Window"
REFRESH_EVENT = "Refresh"
SAVE_PRESET_EVENT = "Save"
LOAD_PRESET_EVENT = "Load"
DELETE_PRESET_EVENT = "Delete"
COMBO_KEY_EVENT = "combo"


# Global Variables
user32: WinDLL = ctypes.windll.user32
PROFILES = {}
ALL_VISIBLE_WINDOWS = {}
VISIBLE_WINDOWS_TITLES_LIST = []
X_POS = 0
Y_POS = 0
H_RES = 0
V_RES = 0
WINDOW: sg.Window | None = None


def get_configs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument(
        "-a",
        "--apply-and-exit",
        action="store_true",
        default=False,
        dest="apply_and_exit",
        help="Automatically apply borderless window and exit (no UI)",
    )
    return parser.parse_args()


def profile_file_path() -> Path:
    script_path = Path(sys.argv[0])
    if script_path is not None:
        return Path(script_path.parent).joinpath(PROFILE_FILE)
    else:
        return Path(PROFILE_FILE)


def read_profiles():
    global PROFILES

    PROFILES = {}
    config = configparser.ConfigParser()
    try:
        config.read(profile_file_path())
    except Exception as e:
        log.warning(f"Failed to read profiles: {e}")
        return PROFILES

    for section in config.sections():
        try:
            PROFILES[section] = {
                X_KEY: config[section].get(X_KEY, fallback=config[section].get(X_KEY, "0")),
                Y_KEY: config[section].get(Y_KEY, fallback=config[section].get(Y_KEY, "0")),
                WIDTH_KEY: config[section].get(WIDTH_KEY, fallback=config[section].get(WIDTH_KEY, "800")),
                HEIGHT_KEY: config[section].get(HEIGHT_KEY, fallback=config[section].get(HEIGHT_KEY, "600")),
            }
        except Exception as e:
            log.warning(f"Invalid profile section '{section}': {e}")

    return PROFILES


def save_window_profile(hwnd):
    global X_KEY, Y_KEY, H_RES_KEY, V_RES_KEY, X_POS, Y_POS, H_RES, V_RES, WINDOW

    window_size_update(hwnd, from_ui=True)

    title = win32gui.GetWindowText(hwnd)
    if not title:
        sg.popup_error("Please select a window first.")
        return

    profile_path = profile_file_path()

    config = configparser.ConfigParser()
    config.read(profile_path)

    output_config = Path(profile_path)
    profile_path.parent.mkdir(exist_ok=True, parents=True)
    with output_config.open("w") as output_file:
        config.remove_section(title)
        config.add_section(title)
        config[title][X_KEY] = str(X_POS)
        config[title][Y_KEY] = str(Y_POS)
        config[title][WIDTH_KEY] = str(H_RES)
        config[title][HEIGHT_KEY] = str(V_RES)

        config.write(output_file)


def delete_window_profile(hwnd):
    title = win32gui.GetWindowText(hwnd)
    if not title:
        sg.popup_error("Please select a window first.")
        return

    profile_path = profile_file_path()

    config = configparser.ConfigParser()
    config.read(profile_path)

    output_config = Path(profile_path)
    profile_path.parent.mkdir(exist_ok=True, parents=True)
    with output_config.open("w") as output_file:
        config.remove_section(title)

        config.write(output_file)


def iter_matching_profile_names(profiles, title):
    exact_matches = []
    wildcard_matches = []
    normalized_title = title.casefold()

    for profile_name in profiles:
        if profile_name == title:
            exact_matches.append(profile_name)
        elif "*" in profile_name:
            profile_pattern = re.escape(profile_name.casefold()).replace(r"\*", ".*")
            if re.fullmatch(profile_pattern, normalized_title):
                wildcard_matches.append(profile_name)

    return exact_matches + wildcard_matches


def load_profile(profiles, title):
    matching_profiles = iter_matching_profile_names(profiles, title)
    if not matching_profiles:
        return None

    return profiles[matching_profiles[0]]


def refresh_all_visible_windows():
    global ALL_VISIBLE_WINDOWS, VISIBLE_WINDOWS_TITLES_LIST, WINDOW
    ALL_VISIBLE_WINDOWS = {}
    win32gui.EnumWindows(win_enum_handler, None)
    VISIBLE_WINDOWS_TITLES_LIST = list(ALL_VISIBLE_WINDOWS.keys())
    VISIBLE_WINDOWS_TITLES_LIST.sort(key=lambda x: bool(iter_matching_profile_names(PROFILES, x)), reverse=True)
    if WINDOW is not None:
        WINDOW[COMBO_KEY_EVENT].update(values=VISIBLE_WINDOWS_TITLES_LIST)


def window_size_update(hwnd, *, from_ui=False):
    global X_POS, Y_POS, H_RES, V_RES, WINDOW

    x_pos = 256
    y_pos = 256
    h_res = 256
    v_res = 256

    if from_ui:
        if WINDOW is not None:
            x_pos = WINDOW[X_KEY].get()
            y_pos = WINDOW[Y_KEY].get()
            h_res = WINDOW[H_RES_KEY].get()
            v_res = WINDOW[V_RES_KEY].get()
    else:
        title = win32gui.GetWindowText(hwnd)
        profiles = read_profiles()
        profile = load_profile(profiles, title)
        if profile is not None:
            x_pos = profile[X_KEY]
            y_pos = profile[Y_KEY]
            h_res = profile[WIDTH_KEY]
            v_res = profile[HEIGHT_KEY]
        else:
            window_rect = win32gui.GetWindowRect(hwnd)
            x_pos = window_rect[0]
            y_pos = window_rect[1]
            h_res = window_rect[2] - window_rect[0]
            v_res = window_rect[3] - window_rect[1]

    try:
        X_POS = int(x_pos)
        Y_POS = int(y_pos)
        H_RES = int(h_res)
        V_RES = int(v_res)
    except ValueError:
        return

    if WINDOW is not None:
        WINDOW[X_KEY].update(X_POS)
        WINDOW[Y_KEY].update(Y_POS)
        WINDOW[H_RES_KEY].update(H_RES)
        WINDOW[V_RES_KEY].update(V_RES)


def win_enum_handler(hwnd, ctx):
    global ALL_VISIBLE_WINDOWS

    if win32gui.IsWindowVisible(hwnd):
        n = win32gui.GetWindowText(hwnd)
        # Exclude this utility's own window to avoid accidental changes
        if n and n != WINDOW_TITLE:
            s = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
            x = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ALL_VISIBLE_WINDOWS.update({n: {HWND_KEY: hwnd, "STYLE": s, "EXSTYLE": x}})


def create_window():
    global WINDOW
    sg.theme("DarkGrey11")
    layout = [
        [sg.HorizontalSeparator(), sg.Text("Window", font="bold"), sg.HorizontalSeparator()],
        [
            sg.Combo(
                VISIBLE_WINDOWS_TITLES_LIST,
                enable_events=True,
                key=COMBO_KEY_EVENT,
                size=50,
                auto_size_text=False,
            ),
            sg.Button(REFRESH_EVENT),
        ],
        [sg.HorizontalSeparator(), sg.Text("Positioning", font="bold"), sg.HorizontalSeparator()],
        [
            sg.Text("Preset:", size=7),
            sg.Button(SAVE_PRESET_EVENT, size=9),
            sg.Button(LOAD_PRESET_EVENT, size=9),
            sg.HorizontalSeparator(),
            sg.Button(DELETE_PRESET_EVENT, size=9),
        ],
        [
            sg.Text("Position:", size=7),
            sg.Text("X", size=1),
            sg.InputText("0", size=7, key=X_KEY),
            sg.Text("Y", size=1),
            sg.InputText("0", size=7, key=Y_KEY),
        ],
        [
            sg.Text("Size:", size=7),
            sg.Text("H", 1),
            sg.InputText("2560", size=7, key=H_RES_KEY),
            sg.Text("V", 1),
            sg.InputText("1440", size=7, key=V_RES_KEY),
        ],
        [
            sg.Text("", size=7),
            sg.Button(RESIZE_EVENT, size=9),
        ],
        [sg.HorizontalSeparator(), sg.Text("Style", font="bold"), sg.HorizontalSeparator()],
        [
            sg.Button(BORDERLESS_WINDOW_EVENT, size=16),
            # TODO: It's not working on Windows 11
            # sg.Button(REVERT_CHANGES_EVENT, size=16),
        ],
        [sg.HorizontalSeparator()],
        [
            sg.Push(),
            sg.Exit(key=EXIT_EVENT),
        ],
    ]
    WINDOW = sg.Window(WINDOW_TITLE, layout, finalize=True)


def set_window_long_ptr(hwnd, index, new_long):
    # Use SetWindowLongPtrW on 64-bit Python if available; fallback to SetWindowLongW
    try:
        if ctypes.sizeof(ctypes.c_void_p) == 8 and hasattr(user32, "SetWindowLongPtrW"):
            return user32.SetWindowLongPtrW(hwnd, index, new_long)
        else:
            return user32.SetWindowLongW(hwnd, index, new_long)
    except Exception:
        # As a last resort, try SetWindowLongW
        return user32.SetWindowLongW(hwnd, index, new_long)


def is_valid_hwnd(hwnd) -> bool:
    try:
        return hwnd is not None and win32gui.IsWindow(hwnd)
    except Exception:
        return False


def update_borderless_window(hwnd):
    global X_POS, Y_POS, H_RES, V_RES, ALL_VISIBLE_WINDOWS

    if not is_valid_hwnd(hwnd):
        log.warning("Please select a valid window.")
        return

    try:
        win32gui.GetWindowRect(hwnd)
    except Exception:
        log.info("Window not found, reloading list")
        refresh_all_visible_windows()
        return

    # Apply borderless styles; keep the window visible
    set_window_long_ptr(hwnd, win32con.GWL_STYLE, win32con.WS_VISIBLE | win32con.WS_CLIPCHILDREN)
    set_window_long_ptr(hwnd, win32con.GWL_EXSTYLE, 0)

    # Move to requested size/position
    user32.MoveWindow(hwnd, X_POS, Y_POS, H_RES, V_RES, True)

    # Nudge size by +1 only for the frame change redraw, without altering globals
    w_temp = H_RES + 1
    h_temp = V_RES + 1
    win32gui.SetWindowPos(
        hwnd,
        None,
        X_POS,
        Y_POS,
        w_temp,
        h_temp,
        win32con.SWP_FRAMECHANGED | win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER,
    )

    # Refresh the UI fields to the actual final rect/profile
    window_size_update(hwnd)


def auto_borderless(hwnd):
    title = win32gui.GetWindowText(hwnd)
    if load_profile(PROFILES, title) is not None:
        log.info("Profile found, applying settings")
        window_size_update(hwnd)
    update_borderless_window(hwnd)


def try_auto_borderless(preferred_title: str | None = None) -> bool:
    global ALL_VISIBLE_WINDOWS, PROFILES, WINDOW

    # If a preferred title is given, try to find it first (case-insensitive substring match)
    if preferred_title:
        needle = preferred_title.lower()
        for title, window in ALL_VISIBLE_WINDOWS.items():
            if needle in title.lower():
                if WINDOW is not None:
                    WINDOW[COMBO_KEY_EVENT].update(value=title)
                log.info(f"Applying settings to target title: '{title}'")
                auto_borderless(window[HWND_KEY])
                return True
        log.warning(f"No window matching target title: '{preferred_title}' found.")
        # fall through to profile-based selection

    found_profile = None
    hwnd = None

    for title, window in ALL_VISIBLE_WINDOWS.items():
        if load_profile(PROFILES, title) is not None:
            if found_profile is None:
                found_profile = title
                hwnd = window[HWND_KEY]
            else:
                log.info("Multiple profile matches found; refusing to auto-apply.")
                return False

    if None not in (found_profile, hwnd):
        log.info(f"Found the only one profile: '{found_profile}', applying settings")
        if WINDOW is not None:
            WINDOW[COMBO_KEY_EVENT].update(value=found_profile)
        auto_borderless(hwnd)
        return True

    log.info("No matching profiles found to auto-apply.")
    return False


def window_event_loop():
    global X_POS, Y_POS, H_RES, V_RES, ALL_VISIBLE_WINDOWS

    event, values = WINDOW.read()

    if event == sg.WIN_CLOSED or event == EXIT_EVENT:
        raise KeyboardInterrupt

    hwnd: int | None = ALL_VISIBLE_WINDOWS.get(values.get(COMBO_KEY_EVENT, None), {}).get(HWND_KEY, None)

    if event == BORDERLESS_WINDOW_EVENT:
        update_borderless_window(hwnd)

    if event == REVERT_CHANGES_EVENT:
        try:
            win32gui.GetWindowRect(hwnd)
        except Exception:
            log.info("Window not found, reloading list")
            refresh_all_visible_windows()
        else:
            style = ALL_VISIBLE_WINDOWS.get(values.get(COMBO_KEY_EVENT), {}).get("STYLE")
            exstyle = ALL_VISIBLE_WINDOWS.get(values.get(COMBO_KEY_EVENT), {}).get("EXSTYLE")
            # Restore original styles
            set_window_long_ptr(hwnd, win32con.GWL_STYLE, style)
            set_window_long_ptr(hwnd, win32con.GWL_EXSTYLE, exstyle)
            win32gui.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                win32con.SWP_FRAMECHANGED
                | win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER
                | win32con.SWP_NOOWNERZORDER,
            )
            window_size_update(hwnd)

    if event == RESIZE_EVENT:
        try:
            win32gui.GetWindowRect(hwnd)
        except Exception:
            log.info("Window not found, reloading list")
            refresh_all_visible_windows()
        else:
            window_size_update(hwnd, from_ui=True)
            user32.MoveWindow(hwnd, X_POS, Y_POS, H_RES, V_RES, True)

    if event == REFRESH_EVENT:
        refresh_all_visible_windows()

    if event == COMBO_KEY_EVENT:
        try:
            win32gui.GetWindowRect(hwnd)
        except Exception:
            log.info("Window not found, reloading list")
            refresh_all_visible_windows()
        else:
            window_size_update(hwnd)

    if event == SAVE_PRESET_EVENT:
        save_window_profile(hwnd)

    if event == LOAD_PRESET_EVENT:
        window_size_update(hwnd)

    if event == DELETE_PRESET_EVENT:
        delete_window_profile(hwnd)


def main():
    args = get_configs()

    read_profiles()
    refresh_all_visible_windows()

    if args.apply_and_exit:
        # In CLI mode, don't launch UI; apply and exit with status code
        ok = try_auto_borderless()
        sys.exit(0 if ok else 1)

    # GUI mode
    create_window()

    while True:
        try:
            window_event_loop()
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
    if WINDOW is not None:
        WINDOW.close()
