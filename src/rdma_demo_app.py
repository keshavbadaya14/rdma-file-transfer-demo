#!/usr/bin/env python3
# rdma_demo_app.py  -- full working GUI with server/client integration, threads, checksums and plots

import os
import threading
import subprocess
import time
import hashlib
import socket
import shutil

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkFont

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
        self.root.geometry("800x760")
        self.root.configure(bg='#0f0f23')
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # colors & fonts
        self.colors = {
            'bg_primary': '#0f0f23',
            'bg_secondary': '#1a1a2e',
            'bg_tertiary': '#16213e',
            'accent_blue': '#00d4ff',
            'accent_purple': '#8b5cf6',
            'accent_green': '#10b981',
            'text_primary': '#ffffff',
            'text_secondary': '#a1a1aa',
            'hover_light': '#2a2a40',
            'border': '#374151'
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
            'subtitle': tkFont.Font(family='Helvetica', size=12),
            'button': tkFont.Font(family='Helvetica', size=11, weight='bold'),
            'label': tkFont.Font(family='Helvetica', size=10),
            'small': tkFont.Font(family='Helvetica', size=9)
        }

    def setup_ui(self):
        # main frame (make it an attribute so other methods can use it)
        self.main_frame = tk.Frame(self.root, bg=self.colors['bg_primary'])
        self.main_frame.pack(fill='both', expand=True, padx=20, pady=16)

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
        tk.Label(header, text="Compare TCP vs RDMA transfers (local demo)", font=self.fonts['subtitle'],
                 bg=self.colors['bg_primary'], fg=self.colors['text_secondary']).pack(anchor='w')

    # ----- file selection -----
    def create_file_section(self, parent):
        file_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        file_frame.pack(fill='x', pady=(10,10))
        inner = tk.Frame(file_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=12, pady=12)

        tk.Label(inner, text="📁 File Selection", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        btn = tk.Button(inner, text="Choose File", font=self.fonts['button'],
                        bg=self.colors['accent_blue'], fg='white',
                        command=self.select_file, relief='flat', bd=0, padx=12, pady=8, cursor='hand2')
        btn.pack(anchor='w', pady=(8,6))

        self.file_info_label = tk.Label(inner, text="No file selected", font=self.fonts['label'],
                                        bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'])
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
        ip_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        ip_frame.pack(fill='x', pady=(6,6))
        inner = tk.Frame(ip_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=12, pady=8)

        tk.Label(inner, text="🌐 Server IP (enter receiver IP)", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        self.ip_entry = tk.Entry(inner, font=self.fonts['label'], bg=self.colors['bg_tertiary'],
                                 fg=self.colors['text_primary'], insertbackground='white')
        # sensible default: localhost
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(fill='x', pady=(8,0))

    # ----- server start section -----
    def create_server_section(self, parent):
        server_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        server_frame.pack(fill='x', pady=(6,8))
        inner = tk.Frame(server_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=12, pady=8)

        tk.Label(inner, text="🖥️ Start Server (local demo)", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        # two small buttons
        btn_row = tk.Frame(inner, bg=self.colors['bg_secondary'])
        btn_row.pack(anchor='w', pady=(8,0))

        self.start_tcp_server_btn = tk.Button(btn_row, text="Start TCP Server", font=self.fonts['button'],
                                              bg=self.colors['accent_purple'], fg='white',
                                              command=self.start_tcp_server, relief='flat', bd=0,
                                              padx=10, pady=6, cursor='hand2')
        self.start_tcp_server_btn.pack(side='left', padx=(0,12))

        self.stop_tcp_server_btn = tk.Button(btn_row, text="Stop TCP Server", font=self.fonts['button'],
                                             bg=self.colors['hover_light'], fg='white',
                                             command=self.stop_tcp_server, relief='flat', bd=0,
                                             padx=10, pady=6, cursor='hand2')
        self.stop_tcp_server_btn.pack(side='left', padx=(0,12))

        self.start_rdma_server_btn = tk.Button(btn_row, text="Start RDMA Server", font=self.fonts['button'],
                                               bg=self.colors['accent_green'], fg='white',
                                               command=self.start_rdma_server, relief='flat', bd=0,
                                               padx=10, pady=6, cursor='hand2')
        self.start_rdma_server_btn.pack(side='left', padx=(0,12))

        self.stop_rdma_server_btn = tk.Button(btn_row, text="Stop RDMA Server", font=self.fonts['button'],
                                              bg=self.colors['hover_light'], fg='white',
                                              command=self.stop_rdma_server, relief='flat', bd=0,
                                              padx=10, pady=6, cursor='hand2')
        self.stop_rdma_server_btn.pack(side='left', padx=(0,12))

    # ----- transfer section -----
    def create_transfer_section(self, parent):
        transfer_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        transfer_frame.pack(fill='x', pady=(6,8))
        inner = tk.Frame(transfer_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='x', padx=12, pady=8)

        tk.Label(inner, text="🚀 Transfer Methods", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        btn_row = tk.Frame(inner, bg=self.colors['bg_secondary'])
        btn_row.pack(anchor='w', pady=(8,0))

        self.tcp_btn = tk.Button(btn_row, text="📡 Send via TCP", font=self.fonts['button'],
                                 bg=self.colors['accent_purple'], fg='white',
                                 command=self.start_tcp_transfer_thread, relief='flat', bd=0,
                                 padx=12, pady=8, cursor='hand2', state='disabled')
        self.tcp_btn.pack(side='left', padx=(0,12))

        self.rdma_btn = tk.Button(btn_row, text="⚡ Send via RDMA", font=self.fonts['button'],
                                  bg=self.colors['accent_green'], fg='white',
                                  command=self.start_rdma_transfer_thread, relief='flat', bd=0,
                                  padx=12, pady=8, cursor='hand2', state='disabled')
        self.rdma_btn.pack(side='left', padx=(0,12))

        # small info label
        tk.Label(inner, text="(Start server locally or point to remote server IP)", font=self.fonts['small'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(8,0))

    # ----- status section -----
    def create_status_section(self, parent):
        status_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        status_frame.pack(fill='both', expand=False, pady=(6,8))
        inner = tk.Frame(status_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='both', padx=12, pady=8)

        tk.Label(inner, text="📊 Transfer Status", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')

        self.status_text = tk.Text(inner, height=8, bg=self.colors['bg_tertiary'], fg=self.colors['text_primary'],
                                   font=self.fonts['small'], bd=0, relief='flat', padx=8, pady=8, wrap='word')
        self.status_text.pack(fill='both', pady=(8,0))
        self.update_status("Ready. Select a file and enter server IP (default 127.0.0.1).")

    # ----- plot frame -----
    def create_plot_frame(self, parent):
        plot_frame = tk.Frame(parent, bg=self.colors['bg_secondary'])
        plot_frame.pack(fill='both', expand=True, pady=(6,8))
        inner = tk.Frame(plot_frame, bg=self.colors['bg_secondary'])
        inner.pack(fill='both', padx=12, pady=8, expand=True)

        tk.Label(inner, text="📈 Performance Chart", font=self.fonts['button'],
                 bg=self.colors['bg_secondary'], fg=self.colors['text_primary']).pack(anchor='w')
        self.plot_container = tk.Frame(inner, bg=self.colors['bg_secondary'])
        self.plot_container.pack(fill='both', expand=True, pady=(8,0))

        # placeholder
        self.canvas = None

    # ----- status helper -----
    def update_status(self, message):
        ts = time.strftime("%H:%M:%S")
        self.status_text.configure(state='normal')
        self.status_text.insert('end', f"[{ts}] {message}\n")
        self.status_text.configure(state='disabled')
        self.status_text.see('end')

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
                else:
                    self._ui_update("⚠️ TCP received file not found for integrity check.")

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
                else:
                    self._ui_update("⚠️ RDMA received file not found for integrity check.")

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
        # clear previous canvas
        for child in self.plot_container.winfo_children():
            child.destroy()

        fig, ax = plt.subplots(figsize=(5,2.5))
        methods = []
        times = []
        if tcp_time and tcp_time > 0:
            methods.append("TCP")
            times.append(tcp_time)
        if rdma_time and rdma_time > 0:
            methods.append("RDMA")
            times.append(rdma_time)
        if not methods:
            ax.text(0.5,0.5,"Run transfers to see results", ha='center', va='center')
        else:
            ax.bar(methods, times)
            ax.set_ylabel("Time (s)")
            ax.set_title("Transfer time")

        canvas = FigureCanvasTkAgg(fig, master=self.plot_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

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
        self.root.destroy()

    # ----- run -----
    def run(self):
        self.root.mainloop()


# ---------- run app ----------
if __name__ == "__main__":
    app = ModernRDMAApp()
    app.run()
