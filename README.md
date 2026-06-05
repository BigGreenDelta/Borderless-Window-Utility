# Borderless-Window-Utility

Modifies window style to force most applications into a borderless windowed mode.  

# Usage

## Just download
[![Release Build](https://github.com/BigGreenDelta/Borderless-Window-Utility/actions/workflows/python-build-publish.yml/badge.svg)](https://github.com/BigGreenDelta/Borderless-Window-Utility/actions/workflows/python-build-publish.yml)

Download the executables [from the latest releases page](https://github.com/BigGreenDelta/Borderless-Window-Utility/releases/latest):

- `Borderless-Window-Utility.exe` launches the interactive Textual terminal UI.
- `Borderless-Window-Utility-Headless.exe` runs silent automation flows without opening the TUI.

### Command-line (headless) usage
You can run the tool without opening the UI to apply borderless mode automatically:

- Apply to the only window that matches a saved profile and exit:
  `Borderless-Window-Utility-Headless.exe`
  - Returns exit code 0 on success, 1 if no single match is found.

- The interactive executable also supports:
  `Borderless-Window-Utility.exe --apply-and-exit`
  - This uses the same logic, but because the interactive app is console-hosted it will run in a console window.


## Using the provided batch files

The repository includes Windows batch files to simplify setup, running, and building.

- One-time setup (installs uv):
  - Double-click `setup_once.bat`.

- Run headless (apply and exit):
  - Double-click `run-apply-and-exit.bat`.
  - Returns exit code 0 on success, 1 if no single match is found.
  - The batch file launches an inline PowerShell command that runs `main_headless.py` with `uv run python ...` and pauses only when the command fails so any error output stays visible.

- Build the executable from source:
  - Double-click `tools\\build.bat`.
  - Output will be in the `.dist` directory.

- Run the full Textual UI:
  - Double-click `run.bat`.
  - `run.bat` opens a fresh PowerShell console window and runs the launcher logic inline from the batch file. It starts `uv run python main.py` and pauses only when the command fails so the console output remains visible.
  - Alternatively, from a terminal:
    - `uv sync`
    - `uv run borderless-window-utility`

The Textual UI shows a filterable list of visible windows on the left and editable bounds on the right. Select a window, adjust the coordinates and size as needed, edit the profile name field if you want an exact or wildcard match pattern, then choose **Apply** to remove the title bar and borders. Profiles can still be saved, loaded, renamed, and deleted from the same screen, and **Load and Apply** will load the saved profile bounds for the selected window and apply them immediately. A compact **Preset** button grid sits directly under the bounds fields and can fill those fields from reusable defaults in `presets.ini`, so you can select a new window, tap a preset, and then just click **Save**. Some applications are fine adapting to non-traditional resolutions, but some will start to stretch.  

Selecting a window now fills the bounds editor with the **actual current window bounds**. If a saved profile is found, its name appears in the profile field and the marker to the left shows `~` until you explicitly press **Load**. The marker states are: `-` no profile found, `~` profile found but not loaded, `=` profile loaded unchanged, `*` loaded profile with unsaved edits.
The currently selected window title is always shown underneath the profile match pattern field. It stays muted while the pattern still matches, and turns red if the typed pattern no longer matches that title.
  
## Refresh  

Refreshes the list of visible windows and re-sorts saved-profile matches to the top of the list.  

# Profiles

Create an entry in `profiles.ini` for the game:

```
[Stationeers*]
width=2560
height=1440
x=420
y=0
```

In this case we are recording video on a 21:9 3440x1440 monitor, so we want to force it to 16:9 and center it (offset by x=420).

Profile names support `*` wildcards. For example, `Stationeers*` matches window titles that start with `Stationeers`, and an exact section name still matches exactly.

The section name is the matcher. Exact section names match exactly, and section names containing `*` act as wildcard patterns. That also means the editable profile name field in the Textual UI is the actual match pattern: if you rename a profile, you are changing what window titles it matches.

# Presets

Reusable bounds presets live in `presets.ini` next to `profiles.ini`. They are not window-title matchers; they are only reusable bounds templates for the Textual UI.

The default file currently contains:

```
[2560x1392]
x=1280
y=0
width=2560
height=1392

[2560x1440]
x=1280
y=0
width=2560
height=1440
```

Pressing a preset button in the UI updates only the bounds fields. It does not change the profile match pattern field, so you can pick a preset for a newly selected window and then save a real matching profile for that window. The matching preset button is highlighted whenever the current bounds exactly match one of the saved presets.

# Development and validation notes

- After each task, run both `uv run ruff check .` and `uv run ty check .`.
- Prefer **UV tools** for environment and package operations whenever UV can do the job; avoid falling back to `pip` for those tasks.
- Build both executables with `tools\\build.bat`.
- The interactive Textual app is console-hosted. `run.bat` opens a fresh PowerShell console window and runs its launcher logic inline, so there are no separate `.ps1` launcher files to manage.
- The headless batch file intentionally launches `main_headless.py` directly so silent automation stays compatible with external launchers.
- For UI work, validate changes with rendered Textual screenshots instead of relying only on widget coordinates:
  - render the UI with `BorderlessWindowApp().run_test(...)`
  - save an SVG screenshot with `app.save_screenshot(...)`
  - rasterize that SVG with Playwright + the locally installed Chrome so the result can be inspected as a PNG
- Avoid repeatedly launching `run.bat` or other long-lived interactive processes just to validate UI tweaks. Prefer the screenshot flow above, and if an interactive process is spawned for validation, stop it immediately after the check.
- Textual itself only exports SVG screenshots. Direct SVG-to-PNG conversion with Cairo-based tools may fail on machines that do not have native Cairo libraries installed, so the Playwright + Chrome path is the more reliable fallback in this repository.
- The right-side profile name field is editable. It is populated from the matched saved profile name when one exists, otherwise from the selected window title. That field is the actual exact-or-wildcard match pattern. Saving after renaming it renames the old profile instead of creating a duplicate section.
- Terminal/Textual apps cannot change the OS mouse pointer shape, so a hand cursor on hover is not supported here.

# Notes

Used and updated for Windows 11.
Created on Windows 10 however it has not been tested long after the creation.
Will not function on any other operating system.

![image](https://github.com/user-attachments/assets/97128673-2620-4a85-bfb8-1ab7ee11db30)


The real reason I made this:  
  
When games dont support the super ultrawide resolution and you have them fullscreen they fill in the unused space with black bars.
![image](https://user-images.githubusercontent.com/38366720/149245669-3457cb9e-6ec4-4fc9-a7ea-743400105b0a.png)

Putting the game a windowed state adds a titlebar which causes bottom of the window to be below the screen space. Some games don't allow you to resize these windows and you're forced to either have a piece of the window cut from the bottom or play at a lower resolution that fits within your vertical screen space.
![image](https://user-images.githubusercontent.com/38366720/149245709-f087ae6a-7ade-46b5-8c9c-899cb1d0f367.png)

I use the tool force a borderless windowed state that floats in the center of the screen (or wherever I want it to be)  for a cleaner look and the upside of not losing any of the game window below the monitor space.
![image](https://user-images.githubusercontent.com/38366720/149245765-e801bf91-091e-4f55-b271-0661e1b55fb9.png)
