# StreamToggles

**StreamToggles** is a native Linux desktop application built with **Python 3** and **Qt 6 / PyQt6**, tailored specifically for the **KDE Plasma** desktop environment adhering strictly to KDE Human Interface Guidelines (HIG). It functions as a customizable virtual macro pad and toggle controller (styled after hardware decks like the Elgato Stream Deck) for streaming workflows and desktop automation (e.g. controlling veadotube mini, OBS Studio HTTP endpoints, PipeWire/PulseAudio audio sources, or local scripts).

---

## Highlights & Features

- **Native & Modern KDE Plasma UI:** Pure Python Qt 6 layout definitions adhering to the KDE Human Interface Guidelines—using modern Breeze aesthetics, system color palette (`QPalette`) and accent color integration, responsive card layouts, and standard KDE actions with Breeze theme icons.
- **Visual Organizational Canvas Sections:** Organize buttons into distinct, labeled visual sections (e.g. "OBS Scenes", "Audio Controls", "Lights"). Each section has a visible header, management controls in Edit Mode (rename, move up/down, delete), and its own responsive flow grid of buttons (`FlowLayout`). Deleting a section is non-destructive—buttons are automatically moved back into the default "Uncategorized" section.
- **Dedicated Background Executor:** Powered by `concurrent.futures.ThreadPoolExecutor` to ensure HTTP requests, timeouts, and shell commands never block or freeze the Qt main GUI loop.
- **Lightweight & Dependency-Free:** Relies solely on Python standard library (`urllib.request`, `concurrent.futures`, `json`, `subprocess`) and PyQt6 (`QtWidgets`, `QtCore`, `QtGui`, `QtDBus`).
- **Global Shortcuts (Wayland / KDE Plasma / Linux):** Integrates directly with the `org.freedesktop.portal.GlobalShortcuts` XDG Desktop Portal via QtDBus. Configured hotkeys trigger toggles globally—even when the window is unfocused, minimized, or when streaming in full-screen.
- **Tactile Visual Feedback:** Clicking any tile triggers an immediate visual press feedback animation before dispatching the background action. Global shortcuts also trigger visual feedback on the corresponding tile.
- **Toast Alerts on Network Failure:** Mini-server responses (2xx/3xx/404) are cleanly handled, while unreachable hosts, network timeouts, or command errors display non-blocking floating toast notifications.
- **XDG Base Directory Persistence:** Configuration is atomically stored in `$XDG_CONFIG_HOME/streamtoggles/config.json` (fallback: `~/.config/streamtoggles/config.json`), ensuring crash-safe atomic updates.

---

## Action Types

1. **OBS Studio Scene Switch:**
   - Switches the active program scene in OBS Studio using **WebSocket v5** (default port 4455, with optional password authentication) or an **HTTP POST bridge** (e.g. `/call`).
   - Automatically populates and dynamically lists available scenes directly from OBS.
   - Can operate standalone or alongside an optional HTTP request (e.g., swapping your PNGTuber outfit or triggering an overlay when switching to a scene).
2. **Single HTTP Request (Fire-and-Forget):**
   - Dispatches a non-blocking `GET` or `POST` request with a 2.5-second timeout.
   - Example endpoint: `/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Black%20Shirt`
3. **Double HTTP Request (Sequenced with Delay):**
   - Sends the first HTTP request, waits for a configurable non-blocking delay (e.g., 2.0s), and dispatches the second HTTP request.
   - Perfect for temporary expressions, alerts, or timed state changes.
4. **Toggle HTTP Request (Discrete On/Off States):**
   - Dispatches `path_on` when turning active, and `path_off` when turning inactive.
   - Distinct KDE accent styling (`[active="true"]`) when active.
   - Supports mutually exclusive button groups (radio button behavior) where only one toggle in a group can be active at a time.
5. **Custom Command:**
   - Asynchronously runs arbitrary shell commands (e.g., `pactl set-source-mute @DEFAULT_SOURCE@ toggle`).

---

## Configuration Schema

Configured target hosts, buttons, sections, and mutually exclusive groups are stored at:
`~/.config/streamtoggles/config.json`

