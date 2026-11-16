"""Computer and display details recorded with each session."""

import platform


def collect(screen_width, screen_height, scale):
    return {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "screen_width": screen_width,
        "screen_height": screen_height,
        "scale": scale,
    }
