import platform
import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
import subprocess
import os
from utils import get_earliest_timestamp, cleanup_empty, activate_app_frontmost

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

_SHARED_ROOT: tk.Tk | None = None


def _bring_to_front(win: tk.Misc):
    activate_app_frontmost(win)


def set_shared_root(root: tk.Tk | None):
    global _SHARED_ROOT
    _SHARED_ROOT = root


def get_shared_root() -> tk.Tk:
    global _SHARED_ROOT
    if _SHARED_ROOT is None or not _SHARED_ROOT.winfo_exists():
        _SHARED_ROOT = tk.Tk()
        _SHARED_ROOT.withdraw()
    _bring_to_front(_SHARED_ROOT)
    return _SHARED_ROOT


def _modal_window(title: str, width: int = 980, height: int = 700) -> tk.Toplevel:
    root = get_shared_root()
    root.update_idletasks()

    x = root.winfo_x()
    y = root.winfo_y()
    if x <= 0 and y <= 0:
        x, y = 80, 80

    win = tk.Toplevel(root)
    win.title(title)
    win.geometry(f"{width}x{height}+{x}+{y}")
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()
    _bring_to_front(win)
    return win


class FolderDialog:
    def __init__(self, path: Path):
        self.path = path
        self.choice = None

    def _set(self, choice, win):
        self.choice = choice
        win.destroy()

    def _open_folder(self, win):
        try:
            if platform.system() == 'Darwin':
                subprocess.run(['open', str(self.path)])
            elif platform.system() == 'Windows':
                os.startfile(str(self.path))
            else:
                subprocess.run(['xdg-open', str(self.path)])
        except Exception as e:
            messagebox.showerror('Open Folder Failed', str(e), parent=win)

    def _rename_folder(self, win):
        new_name = simpledialog.askstring(
            'Rename Folder',
            'Enter new folder name:',
            initialvalue=self.path.name,
            parent=win
        )
        if not new_name or new_name == self.path.name:
            return
        new_path = self.path.parent / new_name
        try:
            self.path.rename(new_path)
            self.path = new_path
        except Exception as e:
            messagebox.showerror('Rename Failed', f'Could not rename folder:\n{e}', parent=win)
            return

        win.title(f"Folder: {self.path.name}")

    def run(self):
        win = _modal_window(f"Folder: {self.path.name}", width=980, height=240)
        win.protocol('WM_DELETE_WINDOW', lambda: self._set('quit', win))

        tk.Label(win, text='What to do with this folder?', font=('TkDefaultFont', 12, 'bold')).pack(pady=12)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)

        tk.Button(btn_frame, text='Open Folder', command=lambda: self._open_folder(win), width=16).grid(row=0, column=0, padx=4, pady=4)
        tk.Button(btn_frame, text='Rename Folder', command=lambda: self._rename_folder(win), width=16).grid(row=0, column=1, padx=4, pady=4)
        tk.Button(btn_frame, text='Keep As Is', command=lambda: self._set('keep', win), width=16).grid(row=0, column=2, padx=4, pady=4)
        tk.Button(btn_frame, text='Sort Inside Only', command=lambda: self._set('sort_inside', win), width=16).grid(row=1, column=0, padx=4, pady=4)
        tk.Button(btn_frame, text='Sort Into Years', command=lambda: self._set('sort_into_years', win), width=16).grid(row=1, column=1, padx=4, pady=4)
        tk.Button(btn_frame, text='Quit', command=lambda: self._set('quit', win), width=16).grid(row=1, column=2, padx=4, pady=4)

        win.bind('<Return>', lambda e: self._set('keep', win))
        win.wait_window()
        return self.choice


