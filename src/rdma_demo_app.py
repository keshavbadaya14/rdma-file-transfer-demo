#!/usr/bin/env python3
# rdma_demo_app_with_rdmacheck.py  -- RDMA GUI with RDMA-check/load & IP detect
# Integrates RDMA module/device checks, auto-load, IP detection, and extended metrics plotting.

import os
import threading
import subprocess
import time
import hashlib
import socket
import shutil
import sys
import tempfile
import numpy as np

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
        cp = subprocess.CompletedProcess(cmd, 127, stdout="", stderr=str(e))
        return cp

def create_temp_file(size_bytes):
    """Create a temporary file of specified size (in bytes)."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(os.urandom(size_bytes))
        return f.name

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

        # plot windows
        self.plot_windows = {}

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
        self.monitoring = False
        self.monitor_thread = None

        # Metrics storage
        self.tcp_times = []  # List to store multiple TCP transfer times
        self.rdma_times = []  # List to store multiple RDMA transfer times
        self.last_tcp_throughput = 0.0  # MB/s
        self.last_rdma_throughput = 0.0  # MB/s
        self.last_tcp_cpu = 0.0  # % CPU usage
        self.last_rdma_cpu = 0.0  # % CPU usage
        self.last_tcp_memory = 0.0  # MB
        self.last_rdma_memory = 0.0  # MB
        self.bandwidth_data = {'TCP': [], 'RDMA': []}  # (size_MB, bandwidth_MB/s)
        self.rtt_data = {'TCP': [], 'RDMA': []}  # (size_MB, rtt_us)

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
        tk.Label(header, text="Compare TCP vs RDMA transfers with extended metrics (local demo).",
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

        tk.Label(inner, text="📈 Performance Charts", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')
        tk.Label(inner, text="Run transfers to view performance comparisons (Time, Throughput, CPU, Memory, Bandwidth, RTT) in separate windows",
                 font=self.fonts['small'],
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
            addrs = psutil.net_if_addrs()
            for iface, addrls in addrs.items():
                for addr in addrls:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        return iface
            return None
        parts = cp.stdout.strip().split()
        if 'dev' in parts:
            i = parts.index('dev')
            if i + 1 < len(parts):
                return parts[i+1]
        return None

    def check_rdma_status(self):
        status = {
            'module_loaded': False,
            'rxe_exists': False,
            'ibv_list': []
        }
        cp = run_command(['lsmod'])
        if cp.returncode == 0 and 'rdma_rxe' in cp.stdout:
            status['module_loaded'] = True

        cp2 = run_command(['rdma', 'link', 'show'])
        if cp2.returncode == 0 and 'rxe' in cp2.stdout:
            status['rxe_exists'] = True

        cp3 = run_command(['ibv_devices'])
        if cp3.returncode == 0:
            lines = cp3.stdout.strip().splitlines()
            for line in lines[1:]:
                line = line.strip()
                if line:
                    parts = line.split()
                    status['ibv_list'].append(parts[0])
        return status

    def _require_sudo_prefix(self):
        try:
            euid = os.geteuid()
        except AttributeError:
            euid = 0
        if euid == 0:
            return []
        else:
            return ['sudo']

    def load_rdma_module_and_create_rxe(self):
        netdev = self.detect_default_netdev()
        if not netdev:
            self.update_status("❌ Cannot detect default network device for RXE binding.")
            return False, "Cannot detect netdev"

        sudo_pref = self._require_sudo_prefix()
        self.update_status("Attempting to load rdma_rxe kernel module...")
        cp = run_command(sudo_pref + ['modprobe', 'rdma_rxe'])
        if cp.returncode != 0:
            err = cp.stderr.strip() if cp.stderr else cp.stdout.strip()
            self.update_status(f"❌ modprobe failed: {err}")
            return False, f"modprobe failed: {err}"

        self.update_status(f"Creating rxe device bound to {netdev}...")
        cp2 = run_command(sudo_pref + ['rdma', 'link', 'add', 'rxe0', 'type', 'rxe', 'netdev', netdev])
        if cp2.returncode != 0:
            stderr = (cp2.stderr or cp2.stdout or "").strip()
            if 'File exists' in stderr or 'already exists' in stderr or 'exists' in stderr:
                self.update_status("rxe0 already exists.")
            else:
                self.update_status(f"❌ rdma link add failed: {stderr}")
                return False, f"rdma link add failed: {stderr}"

        status = self.check_rdma_status()
        if status['module_loaded'] and status['rxe_exists']:
            self.update_status("✅ RDMA module & rxe device ready.")
            return True, "OK"
        else:
            self.update_status("❌ RDMA still not available after attempts.")
            return False, "Not available"

    # ----- UI handlers for RDMA/IP -----
    def on_check_rdma_clicked(self):
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
                threading.Thread(target=self._do_load_rdma_background, daemon=True).start()

    def _do_load_rdma_background(self):
        ok, info = self.load_rdma_module_and_create_rxe()
        if ok:
            messagebox.showinfo("RDMA", "RDMA module and rxe0 are ready.")
        else:
            messagebox.showerror("RDMA", f"Failed to enable RDMA: {info}\nSee status log for details.")

    def on_detect_ip(self):
        addrs = psutil.net_if_addrs()
        choices = []
        for iface, addrls in addrs.items():
            for addr in addrls:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    choices.append((iface, addr.address))
        if not choices:
            messagebox.showwarning("Detect IP", "No non-loopback IPv4 addresses found.")
            return

        choice_lines = [f"{i+1}. {iface} -> {ip}" for i, (iface, ip) in enumerate(choices)]
        choice_str = "\n".join(choice_lines)
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

    # ----- resource monitoring -----
    def monitor_resources(self, process, metric_type):
        """Monitor CPU and memory usage for a given process."""
        cpu_samples = []
        memory_samples = []
        self.monitoring = True

        try:
            p = psutil.Process(process.pid)
            while self.monitoring and p.is_running():
                try:
                    cpu_percent = p.cpu_percent(interval=0.1)
                    memory_info = p.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)
                    cpu_samples.append(cpu_percent)
                    memory_samples.append(memory_mb)
                    time.sleep(0.1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
        except Exception as e:
            self._ui_update("")

        avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
        avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0.0
        return avg_cpu, avg_memory

    # ----- measure roundtrip latency -----
    def measure_rtt(self, server_ip, file_path, protocol):
        """Measure half roundtrip latency for a given file size and protocol."""
        # Note: Assumes tcp_client.py and rdma_file_client support a --rtt flag for quick ping-pong
        # If not, this is a placeholder; actual implementation depends on client capabilities
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            start = time.perf_counter()
            if protocol == "TCP":
                client_py = os.path.join(self.base_dir, "tcp_client.py")
                if not os.path.exists(client_py):
                    raise FileNotFoundError("tcp_client.py missing")
                # Simulate RTT with a quick send-receive (modify tcp_client.py to support --rtt)
                proc = subprocess.run(["python3", client_py, file_path, server_ip, "--rtt"],
                                      cwd=self.base_dir, capture_output=True, text=True)
            else:
                client_exe = os.path.join(self.base_dir, "rdma_file_client")
                if not os.path.exists(client_exe) or not os.access(client_exe, os.X_OK):
                    raise FileNotFoundError("rdma_file_client missing")
                proc = subprocess.run([client_exe, server_ip, file_path, "--rtt"],
                                      cwd=self.base_dir, capture_output=True, text=True)
            end = time.perf_counter()
            if proc.returncode != 0:
                self._ui_update(f"{protocol} RTT error: {proc.stderr.strip()}")
                return file_size_mb, 0.0
            elapsed_us = (end - start) * 1_000_000 / 2  # Half RTT in microseconds
            return file_size_mb, elapsed_us
        except Exception as e:
            self._ui_update(f"Error measuring {protocol} RTT: {e}")
            return file_size_mb, 0.0

    # ----- transfer threads (entry points) -----
    def start_tcp_transfer_thread(self):
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

    # ----- actual transfer implementations -----
    def _do_tcp_transfer(self, server_ip):
        try:
            filename = os.path.basename(self.selected_file)
            file_size = os.path.getsize(self.selected_file) / (1024 * 1024)
            self._ui_update(f"Starting TCP transfer to {server_ip} ...")

            started_local_server = False
            if server_ip in ("127.0.0.1", "localhost"):
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
                    self._ui_update("")

            client_py = os.path.join(self.base_dir, "tcp_client.py")
            if not os.path.exists(client_py):
                self._ui_update("")
                raise FileNotFoundError("tcp_client.py missing")

            # Start monitoring
            self.monitoring = True
            proc = subprocess.Popen(["python3", "tcp_client.py", self.selected_file, server_ip],
                                    cwd=self.base_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            monitor = threading.Thread(target=self.monitor_resources, args=(proc, "TCP"), daemon=True)
            monitor.start()

            start = time.perf_counter()
            proc.wait()
            end = time.perf_counter()
            self.monitoring = False
            monitor.join()

            elapsed = end - start
            self.tcp_times.append(elapsed)
            throughput = file_size / elapsed if elapsed > 0 else 0.0
            self.last_tcp_throughput = throughput
            avg_cpu, avg_memory = self.monitor_resources(proc, "TCP")
            self.last_tcp_cpu = avg_cpu
            self.last_tcp_memory = avg_memory

            # Measure RTT for selected file
            file_size_mb, rtt_us = self.measure_rtt(server_ip, self.selected_file, "TCP")
            self.rtt_data['TCP'].append((file_size_mb, rtt_us))
            self.bandwidth_data['TCP'].append((file_size_mb, throughput))

            # Test multiple file sizes for bandwidth and RTT
            for size_mb in [1, 10, 100]:  # Test with 1MB, 10MB, 100MB files
                temp_file = create_temp_file(int(size_mb * 1024 * 1024))
                try:
                    proc = subprocess.Popen(["python3", "tcp_client.py", temp_file, server_ip],
                                            cwd=self.base_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    start = time.perf_counter()
                    proc.wait()
                    end = time.perf_counter()
                    elapsed = end - start
                    throughput = size_mb / elapsed if elapsed > 0 else 0.0
                    self.bandwidth_data['TCP'].append((size_mb, throughput))
                    _, rtt_us = self.measure_rtt(server_ip, temp_file, "TCP")
                    self.rtt_data['TCP'].append((size_mb, rtt_us))
                finally:
                    os.unlink(temp_file)

            self._ui_update(f"TCP client finished (time={elapsed:.4f}s, throughput={throughput:.5f} MB/s, "
                            f"CPU={avg_cpu:.2f}%, Memory={avg_memory:.2f} MB, RTT={rtt_us:.5f} µs).")
            if proc.returncode != 0:
                self._ui_update(f"TCP client error: {proc.stderr.strip()}")
            else:
                recv_path = os.path.join(self.base_dir, "logs", "tcp_received_file.txt")
                if os.path.exists(recv_path):
                    orig = file_checksum(self.selected_file)
                    recv = file_checksum(recv_path)
                    if orig == recv:
                        self._ui_update("✅ TCP file integrity OK.")
                    else:
                        self._ui_update("")

            if started_local_server and self.tcp_server_process:
                try:
                    self.tcp_server_process.terminate()
                    self.tcp_server_process.wait(timeout=1)
                    self._ui_update("Stopped local TCP server.")
                except Exception:
                    pass
                self.tcp_server_process = None

            self.root.after(0, lambda: self.plot_metrics())

        except Exception as e:
            self._ui_update(f"")
        finally:
            self.root.after(0, lambda: self.tcp_btn.configure(state='normal'))
            self.root.after(0, lambda: self.rdma_btn.configure(state='normal'))

    def _do_rdma_transfer(self, server_ip):
        try:
            filename = os.path.basename(self.selected_file)
            file_size = os.path.getsize(self.selected_file) / (1024 * 1024)
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
                    self._ui_update("")
                    raise FileNotFoundError("rdma_file_server missing")

            client_exe = os.path.join(self.base_dir, "rdma_file_client")
            if not os.path.exists(client_exe) or not os.access(client_exe, os.X_OK):
                self._ui_update("")
                raise FileNotFoundError("")

            self.monitoring = True
            proc = subprocess.Popen([client_exe, server_ip, self.selected_file], cwd=self.base_dir,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            monitor = threading.Thread(target=self.monitor_resources, args=(proc, "RDMA"), daemon=True)
            monitor.start()

            start = time.perf_counter()
            proc.wait()
            end = time.perf_counter()
            self.monitoring = False
            monitor.join()

            elapsed = end - start
            self.rdma_times.append(elapsed)
            throughput = file_size / elapsed if elapsed > 0 else 0.0
            self.last_rdma_throughput = throughput
            avg_cpu, avg_memory = self.monitor_resources(proc, "RDMA")
            self.last_rdma_cpu = avg_cpu
            self.last_rdma_memory = avg_memory

            file_size_mb, rtt_us = self.measure_rtt(server_ip, self.selected_file, "RDMA")
            self.rtt_data['RDMA'].append((file_size_mb, rtt_us))
            self.bandwidth_data['RDMA'].append((file_size_mb, throughput))

            for size_mb in [1, 10, 100]:
                temp_file = create_temp_file(int(size_mb * 1024 * 1024))
                try:
                    proc = subprocess.Popen([client_exe, server_ip, temp_file],
                                            cwd=self.base_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    start = time.perf_counter()
                    proc.wait()
                    end = time.perf_counter()
                    elapsed = end - start
                    throughput = size_mb / elapsed if elapsed > 0 else 0.0
                    self.bandwidth_data['RDMA'].append((size_mb, throughput))
                    _, rtt_us = self.measure_rtt(server_ip, temp_file, "RDMA")
                    self.rtt_data['RDMA'].append((size_mb, rtt_us))
                finally:
                    os.unlink(temp_file)

            self._ui_update(f"RDMA client finished (time={elapsed:.4f}s, throughput={throughput:.5f} MB/s, "
                            f"CPU={avg_cpu:.2f}%, Memory={avg_memory:.2f} MB, RTT={rtt_us:.5f} µs).")
            if proc.returncode != 0:
                self._ui_update(f"RDMA client error: {proc.stderr.strip()}")
            else:
                recv_path = os.path.join(self.base_dir, "received_file.txt")
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
                        self._ui_update("")

            if started_local_server and self.rdma_server_process:
                try:
                    self.rdma_server_process.terminate()
                    self.rdma_server_process.wait(timeout=1)
                    self._ui_update("Stopped local RDMA server.")
                except Exception:
                    pass
                self.rdma_server_process = None

            self.root.after(0, lambda: self.plot_metrics())

        except Exception as e:
            self._ui_update(f"")
        finally:
            self.root.after(0, lambda: self.tcp_btn.configure(state='normal'))
            self.root.after(0, lambda: self.rdma_btn.configure(state='normal'))

    def _ui_update(self, msg):
        self.root.after(0, lambda: self.update_status(msg))

    # ----- plotting -----
    def plot_metrics(self):
        # Average Transfer Time
        avg_tcp_time = sum(self.tcp_times) / len(self.tcp_times) if self.tcp_times else 0.0
        avg_rdma_time = sum(self.rdma_times) / len(self.rdma_times) if self.rdma_times else 0.0
        self.plot_bar_metric(
            title="Average Transfer Time Comparison",
            ylabel="Time (seconds)",
            data=[("TCP", avg_tcp_time), ("RDMA", avg_rdma_time)],
            colors=[self.colors['accent_purple'], self.colors['accent_green']],
            window_title="Average Transfer Time"
        )

        # Throughput
        self.plot_bar_metric(
            title="Transfer Throughput Comparison",
            ylabel="Throughput (MB/s)",
            data=[("TCP", self.last_tcp_throughput), ("RDMA", self.last_rdma_throughput)],
            colors=[self.colors['accent_purple'], self.colors['accent_green']],
            window_title="Transfer Throughput"
        )

        # CPU Utilization
        self.plot_bar_metric(
            title="CPU Utilization Comparison",
            ylabel="CPU Usage (%)",
            data=[("TCP", self.last_tcp_cpu), ("RDMA", self.last_rdma_cpu)],
            colors=[self.colors['accent_purple'], self.colors['accent_green']],
            window_title="CPU Utilization"
        )

        # Memory Footprint
        self.plot_bar_metric(
            title="Memory Footprint Comparison",
            ylabel="Memory Usage (MB)",
            data=[("TCP", self.last_tcp_memory), ("RDMA", self.last_rdma_memory)],
            colors=[self.colors['accent_purple'], self.colors['accent_green']],
            window_title="Memory Footprint"
        )

        # Bandwidth vs. Message Size
        self.plot_line_metric(
            title="Bandwidth vs. Message Size",
            ylabel="Bandwidth (MB/s)",
            xlabel="Message Size (MB)",
            data=self.bandwidth_data,
            window_title="Bandwidth vs. Message Size"
        )

        # Half Roundtrip Latency vs. Message Size
        self.plot_line_metric(
            title="Half Roundtrip Latency vs. Message Size",
            ylabel="Half RTT (µs)",
            xlabel="Message Size (MB)",
            data=self.rtt_data,
            window_title="Half Roundtrip Latency"
        )

    def plot_bar_metric(self, title, ylabel, data, colors, window_title):
        methods = [m for m, v in data if v > 0]
        values = [v for m, v in data if v > 0]
        if not methods:
            return

        window_key = window_title.replace(" ", "_").lower()
        if window_key in self.plot_windows and self.plot_windows[window_key].winfo_exists():
            self.plot_windows[window_key].destroy()

        window = tk.Toplevel(self.root)
        window.title(window_title)
        window.geometry("600x400")
        window.configure(bg=self.colors['bg_primary'])
        window.protocol("WM_DELETE_WINDOW", lambda: window.destroy())
        self.plot_windows[window_key] = window

        fig, ax = plt.subplots(figsize=(6, 3))
        ax.bar(methods, values, color=colors[:len(methods)])
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(title, fontsize=14, pad=15)
        for i, v in enumerate(values):
            ax.text(i, v + 0.05 * max(values, default=1), f"{v:.2f}", ha='center', fontsize=10)

        canvas = FigureCanvasTkAgg(fig, master=window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

    def plot_line_metric(self, title, ylabel, xlabel, data, window_title):
        has_data = False
        for protocol in ['TCP', 'RDMA']:
            if data[protocol]:
                has_data = True
                break
        if not has_data:
            return

        window_key = window_title.replace(" ", "_").lower()
        if window_key in self.plot_windows and self.plot_windows[window_key].winfo_exists():
            self.plot_windows[window_key].destroy()

        window = tk.Toplevel(self.root)
        window.title(window_title)
        window.geometry("600x400")
        window.configure(bg=self.colors['bg_primary'])
        window.protocol("WM_DELETE_WINDOW", lambda: window.destroy())
        self.plot_windows[window_key] = window

        fig, ax = plt.subplots(figsize=(6, 3))
        for protocol, color in [('TCP', self.colors['accent_purple']), ('RDMA', self.colors['accent_green'])]:
            if data[protocol]:
                sizes, values = zip(*sorted(data[protocol], key=lambda x: x[0]))
                ax.plot(sizes, values, marker='o', label=protocol, color=color)
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(title, fontsize=14, pad=15)
        ax.legend()
        ax.grid(True)

        canvas = FigureCanvasTkAgg(fig, master=window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)

    # ----- cleanup on exit -----
    def on_closing(self):
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
        for window in self.plot_windows.values():
            if window.winfo_exists():
                window.destroy()
        self.root.destroy()

    # ----- run -----
    def run(self):
        self.root.mainloop()

# ---------- run app ----------
if __name__ == "__main__":
    app = ModernRDMAApp()
    app.run()