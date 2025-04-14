import sys
from pathlib import Path

import win32gui
import ctypes
import win32con
import win32api
import FreeSimpleGUI as sg
import configparser


PROFILE_FILE = "profiles.ini"


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
SAVE_PROFILE_EVENT = "Save"
LOAD_PROFILE_EVENT = "Load"
COMBO_KEY_EVENT = "combo"


# Global Variables
user32 = ctypes.windll.user32
PROFILES = {}
ALL_VISIBLE_WINDOWS = {}
VISIBLE_WINDOWS_TITLES_LIST = []
X_POS = 0
Y_POS = 0
H_RES = 0
V_RES = 0
WINDOW: sg.Window | None = None


def profile_file_path() -> Path:
    script_path = Path(sys.argv[0])
    if script_path is not None:
        return Path(script_path.parent).joinpath(PROFILE_FILE)
    else:
        return Path(PROFILE_FILE)


def read_profiles():
    global PROFILES

    config = configparser.ConfigParser()
    config.read(profile_file_path())

    for section in config.sections():
        PROFILES[section] = {
            X_KEY: config[section][X_KEY],
            Y_KEY: config[section][Y_KEY],
            WIDTH_KEY: config[section][WIDTH_KEY],
            HEIGHT_KEY: config[section][HEIGHT_KEY],
        }

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


def load_profile(profiles, title):
    if title not in profiles:
        return None

    return PROFILES[title]


def refresh_all_visible_windows():
    global ALL_VISIBLE_WINDOWS, VISIBLE_WINDOWS_TITLES_LIST, WINDOW
    ALL_VISIBLE_WINDOWS = {}
    win32gui.EnumWindows(win_enum_handler, None)
    VISIBLE_WINDOWS_TITLES_LIST = list(ALL_VISIBLE_WINDOWS.keys())
    VISIBLE_WINDOWS_TITLES_LIST.sort(key=lambda x: x in PROFILES, reverse=True)
    if WINDOW is not None:
        WINDOW[COMBO_KEY_EVENT].update(values=VISIBLE_WINDOWS_TITLES_LIST)


def window_size_update(hwnd, *, from_ui=False):
    global X_POS, Y_POS, H_RES, V_RES

    if from_ui:
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
    except:
        return

    WINDOW[X_KEY].update(X_POS)
    WINDOW[Y_KEY].update(Y_POS)
    WINDOW[H_RES_KEY].update(H_RES)
    WINDOW[V_RES_KEY].update(V_RES)


def win_enum_handler(hwnd, ctx):
    global ALL_VISIBLE_WINDOWS

    if win32gui.IsWindowVisible(hwnd):
        n = win32gui.GetWindowText(hwnd)
        s = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
        x = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if n:
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
            sg.Button(SAVE_PROFILE_EVENT, size=9),
            sg.Button(LOAD_PROFILE_EVENT, size=9),
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
            sg.Button(REVERT_CHANGES_EVENT, size=16),
        ],
        [sg.HorizontalSeparator()],
        [
            sg.Push(),
            sg.Exit(key=EXIT_EVENT),
        ],
    ]
    WINDOW = sg.Window("Borderless Window Utility", layout, finalize=True)


def update_borderless_window(hwnd):
    global X_POS, Y_POS, H_RES, V_RES, ALL_VISIBLE_WINDOWS

    try:
        win32gui.GetWindowRect(hwnd)
    except:
        print("Window not found, reloading list")
        refresh_all_visible_windows()
    else:
        user32.SetWindowLongW(hwnd, win32con.GWL_STYLE, win32con.WS_VISIBLE | win32con.WS_CLIPCHILDREN)
        user32.SetWindowLongW(hwnd, win32con.GWL_EXSTYLE, 0)
        user32.MoveWindow(hwnd, X_POS, Y_POS, H_RES, V_RES, True)
        V_RES = V_RES + 1
        H_RES = H_RES + 1
        win32gui.SetWindowPos(
            hwnd,
            None,
            X_POS,
            Y_POS,
            H_RES,
            V_RES,
            win32con.SWP_FRAMECHANGED | win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER,
        )
        window_size_update(hwnd)


def auto_borderless(hwnd):
    title = win32gui.GetWindowText(hwnd)
    if title in PROFILES:
        print("Profile found, applying settings")
        window_size_update(hwnd)
    update_borderless_window(hwnd)


def try_auto_borderless():
    global ALL_VISIBLE_WINDOWS, PROFILES

    found_profile = None
    hwnd = None

    for title, window in ALL_VISIBLE_WINDOWS.items():
        if title in PROFILES:
            if found_profile is None:
                found_profile = title
                hwnd = window[HWND_KEY]
            else:
                return

    if found_profile is not None and hwnd is not None:
        print(f"Found the only one profile: '{found_profile}', applying settings")
        WINDOW[COMBO_KEY_EVENT].update(value=found_profile)
        auto_borderless(hwnd)


def main():
    global X_POS, Y_POS, H_RES, V_RES, ALL_VISIBLE_WINDOWS

    read_profiles()
    refresh_all_visible_windows()
    create_window()

    try_auto_borderless()

    while True:
        event, values = WINDOW.read()

        if event == sg.WIN_CLOSED or event == EXIT_EVENT:
            break

        hwnd = ALL_VISIBLE_WINDOWS.get(values.get(COMBO_KEY_EVENT, None), {}).get(HWND_KEY, None)

        if event == BORDERLESS_WINDOW_EVENT:
            update_borderless_window(hwnd)

        if event == REVERT_CHANGES_EVENT:
            try:
                win32gui.GetWindowRect(hwnd)
            except:
                print("Window not found, reloading list")
                refresh_all_visible_windows()
            else:
                style = ALL_VISIBLE_WINDOWS.get(values[COMBO_KEY_EVENT], {}).get("STYLE")
                exstyle = ALL_VISIBLE_WINDOWS.get(values[COMBO_KEY_EVENT], {}).get("EXSTYLE")
                rect = win32gui.GetWindowRect(hwnd)
                user32.SetWindowLongW(hwnd, win32con.GWL_STYLE, style)
                user32.SetWindowLongW(hwnd, win32con.GWL_EXSTYLE, exstyle)
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
            except:
                print("Window not found, reloading list")
                refresh_all_visible_windows()
            else:
                window_size_update(hwnd, from_ui=True)
                user32.MoveWindow(hwnd, X_POS, Y_POS, H_RES, V_RES, True)

        if event == REFRESH_EVENT:
            refresh_all_visible_windows()

        if event == COMBO_KEY_EVENT:
            try:
                win32gui.GetWindowRect(hwnd)
            except:
                print("Window not found, reloading list")
                refresh_all_visible_windows()
            else:
                auto_borderless(hwnd)

        if event == SAVE_PROFILE_EVENT:
            save_window_profile(hwnd)

        if event == LOAD_PROFILE_EVENT:
            window_size_update(hwnd)


if __name__ == "__main__":
    main()
    WINDOW.close()
