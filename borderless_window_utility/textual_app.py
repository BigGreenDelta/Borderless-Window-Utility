from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Button, Header, Input, Label, OptionList, Static

from .core import (
    BorderlessError,
    WindowBounds,
    WindowSnapshot,
    apply_borderless_window,
    delete_window_profile,
    enumerate_visible_windows,
    get_matching_profile_name,
    get_window_rect_bounds,
    load_profile,
    parse_window_bounds,
    read_presets,
    read_profiles,
    save_window_profile,
    sort_window_titles,
    title_matches_profile_pattern,
)


class WindowOptionList(OptionList):
    def __init__(self, *content: object, **kwargs: object) -> None:
        super().__init__(*content, **kwargs)
        self._full_titles: list[str] = []

    def set_window_titles(self, titles: list[str]) -> None:
        self._full_titles = list(titles)
        self.tooltip = None
        padding = self.get_component_styles("option-list--option").padding.width
        available_width = max(1, self.scrollable_content_region.width - padding)
        self.set_options(self._truncate_title(title, available_width) for title in titles)

    def _truncate_title(self, title: str, width: int) -> str:
        if cell_len(title) <= width:
            return title
        if width <= 1:
            return "…"
        return f"{set_cell_size(title, width - 1)}…"

    def _tooltip_for_index(self, index: int | None) -> str | None:
        if index is None or not 0 <= index < len(self._full_titles):
            return None
        return self._full_titles[index]

    def _on_mouse_move(self, event: events.MouseMove) -> None:
        super()._on_mouse_move(event)
        self.tooltip = self._tooltip_for_index(self._mouse_hovering_over)

    def _on_leave(self, event: events.Leave) -> None:
        super()._on_leave(event)
        self.tooltip = None


