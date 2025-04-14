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
RESIZE_EVENT = "resize"
BORDERLESS_WINDOW_EVENT = "Borderless Window"
REVERT_CHANGES_EVENT = "Revert Changes"
REFRESH_EVENT = "Refresh"
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


def read_profiles():
    global PROFILES

    config = configparser.ConfigParser()
    config.read(PROFILE_FILE)

    for section in config.sections():
        print(f"Found profile: {section}")
        PROFILES[section] = {
            X_KEY: config[section][X_KEY],
            Y_KEY: config[section][Y_KEY],
            WIDTH_KEY: config[section][WIDTH_KEY],
            HEIGHT_KEY: config[section][HEIGHT_KEY],
        }

    return PROFILES


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
        WINDOW.Element(COMBO_KEY_EVENT).update(values=VISIBLE_WINDOWS_TITLES_LIST)


def window_size_update(hwnd):
    global X_POS, Y_POS, H_RES, V_RES

    window_rect = win32gui.GetWindowRect(hwnd)
    title = win32gui.GetWindowText(hwnd)
    profiles = read_profiles()
    profile = load_profile(profiles, title)
    if profile is not None:
        WINDOW.Element(X_KEY).update(profile[X_KEY])
        X_POS = int(profile[X_KEY])
        WINDOW.Element(Y_KEY).update(profile[Y_KEY])
        Y_POS = int(profile[Y_KEY])
        WINDOW.Element(H_RES_KEY).update(profile[WIDTH_KEY])
        H_RES = int(profile[WIDTH_KEY])
        WINDOW.Element(V_RES_KEY).update(profile[HEIGHT_KEY])
        V_RES = int(profile[HEIGHT_KEY])
    else:
        WINDOW.Element(X_KEY).update(int(window_rect[0]))
        X_POS = int(window_rect[0])
        WINDOW.Element(Y_KEY).update(int(window_rect[1]))
        Y_POS = int(window_rect[1])
        WINDOW.Element(H_RES_KEY).update(int(window_rect[2] - window_rect[0]))
        H_RES = int(window_rect[2] - window_rect[0])
        WINDOW.Element(V_RES_KEY).update(int(window_rect[3] - window_rect[1]))
        V_RES = int(window_rect[3] - window_rect[1])


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
        [sg.Text("Window Selection: ")],
        [
            sg.Combo(
                VISIBLE_WINDOWS_TITLES_LIST,
                enable_events=True,
                key=COMBO_KEY_EVENT,
                size=(100, 1),
                auto_size_text=False,
            ),
            sg.Button(REFRESH_EVENT),
        ],
        [
            sg.Text("X Pos:"),
            sg.InputText("0", size=(7, 7), key=X_KEY),
            sg.Text("Y Pos:"),
            sg.InputText("0", size=(7, 7), key=Y_KEY),
        ],
        [
            sg.Text("H Res:"),
            sg.InputText("2560", size=(7, 7), key=H_RES_KEY),
            sg.Text("V Res:"),
            sg.InputText("1440", size=(7, 7), key=V_RES_KEY),
        ],
        [
            sg.Button(BORDERLESS_WINDOW_EVENT),
            sg.Button(REVERT_CHANGES_EVENT),
            sg.Button("Resize/Position", key=RESIZE_EVENT),
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
        WINDOW.Element(COMBO_KEY_EVENT).update(value=found_profile)
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
                X_POS = int(values[X_KEY])
                Y_POS = int(values[Y_KEY])
                H_RES = int(values[H_RES_KEY])
                V_RES = int(values[V_RES_KEY])
                user32.MoveWindow(hwnd, X_POS, Y_POS, H_RES, V_RES, True)
                window_size_update(hwnd)

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


if __name__ == "__main__":
    main()
    WINDOW.close()
