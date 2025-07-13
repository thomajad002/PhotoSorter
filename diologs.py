import platform
import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
import subprocess
import os
from utils import get_earliest_timestamp, cleanup_empty, safe_mkdir
# Ensure HEIC support
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

class FolderDialog:
    def __init__(self, path: Path):
        self.path = path
        self.choice = None

    def _set(self, choice, root):
        self.choice = choice
        root.destroy()

    def _open_folder(self, root):
        """Reveal this folder in Finder/Explorer so you can inspect its contents."""
        try:
            if platform.system() == 'Darwin':
                subprocess.run(['open', str(self.path)])
            elif platform.system() == 'Windows':
                os.startfile(str(self.path))
            else:
                subprocess.run(['xdg-open', str(self.path)])
        except Exception as e:
            messagebox.showerror('Open Folder Failed', str(e), parent=root)

    def _rename_folder(self, root):
        """Prompt for a new folder name, rename it on disk, and update self.path."""
        new_name = simpledialog.askstring(
            'Rename Folder',
            'Enter new folder name:',
            initialvalue=self.path.name,
            parent=root
        )
        if not new_name or new_name == self.path.name:
            return  # no change, stay in dialog
        new_path = self.path.parent / new_name
        try:
            self.path.rename(new_path)
            self.path = new_path
            # optionally: if this new name matches a backup pattern, your backup logic will detect it
        except Exception as e:
            messagebox.showerror('Rename Failed', f'Could not rename folder:\n{e}', parent=root)
            return

        # After rename, update the window title so you see the new name
        root.title(f"Folder: {self.path.name}")

    def run(self):
        root = tk.Tk()
        root.title(f"Folder: {self.path.name}")
        tk.Label(root, text="What to do with this folder?").pack(pady=10)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)

        tk.Button(btn_frame, text='Open Folder', 
                  command=lambda: self._open_folder(root)
        ).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Rename Folder', 
                  command=lambda: self._rename_folder(root)
        ).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Keep As Is', 
                  command=lambda: self._set('keep', root)
        ).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Sort Inside Only', 
                  command=lambda: self._set('sort_inside', root)
        ).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Sort Into Years', 
                  command=lambda: self._set('sort_into_years', root)
        ).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Quit', 
                  command=lambda: self._set('quit', root)
        ).pack(side='left', padx=5)

        # Allow Enter to mean “Keep As Is”
        root.bind('<Return>', lambda e: self._set('keep', root))
        root.mainloop()
        return self.choice

class DecisionDialog:
    def __init__(self, path: Path, src: Path):
        self.path = path
        self.src = src
        self.choice = None
    def _set(self, choice, root):
        self.choice = choice
        root.destroy()
    def _rename(self, root):
        base = simpledialog.askstring('Rename', 'New base filename (no ext):',
                                      initialvalue=self.path.stem, parent=root)
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
        root.destroy()
    def _change_date(self, root):
        initial = datetime.fromtimestamp(get_earliest_timestamp(self.path)).strftime('%Y-%m')
        s = simpledialog.askstring('Change Date Folder', 'Enter YYYY[-MM][-DD]:',
                                   initialvalue=initial, parent=root)
        if s:
            parts = s.split('-')
            y, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
            dest = self.src / str(y) / datetime(y, m, 1).strftime('%B')
            dest.mkdir(parents=True, exist_ok=True)
            newp = dest / self.path.name
            orig_dir = self.path.parent
            self.path = self.path.rename(newp)
            old_live = orig_dir / f"{self.path.stem.replace('-Live','')}-Live{self.path.suffix}"
            if old_live.exists():
                old_live.rename(dest / f"{self.path.stem.replace('-Live','')}-Live{self.path.suffix}")
            cleanup_empty(orig_dir, self.src)
            self.choice = 'ok'
        root.destroy()
    def run(self):
        root = tk.Tk()
        ts = get_earliest_timestamp(self.path)
        dt = datetime.fromtimestamp(ts)
        root.title(dt.strftime('%B %d, %Y') + ' – ' + self.path.name)
        root.bind('<Return>', lambda e: self._set('ok', root))
        try:
            img = Image.open(self.path)
            img.thumbnail((400,400))
            tkimg = ImageTk.PhotoImage(img)
            lbl = tk.Label(root, image=tkimg)
            lbl.image = tkimg
            lbl.pack(pady=10)
        except:
            pass
        frm = tk.Frame(root)
        frm.pack(pady=5)
        for txt in ('OK', 'Junk', 'Meme'):
            tk.Button(frm, text=txt,
                      command=lambda c=txt.lower(): self._set(c, root)).pack(side='left', padx=5)
        tk.Button(frm, text='Rename', command=lambda: self._rename(root)).pack(side='left', padx=5)
        tk.Button(frm, text='Change Date Folder', command=lambda: self._change_date(root)).pack(side='left', padx=5)
        tk.Button(frm, text='Skip Folder', command=lambda: self._set('skip_folder', root)).pack(side='left', padx=5)
        tk.Button(frm, text='Quit', command=lambda: self._set('quit', root)).pack(side='left', padx=5)
        root.mainloop()
        return self.choice


