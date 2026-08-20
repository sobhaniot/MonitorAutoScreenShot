import mss
import mss.tools
import schedule
from datetime import datetime
import os
import logging
import json
import shutil
import sys
import threading
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

# Configuration
SCREENSHOT_FOLDER_NAME = 'Screenshots'
EXCEL_BACKUP_FOLDER_NAME = 'Excel Backups'
MAX_SIZE_GB = 2
MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 * 1024 * 1024  # Convert GB to Bytes
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
BACKUP_CONFIG_FILE = os.path.join(APP_DIR, 'backup_config.json')
FONT_DIR = os.path.join(RESOURCE_DIR, 'src', 'fonts')

logging.basicConfig(
    filename='screen_monitor.log',
    level=logging.ERROR,
    format='%(asctime)s | %(levelname)s | %(message)s',
)

def register_bundled_fonts():
    registered_fonts = []
    if sys.platform != 'win32':
        return registered_fonts

    add_font_resource = ctypes.windll.gdi32.AddFontResourceExW
    private_font = 0x10
    for font_filename in ('Tanha-FD.ttf', 'Tanha.ttf'):
        font_path = os.path.join(FONT_DIR, font_filename)
        if not os.path.isfile(font_path):
            logging.error("Bundled font was not found: %s", font_path)
            continue
        try:
            if add_font_resource(font_path, private_font, 0):
                registered_fonts.append(font_filename)
            else:
                logging.error("Windows could not register bundled font: %s", font_path)
        except OSError:
            logging.exception("Could not register bundled font: %s", font_path)

    return registered_fonts