```json
{
  "version": 1,
  "hosts": [
    {
      "id": "veadotube-default",
      "label": "veadotube mini",
      "host": "127.0.0.1",
      "port": 36939
    }
  ],
  "sections": [
    {
      "id": "section_audio",
      "title": "Audio Controls"
    },
    {
      "id": "section_scenes",
      "title": "OBS Scenes"
    }
  ],
  "groups": [
    {
      "id": "group_outfits",
      "label": "Outfits"
    }
  ],
  "buttons": [
    {
      "id": "toggle-shirt-black",
      "label": "Black Shirt",
      "image_path": "",
      "shortcut": "<Control><Alt>1",
      "section_id": "section_scenes",
      "group_id": "group_outfits",
      "action_type": "toggle_http",
      "action_params": {
        "host_id": "veadotube-default",
        "path_on": "/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Black%20Shirt",
        "path_off": "/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Default"
      }
    }
  ]
}
```

---

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl + N` | Add New Toggle Button |
| `Ctrl + E` | Toggle Edit Mode |
| `Ctrl + ,` | Open Target Host Settings |
| `Ctrl + ?` | View Keyboard Shortcuts Help |
| `Ctrl + Q` | Quit StreamToggles |

---

## Project Structure

```
StreamToggles/
├── PKGBUILD                      # Arch Linux package build script (Qt6/PyQt6)
├── .SRCINFO                      # Generated Arch package metadata
├── pyproject.toml                # Modern PEP 517/518 build metadata & entrypoints
├── LICENSE                       # MIT License
├── run.py                        # Executable application launcher
├── streamtoggles/
│   ├── __init__.py               # Package metadata
│   ├── main.py                   # QApplication lifecycle, services, and actions
│   ├── config.py                 # XDG persistence & atomic JSON management (sections, groups, hosts, buttons)
│   ├── executor.py               # Background ThreadPoolExecutor & HTTP/shell runner with Qt signals
│   ├── portal.py                 # org.freedesktop.portal.GlobalShortcuts DBus client
│   └── ui/
│       ├── __init__.py
│       ├── style.py              # Modern KDE Plasma Breeze-compatible QSS stylesheet
│       ├── flow_layout.py        # Responsive flow layout for wrapping deck tiles
│       ├── window.py             # StreamTogglesWindow (QMainWindow) with toolbar & sectioned canvas
│       ├── section.py            # SectionContainer widget & SectionEditDialog modal
│       ├── tile.py               # Responsive Stream Deck button tile widget with tactile animations
│       ├── button_dialog.py      # QDialog for button configuration (section & group pickers)
│       ├── group_dialog.py       # QDialog for mutually exclusive radio groups
│       ├── host_dialog.py        # QDialog for managing network targets
│       ├── shortcuts_dialog.py   # KDE shortcuts help window
│       └── about_dialog.py       # KDE About dialog
├── data/
│   ├── com.github.streamtoggles.StreamToggles.desktop        # FreeDesktop application launcher entry
│   ├── com.github.streamtoggles.StreamToggles.metainfo.xml   # AppStream software metadata
│   └── icons/
│       ├── com.github.streamtoggles.StreamToggles.svg         # Scalable SVG application icon
│       ├── com.github.streamtoggles.StreamToggles-symbolic.svg# Symbolic vector icon
│       └── {16x16..512x512}/                                  # Standard hicolor rasterized PNG icons
└── tests/
    ├── test_config.py            # Unit tests for config & persistence (including sections & backwards compatibility)
    ├── test_executor.py          # Unit tests for HTTP GET & command execution with Qt event loop
    ├── test_sections.py          # Unit tests for visual canvas sections, SectionContainer, and SectionEditDialog
    ├── test_toggle_groups.py     # Unit tests for toggle HTTP & mutually exclusive radio groups
    └── test_ui.py                # Smoke tests for Qt6 & KDE components
```

---

## Installation & Running

Ensure Qt 6 and PyQt6 are installed on your Linux system (`pacman -S qt6-base qt6-svg python-pyqt6`).

### Install as a Native System Application (Arch Linux / Pacman):

Build and install using the included `PKGBUILD`:

```bash
git clone https://github.com/cptn-cosmo/streamtoggles.git
cd streamtoggles
# Downloads the tagged release tarball, builds, tests and installs it
makepkg -si
```

This installs:
- Executable binary to `/usr/bin/streamtoggles`
- Desktop launcher entry in `/usr/share/applications/`
- AppStream metadata in `/usr/share/metainfo/`
- Scalable, symbolic, and multi-resolution PNG icons in `/usr/share/icons/hicolor/`

Once installed, launch it directly from your terminal (`streamtoggles`) or search for "StreamToggles" in your KDE Plasma application launcher (Application Menu, KRunner, Kickoff, etc.).

### Launch Directly in Development:
```bash
./run.py
```
Or:
```bash
python3 -m streamtoggles.main
```

### Run Automated Tests:
```bash
python3 -m unittest discover -s tests -v
```