class DuplicateDialog:
    def __init__(self, files: list[Path], default_index: int = 0):
        self.files = files
        self.choice = None
        self.default_index = default_index

    def _set(self, root, choice):
        self.choice = choice
        root.destroy()

    def run(self):
        root = tk.Tk()
        root.title("Duplicate Found")

        # grid of thumbnails
        for idx, file in enumerate(self.files):
            # draw a blue border if this is the default
            highlight = 2 if idx == self.default_index else 0
            frm = tk.Frame(
                root,
                bd=0,
                highlightthickness=highlight,
                highlightbackground="blue",
                highlightcolor="blue",
                padx=5, pady=5
            )
            frm.grid(row=idx//3, column=idx%3, padx=5, pady=5)

            # thumbnail
            try:
                img = Image.open(file)
                img.thumbnail((200, 200))
                tkimg = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(frm, image=tkimg)
                lbl_img.image = tkimg
                lbl_img.pack()
            except Exception:
                pass

            # filename, path, and earliest timestamp
            ts = get_earliest_timestamp(file)
            ts_str = datetime.fromtimestamp(ts).strftime('%b %d, %Y %I:%M %p')
            lbl_txt = tk.Label(frm, text=f"{file.name}\n{file.parent}\n{ts_str}",
                                justify='center', wraplength=200)
            lbl_txt.pack()

            # “Keep This One” button
            btn = tk.Button(frm, text="Keep This One",
                            command=lambda i=idx: self._set(root, f'keep{i}'))
            btn.pack(pady=5)

        # bottom controls
        bot = tk.Frame(root)
        bot.grid(row=(len(self.files)//3)+1, column=0, columnspan=3, pady=10)
        tk.Button(bot, text="Keep All",
                  command=lambda: self._set(root, 'keep_all')
        ).pack(side='left', padx=5)
        tk.Button(bot, text="Delete All",
                  command=lambda: self._set(root, 'delete_all')
        ).pack(side='left', padx=5)
        tk.Button(bot, text="Quit",
                  command=lambda: self._set(root, 'quit')
        ).pack(side='left', padx=5)

        # Enter → default keep
        root.bind('<Return>', lambda e: self._set(root, f'keep{self.default_index}'))

        root.mainloop()
        return self.choice

class LiveDialog:
    def __init__(self, path: Path, src: Path):
        self.path = path
        self.src = src
        self.choice = None
    def _set(self, choice, root):
        self.choice = choice
        root.destroy()
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
        root = tk.Tk()
        root.title(self.path.name)
        tk.Label(root, text=f"Review Live Photo: {self.path.name}").pack(pady=10)
        frm = tk.Frame(root)
        frm.pack(pady=5)
        tk.Button(frm, text='Keep', command=lambda: self._set('keep', root)).pack(side='left', padx=5)
        tk.Button(frm, text='Delete', command=lambda: self._set('delete', root)).pack(side='left', padx=5)
        tk.Button(frm, text='Quit', command=lambda: self._set('quit', root)).pack(side='left', padx=5)
        root.mainloop()
        return self.choice