class BorderlessWindowApp(App[None]):
    TITLE = "Borderless Window Utility"
    SUB_TITLE = "Textual"
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #top-guide {
        height: 1;
        min-height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #window-pane {
        width: 4fr;
        min-width: 48;
        padding: 0 2 1 1;
    }

    #editor-pane {
        width: 3fr;
        padding: 0 1 1 2;
    }

    .button-row {
        height: auto;
        margin: 0 0 1 0;
    }

    .apply-button-row {
        height: auto;
        margin: 0;
    }

    .profile-button-row {
        height: auto;
        padding: 0 1 0 0;
        margin: 0 0 1 0;
    }

    .filter-row {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    .field-row {
        height: auto;
        margin: 0 0 1 0;
    }

    .field-pair {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    .field-pair Label {
        width: 7;
        content-align: left middle;
    }

    .field-pair Input {
        width: 1fr;
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 1;
    }

    #profile-name {
        width: 1fr;
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 1;
        margin: 0;
    }

    #profile-match-warning {
        height: auto;
        margin: 0 0 0 3;
        color: $text-muted;
    }

    #profile-match-warning.error {
        color: $error;
    }

    #profile-state-row {
        height: auto;
        margin: 0;
    }

    #profile-state {
        width: 1;
        min-width: 1;
        margin-right: 1;
        content-align: center middle;
    }

    #profile-gap {
        height: 2;
        min-height: 2;
    }

    #preset-section {
        height: auto;
        margin: 0 0 1 0;
    }

    #preset-grid {
        width: 1fr;
        height: auto;
        grid-size-columns: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 1 1;
    }

    .preset-button {
        width: 1fr;
    }

    .preset-button.active-preset {
        tint: $success 30%;
        text-style: bold;
    }

    #window-filter {
        width: 1fr;
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 1;
        margin: 0;
    }

    #window-list {
        width: 1fr;
        height: 1fr;
        margin: 0 0 1 0;
    }

    #status {
        height: 1;
        min-height: 1;
        border-top: solid $primary;
        padding: 0 1;
        margin: 0;
        color: $text-muted;
        background: $surface;
    }

    Button {
        margin-right: 1;
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 1;
    }

    #refresh {
        width: 12;
        margin-left: 1;
    }

    .action-button {
        width: 1fr;
    }

    .delete-button {
        width: 5;
        min-width: 5;
        margin-right: 0;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_windows", "Refresh"),
        ("a", "apply_selected", "Apply"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.profiles: dict[str, WindowBounds] = {}
        self.windows: dict[str, WindowSnapshot] = {}
        self.window_titles: list[str] = []
        self.filtered_titles: list[str] = []
        self.selected_title: str | None = None
        self.active_profile_name: str | None = None
        self.loaded_profile_bounds: WindowBounds | None = None
        self.presets: dict[str, WindowBounds] = {}
        self._active_preset_name: str | None = None
        self._preset_buttons: dict[str, Button] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="top-guide")
        with Horizontal(id="body"):
            with Vertical(id="window-pane"):
                with Horizontal(classes="filter-row"):
                    yield Input(placeholder="Filter visible windows", id="window-filter")
                    yield Button("Refresh", id="refresh")
                yield WindowOptionList(id="window-list")
            with Vertical(id="editor-pane"):
                with Horizontal(classes="field-row"):
                    with Horizontal(classes="field-pair"):
                        yield Label("X")
                        yield Input("0", id="x")
                    with Horizontal(classes="field-pair"):
                        yield Label("Y")
                        yield Input("0", id="y")
                with Horizontal(classes="field-row"):
                    with Horizontal(classes="field-pair"):
                        yield Label("Width")
                        yield Input("2560", id="width")
                    with Horizontal(classes="field-pair"):
                        yield Label("Height")
                        yield Input("1440", id="height")
                with Vertical(id="preset-section"):
                    yield Grid(id="preset-grid")
                with Horizontal(classes="apply-button-row"):
                    yield Button("Apply", id="apply", variant="primary", classes="action-button")
                yield Static("", id="profile-gap")
                with Horizontal(id="profile-state-row"):
                    yield Static("-", id="profile-state")
                    yield Input(placeholder="Profile match pattern", id="profile-name")
                yield Static("", id="profile-match-warning")
                with Horizontal(classes="profile-button-row"):
                    yield Button("Load", id="load", classes="action-button")
                    yield Button("Save", id="save", classes="action-button")
                    yield Button("X", id="delete", classes="delete-button", tooltip="Delete saved profile")
                with Horizontal(classes="apply-button-row"):
                    yield Button("Load and Apply", id="load-apply", variant="primary", classes="action-button")
        yield Static("Refreshing visible windows...", id="status")

    def on_mount(self) -> None:
        self.refresh_windows()

    def on_resize(self, _event: events.Resize) -> None:
        if self.window_titles:
            self.call_after_refresh(self._rebuild_window_list, self.selected_title)

    def action_refresh_windows(self) -> None:
        self.refresh_windows(preserve_selection=True)

    def action_apply_selected(self) -> None:
        title = self.selected_title
        if title is None:
            self._set_status("Select a window first.")
            return

        try:
            bounds = self._read_input_bounds()
        except BorderlessError as exc:
            self._set_status(str(exc))
            return

        self.apply_selected_window(title, bounds)

    @work(thread=True, exclusive=True)
    def refresh_windows(self, preserve_selection: bool = False) -> None:
        try:
            profiles = read_profiles()
            presets = read_presets()
            windows = enumerate_visible_windows()
            window_titles = sort_window_titles(windows, profiles)
        except BorderlessError as exc:
            self.call_from_thread(self._set_status, str(exc))
            return

        preferred_selection = self.selected_title if preserve_selection else None
        self.call_from_thread(
            self._apply_window_refresh,
            profiles,
            presets,
            windows,
            window_titles,
            preferred_selection,
        )

    @work(thread=True, exclusive=True)
    def inspect_selected_window(self, title: str) -> None:
        snapshot = self.windows.get(title)
        if snapshot is None:
            self.call_from_thread(self._set_status, "Window not found. Refresh the list and try again.")
            return

        try:
            profiles = read_profiles()
            bounds = get_window_rect_bounds(snapshot.hwnd)
            matched_profile_name = get_matching_profile_name(profiles, title)
        except BorderlessError as exc:
            self.call_from_thread(self._set_status, str(exc))
            return

        self.call_from_thread(
            self._apply_selected_window,
            title,
            profiles,
            bounds,
            matched_profile_name,
        )

    @work(thread=True, exclusive=True)
    def load_profile_for_selected_window(self, title: str) -> None:
        snapshot = self.windows.get(title)
        if snapshot is None:
            self.call_from_thread(self._set_status, "Window not found. Refresh the list and try again.")
            return

        try:
            profiles = read_profiles()
            matched_profile_name = get_matching_profile_name(profiles, title)
            if matched_profile_name is None:
                raise BorderlessError("No saved profile for the selected window.")
            bounds = load_profile(profiles, title)
            if bounds is None:
                raise BorderlessError("No saved profile for the selected window.")
        except BorderlessError as exc:
            self.call_from_thread(self._set_status, str(exc))
            return

        self.call_from_thread(
            self._apply_loaded_profile,
            title,
            profiles,
            bounds,
            matched_profile_name,
            None,
        )

    @work(thread=True, exclusive=True)
    def load_and_apply_profile_for_selected_window(self, title: str) -> None:
        snapshot = self.windows.get(title)
        if snapshot is None:
            self.call_from_thread(self._set_status, "Window not found. Refresh the list and try again.")
            return

        try:
            profiles = read_profiles()
            matched_profile_name = get_matching_profile_name(profiles, title)
            if matched_profile_name is None:
                raise BorderlessError("No saved profile for the selected window.")
            bounds = load_profile(profiles, title)
            if bounds is None:
                raise BorderlessError("No saved profile for the selected window.")
            apply_borderless_window(snapshot.hwnd, bounds)
        except BorderlessError as exc:
            self.call_from_thread(self._set_status, str(exc))
            return

        self.call_from_thread(
            self._apply_loaded_profile,
            title,
            profiles,
            bounds,
            matched_profile_name,
            f"Loaded and applied profile: {self._format_title(matched_profile_name)}",
        )

    @work(thread=True, exclusive=True)
    def apply_selected_window(self, title: str, bounds: WindowBounds) -> None:
        snapshot = self.windows.get(title)
        if snapshot is None:
            self.call_from_thread(self._set_status, "Window not found. Refresh the list and try again.")
            return

        try:
            apply_borderless_window(snapshot.hwnd, bounds)
        except BorderlessError as exc:
            self.call_from_thread(self._set_status, str(exc))
            return

        self.call_from_thread(self._set_status, f"Applied borderless mode to '{title}'.")

    @on(Input.Changed, "#window-filter")
    def handle_filter_change(self, _event: Input.Changed) -> None:
        self._rebuild_window_list(self.selected_title)

    @on(Input.Changed, "#x")
    @on(Input.Changed, "#y")
    @on(Input.Changed, "#width")
    @on(Input.Changed, "#height")
    @on(Input.Changed, "#profile-name")
    def handle_profile_editor_change(self, _event: Input.Changed) -> None:
        self._update_profile_state_indicator()
        self._update_profile_match_warning()
        self._sync_preset_buttons()

    @on(OptionList.OptionHighlighted, "#window-list")
    def handle_window_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is None:
            return

        if 0 <= event.option_index < len(self.filtered_titles):
            self.inspect_selected_window(self.filtered_titles[event.option_index])

    @on(Button.Pressed)
    def handle_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.has_class("preset-button"):
            preset_name = self._preset_name_for_button(event.button)
            if preset_name is None:
                return
            preset = self.presets.get(preset_name)
            if preset is None:
                return

            self._set_input_value("x", preset.x)
            self._set_input_value("y", preset.y)
            self._set_input_value("width", preset.width)
            self._set_input_value("height", preset.height)
            self._set_status(f"Applied preset bounds: {preset_name}")
            return

        button_id = event.button.id
        if button_id == "refresh":
            self.action_refresh_windows()
        elif button_id == "load":
            if self.selected_title is None:
                self._set_status("Select a window first.")
            else:
                self.load_profile_for_selected_window(self.selected_title)
        elif button_id == "save":
            self._save_selected_profile()
        elif button_id == "delete":
            self._delete_selected_profile()
        elif button_id == "load-apply":
            if self.selected_title is None:
                self._set_status("Select a window first.")
            else:
                self.load_and_apply_profile_for_selected_window(self.selected_title)
        elif button_id == "apply":
            self.action_apply_selected()

    def _apply_window_refresh(
        self,
        profiles: dict[str, WindowBounds],
        presets: dict[str, WindowBounds],
        windows: dict[str, WindowSnapshot],
        window_titles: list[str],
        preferred_selection: str | None,
    ) -> None:
        self.profiles = profiles
        self.presets = presets
        self.windows = windows
        self.window_titles = window_titles
        self._rebuild_preset_grid()
        self._rebuild_window_list(preferred_selection)

        if self.window_titles:
            self._set_status(f"{len(self.window_titles)} visible windows.")
        else:
            self._set_status("No visible windows found.")

    def _apply_selected_window(
        self,
        title: str,
        profiles: dict[str, WindowBounds],
        bounds: WindowBounds,
        matched_profile_name: str | None,
    ) -> None:
        self.profiles = profiles
        self.selected_title = title
        self.active_profile_name = matched_profile_name
        self.loaded_profile_bounds = None
        self._set_input_value("x", bounds.x)
        self._set_input_value("y", bounds.y)
        self._set_input_value("width", bounds.width)
        self._set_input_value("height", bounds.height)
        self._set_profile_name_value(self.active_profile_name or title)
        self._update_profile_state_indicator()
        self._update_profile_match_warning()
        self._set_status(f"Loaded: {self._format_title(title)}")

    def _apply_loaded_profile(
        self,
        title: str,
        profiles: dict[str, WindowBounds],
        bounds: WindowBounds,
        matched_profile_name: str,
        status_message: str | None,
    ) -> None:
        self.profiles = profiles
        self.selected_title = title
        self.active_profile_name = matched_profile_name
        self.loaded_profile_bounds = bounds
        self._set_input_value("x", bounds.x)
        self._set_input_value("y", bounds.y)
        self._set_input_value("width", bounds.width)
        self._set_input_value("height", bounds.height)
        self._set_profile_name_value(matched_profile_name)
        self._update_profile_state_indicator()
        self._update_profile_match_warning()
        self._set_status(status_message or f"Loaded profile: {self._format_title(matched_profile_name)}")

    def _save_selected_profile(self) -> None:
        title = self.selected_title
        if title is None:
            self._set_status("Select a window first.")
            return

        try:
            profile_name = self._read_profile_name()
            bounds = self._read_input_bounds()
            save_window_profile(
                profile_name,
                bounds,
                original_title=self.active_profile_name,
            )
            self.profiles = read_profiles()
        except BorderlessError as exc:
            self._set_status(str(exc))
            return

        renamed_profile = self.active_profile_name and self.active_profile_name != profile_name
        self.active_profile_name = profile_name
        self.loaded_profile_bounds = bounds
        self.window_titles = sort_window_titles(self.windows, self.profiles)
        self._rebuild_window_list(title)
        self._update_profile_state_indicator()
        self._update_profile_match_warning()
        action = "Renamed and saved profile" if renamed_profile else "Saved profile"
        self._set_status(f"{action}: {self._format_title(profile_name)}")

    def _delete_selected_profile(self) -> None:
        if self.selected_title is None:
            self._set_status("Select a window first.")
            return
        if self.active_profile_name is None:
            self._set_status("No saved profile for the selected window.")
            return

        try:
            profile_name = self.active_profile_name
            delete_window_profile(profile_name)
            self.profiles = read_profiles()
        except BorderlessError as exc:
            self._set_status(str(exc))
            return

        self.active_profile_name = None
        self.loaded_profile_bounds = None
        self.window_titles = sort_window_titles(self.windows, self.profiles)
        self._rebuild_window_list(self.selected_title)
        self._set_profile_name_value(self.selected_title)
        self._update_profile_state_indicator()
        self._update_profile_match_warning()
        self._set_status(f"Deleted profile: {self._format_title(profile_name)}")

    def _read_input_bounds(self) -> WindowBounds:
        return parse_window_bounds(
            self.query_one("#x", Input).value,
            self.query_one("#y", Input).value,
            self.query_one("#width", Input).value,
            self.query_one("#height", Input).value,
        )

    def _read_profile_name(self) -> str:
        profile_name = self.query_one("#profile-name", Input).value.strip()
        if not profile_name:
            raise BorderlessError("Profile name cannot be empty.")
        return profile_name

    def _set_input_value(self, widget_id: str, value: int) -> None:
        self.query_one(f"#{widget_id}", Input).value = str(value)

    def _set_profile_name_value(self, value: str) -> None:
        self.query_one("#profile-name", Input).value = value

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _update_profile_state_indicator(self) -> None:
        marker = self.query_one("#profile-state", Static)
        if self.active_profile_name is None or self.loaded_profile_bounds is None:
            if self.active_profile_name is None:
                marker.update("-")
                marker.tooltip = "No saved profile was found for the selected window."
            else:
                marker.update("~")
                marker.tooltip = "Saved profile found for this window, but not loaded into the bounds editor."
            return

        profile_name_matches = self.query_one("#profile-name", Input).value.strip() == self.active_profile_name
        try:
            current_bounds = self._read_input_bounds()
        except BorderlessError:
            current_bounds = None

        if profile_name_matches and current_bounds == self.loaded_profile_bounds:
            marker.update("=")
            marker.tooltip = "Saved profile is loaded with no unsaved changes."
        else:
            marker.update("*")
            marker.tooltip = "Saved profile is loaded, but the editor has unsaved changes."

    def _update_profile_match_warning(self) -> None:
        warning = self.query_one("#profile-match-warning", Static)
        if self.selected_title is None:
            warning.update("")
            warning.remove_class("error")
            return

        pattern = self.query_one("#profile-name", Input).value.strip()
        is_match = not pattern or title_matches_profile_pattern(pattern, self.selected_title)
        warning.update(self.selected_title)
        warning.set_class(not is_match, "error")

    def _format_title(self, title: str, max_length: int = 48) -> str:
        if len(title) <= max_length:
            return title

        return f"{title[: max_length - 3]}..."

    def _rebuild_preset_grid(self) -> None:
        grid = self.query_one("#preset-grid", Grid)
        grid.remove_children()
        self._preset_buttons.clear()

        buttons: list[Button] = []
        for name in self.presets:
            label = self._format_title(name, max_length=18)
            button = Button(label, classes="preset-button")
            if label != name:
                button.tooltip = name
            self._preset_buttons[name] = button
            buttons.append(button)

        if buttons:
            grid.mount(*buttons)

        self._sync_preset_buttons()

    def _sync_preset_buttons(self) -> None:
        try:
            current_bounds = self._read_input_bounds()
        except BorderlessError:
            next_name = None
        else:
            next_name = next(
                (name for name, bounds in self.presets.items() if bounds == current_bounds),
                None,
            )

        self._active_preset_name = next_name
        for name, button in self._preset_buttons.items():
            button.set_class(name == next_name, "active-preset")

    def _preset_name_for_button(self, target: Button) -> str | None:
        for name, button in self._preset_buttons.items():
            if button is target:
                return name
        return None

    def _rebuild_window_list(self, preferred_selection: str | None) -> None:
        option_list = self.query_one("#window-list", WindowOptionList)
        filter_value = self.query_one("#window-filter", Input).value.casefold().strip()
        self.filtered_titles = [
            title for title in self.window_titles if filter_value in title.casefold()
        ]

        option_list.set_window_titles(self.filtered_titles)
        if self.filtered_titles:
            if preferred_selection in self.filtered_titles:
                next_selection = preferred_selection
            else:
                next_selection = self.filtered_titles[0]

            option_index = self.filtered_titles.index(next_selection)
            option_list.highlighted = option_index
            self.selected_title = next_selection
            self.inspect_selected_window(next_selection)
        else:
            self.selected_title = None
            self.active_profile_name = None
            self.loaded_profile_bounds = None
            self._set_profile_name_value("")
            self._update_profile_state_indicator()
            self._update_profile_match_warning()