class DecisionDialog:
    def __init__(self, path: Path, src: Path):
        self.path = path
        self.src = src
        self.choice = None

    def _set(self, choice, win):
        self.choice = choice
        win.destroy()

    def _rename(self, win):
        base = simpledialog.askstring('Rename', 'New base filename (no ext):',
                                      initialvalue=self.path.stem, parent=win)
        if base:
            oldstem = self.path.stem
            newstem = base
            parent = self.path.parent
            newfile = parent / (newstem + self.path.suffix)
            self.path = self.path.rename(newfile)
            pair = parent / f"{oldstem}-Live{self.path.suffix}"
            if pair.exists():
                pair.rename(parent / f"{newstem}-Live{self.path.suffix}")
            self.choice = 'ok'
        win.destroy()

    def _change_date(self, win):
        initial = datetime.fromtimestamp(get_earliest_timestamp(self.path)).strftime('%Y-%m')
        s = simpledialog.askstring('Change Date Folder', 'Enter YYYY[-MM][-DD]:',
                                   initialvalue=initial, parent=win)
        if s:
            parts = s.split('-')
            y, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
            dest = self.src / str(y) / datetime(y, m, 1).strftime('%m-%B')
            dest.mkdir(parents=True, exist_ok=True)
            newp = dest / self.path.name
            orig_dir = self.path.parent
            self.path = self.path.rename(newp)
            old_live = orig_dir / f"{self.path.stem.replace('-Live','')}-Live{self.path.suffix}"
            if old_live.exists():
                old_live.rename(dest / f"{self.path.stem.replace('-Live','')}-Live{self.path.suffix}")
            cleanup_empty(orig_dir, self.src)
            self.choice = 'ok'
        win.destroy()

    def run(self):
        ts = get_earliest_timestamp(self.path)
        dt = datetime.fromtimestamp(ts)
        win = _modal_window(dt.strftime('%B %d, %Y') + ' – ' + self.path.name)
        win.protocol('WM_DELETE_WINDOW', lambda: self._set('quit', win))

        win.bind('<Return>', lambda e: self._set('ok', win))

        body = tk.Frame(win)
        body.pack(fill='both', expand=True, padx=12, pady=12)

        try:
            img = Image.open(self.path)
            img.thumbnail((720, 520))
            tkimg = ImageTk.PhotoImage(img)
            lbl = tk.Label(body, image=tkimg)
            lbl.image = tkimg
            lbl.pack(pady=10)
        except Exception:
            tk.Label(body, text=self.path.name).pack(pady=12)

        frm = tk.Frame(body)
        frm.pack(pady=8)

        for txt in ('OK', 'Junk', 'Meme'):
            tk.Button(frm, text=txt, width=12,
                      command=lambda c=txt.lower(): self._set(c, win)).pack(side='left', padx=4)
        tk.Button(frm, text='Rename', width=14, command=lambda: self._rename(win)).pack(side='left', padx=4)
        tk.Button(frm, text='Change Date Folder', width=16, command=lambda: self._change_date(win)).pack(side='left', padx=4)
        tk.Button(frm, text='Skip Folder', width=12, command=lambda: self._set('skip_folder', win)).pack(side='left', padx=4)
        tk.Button(frm, text='Quit', width=10, command=lambda: self._set('quit', win)).pack(side='left', padx=4)

        win.wait_window()
        return self.choice


class DuplicateDialog:
    def __init__(self, files: list[Path], default_index: int = 0):
        self.files = files
        self.choice = None
        self.default_index = default_index
        self._images: list[ImageTk.PhotoImage] = []

    def _set(self, win, choice):
        self.choice = choice
        win.destroy()

    def run(self):
        win = _modal_window('Duplicate Found')
        win.protocol('WM_DELETE_WINDOW', lambda: self._set(win, 'quit'))

        grid = tk.Frame(win)
        grid.pack(fill='both', expand=True, padx=10, pady=10)

        for idx, file in enumerate(self.files):
            highlight = 2 if idx == self.default_index else 0
            frm = tk.Frame(
                grid,
                bd=0,
                highlightthickness=highlight,
                highlightbackground='blue',
                highlightcolor='blue',
                padx=5,
                pady=5
            )
            frm.grid(row=idx // 3, column=idx % 3, padx=5, pady=5, sticky='n')

            try:
                img = Image.open(file)
                img.thumbnail((220, 220))
                tkimg = ImageTk.PhotoImage(img)
                self._images.append(tkimg)
                lbl_img = tk.Label(frm, image=tkimg)
                lbl_img.pack()
            except Exception:
                tk.Label(frm, text=file.name, wraplength=220).pack()

            ts = get_earliest_timestamp(file)
            ts_str = datetime.fromtimestamp(ts).strftime('%b %d, %Y %I:%M %p')
            lbl_txt = tk.Label(frm, text=f"{file.name}\n{file.parent}\n{ts_str}", justify='center', wraplength=220)
            lbl_txt.pack()

            btn = tk.Button(frm, text='Keep This One', width=18,
                            command=lambda i=idx: self._set(win, f'keep{i}'))
            btn.pack(pady=5)

        bot = tk.Frame(win)
        bot.pack(pady=10)
        tk.Button(bot, text='Keep All', width=12, command=lambda: self._set(win, 'keep_all')).pack(side='left', padx=5)
        tk.Button(bot, text='Delete All', width=12, command=lambda: self._set(win, 'delete_all')).pack(side='left', padx=5)
        tk.Button(bot, text='Quit', width=12, command=lambda: self._set(win, 'quit')).pack(side='left', padx=5)

        win.bind('<Return>', lambda e: self._set(win, f'keep{self.default_index}'))
        win.wait_window()
        return self.choice


class LiveDialog:
    def __init__(self, path: Path, src: Path):
        self.path = path
        self.src = src
        self.choice = None

    def _set(self, choice, win):
        self.choice = choice
        win.destroy()

    def run(self):
        try:
            if platform.system() == 'Darwin':
                subprocess.run(['open', str(self.path)])
            elif platform.system() == 'Windows':
                os.startfile(str(self.path))
            else:
                subprocess.run(['xdg-open', str(self.path)])
        except Exception:
            pass

        win = _modal_window(self.path.name, width=680, height=240)
        win.protocol('WM_DELETE_WINDOW', lambda: self._set('quit', win))

        tk.Label(win, text=f'Review Live Photo: {self.path.name}', font=('TkDefaultFont', 12, 'bold')).pack(pady=16)
        frm = tk.Frame(win)
        frm.pack(pady=8)
        tk.Button(frm, text='Keep', width=12, command=lambda: self._set('keep', win)).pack(side='left', padx=5)
        tk.Button(frm, text='Delete', width=12, command=lambda: self._set('delete', win)).pack(side='left', padx=5)
        tk.Button(frm, text='Quit', width=12, command=lambda: self._set('quit', win)).pack(side='left', padx=5)

        win.wait_window()
        return self.choice