def load_backup_config():
    try:
        with open(BACKUP_CONFIG_FILE, 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        logging.error("Backup configuration file was not found: %s", BACKUP_CONFIG_FILE)
        return None
    except (OSError, json.JSONDecodeError):
        logging.exception("Could not read backup configuration: %s", BACKUP_CONFIG_FILE)
        return None

    if not isinstance(config.get('files'), list):
        logging.error("The 'files' value in backup_config.json must be a list")
        return None

    return config

def save_backup_config(config):
    temporary_path = BACKUP_CONFIG_FILE + '.tmp'
    try:
        with open(temporary_path, 'w', encoding='utf-8') as config_file:
            json.dump(config, config_file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, BACKUP_CONFIG_FILE)
        return True
    except OSError:
        logging.exception("Could not save backup configuration: %s", BACKUP_CONFIG_FILE)
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            logging.exception("Could not remove incomplete configuration: %s", temporary_path)
        return False

def resolve_config_path(path):
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(path):
        path = os.path.join(APP_DIR, path)
    return os.path.abspath(path)

def get_storage_directories(config=None):
    if config is None:
        config = load_backup_config()
    if config is None:
        return None, None, None

    storage_root = config.get('backup_directory', 'accounting_backups')
    if not isinstance(storage_root, str) or not storage_root.strip():
        logging.error("The 'backup_directory' value in backup_config.json is invalid")
        return None, None, None

    storage_root = resolve_config_path(storage_root)
    return (
        storage_root,
        os.path.join(storage_root, SCREENSHOT_FOLDER_NAME),
        os.path.join(storage_root, EXCEL_BACKUP_FOLDER_NAME),
    )

def create_storage_directories(config=None):
    storage_root, screenshot_directory, excel_backup_directory = get_storage_directories(config)
    if storage_root is None:
        return False

    try:
        os.makedirs(screenshot_directory, exist_ok=True)
        os.makedirs(excel_backup_directory, exist_ok=True)
        return True
    except OSError:
        logging.exception("Could not create storage directories in: %s", storage_root)
        return False

def take_backups():
    config = load_backup_config()
    if config is None:
        return 0, 1

    _, _, backup_directory = get_storage_directories(config)
    if backup_directory is None or not create_storage_directories(config):
        return 0, 1

    backup_directory = resolve_config_path(backup_directory)
    backup_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    successful_backups = 0
    failed_backups = 0

    for item in config['files']:
        if not isinstance(item, dict):
            logging.error("Each backup item must contain 'name' and 'path': %r", item)
            failed_backups += 1
            continue

        backup_name = item.get('name')
        source = item.get('path')
        if not isinstance(backup_name, str) or not backup_name.strip():
            logging.error("A backup item has an invalid name: %r", item)
            failed_backups += 1
            continue
        if not isinstance(source, str) or not source.strip():
            logging.error("Backup path is invalid for item: %s", backup_name)
            failed_backups += 1
            continue

        source_path = resolve_config_path(source)
        if not os.path.isfile(source_path):
            logging.error("Backup source file was not found: %s", source_path)
            failed_backups += 1
            continue

        original_name = os.path.basename(source_path)
        original_stem, original_extension = os.path.splitext(original_name)
        destination_path = os.path.join(
            backup_directory,
            f"{backup_timestamp}_{original_name}",
        )
        duplicate_number = 2
        while os.path.exists(destination_path):
            destination_path = os.path.join(
                backup_directory,
                f"{backup_timestamp}_{original_stem}_{duplicate_number}{original_extension}",
            )
            duplicate_number += 1
        temporary_path = destination_path + '.tmp'

        try:
            shutil.copy2(source_path, temporary_path)
            os.replace(temporary_path, destination_path)
            successful_backups += 1
            print(f"Backup saved: {destination_path}")
        except OSError:
            failed_backups += 1
            logging.exception("Could not back up file: %s", source_path)
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                logging.exception("Could not remove incomplete backup: %s", temporary_path)

    return successful_backups, failed_backups

def take_complete_backup():
    screenshot_count = take_screenshots()
    successful_backups, failed_backups = take_backups()
    return successful_backups, failed_backups, screenshot_count

def get_backup_time():
    config = load_backup_config()
    if config is None:
        return '23:00'

    backup_time = config.get('backup_time', '23:00')
    try:
        parsed_time = datetime.strptime(backup_time, '%H:%M')
    except (TypeError, ValueError):
        logging.error("Invalid backup_time; using 23:00 instead: %r", backup_time)
        return '23:00'

    return parsed_time.strftime('%H:%M')

def manage_storage():
    _, screenshot_directory, _ = get_storage_directories()
    if screenshot_directory is None or not os.path.exists(screenshot_directory):
        return

    # Get list of all files with full path and creation time
    files = []
    try:
        directory_files = os.listdir(screenshot_directory)
    except OSError:
        logging.exception("Could not read screenshot directory: %s", screenshot_directory)
        return

    for f in directory_files:
        full_path = os.path.join(screenshot_directory, f)
        try:
            if os.path.isfile(full_path):
                files.append((full_path, os.path.getctime(full_path)))
        except OSError:
            logging.exception("Could not inspect file: %s", full_path)

    # Sort files by time (oldest to newest)
    files.sort(key=lambda x: x[1])

    # Calculate current total size of the directory
    files_with_sizes = []
    total_size = 0
    for file_path, created_at in files:
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            logging.exception("Could not get file size: %s", file_path)
            continue

        files_with_sizes.append((file_path, created_at, file_size))
        total_size += file_size

    if total_size > MAX_SIZE_BYTES:
        print(f"Directory size ({total_size / (1024 ** 3):.2f} GB) exceeds limit. Starting cleanup...")

        for file_path, _, file_size in files_with_sizes:
            if total_size <= MAX_SIZE_BYTES:
                break

            try:
                os.remove(file_path)
            except OSError:
                logging.exception("Could not delete old screenshot: %s", file_path)
                continue

            total_size -= file_size
            print(f"Deleted old file: {os.path.basename(file_path)}")

        if total_size <= MAX_SIZE_BYTES:
            print("Cleanup complete. Storage usage is now under 2 GB.")
        else:
            logging.error(
                "Cleanup finished, but storage is still above the limit: %.2f GB",
                total_size / (1024 ** 3),
            )

def take_screenshots():
    successful_screenshots = 0
    _, screenshot_directory, _ = get_storage_directories()
    if screenshot_directory is None:
        return 0

    # Create directory for screenshots if it doesn't exist
    try:
        os.makedirs(screenshot_directory, exist_ok=True)
    except OSError:
        logging.exception("Could not create screenshot directory: %s", screenshot_directory)
        return 0

    try:
        with mss.mss() as sct:
            # Get list of monitors
            # sct.monitors[0] is the "all-in-one" monitor, so we use [1:] for individual ones
            for i, monitor in enumerate(sct.monitors[1:], 1):
                try:
                    # Capture the screen of monitor i
                    sct_img = sct.grab(monitor)

                    # Generate filename
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    filename = os.path.join(screenshot_directory, f"{timestamp}M{i}.png")

                    # Save file using mss internal tools
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=filename)
                    successful_screenshots += 1
                    print(f"Screenshot saved from Monitor {i}: {filename}")
                except Exception:
                    logging.exception("Could not capture or save screenshot from monitor %s", i)
    except Exception:
        logging.exception("Could not initialize screen capture")

    return successful_screenshots

