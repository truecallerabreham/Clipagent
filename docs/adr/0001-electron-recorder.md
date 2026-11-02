# The recorder is an Electron app

The recorder must capture screen, webcam, mic and global input on Linux (including Wayland), macOS and Windows from one codebase. We chose Electron over Tauri because Tauri uses the OS webview, and WebKitGTK on Linux has poor screen-capture support, while Electron bundles Chromium, whose capture works on Wayland through PipeWire. We accept a ~100 MB download for capture that works everywhere.
