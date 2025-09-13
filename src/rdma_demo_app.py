#!/usr/bin/env python3
# rdma_demo_app_with_rdmacheck.py  -- RDMA GUI with RDMA-check/load & IP detect
# Integrates RDMA module/device checks, auto-load, and IP detection into your existing app.

import os
import threading
import subprocess
import time
import hashlib
import socket
import shutil
import sys

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkFont
from tkinter.simpledialog import askstring

import psutil
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---------- Utilities ----------

def file_checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def human_readable_size(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

def run_command(cmd, check=False, capture_output=True, text=True):
    """Helper wrapper for subprocess.run that returns CompletedProcess."""
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
    except FileNotFoundError as e:
        # command not found
        cp = subprocess.CompletedProcess(cmd, 127, stdout="", stderr=str(e))
        return cp

# ---------- Main App ----------

class ModernRDMAApp:
    def __init__(self):
        # base dir (directory containing this script)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.logs_dir = os.path.join(self.base_dir, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)

        # root window
        self.root = tk.Tk()
        self.root.title("RDMA File Transfer Demo")
        self.root.geometry("980x820")
        self.root.configure(bg='#0f0f23')
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # plot window
        self.plot_window = None

        # colors & fonts
        self.colors = {
            'bg_primary': '#0f0f23',
            'bg_secondary': '#1a1a2e',
            'bg_tertiary': '#16213e',
            'accent_blue': '#00d4ff',
            'accent_purple': '#8b5cf6',
            'accent_green': '#10b981',
            'text_primary': '#ffffff',
            'text_secondary': '#d1d5db',
            'hover_light': '#2a2a40',
            'border': '#4b5563'
        }

        self.setup_styles()

        # state
        self.selected_file = None
        self.tcp_server_process = None
        self.rdma_server_process = None
        self.last_tcp_time = 0.0
        self.last_rdma_time = 0.0

        # UI build
        self.setup_ui()

    def setup_styles(self):
        self.fonts = {
            'title': tkFont.Font(family='Helvetica', size=22, weight='bold'),
            'subtitle': tkFont.Font(family='Helvetica', size=13),
            'button': tkFont.Font(family='Helvetica', size=11, weight='bold'),
            'label': tkFont.Font(family='Helvetica', size=10),
            'small': tkFont.Font(family='Helvetica', size=9)
        }

    def setup_ui(self):
        # main frame
        self.main_frame = tk.Frame(self.root, bg=self.colors['bg_primary'], highlightbackground=self.colors['border'], highlightthickness=1)
        self.main_frame.pack(fill='both', expand=True, padx=20, pady=20)

        # header
        self.create_header(self.main_frame)

        # file section + ip + servers + transfer + status + plot
        self.create_file_section(self.main_frame)
        self.create_ip_section(self.main_frame)
        self.create_server_section(self.main_frame)
        self.create_transfer_section(self.main_frame)
        self.create_status_section(self.main_frame)
        self.create_plot_frame(self.main_frame)

    # ----- header -----
    def create_header(self, parent):
        header = tk.Frame(parent, bg=self.colors['bg_primary'])
        header.pack(fill='x', pady=(0,12))
        tk.Label(header, text="⚡ RDMA File Transfer", font=self.fonts['title'],
                 bg=self.colors['bg_primary'], fg=self.colors['accent_blue']).pack(anchor='w')
        tk.Label(header, text="Compare TCP vs RDMA transfers (local demo). Added: RDMA-check/load & IP detect.",
                 font=self.fonts['subtitle'],
                 bg=self.colors['bg_primary'], fg=self.colors['text_secondary']).pack(anchor='w')

    # ----- file selection -----
    def create_file_section(self, parent):
        file_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        file_frame.pack(fill='x', pady=10)
        inner = tk.Frame(file_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=16, pady=16)

        tk.Label(inner, text="📁 File Selection", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        btn = tk.Button(inner, text="Choose File", font=self.fonts['button'],
                        bg=self.colors['accent_blue'], fg='white',
                        command=self.select_file, relief='flat', bd=0, padx=16, pady=8,
                        highlightthickness=2, highlightbackground=self.colors['hover_light'], cursor='hand2')
        btn.pack(anchor='w', pady=(10,8))

        self.file_info_label = tk.Label(inner, text="No file selected", font=self.fonts['label'],
                                        bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'], wraplength=880, justify='left')
        self.file_info_label.pack(anchor='w')

    def select_file(self):
        path = filedialog.askopenfilename(title="Select file to transfer")
        if not path:
            return
        self.selected_file = path
        size = os.path.getsize(path)
        self.file_info_label.config(text=f"{os.path.basename(path)} — {human_readable_size(size)}\n{path}")
        self.update_status(f"Selected file: {os.path.basename(path)} ({human_readable_size(size)})")

        # enable send buttons
        self.tcp_btn.configure(state='normal')
        self.rdma_btn.configure(state='normal')

    # ----- IP entry -----
    def create_ip_section(self, parent):
        ip_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        ip_frame.pack(fill='x', pady=10)
        inner = tk.Frame(ip_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=16, pady=12)

        tk.Label(inner, text="🌐 Server IP (enter receiver IP)", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        row = tk.Frame(inner, bg=self.colors['bg_secondary'])
        row.pack(fill='x', pady=(8,0))

        self.ip_entry = tk.Entry(row, font=self.fonts['label'], bg=self.colors['bg_tertiary'],
                                 fg=self.colors['text_primary'], insertbackground='white')
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(side='left', fill='x', expand=True)

        detect_btn = tk.Button(row, text="Detect IP", font=self.fonts['label'],
                               bg=self.colors['accent_blue'], fg='white',
                               command=self.on_detect_ip, relief='flat', bd=0, padx=10, pady=6,
                               highlightthickness=1, highlightbackground=self.colors['hover_light'], cursor='hand2')
        detect_btn.pack(side='left', padx=(8,0))

        check_rdma_btn = tk.Button(row, text="Check RDMA", font=self.fonts['label'],
                                   bg=self.colors['accent_green'], fg='white',
                                   command=self.on_check_rdma_clicked, relief='flat', bd=0, padx=10, pady=6,
                                   highlightthickness=1, highlightbackground=self.colors['hover_light'], cursor='hand2')
        check_rdma_btn.pack(side='left', padx=(8,0))

    # ----- server start section -----
    def create_server_section(self, parent):
        server_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        server_frame.pack(fill='x', pady=10)
        inner = tk.Frame(server_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=16, pady=12)

        tk.Label(inner, text="🖥️ Start Server (local demo)", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        # two rows of buttons for better spacing
        btn_row1 = tk.Frame(inner, bg=self.colors['bg_secondary'])
        btn_row1.pack(anchor='w', pady=(10,4))
        btn_row2 = tk.Frame(inner, bg=self.colors['bg_secondary'])
        btn_row2.pack(anchor='w', pady=(4,0))

        self.start_tcp_server_btn = tk.Button(btn_row1, text="Start TCP Server", font=self.fonts['button'],
                                              bg=self.colors['accent_purple'], fg='white',
                                              command=self.start_tcp_server, relief='flat', bd=0,
                                              padx=14, pady=8, highlightthickness=2,
                                              highlightbackground=self.colors['hover_light'], cursor='hand2')
        self.start_tcp_server_btn.pack(side='left', padx=(0,12))

        self.stop_tcp_server_btn = tk.Button(btn_row1, text="Stop TCP Server", font=self.fonts['button'],
                                             bg=self.colors['hover_light'], fg='white',
                                             command=self.stop_tcp_server, relief='flat', bd=0,
                                             padx=14, pady=8, highlightthickness=2,
                                             highlightbackground=self.colors['accent_purple'], cursor='hand2')
        self.stop_tcp_server_btn.pack(side='left', padx=(0,12))

        self.start_rdma_server_btn = tk.Button(btn_row2, text="Start RDMA Server", font=self.fonts['button'],
                                               bg=self.colors['accent_green'], fg='white',
                                               command=self.start_rdma_server, relief='flat', bd=0,
                                               padx=14, pady=8, highlightthickness=2,
                                               highlightbackground=self.colors['hover_light'], cursor='hand2')
        self.start_rdma_server_btn.pack(side='left', padx=(0,12))

        self.stop_rdma_server_btn = tk.Button(btn_row2, text="Stop RDMA Server", font=self.fonts['button'],
                                              bg=self.colors['hover_light'], fg='white',
                                              command=self.stop_rdma_server, relief='flat', bd=0,
                                              padx=14, pady=8, highlightthickness=2,
                                              highlightbackground=self.colors['accent_green'], cursor='hand2')
        self.stop_rdma_server_btn.pack(side='left', padx=(0,12))

    # ----- transfer section -----
    def create_transfer_section(self, parent):
        transfer_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        transfer_frame.pack(fill='x', pady=10)
        inner = tk.Frame(transfer_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=16, pady=12)

        tk.Label(inner, text="🚀 Transfer Methods", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        btn_row = tk.Frame(inner, bg=self.colors['bg_secondary'])
        btn_row.pack(anchor='w', pady=(10,0))

        self.tcp_btn = tk.Button(btn_row, text="📡 Send via TCP", font=self.fonts['button'],
                                 bg=self.colors['accent_purple'], fg='white',
                                 command=self.start_tcp_transfer_thread, relief='flat', bd=0,
                                 padx=16, pady=10, highlightthickness=2,
                                 highlightbackground=self.colors['hover_light'], cursor='hand2', state='disabled')
        self.tcp_btn.pack(side='left', padx=(0,12))

        self.rdma_btn = tk.Button(btn_row, text="⚡ Send via RDMA", font=self.fonts['button'],
                                  bg=self.colors['accent_green'], fg='white',
                                  command=self.start_rdma_transfer_thread, relief='flat', bd=0,
                                  padx=16, pady=10, highlightthickness=2,
                                  highlightbackground=self.colors['hover_light'], cursor='hand2', state='disabled')
        self.rdma_btn.pack(side='left', padx=(0,12))

        tk.Label(inner, text="(Start server locally or point to remote server IP)", font=self.fonts['small'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(8,0))

    # ----- status section -----
    def create_status_section(self, parent):
        status_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        status_frame.pack(fill='both', expand=False, pady=10)
        inner = tk.Frame(status_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='both', padx=16, pady=12)

        tk.Label(inner, text="📊 Transfer Status", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        self.status_text = tk.Text(inner, height=8, bg=self.colors['bg_tertiary'], fg=self.colors['text_primary'],
                                   font=self.fonts['small'], bd=0, relief='flat', padx=12, pady=12, wrap='word')
        self.status_text.pack(fill='both', pady=(10,0))
        self.update_status("Ready. Select a file and enter server IP (default 127.0.0.1). Use 'Detect IP' or 'Check RDMA' as needed.")

    # ----- plot frame -----
    def create_plot_frame(self, parent):
        plot_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], highlightbackground=self.colors['border'], highlightthickness=1)
        plot_frame.pack(fill='both', expand=True, pady=10)
        inner = tk.Frame(plot_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='both', padx=16, pady=12, expand=True)

        tk.Label(inner, text="📈 Performance Chart", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')
        tk.Label(inner, text="Run transfers to view performance comparison in a separate window", font=self.fonts['small'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(8,0))

    # ----- status helper -----
    def update_status(self, message):
        ts = time.strftime("%H:%M:%S")
        self.status_text.configure(state='normal')
        self.status_text.insert('end', f"[{ts}] {message}\n")
        self.status_text.configure(state='disabled')
        self.status_text.see('end')

    # ----- RDMA check/load helpers -----
    def detect_default_netdev(self):
        cp = run_command(['ip', '-o', '-4', 'route', 'show', 'to', 'default'])
        if cp.returncode != 0 or not cp.stdout.strip():
            # fallback to first active interface with IPv4
            addrs = psutil.net_if_addrs()
            for iface, addrls in addrs.items():
                for addr in addrls:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        return iface
            return None
        # parse default route output: "<proto> ... dev <iface> ..."
        parts = cp.stdout.strip().split()
        if 'dev' in parts:
            i = parts.index('dev')
            if i + 1 < len(parts):
                return parts[i+1]
        return None

    def check_rdma_status(self):
        """Return dict with module_loaded(bool), rxe_exists(bool), ibv_devices(list)."""
        status = {
            'module_loaded': False,
            'rxe_exists': False,
            'ibv_list': []
        }
        # Check module via lsmod
        cp = run_command(['lsmod'])
        if cp.returncode == 0 and 'rdma_rxe' in cp.stdout:
            status['module_loaded'] = True

        # rdma link show
        cp2 = run_command(['rdma', 'link', 'show'])
        if cp2.returncode == 0 and 'rxe' in cp2.stdout:
            # crude check for rxe0 or any rxe
            status['rxe_exists'] = True

        # ibv_devices
        cp3 = run_command(['ibv_devices'])
        if cp3.returncode == 0:
            lines = cp3.stdout.strip().splitlines()
            # skip header if present
            for line in lines[1:]:
                line = line.strip()
                if line:
                    # first column is device name
                    parts = line.split()
                    status['ibv_list'].append(parts[0])
        return status

    def _require_sudo_prefix(self):
        # If running as root, no sudo needed
        try:
            euid = os.geteuid()
        except AttributeError:
            euid = 0  # Windows won't reach here for RDMA use-case
        if euid == 0:
            return []
        else:
            return ['sudo']

    def load_rdma_module_and_create_rxe(self):
        """Attempt to load rdma_rxe and create rxe0 bound to default netdev."""
        netdev = self.detect_default_netdev()
        if not netdev:
            self.update_status("❌ Cannot detect default network device for RXE binding.")
            return False, "Cannot detect netdev"

        sudo_pref = self._require_sudo_prefix()

        # modprobe rdma_rxe
        self.update_status("Attempting to load rdma_rxe kernel module...")
        cp = run_command(sudo_pref + ['modprobe', 'rdma_rxe'])
        if cp.returncode != 0:
            err = cp.stderr.strip() if cp.stderr else cp.stdout.strip()
            self.update_status(f"❌ modprobe failed: {err}")
            return False, f"modprobe failed: {err}"

        # create rxe link (ignore if already exists)
        self.update_status(f"Creating rxe device bound to {netdev}...")
        cp2 = run_command(sudo_pref + ['rdma', 'link', 'add', 'rxe0', 'type', 'rxe', 'netdev', netdev])
        # If it returns non-zero, check stderr for "already exists" or similar
        if cp2.returncode != 0:
            stderr = (cp2.stderr or cp2.stdout or "").strip()
            # if already exists, treat as success
            if 'File exists' in stderr or 'already exists' in stderr or 'exists' in stderr:
                self.update_status("rxe0 already exists.")
            else:
                self.update_status(f"❌ rdma link add failed: {stderr}")
                return False, f"rdma link add failed: {stderr}"

        # verify
        status = self.check_rdma_status()
        if status['module_loaded'] and status['rxe_exists']:
            self.update_status("✅ RDMA module & rxe device ready.")
            return True, "OK"
        else:
            self.update_status("❌ RDMA still not available after attempts.")
            return False, "Not available"

    # ----- UI handlers for RDMA/IP -----
    def on_check_rdma_clicked(self):
        """Triggered by UI button: check then offer to load if missing."""
        self.update_status("Checking RDMA status...")
        status = self.check_rdma_status()
        msg_lines = []
        msg_lines.append(f"rdma_rxe module loaded: {status['module_loaded']}")
        msg_lines.append(f"rxe device present: {status['rxe_exists']}")
        msg_lines.append(f"ibv devices: {', '.join(status['ibv_list']) if status['ibv_list'] else '(none)'}")
        summary = "\n".join(msg_lines)
        self.update_status(summary)

        if not (status['module_loaded'] and status['rxe_exists']):
            if messagebox.askyesno("RDMA missing", "RDMA not fully available. Try to load module and create rxe0 now? (sudo may be required)"):
                # run loader in background to keep GUI responsive
                threading.Thread(target=self._do_load_rdma_background, daemon=True).start()

    def _do_load_rdma_background(self):
        ok, info = self.load_rdma_module_and_create_rxe()
        if ok:
            messagebox.showinfo("RDMA", "RDMA module and rxe0 are ready.")
        else:
            messagebox.showerror("RDMA", f"Failed to enable RDMA: {info}\nSee status log for details.")

    def on_detect_ip(self):
        """Detect available IPv4 addresses and let user pick one to fill the IP entry."""
        addrs = psutil.net_if_addrs()
        choices = []
        for iface, addrls in addrs.items():
            for addr in addrls:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    choices.append((iface, addr.address))
        if not choices:
            messagebox.showwarning("Detect IP", "No non-loopback IPv4 addresses found.")
            return

        # build choice string
        choice_lines = [f"{i+1}. {iface} -> {ip}" for i, (iface, ip) in enumerate(choices)]
        choice_str = "\n".join(choice_lines)
        # ask user which index (simple)
        pick = askstring("Choose IP", f"Interfaces detected:\n\n{choice_str}\n\nEnter number to use (1-{len(choices)}):")
        if not pick:
            return
        try:
            idx = int(pick.strip()) - 1
            if idx < 0 or idx >= len(choices):
                raise ValueError()
        except Exception:
            messagebox.showerror("Invalid", "Not a valid selection.")
            return
        chosen_ip = choices[idx][1]
        self.ip_entry.delete(0, tk.END)
        self.ip_entry.insert(0, chosen_ip)
        self.update_status(f"Detected and set IP: {chosen_ip}")

    # ----- server control (start/stop) -----
    def start_tcp_server(self):
        # if already running, warn
        if self.tcp_server_process and self.tcp_server_process.poll() is None:
            self.update_status("TCP server already running.")
            return

        server_py = os.path.join(self.base_dir, "tcp_server.py")
        if not os.path.exists(server_py):
            self.update_status("tcp_server.py not found in src/. Please add it.")
            return

        def _start():
            self.update_status("Starting TCP server (background)...")
            self.tcp_server_process = subprocess.Popen(
                ["python3", "tcp_server.py"],
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(0.2)
            self.update_status("✅ TCP server started (local).")

        threading.Thread(target=_start, daemon=True).start()

    def stop_tcp_server(self):
        if self.tcp_server_process:
            try:
                self.tcp_server_process.terminate()
                self.tcp_server_process.wait(timeout=1)
                self.update_status("Stopped TCP server.")
            except Exception as e:
                self.update_status(f"Error stopping TCP server: {e}")
            self.tcp_server_process = None
        else:
            self.update_status("TCP server not running.")

    def start_rdma_server(self):
        # start precompiled rdma_file_server in src
        exe = os.path.join(self.base_dir, "rdma_file_server")
        if not os.path.exists(exe) or not os.access(exe, os.X_OK):
            self.update_status("rdma_file_server not found or not executable in src/. Compile it first.")
            return

        if self.rdma_server_process and self.rdma_server_process.poll() is None:
            self.update_status("RDMA server already running.")
            return

        def _start():
            self.update_status("Starting RDMA server (background)...")
            self.rdma_server_process = subprocess.Popen(
                [exe],
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(0.2)
            self.update_status("✅ RDMA server started (local).")

        threading.Thread(target=_start, daemon=True).start()

    def stop_rdma_server(self):
        if self.rdma_server_process:
            try:
                self.rdma_server_process.terminate()
                self.rdma_server_process.wait(timeout=1)
                self.update_status("Stopped RDMA server.")
            except Exception as e:
                self.update_status(f"Error stopping RDMA server: {e}")
            self.rdma_server_process = None
        else:
            self.update_status("RDMA server not running.")

    # ----- transfer threads (entry points) -----
    def start_tcp_transfer_thread(self):
        # called by button - spawn thread so GUI remains responsive
        if not self.selected_file:
            messagebox.showwarning("No File", "Select a file first.")
            return
        server_ip = self.ip_entry.get().strip()
        if not server_ip:
            messagebox.showwarning("No IP", "Enter server IP (or start local server).")
            return
        self.tcp_btn.configure(state='disabled')
        self.rdma_btn.configure(state='disabled')
        threading.Thread(target=self._do_tcp_transfer, args=(server_ip,), daemon=True).start()

    def start_rdma_transfer_thread(self):
        if not self.selected_file:
            messagebox.showwarning("No File", "Select a file first.")
            return
        server_ip = self.ip_entry.get().strip()
        if not server_ip:
            messagebox.showwarning("No IP", "Enter server IP (or start local server).")
            return
        self.tcp_btn.configure(state='disabled')
        self.rdma_btn.configure(state='disabled')
        threading.Thread(target=self._do_rdma_transfer, args=(server_ip,), daemon=True).start()

    # ----- actual transfer implementations (run in background threads) -----
    def _do_tcp_transfer(self, server_ip):
        try:
            filename = os.path.basename(self.selected_file)
            self._ui_update(f"Starting TCP transfer to {server_ip} ...")

            # if server_ip is local, start local tcp_server automatically
            started_local_server = False
            if server_ip in ("127.0.0.1", "localhost"):
                # ensure server exists
                if os.path.exists(os.path.join(self.base_dir, "tcp_server.py")):
                    self._ui_update("Launching local TCP server for demo...")
                    self.tcp_server_process = subprocess.Popen(
                        ["python3", "tcp_server.py"],
                        cwd=self.base_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    started_local_server = True
                    time.sleep(0.5)
                else:
                    self._ui_update("tcp_server.py not found; assuming remote server.")

            # run tcp client (client takes: <file> <server_ip>)
            client_py = os.path.join(self.base_dir, "tcp_client.py")
            if not os.path.exists(client_py):
                # fallback: attempt netcat if available (not ideal)
                self._ui_update("tcp_client.py not found in src/; aborting TCP transfer.")
                raise FileNotFoundError("tcp_client.py missing")

            start = time.perf_counter()
            proc = subprocess.run(["python3", "tcp_client.py", self.selected_file, server_ip],
                                  cwd=self.base_dir, capture_output=True, text=True)
            end = time.perf_counter()
            elapsed = end - start
            self.last_tcp_time = elapsed

            self._ui_update(f"TCP client finished (time={elapsed:.4f}s).")
            if proc.returncode != 0:
                self._ui_update(f"TCP client error: {proc.stderr.strip()}")
            else:
                # verify file integrity (assume server wrote to logs/tcp_received_file.txt)
                recv_path = os.path.join(self.base_dir, "logs", "tcp_received_file.txt")
                if os.path.exists(recv_path):
                    orig = file_checksum(self.selected_file)
                    recv = file_checksum(recv_path)
                    if orig == recv:
                        self._ui_update("✅ TCP file integrity OK.")
                    else:
                        self._ui_update("❌ TCP file checksum mismatch.")
                #else:
                #    self._ui_update("⚠️ TCP received file not found for integrity check.")

            # stop local server if we launched it
            if started_local_server and self.tcp_server_process:
                try:
                    self.tcp_server_process.terminate()
                    self.tcp_server_process.wait(timeout=1)
                    self._ui_update("Stopped local TCP server.")
                except Exception:
                    pass
                self.tcp_server_process = None

            # update plot on main thread
            self.root.after(0, lambda: self.plot_transfer_times(self.last_tcp_time, self.last_rdma_time))

        except Exception as e:
            self._ui_update(f"Error during TCP transfer: {e}")
        finally:
            # re-enable buttons
            self.root.after(0, lambda: self.tcp_btn.configure(state='normal'))
            self.root.after(0, lambda: self.rdma_btn.configure(state='normal'))

    def _do_rdma_transfer(self, server_ip):
        try:
            filename = os.path.basename(self.selected_file)
            self._ui_update(f"Starting RDMA transfer to {server_ip} ...")

            started_local_server = False
            if server_ip in ("127.0.0.1", "localhost"):
                exe = os.path.join(self.base_dir, "rdma_file_server")
                if os.path.exists(exe) and os.access(exe, os.X_OK):
                    self._ui_update("Launching local RDMA server for demo...")
                    self.rdma_server_process = subprocess.Popen([exe], cwd=self.base_dir,
                                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    started_local_server = True
                    time.sleep(0.5)
                else:
                    self._ui_update("rdma_file_server not found or not executable in src/; aborting RDMA demo.")
                    raise FileNotFoundError("rdma_file_server missing")

            client_exe = os.path.join(self.base_dir, "rdma_file_client")
            if not os.path.exists(client_exe) or not os.access(client_exe, os.X_OK):
                self._ui_update("rdma_file_client missing or not executable in src/. Compile it and retry.")
                raise FileNotFoundError("rdma_file_client missing")

            start = time.perf_counter()
            proc = subprocess.run([client_exe, server_ip, self.selected_file], cwd=self.base_dir,
                                  capture_output=True, text=True)
            end = time.perf_counter()
            elapsed = end - start
            self.last_rdma_time = elapsed

            self._ui_update(f"RDMA client finished (time={elapsed:.4f}s).")
            if proc.returncode != 0:
                self._ui_update(f"RDMA client error: {proc.stderr.strip()}")
            else:
                # integrity: server should have written received_file.txt in base_dir
                recv_path = os.path.join(self.base_dir, "received_file.txt")
                # some server implementations write to logs/ ; check both
                if not os.path.exists(recv_path):
                    alt = os.path.join(self.base_dir, "logs", "rdma_received_file.txt")
                    if os.path.exists(alt):
                        recv_path = alt

                if os.path.exists(recv_path):
                    orig = file_checksum(self.selected_file)
                    recv = file_checksum(recv_path)
                    if orig == recv:
                        self._ui_update("✅ RDMA file integrity OK.")
                    else:
                        self._ui_update("❌ RDMA file checksum mismatch.")

            if started_local_server and self.rdma_server_process:
                try:
                    self.rdma_server_process.terminate()
                    self.rdma_server_process.wait(timeout=1)
                    self._ui_update("Stopped local RDMA server.")
                except Exception:
                    pass
                self.rdma_server_process = None

            self.root.after(0, lambda: self.plot_transfer_times(self.last_tcp_time, self.last_rdma_time))

        except Exception as e:
            self._ui_update(f"Error during RDMA transfer: {e}")
        finally:
            self.root.after(0, lambda: self.tcp_btn.configure(state='normal'))
            self.root.after(0, lambda: self.rdma_btn.configure(state='normal'))

    # small helper to safely update UI from worker threads
    def _ui_update(self, msg):
        self.root.after(0, lambda: self.update_status(msg))

    # ----- plotting -----
    def plot_transfer_times(self, tcp_time, rdma_time):
        # create or reuse plot window
        if not self.plot_window or not self.plot_window.winfo_exists():
            self.plot_window = tk.Toplevel(self.root)
            self.plot_window.title("Transfer Performance")
            self.plot_window.geometry("600x400")
            self.plot_window.configure(bg=self.colors['bg_primary'])
            self.plot_window.protocol("WM_DELETE_WINDOW", lambda: self.plot_window.destroy())

        # clear previous content
        for widget in self.plot_window.winfo_children():
            widget.destroy()

        # create plot
        fig, ax = plt.subplots(figsize=(6,3))
        methods = []
        times = []
        if tcp_time and tcp_time > 0:
            methods.append("TCP")
            times.append(tcp_time)
        if rdma_time and rdma_time > 0:
            methods.append("RDMA")
            times.append(rdma_time)
        if not methods:
            ax.text(0.5, 0.5, "Run transfers to see results", ha='center', va='center')
        else:
            # note: matplotlib colors here were used previously; keeping them is ok
            ax.bar(methods, times, color=[self.colors['accent_purple'], self.colors['accent_green']][:len(methods)])
            ax.set_ylabel("Time (seconds)", fontsize=12)
            ax.set_title("Transfer Time Comparison", fontsize=14, pad=15)
            for i, v in enumerate(times):
                ax.text(i, v + 0.05 * max(times, default=1), f"{v:.2f}s", ha='center', fontsize=10)

        canvas = FigureCanvasTkAgg(fig, master=self.plot_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

    # ----- cleanup on exit -----
    def on_closing(self):
        # terminate any servers started by GUI
        if self.tcp_server_process and self.tcp_server_process.poll() is None:
            try:
                self.tcp_server_process.terminate()
            except Exception:
                pass
        if self.rdma_server_process and self.rdma_server_process.poll() is None:
            try:
                self.rdma_server_process.terminate()
            except Exception:
                pass
        if self.plot_window and self.plot_window.winfo_exists():
            self.plot_window.destroy()
        self.root.destroy()

    # ----- run -----
    def run(self):
        self.root.mainloop()

# ---------- run app ----------
if __name__ == "__main__":
    app = ModernRDMAApp()
    app.run()