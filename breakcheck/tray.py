"""Optional Windows notification-area integration. Tk stays on the main thread."""
from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
import json
import hashlib
from .agent import write_json
from .safety import state_path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'BreakCheck'


def startup_supported():
    # Avoid registering a transient source checkout or a console process.
    return os.name == 'nt' and getattr(sys, 'frozen', False) and os.path.basename(sys.executable).lower() == 'breakcheck.exe'


def startup_command():
    if not startup_supported():
        raise RuntimeError('Windows startup is available in the packaged desktop app.')
    return f'"{sys.executable}" --background'


def startup_enabled():
    if not startup_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_NAME)[0] == startup_command()
    except FileNotFoundError:
        return False


def set_startup(enabled):
    if not startup_supported():
        raise RuntimeError('Windows startup is available in the packaged desktop app.')
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


class WindowsInstance:
    """One desktop instance per Windows user session; forward launch requests."""
    def __init__(self):
        self.handle = None
        self.primary = True
        self.request = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
        self.kernel.ProcessIdToSessionId.restype = wintypes.BOOL
        session = wintypes.DWORD()
        if not self.kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            raise ctypes.WinError(ctypes.get_last_error())
        directory = state_path().resolve().parent
        digest = hashlib.sha256(str(directory).casefold().encode('utf-8')).hexdigest()[:24]
        self.request = directory / f'open-request-{session.value}.json'
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\BreakCheck-' + digest)
        error = ctypes.get_last_error()
        if not self.handle:
            raise ctypes.WinError(error)
        self.primary = error != 183

    def forward(self, inspect=None, root=None):
        write_json(self.request, {'inspect': str(Path(inspect).absolute()) if inspect else None,
                                  'root': str(Path(root).absolute()) if root else None})

    def take(self):
        if self.request is None:
            return None
        path = self.request.with_suffix(f'.{os.getpid()}.pending')
        try:
            os.replace(self.request, path)
        except FileNotFoundError:
            return None
        try:
            if path.stat().st_size > 65536:
                return None
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and all(data.get(k) is None or isinstance(data.get(k), str) for k in ('inspect', 'root')):
                return data
            return None
        finally:
            path.unlink(missing_ok=True)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class WindowsTray:
    def __init__(self, app, background=False):
        self.app = app
        self.icon = None
        self.ready = False
        self.events = queue.Queue()
        self.background = background
        self.closed = False
        self.pending_notifications = 0
        if os.name != 'nt':
            return
        try:
            import pystray
            from PIL import Image, ImageDraw
            image = Image.new('RGBA', (64, 64))
            draw = ImageDraw.Draw(image)
            draw.polygon([(32, 3), (58, 13), (55, 39), (44, 52), (32, 61), (20, 52), (9, 39), (6, 13)], fill='#2563eb')
            draw.line([(17, 32), (28, 43), (47, 22)], fill='white', width=6)
            self.icon = pystray.Icon('BreakCheck', image, 'BreakCheck',
                menu=pystray.Menu(
                    pystray.MenuItem('Open BreakCheck', lambda *_: self.events.put('open'), default=True),
                    pystray.MenuItem('Check now', lambda *_: self.events.put('check')),
                    pystray.MenuItem('Quit BreakCheck', lambda *_: self.events.put('quit'))))
            def setup(icon):
                icon.visible = True
                self.events.put('ready')
            def runner():
                try:
                    self.icon.run(setup=setup)
                except Exception:
                    pass
                finally:
                    self.events.put('lost')
            threading.Thread(target=runner, daemon=True).start()
            app.protocol('WM_DELETE_WINDOW', self.hide_or_quit)
            app.after(200, self.poll)
        except (ImportError, OSError, RuntimeError):
            self.icon = None

    def poll(self):
        if self.closed:
            return
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event == 'ready':
                self.ready = True
                self.notify(self.pending_notifications)
                self.pending_notifications = 0
                if self.background:
                    self.app.withdraw()
            elif event in ('open', 'lost'):
                if event == 'lost':
                    self.ready = False
                self.app.deiconify()
                self.app.lift()
            elif event == 'check':
                self.app.deiconify()
                self.app.safety.check()
            elif event == 'quit':
                self.quit()
                return
        self.app.after(200, self.poll)

    def hide_or_quit(self):
        if self.ready:
            self.app.withdraw()
        else:
            self.quit()

    def notify(self, count):
        if not self.ready and self.icon is not None:
            self.pending_notifications += count
            return
        if self.ready and count:
            try:
                if self.icon.HAS_NOTIFICATION:
                    self.icon.notify(f'{count} newly detected broken file link(s). Open BreakCheck to review.', 'BreakCheck')
            except Exception:
                pass

    def quit(self):
        self.closed = True
        self.app.safety.shutdown()
        if self.icon is not None and self.ready:
            # pystray's stop can wait for its own thread: do not block Tk.
            threading.Thread(target=self.icon.stop, daemon=True).start()
        self.app.destroy()
