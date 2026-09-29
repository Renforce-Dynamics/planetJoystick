"""Linux js_event and SDL gamepads with the same Xbox button/axis layout."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import threading


_JS_EVENT = struct.Struct("IhBB")
_JS_EVENT_BUTTON = 0x01
_JS_EVENT_AXIS = 0x02
_JS_EVENT_INIT = 0x80

# Existing configs use the Linux Xbox layout, not SDL's enum order.
_BUTTONS = (
    "A", "B", "X", "Y", "LEFTSHOULDER", "RIGHTSHOULDER", "BACK", "START",
    "GUIDE", "LEFTSTICK", "RIGHTSTICK",
)


def validate_device(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device must be auto, sdl:auto, sdl:INDEX, or a Linux/FIFO path")
    if value.startswith("sdl:"):
        index = value[4:]
        if index != "auto" and (not index.isascii() or not index.isdecimal()):
            raise ValueError("SDL device must be sdl:auto or sdl:INDEX (nonnegative integer)")


def resolve_device(value):
    validate_device(value)
    if value == "auto":
        if sys.platform == "darwin":
            return "sdl:auto"
        if sys.platform.startswith("linux"):
            return "/dev/input/js0"
        raise ValueError("device:auto supports Linux and macOS; select sdl:auto explicitly on other platforms")
    return value


def create_joystick(device):
    selected = resolve_device(device)
    return SDLJoystick(selected) if selected.startswith("sdl:") else LinuxJoystick(selected)


class LinuxJoystick:
    def __init__(self, path: str) -> None:
        self.path = str(path)
        self.fd: int | None = None
        self.buttons = [False] * 11
        self.axes = [0.0] * 8
        self._last_open_attempt = 0.0

    @property
    def connected(self) -> bool:
        return self.fd is not None

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.buttons = [False] * len(self.buttons)
        self.axes = [0.0] * len(self.axes)

    def poll(self, now_s: float) -> None:
        if self.fd is None:
            if now_s - self._last_open_attempt < 1.0:
                return
            self._last_open_attempt = now_s
            try:
                self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                return
        try:
            while True:
                data = os.read(self.fd, _JS_EVENT.size)
                if len(data) != _JS_EVENT.size:
                    raise OSError("short joystick event")
                _, value, event_type, number = _JS_EVENT.unpack(data)
                event_type &= ~_JS_EVENT_INIT
                if event_type == _JS_EVENT_AXIS:
                    if number >= len(self.axes):
                        self.axes.extend([0.0] * (number + 1 - len(self.axes)))
                    self.axes[number] = max(-1.0, min(1.0, float(value) / 32767.0))
                elif event_type == _JS_EVENT_BUTTON:
                    if number >= len(self.buttons):
                        self.buttons.extend([False] * (number + 1 - len(self.buttons)))
                    self.buttons[number] = bool(value)
        except BlockingIOError:
            return
        except OSError:
            self.close()


class _SDL:
    """Own only the pygame subsystems initialized by this input session."""

    def __init__(self):
        if threading.current_thread() is not threading.main_thread():
            raise ValueError("SDL gamepad input must run on the main thread (required on macOS)")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        try:
            import pygame
            from pygame._sdl2 import controller
        except ImportError as error:
            raise ValueError(
                "SDL gamepad input requires pygame-ce; rerun bootstrap on macOS or install planetj[sdl]"
            ) from error
        self.pg, self.controllers = pygame, controller
        self._owns_display = not pygame.display.get_init()
        self._owns_joysticks = not pygame.joystick.get_init()
        self._owns_controllers = not controller.get_init()
        try:
            # Event pumping requires video initialization. No window or audio is opened.
            if self._owns_display:
                pygame.display.init()
            if self._owns_joysticks:
                pygame.joystick.init()
            if self._owns_controllers:
                controller.init()
        except pygame.error as error:
            self.close()
            raise ValueError(f"SDL gamepad initialization failed: {error}") from error

    def pump(self):
        # Pump native events and drain the queue so long-running senders do not fill it.
        self.pg.event.get()

    def devices(self):
        self.pump()
        result = []
        for index in range(self.controllers.get_count()):
            joystick = self.pg.joystick.Joystick(index)
            try:
                result.append({"device": f"sdl:{index}", "name": joystick.get_name(),
                               "guid": joystick.get_guid(), "mapped": bool(self.controllers.is_controller(index))})
            finally:
                joystick.quit()
        return result

    def close(self):
        if self._owns_controllers:
            self.controllers.quit()
        if self._owns_joysticks:
            self.pg.joystick.quit()
        if self._owns_display:
            self.pg.display.quit()


class SDLJoystick:
    def __init__(self, selector="sdl:auto"):
        validate_device(selector)
        self.path = selector
        self.index = None if selector == "sdl:auto" else int(selector[4:])
        self._sdl = _SDL()
        self._controller = None
        self._next_open_s = 0.0
        self._closed = False
        self.description = selector
        self.buttons, self.axes = [False] * 11, [0.0] * 8

    @property
    def connected(self):
        return self._controller is not None

    def _disconnect(self):
        previous, self._controller = self._controller, None
        self.buttons, self.axes = [False] * 11, [0.0] * 8
        if previous is not None:
            try:
                previous.quit()
            except self._sdl.pg.error:
                pass

    def close(self):
        self._disconnect()
        if not self._closed:
            self._sdl.close()
            self._closed = True

    def poll(self, now_s):
        if self._closed:
            raise ValueError("SDL joystick is closed")
        try:
            self._sdl.pump()
            if self._controller is not None and not self._controller.attached():
                self._disconnect()
                self._next_open_s = now_s + 1.0
                return  # Publish a disconnected frame before any replacement is opened.
            if self._controller is None:
                if now_s < self._next_open_s:
                    return
                self._next_open_s = now_s + 1.0
                module = self._sdl.controllers
                count = module.get_count()
                candidates = range(count) if self.index is None else (self.index,)
                for index in candidates:
                    if index < count and module.is_controller(index):
                        self._controller = module.Controller(index)
                        self.description = f"sdl:{index} ({self._controller.name})"
                        break
                if self._controller is None:
                    return
            pg, device = self._sdl.pg, self._controller
            button = lambda name: bool(device.get_button(getattr(pg, "CONTROLLER_BUTTON_" + name)))
            axis = lambda name: device.get_axis(getattr(pg, "CONTROLLER_AXIS_" + name))
            stick = lambda name: max(-1.0, min(1.0, axis(name) / 32767.0))
            # SDL triggers are [0, 32767]; Linux Xbox axes rest at -1 and press to +1.
            trigger = lambda name: 2.0 * max(0.0, min(1.0, axis(name) / 32767.0)) - 1.0
            buttons = [button(name) for name in _BUTTONS]
            axes = [stick("LEFTX"), stick("LEFTY"), trigger("TRIGGERLEFT"),
                    stick("RIGHTX"), stick("RIGHTY"), trigger("TRIGGERRIGHT"),
                    float(button("DPAD_RIGHT")) - float(button("DPAD_LEFT")),
                    float(button("DPAD_DOWN")) - float(button("DPAD_UP"))]
            self.buttons, self.axes = buttons, axes
        except self._sdl.pg.error:
            # Unplugging between attached() and a read must never retain old controls.
            self._disconnect()
            self._next_open_s = now_s + 1.0


def list_devices(selector):
    selected = resolve_device(selector)
    if selected.startswith("sdl:"):
        session = _SDL()
        try:
            return session.devices()
        except session.pg.error as error:
            raise ValueError(f"SDL device listing failed; reconnect the controller and retry: {error}") from error
        finally:
            session.close()
    paths = sorted(Path("/dev/input").glob("js*"))
    if Path(selected).exists() and Path(selected) not in paths:
        paths.append(Path(selected))
    return [{"device": str(path), "name": "Linux joystick / FIFO", "mapped": True} for path in paths]
