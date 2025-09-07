import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from tkinter import font as tkFont

class ModernRDMAApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RDMA File Transfer Demo")
        self.root.geometry("600x700")
        self.root.configure(bg='#0f0f23')
        self.root.resizable(True, True)
        
        # Modern color scheme
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
        
        self.selected_file = None
        self.setup_ui()
        self.create_animations()
        
    def setup_ui(self):
        # Configure styles
        self.setup_styles()
        
        # Main container with padding
        main_frame = tk.Frame(self.root, bg=self.colors['bg_primary'])
        main_frame.pack(fill='both', expand=True, padx=30, pady=30)
        
        # Header section
        self.create_header(main_frame)
        
        # File selection section
        self.create_file_section(main_frame)
        
        # Transfer methods section
        self.create_transfer_section(main_frame)
        
        # Status section
        self.create_status_section(main_frame)
        
    def setup_styles(self):
        # Custom fonts
        self.fonts = {
            'title': tkFont.Font(family='Helvetica', size=28, weight='bold'),
            'subtitle': tkFont.Font(family='Helvetica', size=14),
            'button': tkFont.Font(family='Helvetica', size=12, weight='bold'),
            'label': tkFont.Font(family='Helvetica', size=11),
            'small': tkFont.Font(family='Helvetica', size=9)
        }
        
    def create_header(self, parent):
        # Header frame with gradient effect
        header_frame = tk.Frame(parent, bg=self.colors['bg_primary'], height=120)
        header_frame.pack(fill='x', pady=(0, 30))
        header_frame.pack_propagate(False)
        
        # Title with gradient effect simulation
        title_label = tk.Label(
            header_frame,
            text="⚡ RDMA File Transfer",
            font=self.fonts['title'],
            bg=self.colors['bg_primary'],
            fg=self.colors['accent_blue']
        )
        title_label.pack(pady=(20, 5))
        
        subtitle_label = tk.Label(
            header_frame,
            text="High-performance network file transfer demonstration",
            font=self.fonts['subtitle'],
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        subtitle_label.pack()
        
    def create_file_section(self, parent):
        # File selection container
        file_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', bd=0)
        file_frame.pack(fill='x', pady=(0, 25))
        
        # Add rounded corners effect with padding
        inner_frame = tk.Frame(file_frame, bg=self.colors['bg_secondary'])
        inner_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Section title
        section_title = tk.Label(
            inner_frame,
            text="📁 File Selection",
            font=self.fonts['button'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        section_title.pack(anchor='w', pady=(0, 15))
        
        # File selection button
        self.select_btn = self.create_modern_button(
            inner_frame,
            text="Choose File",
            command=self.select_file,
            bg_color=self.colors['accent_blue'],
            hover_color='#0ea5db',
            width=200
        )
        self.select_btn.pack(pady=(0, 10))
        
        # Selected file display
        self.file_info_frame = tk.Frame(inner_frame, bg=self.colors['bg_tertiary'])
        self.file_info_frame.pack(fill='x', pady=(10, 0))
        self.file_info_frame.pack_forget()  # Hide initially
        
        self.file_name_label = tk.Label(
            self.file_info_frame,
            text="",
            font=self.fonts['label'],
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            wraplength=500
        )
        self.file_name_label.pack(anchor='w', padx=15, pady=(10, 5))
        
        self.file_size_label = tk.Label(
            self.file_info_frame,
            text="",
            font=self.fonts['small'],
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_secondary']
        )
        self.file_size_label.pack(anchor='w', padx=15, pady=(0, 10))
        
    def create_transfer_section(self, parent):
        # Transfer methods container
        transfer_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', bd=0)
        transfer_frame.pack(fill='x', pady=(0, 25))
        
        inner_frame = tk.Frame(transfer_frame, bg=self.colors['bg_secondary'])
        inner_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Section title
        section_title = tk.Label(
            inner_frame,
            text="🚀 Transfer Methods",
            font=self.fonts['button'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        section_title.pack(anchor='w', pady=(0, 20))
        
        # Button container
        button_container = tk.Frame(inner_frame, bg=self.colors['bg_secondary'])
        button_container.pack(fill='x')
        
        # TCP Transfer button
        tcp_frame = tk.Frame(button_container, bg=self.colors['bg_secondary'])
        tcp_frame.pack(fill='x', pady=(0, 15))
        
        self.tcp_btn = self.create_modern_button(
            tcp_frame,
            text="📡 Send via TCP",
            command=self.send_tcp,
            bg_color=self.colors['accent_purple'],
            hover_color='#7c3aed',
            width=250
        )
        self.tcp_btn.pack(side='left')
        
        tcp_info = tk.Label(
            tcp_frame,
            text="Traditional network protocol • Reliable • Standard",
            font=self.fonts['small'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_secondary']
        )
        tcp_info.pack(side='left', padx=(20, 0), anchor='w')
        
        # RDMA Transfer button
        rdma_frame = tk.Frame(button_container, bg=self.colors['bg_secondary'])
        rdma_frame.pack(fill='x')
        
        self.rdma_btn = self.create_modern_button(
            rdma_frame,
            text="⚡ Send via RDMA",
            command=self.send_rdma,
            bg_color=self.colors['accent_green'],
            hover_color='#059669',
            width=250
        )
        self.rdma_btn.pack(side='left')
        
        rdma_info = tk.Label(
            rdma_frame,
            text="Remote Direct Memory Access • Ultra-fast • Low latency",
            font=self.fonts['small'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_secondary']
        )
        rdma_info.pack(side='left', padx=(20, 0), anchor='w')
        
    def create_status_section(self, parent):
        # Status container
        status_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', bd=0)
        status_frame.pack(fill='both', expand=True)
        
        inner_frame = tk.Frame(status_frame, bg=self.colors['bg_secondary'])
        inner_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Section title
        section_title = tk.Label(
            inner_frame,
            text="📊 Transfer Status",
            font=self.fonts['button'],
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary']
        )
        section_title.pack(anchor='w', pady=(0, 15))
        
        # Status display
        self.status_text = tk.Text(
            inner_frame,
            height=8,
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            font=self.fonts['small'],
            relief='flat',
            bd=0,
            padx=15,
            pady=15,
            wrap='word',
            state='disabled'
        )
        self.status_text.pack(fill='both', expand=True)
        
        # Add initial status message
        self.update_status("Ready to transfer files. Select a file and choose transfer method.")
        
    def create_modern_button(self, parent, text, command, bg_color, hover_color, width=None):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=self.fonts['button'],
            bg=bg_color,
            fg='white',
            relief='flat',
            bd=0,
            padx=20,
            pady=12,
            cursor='hand2',
            activebackground=hover_color,
            activeforeground='white'
        )
        
        if width:
            btn.configure(width=width//8)  # Approximate character width
        
        # Hover effects
        def on_enter(e):
            btn.configure(bg=hover_color)
            
        def on_leave(e):
            btn.configure(bg=bg_color)
            
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        
        return btn
        
    def create_animations(self):
        # Simple pulsing animation for the title (optional)
        pass
        
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a file to transfer",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt"),
                ("Images", "*.png *.jpg *.jpeg *.gif"),
                ("Documents", "*.pdf *.doc *.docx")
            ]
        )
        
        if file_path:
            self.selected_file = file_path
            filename = os.path.basename(file_path)
            
            # Get file size
            try:
                size = os.path.getsize(file_path)
                size_str = self.format_file_size(size)
            except:
                size_str = "Size unknown"
            
            # Update UI
            self.file_name_label.configure(text=f"📄 {filename}")
            self.file_size_label.configure(text=f"Size: {size_str} • Path: {file_path}")
            self.file_info_frame.pack(fill='x', pady=(10, 0))
            
            self.update_status(f"File selected: {filename} ({size_str})")
            
            # Enable transfer buttons
            self.tcp_btn.configure(state='normal')
            self.rdma_btn.configure(state='normal')
        
    def format_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
        
    def send_tcp(self):
        if not self.selected_file:
            messagebox.showwarning("No File Selected", "Please select a file first.")
            return
            
        filename = os.path.basename(self.selected_file)
        self.update_status(f"🔄 Initiating TCP transfer for {filename}...")
        self.root.after(1000, lambda: self.update_status("📡 TCP transfer completed successfully! (Demo mode)"))
        messagebox.showinfo("TCP Transfer", f"File '{filename}' sent via TCP\n\n(This is a demo - no actual transfer performed)")
        
    def send_rdma(self):
        if not self.selected_file:
            messagebox.showwarning("No File Selected", "Please select a file first.")
            return
            
        filename = os.path.basename(self.selected_file)
        self.update_status(f"🔄 Initiating RDMA transfer for {filename}...")
        self.root.after(800, lambda: self.update_status("⚡ RDMA transfer completed at high speed! (Demo mode)"))
        messagebox.showinfo("RDMA Transfer", f"File '{filename}' sent via RDMA\n\n(This is a demo - no actual transfer performed)")
        
    def update_status(self, message):
        self.status_text.configure(state='normal')
        self.status_text.insert('end', f"[{self.get_timestamp()}] {message}\n")
        self.status_text.configure(state='disabled')
        self.status_text.see('end')
        
    def get_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
        
    def run(self):
        # Initially disable transfer buttons
        self.tcp_btn.configure(state='disabled')
        self.rdma_btn.configure(state='disabled')
        
        # Center the window
        self.center_window()
        
        # Start the application
        self.root.mainloop()
        
    def center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.root.winfo_screenheight() // 2) - (700 // 2)
        self.root.geometry(f"600x700+{x}+{y}")

# Run the application
if __name__ == "__main__":
    app = ModernRDMAApp()
    app.run()