class BackupApp:
    BACKGROUND = '#f6f8fc'
    CARD = '#ffffff'
    PRIMARY = '#4f46e5'
    PRIMARY_DARK = '#4338ca'
    PRIMARY_LIGHT = '#eef2ff'
    BORDER = '#e2e8f0'
    TEXT = '#111827'
    MUTED = '#64748b'
    DANGER = '#dc2626'

    def __init__(self, root):
        self.root = root
        self.files = []
        self.hour_var = tk.StringVar(value='23')
        self.minute_var = tk.StringVar(value='00')
        self.destination_var = tk.StringVar()
        self.status_var = tk.StringVar(value='برنامه آماده است')
        self.save_status_var = tk.StringVar(value='تنظیمات به‌صورت خودکار ذخیره می‌شوند')
        self.activity_var = tk.StringVar(value='● برنامه در حال راه‌اندازی است...')
        self.last_screenshot_time = None
        self.last_backup_time = None
        registered_fonts = register_bundled_fonts()
        available_fonts = set(tkfont.families(self.root))
        self.font_family = next(
            (
                font_name
                for font_name in ('Tanha FD', 'Tanha', 'Tahoma')
                if font_name in available_fonts
            ),
            'Tanha FD' if 'Tanha-FD.ttf' in registered_fonts else 'Tahoma',
        )

        self.root.title('Screen Monitor | مدیریت بکاپ')
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(960, max(720, screen_width - 40))
        window_height = min(700, max(520, screen_height - 80))
        position_x = max(0, (screen_width - window_width) // 2)
        position_y = max(0, (screen_height - window_height) // 2)
        self.root.geometry(
            f'{window_width}x{window_height}+{position_x}+{position_y}'
        )
        self.root.minsize(
            min(720, max(640, screen_width - 20)),
            min(520, max(480, screen_height - 60)),
        )
        self.root.configure(bg=self.BACKGROUND)
        self.root.protocol('WM_DELETE_WINDOW', self.root.destroy)
        self._set_icon()
        self._configure_styles()
        self._build_ui()
        self._load_settings_into_ui()
        self._configure_schedules()

        self.root.after(1000, self._run_scheduler)
        self.root.after(
            500,
            lambda: self._run_in_background(take_screenshots, self._screenshot_finished),
        )
        self.root.after(700, lambda: self._run_in_background(manage_storage))
        self.root.after(1000, self._update_activity_status)

    def _set_icon(self):
        icon_candidates = [
            os.path.join(RESOURCE_DIR, 'src', 'icon.ico'),
            os.path.join(APP_DIR, 'icon.ico'),
            os.path.join(APP_DIR, 'src', 'icon.ico'),
        ]
        for icon_path in icon_candidates:
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                except tk.TclError:
                    pass
                break

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure('App.TFrame', background=self.BACKGROUND)
        style.configure(
            'Card.TFrame',
            background=self.CARD,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            relief='solid',
            borderwidth=1,
        )
        style.configure(
            'Title.TLabel',
            background=self.BACKGROUND,
            foreground=self.TEXT,
            font=(self.font_family, 19, 'bold'),
        )
        style.configure(
            'Subtitle.TLabel',
            background=self.BACKGROUND,
            foreground=self.MUTED,
            font=(self.font_family, 9),
        )
        style.configure(
            'CardTitle.TLabel',
            background=self.CARD,
            foreground=self.TEXT,
            font=(self.font_family, 11, 'bold'),
        )
        style.configure(
            'CardText.TLabel',
            background=self.CARD,
            foreground=self.MUTED,
            font=(self.font_family, 9),
        )
        style.configure(
            'Primary.TButton',
            font=(self.font_family, 9, 'bold'),
            padding=(16, 9),
            foreground='#ffffff',
            background=self.PRIMARY,
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            'Primary.TButton',
            background=[('pressed', self.PRIMARY_DARK), ('active', '#6366f1')],
            foreground=[('disabled', '#c7d2fe'), ('!disabled', '#ffffff')],
        )
        style.configure(
            'Secondary.TButton',
            font=(self.font_family, 9),
            padding=(14, 8),
            foreground=self.TEXT,
            background='#ffffff',
            bordercolor=self.BORDER,
            borderwidth=1,
            focusthickness=0,
        )
        style.map('Secondary.TButton', background=[('active', '#f1f5f9')])
        style.configure(
            'Danger.TButton',
            font=(self.font_family, 9),
            padding=(14, 8),
            foreground=self.DANGER,
            background='#fff1f2',
            bordercolor='#fecdd3',
            borderwidth=1,
            focusthickness=0,
        )
        style.map('Danger.TButton', background=[('active', '#ffe4e6')])
        style.configure(
            'Modern.TEntry',
            padding=8,
            fieldbackground='#f8fafc',
            foreground=self.TEXT,
            bordercolor=self.BORDER,
        )
        style.configure(
            'Treeview',
            font=(self.font_family, 9),
            rowheight=34,
            background='#ffffff',
            fieldbackground='#ffffff',
            foreground=self.TEXT,
            borderwidth=0,
        )
        style.map('Treeview', background=[('selected', '#e0e7ff')], foreground=[('selected', self.TEXT)])
        style.configure(
            'Treeview.Heading',
            font=(self.font_family, 9, 'bold'),
            background='#f8fafc',
            foreground=self.MUTED,
            relief='flat',
            padding=(8, 8),
        )

    def _build_ui(self):
        container = ttk.Frame(self.root, style='App.TFrame', padding=(22, 16))
        container.pack(fill='both', expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(
            container,
            text='مدیریت بکاپ فایل‌های حسابداری',
            style='Title.TLabel',
            anchor='e',
        ).grid(row=0, column=0, sticky='ew')
        ttk.Label(
            container,
            text='فایل‌ها، پوشه مقصد و ساعت بکاپ روزانه را از اینجا انتخاب کنید.',
            style='Subtitle.TLabel',
            anchor='e',
        ).grid(row=1, column=0, sticky='ew', pady=(4, 12))

        settings_card = ttk.Frame(container, style='Card.TFrame', padding=12)
        settings_card.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        settings_card.columnconfigure(0, weight=1)

        ttk.Label(settings_card, text='تنظیمات بکاپ', style='CardTitle.TLabel', anchor='e').grid(
            row=0, column=0, columnspan=4, sticky='ew', pady=(0, 9)
        )

        ttk.Button(
            settings_card,
            text='انتخاب پوشه',
            command=self._choose_destination,
            style='Secondary.TButton',
        ).grid(row=1, column=0, padx=(0, 10), sticky='w')
        destination_entry = ttk.Entry(
            settings_card,
            textvariable=self.destination_var,
            state='readonly',
            justify='right',
            font=(self.font_family, 9),
            style='Modern.TEntry',
        )
        destination_entry.grid(row=1, column=1, columnspan=2, sticky='ew', padx=(0, 12))
        ttk.Label(settings_card, text='پوشه اصلی ذخیره‌سازی', style='CardText.TLabel').grid(
            row=1, column=3, sticky='e'
        )
        settings_card.columnconfigure(1, weight=1)

        time_frame = tk.Frame(
            settings_card,
            bg=self.PRIMARY_LIGHT,
            highlightbackground='#c7d2fe',
            highlightthickness=1,
            bd=0,
            padx=8,
            pady=4,
        )
        time_frame.grid(
            row=2,
            column=1,
            columnspan=2,
            sticky='e',
            pady=(8, 0),
            padx=(0, 12),
        )

        time_controls = tk.Frame(time_frame, bg=self.PRIMARY_LIGHT)
        time_controls.pack()
        self._create_time_control(time_controls, self.hour_var, 60, 'ساعت').pack(side='left')
        tk.Label(
            time_controls,
            text=':',
            bg=self.PRIMARY_LIGHT,
            fg=self.PRIMARY,
            font=(self.font_family, 16, 'bold'),
            padx=5,
        ).pack(side='left')
        self._create_time_control(time_controls, self.minute_var, 5, 'دقیقه').pack(side='left')
        ttk.Label(settings_card, text='زمان بکاپ روزانه', style='CardText.TLabel').grid(
            row=2, column=3, sticky='e', pady=(8, 0)
        )
        ttk.Label(
            settings_card,
            textvariable=self.save_status_var,
            style='CardText.TLabel',
            anchor='e',
        ).grid(row=3, column=0, columnspan=4, sticky='ew', pady=(7, 0))

        files_card = ttk.Frame(container, style='Card.TFrame', padding=14)
        files_card.grid(row=3, column=0, sticky='nsew', pady=(0, 10))
        files_card.columnconfigure(0, weight=1)
        files_card.rowconfigure(2, weight=1)

        ttk.Label(files_card, text='فایل‌های انتخاب‌شده', style='CardTitle.TLabel', anchor='e').grid(
            row=0, column=0, sticky='ew'
        )
        ttk.Label(
            files_card,
            text='می‌توانید چند فایل را هم‌زمان انتخاب کنید.',
            style='CardText.TLabel',
            anchor='e',
        ).grid(row=1, column=0, sticky='ew', pady=(3, 12))

        tree_frame = ttk.Frame(files_card, style='Card.TFrame')
        tree_frame.grid(row=2, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.files_tree = ttk.Treeview(
            tree_frame,
            columns=('path', 'name'),
            show='headings',
            selectmode='extended',
            height=7,
        )
        self.files_tree.heading('name', text='نام فایل', anchor='e')
        self.files_tree.heading('path', text='مسیر فایل', anchor='e')
        self.files_tree.column('name', width=190, minwidth=140, anchor='e')
        self.files_tree.column('path', width=570, minwidth=300, anchor='e')
        self.files_tree.tag_configure('empty', foreground=self.MUTED)
        self.files_tree.grid(row=0, column=0, sticky='nsew')

        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.files_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.files_tree.configure(yscrollcommand=scrollbar.set)

        file_buttons = ttk.Frame(files_card, style='Card.TFrame')
        file_buttons.grid(row=3, column=0, sticky='ew', pady=(12, 0))
        ttk.Button(
            file_buttons,
            text='حذف انتخاب‌شده‌ها',
            command=self._remove_selected_files,
            style='Danger.TButton',
        ).pack(side='left')
        ttk.Button(
            file_buttons,
            text='＋ انتخاب فایل‌های اکسل',
            command=self._add_files,
            style='Primary.TButton',
        ).pack(side='right')

        actions = ttk.Frame(container, style='App.TFrame')
        actions.grid(row=4, column=0, sticky='ew')
        ttk.Label(
            actions,
            textvariable=self.status_var,
            style='Subtitle.TLabel',
            anchor='w',
        ).pack(side='left', fill='x', expand=True)
        ttk.Button(
            actions,
            text='بکاپ الآن',
            command=self._backup_now,
            style='Secondary.TButton',
        ).pack(side='right', padx=(8, 0))
        ttk.Button(
            actions,
            text='ذخیره تنظیمات',
            command=self._save_settings,
            style='Primary.TButton',
        ).pack(side='right')

        ttk.Separator(container, orient='horizontal').grid(
            row=5, column=0, sticky='ew', pady=(10, 7)
        )
        self.activity_label = tk.Label(
            container,
            textvariable=self.activity_var,
            bg=self.BACKGROUND,
            fg='#15803d',
            font=(self.font_family, 9, 'bold'),
            anchor='e',
        )
        self.activity_label.grid(row=6, column=0, sticky='ew')

    def _load_settings_into_ui(self):
        config = load_backup_config() or {
            'backup_time': '23:00',
            'backup_directory': 'accounting_backups',
            'files': [],
        }
        backup_time = config.get('backup_time', '23:00')
        try:
            parsed_time = datetime.strptime(backup_time, '%H:%M')
        except (TypeError, ValueError):
            parsed_time = datetime.strptime('23:00', '%H:%M')

        self.hour_var.set(parsed_time.strftime('%H'))
        self.minute_var.set(parsed_time.strftime('%M'))

        destination = config.get('backup_directory', 'accounting_backups')
        if isinstance(destination, str) and destination.strip():
            self.destination_var.set(resolve_config_path(destination))

        for item in config.get('files', []):
            if not isinstance(item, dict):
                continue
            name = item.get('name')
            path = item.get('path')
            if isinstance(name, str) and isinstance(path, str):
                self.files.append({'name': name, 'path': resolve_config_path(path)})

        create_storage_directories(config)
        self._refresh_files_tree()

    def _refresh_files_tree(self):
        for row in self.files_tree.get_children():
            self.files_tree.delete(row)
        if not self.files:
            self.files_tree.insert(
                '',
                'end',
                iid='empty',
                values=('از دکمه «انتخاب فایل‌های اکسل» استفاده کنید', 'هنوز فایلی انتخاب نشده'),
                tags=('empty',),
            )
        for index, item in enumerate(self.files):
            self.files_tree.insert('', 'end', iid=str(index), values=(item['path'], item['name']))
        self.status_var.set(f'{len(self.files)} فایل برای بکاپ انتخاب شده است')

    def _create_time_control(self, parent, variable, step_minutes, caption):
        control = tk.Frame(parent, bg=self.PRIMARY_LIGHT)
        tk.Label(
            control,
            text=caption,
            bg=self.PRIMARY_LIGHT,
            fg=self.MUTED,
            font=(self.font_family, 8),
        ).pack(side='left', padx=(0, 5))

        value_row = tk.Frame(control, bg=self.PRIMARY_LIGHT)
        value_row.pack(side='left')
        for symbol, direction in (('−', -1), ('＋', 1)):
            button = tk.Button(
                value_row,
                text=symbol,
                command=lambda d=direction: self._change_time(d * step_minutes),
                bg='#ffffff',
                activebackground='#c7d2fe',
                fg=self.PRIMARY,
                activeforeground=self.PRIMARY_DARK,
                font=(self.font_family, 10, 'bold'),
                relief='flat',
                bd=0,
                width=2,
                pady=1,
                cursor='hand2',
            )
            if direction < 0:
                button.pack(side='left')
            else:
                button.pack(side='right')

        value_label = tk.Label(
            value_row,
            textvariable=variable,
            bg=self.PRIMARY_LIGHT,
            fg=self.TEXT,
            font=(self.font_family, 15, 'bold'),
            width=3,
        )
        value_label.pack(side='left', padx=2)
        return control

    def _change_time(self, delta_minutes):
        current_minutes = int(self.hour_var.get()) * 60 + int(self.minute_var.get())
        updated_minutes = (current_minutes + delta_minutes) % (24 * 60)
        self.hour_var.set(f'{updated_minutes // 60:02d}')
        self.minute_var.set(f'{updated_minutes % 60:02d}')
        self._auto_save_settings()

    def _choose_destination(self):
        initial_directory = self.destination_var.get() or APP_DIR
        selected = filedialog.askdirectory(
            title='انتخاب پوشه ذخیره بکاپ‌ها',
            initialdir=initial_directory if os.path.isdir(initial_directory) else APP_DIR,
        )
        if selected:
            self.destination_var.set(os.path.abspath(selected))
            self._auto_save_settings()

    def _add_files(self):
        selected_files = filedialog.askopenfilenames(
            title='انتخاب فایل‌های اکسل برای بکاپ',
            filetypes=[
                ('Excel files', '*.xlsx *.xls *.xlsm *.xlsb'),
                ('All files', '*.*'),
            ],
        )
        existing_paths = {os.path.normcase(item['path']) for item in self.files}
        existing_names = {item['name'] for item in self.files}

        for selected_path in selected_files:
            normalized_path = os.path.normcase(os.path.abspath(selected_path))
            if normalized_path in existing_paths:
                continue

            base_name = os.path.splitext(os.path.basename(selected_path))[0]
            unique_name = base_name
            suffix = 2
            while unique_name in existing_names:
                unique_name = f'{base_name}_{suffix}'
                suffix += 1

            self.files.append({'name': unique_name, 'path': os.path.abspath(selected_path)})
            existing_paths.add(normalized_path)
            existing_names.add(unique_name)

        self._refresh_files_tree()
        if selected_files:
            self._auto_save_settings()

    def _remove_selected_files(self):
        selected_indexes = sorted(
            (
                int(item_id)
                for item_id in self.files_tree.selection()
                if item_id.isdigit()
            ),
            reverse=True,
        )
        for index in selected_indexes:
            del self.files[index]
        self._refresh_files_tree()
        if selected_indexes:
            self._auto_save_settings()

    def _build_config_from_ui(self):
        return {
            'backup_time': f'{self.hour_var.get()}:{self.minute_var.get()}',
            'backup_directory': self.destination_var.get(),
            'files': self.files,
        }

    def _auto_save_settings(self):
        config = self._build_config_from_ui()
        if save_backup_config(config) and create_storage_directories(config):
            self._schedule_backup_job()
            saved_at = datetime.now().strftime('%H:%M:%S')
            self.save_status_var.set(f'✓ تنظیمات خودکار ذخیره شد — {saved_at}')
        else:
            self.save_status_var.set('✕ ذخیره تنظیمات ناموفق بود؛ گزارش خطا را بررسی کنید')

    def _persist_settings(self, show_confirmation=True):
        if not self.destination_var.get():
            messagebox.showwarning('پوشه مقصد', 'ابتدا پوشه ذخیره بکاپ‌ها را انتخاب کنید.')
            return False

        if not self.files:
            messagebox.showwarning('فایل‌های بکاپ', 'حداقل یک فایل برای بکاپ انتخاب کنید.')
            return False

        config = self._build_config_from_ui()
        if not save_backup_config(config) or not create_storage_directories(config):
            messagebox.showerror('خطا', 'ذخیره تنظیمات انجام نشد. فایل گزارش خطا را بررسی کنید.')
            return False

        self._schedule_backup_job()
        self.status_var.set(f'تنظیمات ذخیره شد؛ بکاپ روزانه ساعت {get_backup_time()}')
        self.save_status_var.set(
            f"✓ تنظیمات ذخیره شد — {datetime.now().strftime('%H:%M:%S')}"
        )
        if show_confirmation:
            messagebox.showinfo('ذخیره شد', 'تنظیمات بکاپ با موفقیت ذخیره شد.')
        return True

    def _save_settings(self):
        self._persist_settings(show_confirmation=True)

    def _backup_now(self):
        if not self._persist_settings(show_confirmation=False):
            return
        self.status_var.set('بکاپ اکسل و عکس‌گیری در حال انجام است...')
        self._run_in_background(take_complete_backup, self._backup_finished)

    def _backup_finished(self, result):
        successful, failed, screenshot_count = result if result is not None else (0, 1, 0)
        if failed == 0 and screenshot_count > 0:
            self.last_backup_time = datetime.now()
            if screenshot_count:
                self.last_screenshot_time = datetime.now()
            self.status_var.set(
                f'بکاپ {successful} فایل و عکس‌گیری از {screenshot_count} مانیتور انجام شد'
            )
            messagebox.showinfo(
                'بکاپ کامل شد',
                f'از {successful} فایل اکسل بکاپ گرفته شد و '
                f'از {screenshot_count} مانیتور عکس گرفته شد.',
            )
        else:
            if screenshot_count:
                self.last_screenshot_time = datetime.now()
            self.status_var.set(
                f'{successful} بکاپ موفق، {failed} خطا، {screenshot_count} اسکرین‌شات'
            )
            messagebox.showwarning(
                'بکاپ با خطا همراه بود',
                f'{successful} فایل موفق، {failed} فایل ناموفق و '
                f'{screenshot_count} اسکرین‌شات ثبت شد. گزارش خطا را بررسی کنید.',
            )

    def _scheduled_backup_finished(self, result):
        successful, failed = result if result is not None else (0, 1)
        if successful:
            self.last_backup_time = datetime.now()
        if failed == 0:
            self.status_var.set(f'بکاپ خودکار {successful} فایل انجام شد')
        else:
            self.status_var.set(f'بکاپ خودکار: {successful} موفق، {failed} خطا')

    def _screenshot_finished(self, result):
        screenshot_count = result or 0
        if screenshot_count:
            self.last_screenshot_time = datetime.now()
            self.status_var.set(f'از {screenshot_count} مانیتور عکس گرفته شد')
        else:
            self.status_var.set('عکس‌گیری انجام نشد؛ گزارش خطا را بررسی کنید')

    def _run_in_background(self, function, on_complete=None):
        def worker():
            result = None
            try:
                result = function()
            except Exception:
                logging.exception("Unexpected background task error: %s", function.__name__)
            if on_complete is not None:
                try:
                    self.root.after(0, lambda: on_complete(result))
                except tk.TclError:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _configure_schedules(self):
        schedule.clear()
        schedule.every(10).minutes.do(
            lambda: self._run_in_background(take_screenshots, self._screenshot_finished)
        ).tag('screenshots')
        schedule.every().day.at('00:00').do(
            lambda: self._run_in_background(manage_storage)
        ).tag('storage')
        self._schedule_backup_job()

    def _schedule_backup_job(self):
        schedule.clear('backup')
        schedule.every().day.at(get_backup_time()).do(
            lambda: self._run_in_background(take_backups, self._scheduled_backup_finished)
        ).tag('backup')

    def _get_next_run_text(self, tag):
        jobs = schedule.get_jobs(tag)
        if not jobs or jobs[0].next_run is None:
            return 'نامشخص'
        next_run = jobs[0].next_run
        if next_run.date() == datetime.now().date():
            return next_run.strftime('%H:%M')
        return next_run.strftime('%Y-%m-%d %H:%M')

    def _update_activity_status(self):
        backup_next = self._get_next_run_text('backup')
        screenshot_next = self._get_next_run_text('screenshots')
        last_screenshot = (
            self.last_screenshot_time.strftime('%H:%M:%S')
            if self.last_screenshot_time
            else 'در انتظار اولین اجرا'
        )
        self.activity_var.set(
            f'● برنامه فعال است  |  بکاپ بعدی: {backup_next}'
            f'  |  عکس بعدی: {screenshot_next}'
            f'  |  آخرین عکس: {last_screenshot}'
        )
        try:
            self.root.after(1000, self._update_activity_status)
        except tk.TclError:
            pass

    def _run_scheduler(self):
        try:
            schedule.run_pending()
        except Exception:
            logging.exception("Unexpected error while running scheduled tasks")
        try:
            self.root.after(1000, self._run_scheduler)
        except tk.TclError:
            pass


def main():
    root = tk.Tk()
    BackupApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
