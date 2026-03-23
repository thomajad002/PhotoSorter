import contextlib
import queue
import threading
import traceback
import platform
import subprocess
import os
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

from utils import choose_folder, choose_files, activate_app_frontmost
from sort_logic import sort_files, strong_sort, find_duplicates, handle_live, sort_files_copy, sort_selected_files_copy
from diologs import set_shared_root


class _QueueWriter:
    def __init__(self, put_line):
        self._put_line = put_line
        self._buffer = ''

    def write(self, text: str):
        if not text:
            return
        self._buffer += text
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self._put_line(line)

    def flush(self):
        if self._buffer:
            self._put_line(self._buffer)
            self._buffer = ''


class _DirectWriter:
    def __init__(self, append_line):
        self._append_line = append_line
        self._buffer = ''

    def write(self, text: str):
        if not text:
            return
        self._buffer += text
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self._append_line(line)

    def flush(self):
        if self._buffer:
            self._append_line(self._buffer)
            self._buffer = ''


class PhotoSorterApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('PhotoSorter')
        self.root.geometry('860x620+80+80')
        self.root.resizable(False, False)

        set_shared_root(self.root)

        self.feature_var = tk.StringVar(value='sort')
        self.src_var = tk.StringVar()
        self.selected_files_var = tk.StringVar(value='No files selected')
        self.dest_var = tk.StringVar()
        self.status_var = tk.StringVar(value='Ready')
        self.selected_copy_files: list[Path] = []

        self.is_running = False
        self._event_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._interactive_widgets: list[tk.Widget] = []

        self._build_ui()
        self._toggle_dest_visibility()
        self.root.after(0, lambda: activate_app_frontmost(self.root))

    def _open_in_system_file_browser(self, folder: Path):
        if platform.system() == 'Darwin':
            subprocess.run(['open', str(folder)])
        elif platform.system() == 'Windows':
            os.startfile(str(folder))
        else:
            subprocess.run(['xdg-open', str(folder)])

    def _open_selected_folder(self, folder_value: str, label: str):
        raw = folder_value.strip()
        if not raw:
            messagebox.showerror('Missing folder', f'Please choose a {label} first.', parent=self.root)
            return

        folder = Path(raw).expanduser()
        if not folder.exists() or not folder.is_dir():
            messagebox.showerror('Invalid folder', f'The selected {label} does not exist or is not a directory.', parent=self.root)
            return

        try:
            self._open_in_system_file_browser(folder)
        except Exception as exc:
            messagebox.showerror('Open failed', str(exc), parent=self.root)

    def _show_feature_help(self):
        help_text = (
            'Sort in place:\n'
            '- Sorts files directly inside the source folder.\n\n'
            'Sort in place + Strong Sort review:\n'
            '- Runs normal sort, then opens review dialogs to mark Keep/Junk/Meme, rename, or move date.\n\n'
            'Find duplicates:\n'
            '- Scans for duplicate images and lets you choose which copy to keep.\n\n'
            'Review Live Photos:\n'
            '- Steps through *-Live.mov files so you can keep or delete each one.\n\n'
            'Copy then sort into a second location:\n'
            '- Copies a source folder OR selected files into destination root and sorts there, so originals stay untouched.'
        )
        messagebox.showinfo('Feature Help', help_text, parent=self.root)

    def _maybe_offer_open_folder(self, folder: Path | None):
        if folder is None:
            return
        try:
            if not folder.exists() or not folder.is_dir():
                return
        except Exception:
            return

        open_now = messagebox.askyesno(
            'Open Folder?',
            f'Success. Open this folder now?\n\n{folder}',
            parent=self.root,
        )
        if open_now:
            try:
                self._open_in_system_file_browser(folder)
            except Exception as exc:
                messagebox.showerror('Open failed', str(exc), parent=self.root)

    def _build_ui(self):
        outer = tk.Frame(self.root, padx=20, pady=18)
        outer.pack(fill='both', expand=True)

        tk.Label(outer, text='PhotoSorter', font=('TkDefaultFont', 16, 'bold')).pack(anchor='w')
        tk.Label(outer, text='Choose a feature, then select your folder(s).').pack(anchor='w', pady=(2, 14))

        feature_frame = tk.LabelFrame(outer, text='Feature', padx=10, pady=8)
        feature_frame.pack(fill='x')
        feature_frame.columnconfigure(0, weight=1)
        feature_frame.columnconfigure(1, weight=1)

        options = [
            ('Sort in place', 'sort'),
            ('Sort in place + Strong Sort review', 'sort_strong'),
            ('Find duplicates', 'duplicates'),
            ('Review Live Photos', 'live'),
            ('Copy then sort into a second location', 'sort_copy'),
        ]

        for idx, (label, value) in enumerate(options):
            btn = tk.Radiobutton(
                feature_frame,
                text=label,
                variable=self.feature_var,
                value=value,
                command=self._toggle_dest_visibility,
            )
            btn.grid(row=idx // 2, column=idx % 2, sticky='w', padx=6, pady=4)
            self._interactive_widgets.append(btn)

        self.feature_help_button = tk.Button(feature_frame, text='Help Info', width=12, command=self._show_feature_help)
        self.feature_help_button.grid(row=3, column=1, sticky='e', padx=6, pady=(6, 2))
        self._interactive_widgets.append(self.feature_help_button)

        path_frame = tk.LabelFrame(outer, text='Folders', padx=10, pady=10)
        path_frame.pack(fill='x', pady=(14, 0))
        path_frame.columnconfigure(0, weight=1)

        tk.Label(path_frame, text='Source folder:').grid(row=0, column=0, sticky='w')
        self.src_entry = tk.Entry(path_frame, textvariable=self.src_var)
        self.src_entry.grid(row=1, column=0, padx=(0, 8), pady=(2, 0), sticky='ew')
        self._interactive_widgets.append(self.src_entry)

        self.src_browse_button = tk.Button(path_frame, text='Browse', width=10, command=self._browse_src)
        self.src_browse_button.grid(row=1, column=1, pady=(2, 0))
        self._interactive_widgets.append(self.src_browse_button)

        self.src_open_button = tk.Button(
            path_frame,
            text='Open',
            width=10,
            command=lambda: self._open_selected_folder(self.src_var.get(), 'source folder'),
        )
        self.src_open_button.grid(row=1, column=2, padx=(8, 0), pady=(2, 0))
        self._interactive_widgets.append(self.src_open_button)

        self.selected_files_label = tk.Label(path_frame, text='Selected files (copy mode):')
        self.selected_files_value = tk.Label(path_frame, textvariable=self.selected_files_var, anchor='w')

        self.dest_label = tk.Label(path_frame, text='Destination root (for copy):')
        self.dest_entry = tk.Entry(path_frame, textvariable=self.dest_var)
        self.dest_button = tk.Button(path_frame, text='Browse', width=10, command=self._browse_dest)
        self.dest_open_button = tk.Button(
            path_frame,
            text='Open',
            width=10,
            command=lambda: self._open_selected_folder(self.dest_var.get(), 'destination folder'),
        )
        self._interactive_widgets.extend([self.dest_entry, self.dest_button, self.dest_open_button])

        action_row = tk.Frame(outer)
        action_row.pack(fill='x', pady=(16, 8))

        self.run_button = tk.Button(action_row, text='Run', width=14, command=self._run)
        self.run_button.pack(side='left')
        self._interactive_widgets.append(self.run_button)

        self.quit_button = tk.Button(action_row, text='Quit', width=14, command=self.root.destroy)
        self.quit_button.pack(side='left', padx=8)

        tk.Label(action_row, textvariable=self.status_var, anchor='w').pack(side='left', padx=12)

        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 10))

        log_frame = tk.LabelFrame(outer, text='Status Log', padx=8, pady=8)
        log_frame.pack(fill='both', expand=True)

        log_toolbar = tk.Frame(log_frame)
        log_toolbar.pack(fill='x')

        self.clear_log_button = tk.Button(log_toolbar, text='Clear Log', width=12, command=self._clear_log)
        self.clear_log_button.pack(side='right')
        self._interactive_widgets.append(self.clear_log_button)

        self.log_text = ScrolledText(log_frame, height=14, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True, pady=(6, 0))

    def _toggle_dest_visibility(self):
        enabled = self.feature_var.get() == 'sort_copy'

        if enabled:
            self.selected_files_label.grid(row=2, column=0, sticky='w', pady=(10, 0))
            self.selected_files_value.grid(row=2, column=1, columnspan=3, sticky='w', pady=(10, 0))
            self.dest_label.grid(row=3, column=0, sticky='w', pady=(10, 0))
            self.dest_entry.grid(row=4, column=0, padx=(0, 8), pady=(2, 0), sticky='ew')
            self.dest_button.grid(row=4, column=1, pady=(2, 0))
            self.dest_open_button.grid(row=4, column=3, padx=(8, 0), pady=(2, 0))
        else:
            self.selected_files_label.grid_remove()
            self.selected_files_value.grid_remove()
            self.dest_label.grid_remove()
            self.dest_entry.grid_remove()
            self.dest_button.grid_remove()
            self.dest_open_button.grid_remove()

    def _set_busy(self, busy: bool, status: str | None = None):
        self.is_running = busy
        if status:
            self.status_var.set(status)

        for widget in self._interactive_widgets:
            try:
                widget.configure(state='disabled' if busy else 'normal')
            except tk.TclError:
                continue

        self.quit_button.configure(state='normal')

        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            self.status_var.set('Ready')

    def _append_log(self, line: str):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', f'{line}\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')
        self.root.update_idletasks()

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _queue_log(self, line: str):
        self._event_queue.put(('log', line))

    def _browse_src(self):
        if self.feature_var.get() == 'sort_copy':
            select_folder = messagebox.askyesnocancel(
                'Copy Source Type',
                'Choose source folder?\n\nYes = source folder\nNo = one or more files',
                parent=self.root,
            )
            if select_folder is None:
                return

            if select_folder:
                picked = choose_folder(title='Select source photo folder', parent=self.root)
                if picked:
                    self.src_var.set(str(picked))
                    self.selected_copy_files = []
                    self.selected_files_var.set('No files selected')
                return

            initial = self.src_var.get().strip() or None
            picked_files = choose_files(
                title='Select files to copy and sort',
                parent=self.root,
                initialdir=initial,
            )
            if not picked_files:
                return

            self.selected_copy_files = picked_files
            self.src_var.set('')
            self.selected_files_var.set(f'{len(picked_files)} file(s) selected')
            return

        picked = choose_folder(title='Select source photo folder', parent=self.root)
        if picked:
            self.src_var.set(str(picked))
            self.selected_copy_files = []
            self.selected_files_var.set('No files selected')

    def _browse_dest(self):
        initial = self.src_var.get().strip() or None
        picked = choose_folder(
            title='Select destination root for copied/sorted photos',
            parent=self.root,
            initialdir=initial,
        )
        if picked:
            self.dest_var.set(str(picked))

    def _validate_paths(self) -> tuple[Path | None, Path | None]:
        feature = self.feature_var.get()
        src_text = self.src_var.get().strip()

        src = None
        if feature != 'sort_copy' or src_text:
            if not src_text:
                messagebox.showerror('Missing source', 'Please choose a source folder.', parent=self.root)
                return None, None
            src = Path(src_text).expanduser()
            if not src.exists() or not src.is_dir():
                messagebox.showerror('Invalid source', 'Source folder does not exist or is not a directory.', parent=self.root)
                return None, None

        if feature == 'sort_copy' and src is None and not self.selected_copy_files:
            messagebox.showerror(
                'Missing source',
                'Choose either a source folder or one/more files for copy mode.',
                parent=self.root,
            )
            return None, None

        dest = None
        if feature == 'sort_copy':
            dest_text = self.dest_var.get().strip()
            if not dest_text:
                messagebox.showerror('Missing destination', 'Please choose a destination root folder.', parent=self.root)
                return None, None
            dest = Path(dest_text).expanduser()
            if not dest.exists() or not dest.is_dir():
                messagebox.showerror('Invalid destination', 'Destination root does not exist or is not a directory.', parent=self.root)
                return None, None

        return src, dest

    def _run_feature(self, feature: str, src: Path | None, dest: Path | None, selected_files: list[Path]) -> tuple[str, Path | None]:
        if feature == 'sort':
            if src is None:
                raise ValueError('Source folder is required for in-place sorting.')
            sort_files(src)
            return 'Sorting completed.', src
        if feature == 'sort_strong':
            if src is None:
                raise ValueError('Source folder is required for strong sort.')
            sort_files(src)
            strong_sort(src)
            return 'Sorting and Strong Sort review completed.', src
        if feature == 'duplicates':
            if src is None:
                raise ValueError('Source folder is required for duplicate review.')
            find_duplicates(src)
            return 'Duplicate review completed.', src
        if feature == 'live':
            if src is None:
                raise ValueError('Source folder is required for Live Photo review.')
            handle_live(src)
            return 'Live Photo review completed.', src
        if feature == 'sort_copy':
            if dest is None:
                raise ValueError('Destination root is required for copy mode.')
            if selected_files:
                copied_to = sort_selected_files_copy(selected_files, dest)
            else:
                if src is None:
                    raise ValueError('Choose source folder or files for copy mode.')
                copied_to = sort_files_copy(src, dest)
            return f'Copied and sorted successfully:\n{copied_to}', copied_to
        raise ValueError(f'Unknown feature: {feature}')

    def _run_worker(self, feature: str, src: Path | None, dest: Path | None, selected_files: list[Path]):
        writer = _QueueWriter(self._queue_log)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                msg, open_path = self._run_feature(feature, src, dest, selected_files)
                writer.flush()
            payload = {'message': msg, 'open_path': str(open_path) if open_path else ''}
            self._event_queue.put(('done', payload))
        except Exception as exc:
            writer.flush()
            details = ''.join(traceback.format_exception_only(type(exc), exc)).strip()
            self._event_queue.put(('error', details))

    def _poll_worker_events(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'log':
                self._append_log(payload)
            elif kind == 'done':
                done_message = payload.get('message', 'Done.')
                open_path_raw = payload.get('open_path', '')
                self._append_log(done_message)
                self._set_busy(False)
                messagebox.showinfo('Done', done_message, parent=self.root)
                open_path = Path(open_path_raw).expanduser() if open_path_raw else None
                self._maybe_offer_open_folder(open_path)
                return
            elif kind == 'error':
                self._append_log(f'ERROR: {payload}')
                self._set_busy(False)
                messagebox.showerror('Error', payload, parent=self.root)
                return

        if self.is_running:
            self.root.after(120, self._poll_worker_events)

    def _run(self):
        if self.is_running:
            return

        src, dest = self._validate_paths()
        if src is None and not (self.feature_var.get() == 'sort_copy' and self.selected_copy_files):
            return

        self._append_log('---')
        self._append_log(f'Feature: {self.feature_var.get()}')
        if src:
            self._append_log(f'Source: {src}')
        if self.feature_var.get() == 'sort_copy' and self.selected_copy_files:
            self._append_log(f'Selected files: {len(self.selected_copy_files)}')
        if dest:
            self._append_log(f'Destination: {dest}')

        feature = self.feature_var.get()
        status_map = {
            'sort': 'Sorting in place...',
            'sort_strong': 'Sorting + Strong Sort review...',
            'duplicates': 'Scanning for duplicates...',
            'live': 'Reviewing Live Photos...',
            'sort_copy': 'Copying and sorting...',
        }
        run_status = status_map.get(feature, 'Running...')

        if feature in {'sort', 'sort_copy'}:
            self._set_busy(True, status=run_status)
            t = threading.Thread(target=self._run_worker, args=(feature, src, dest, self.selected_copy_files.copy()), daemon=True)
            t.start()
            self.root.after(120, self._poll_worker_events)
            return

        self._set_busy(True, status=run_status)
        writer = _DirectWriter(self._append_log)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                msg, open_path = self._run_feature(feature, src, dest, self.selected_copy_files.copy())
                writer.flush()
            self._append_log(msg)
            messagebox.showinfo('Done', msg, parent=self.root)
            self._maybe_offer_open_folder(open_path)
        except Exception as exc:
            writer.flush()
            details = ''.join(traceback.format_exception_only(type(exc), exc)).strip()
            self._append_log(f'ERROR: {details}')
            messagebox.showerror('Error', details, parent=self.root)
        finally:
            self._set_busy(False)

    def run(self):
        self.root.mainloop()


def launch_app():
    app = PhotoSorterApp()
    app.run()
