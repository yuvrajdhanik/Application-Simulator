from enum import Enum
import random

class ThreadState(Enum):
    NEW = 'NEW'
    READY = 'READY'
    RUNNING = 'RUNNING'
    BLOCKED = 'BLOCKED'
    TERMINATED = 'TERMINATED'

STATE_COLOR = {
    ThreadState.NEW: '#7f8c8d',       # Grey
    ThreadState.READY: '#2ecc71',     # Green
    ThreadState.RUNNING: '#3498db',   # Blue
    ThreadState.BLOCKED: '#e67e22',   # Orange
    ThreadState.TERMINATED: '#95a5a6' # Concrete
}

def rand_bursts(count=3, max_len=5):
    bursts = []
    for i in range(count):
        cpu = random.randint(1, max_len)
        io = random.randint(0, max_len) if i < count-1 else 0
        bursts.append((cpu, io))
    return bursts

# ========================= simulator.py =========================

import threading
import time
import queue
from collections import deque

class SimThread:
    def __init__(self, tid, bursts=None, state_enum=None):
        self.tid = tid
        self.bursts = bursts or rand_bursts()
        self.state = state_enum.NEW if state_enum else 'NEW'
        self.current_burst_remaining = 0
        self.lock = threading.Lock()
        self.timeline = []  # list of (timestamp, state)

    def start_ready(self):
        with self.lock:
            if self.state == 'NEW' or getattr(self.state, 'value', None) == 'NEW':
                self.state = 'READY'
                self.current_burst_remaining = self.bursts[0][0]

    def to_running(self):
        with self.lock:
            self.state = 'RUNNING'

    def to_blocked(self):
        with self.lock:
            self.state = 'BLOCKED'

    def to_ready(self):
        with self.lock:
            self.state = 'READY'

    def terminate(self):
        with self.lock:
            self.state = 'TERMINATED'

class Scheduler:
    def __init__(self, model='Many-to-Many', cpu_cores=1, quantum=1):
        self.model = model
        self.cpu_cores = cpu_cores
        self.quantum = quantum
        self.ready_queue = deque()
        self.blocked = []
        self.running = []
        self.all_threads = []
        self.time = 0
        self.lock = threading.Lock()
        self.event_queue = queue.Queue()
        self.running_flag = False

    def add_thread(self, simthread: SimThread):
        self.all_threads.append(simthread)
        simthread.start_ready()
        self.ready_queue.append(simthread)
        self._emit('added', simthread)

    def _emit(self, ev, data=None):
        self.event_queue.put((self.time, ev, data))

    def reset(self):
        """Resets the simulation state entirely."""
        self.stop()
        with self.lock:
            self.time = 0
            self.ready_queue.clear()
            self.blocked.clear()
            self.running.clear()
            self.all_threads.clear()
            # Clear event queue
            with self.event_queue.mutex:
                self.event_queue.queue.clear()

    def step(self):
        with self.lock:
            self.time += 1
            # 1. IO Unblocking
            new_ready = []
            still_blocked = []
            for (th, remaining_io) in list(self.blocked):
                remaining_io -= 1
                if remaining_io <= 0:
                    th.to_ready()
                    new_ready.append(th)
                    self._emit('unblocked', th)
                else:
                    still_blocked.append((th, remaining_io))
            self.blocked = still_blocked
            
            # Add unblocked to ready queue
            for th in new_ready:
                self.ready_queue.append(th)

            # 2. Scheduling (Fill empty cores)
            self.running = [th for th in self.running if th.state == 'RUNNING']
            
            vacancies = self.cpu_cores - len(self.running)
            for _ in range(vacancies):
                if self.ready_queue:
                    th = self.ready_queue.popleft()
                    th.to_running()
                    self.running.append(th)
                    self._emit('running', th)

            # 3. Execution
            for th in list(self.running):
                th.current_burst_remaining -= 1
                th.timeline.append((self.time, th.state))
                
                if th.current_burst_remaining <= 0:
                    # Burst finished
                    if len(th.bursts) > 1:
                        th.bursts.pop(0)
                        io_time = th.bursts[0][1]
                        if io_time > 0:
                            th.to_blocked()
                            self.blocked.append((th, io_time))
                            self._emit('blocked', th)
                        else:
                            th.to_ready()
                            th.current_burst_remaining = th.bursts[0][0]
                            self.ready_queue.append(th)
                            self._emit('ready', th)
                    else:
                        th.terminate()
                        self._emit('terminated', th)

            self._emit('tick', None)

            # 4. Check for Completion (NEW LOGIC)
            if self.all_threads:
                all_done = True
                for th in self.all_threads:
                    s = th.state
                    if hasattr(s, 'value'): s = s.value
                    if s != 'TERMINATED':
                        all_done = False
                        break
                
                if all_done:
                    self.stop()
                    self._emit('finished', None)

    def run(self, speed=0.5):
        self.running_flag = True
        while self.running_flag:
            self.step()
            time.sleep(speed)

    def stop(self):
        self.running_flag = False

# ========================= app.py (Tkinter + ttk) =========================

import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import threading
import time

# Colors
COLOR_BG = "#2b2b2b"      # Dark Grey Background
COLOR_PANEL = "#3c3f41"   # Panel Grey
COLOR_FG = "#ffffff"      # White Text
COLOR_ACCENT = "#3498db"  # Blue Accent
COLOR_BTN_BG = "#505050"  # Button standard

STATE_COLOR_STR = {
    'NEW': '#7f8c8d',
    'READY': '#2ecc71',
    'RUNNING': '#3498db',
    'BLOCKED': '#e67e22',
    'TERMINATED': '#95a5a6'
}

class SimulatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Real-Time OS Simulator')
        self.geometry('1200x750')
        self.configure(bg=COLOR_BG)
        
        # Setup Style
        self._setup_style()

        # Layout Containers
        self.top_frame = ttk.Frame(self, style="Panel.TFrame")
        self.top_frame.pack(side='top', fill='x', padx=10, pady=10)
        
        self.content_frame = tk.Frame(self, bg=COLOR_BG)
        self.content_frame.pack(side='bottom', fill='both', expand=True, padx=10, pady=(0,10))

        # UI Components
        self._build_controls()
        self._build_thread_list()
        self._build_visual()
        
        # Simulator Logic
        self.scheduler = Scheduler()
        self.sim_thread = None
        self.ui_update_job = None
        self._start_ui_updater()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('clam') 
        style.configure(".", background=COLOR_BG, foreground=COLOR_FG, font=('Segoe UI', 10))
        style.configure("Panel.TFrame", background=COLOR_PANEL, relief='flat')
        style.configure("TButton", background=COLOR_BTN_BG, foreground=COLOR_FG, borderwidth=0, focuscolor=COLOR_ACCENT, padding=6)
        style.map("TButton", background=[('active', COLOR_ACCENT), ('disabled', '#333333')], foreground=[('disabled', '#888888')])
        style.configure("Accent.TButton", background=COLOR_ACCENT, font=('Segoe UI', 10, 'bold'))
        style.configure("TCombobox", fieldbackground=COLOR_BTN_BG, background=COLOR_BTN_BG, foreground=COLOR_FG, arrowcolor=COLOR_FG)
        style.map("TCombobox", fieldbackground=[('readonly', COLOR_BTN_BG)])
        style.configure("TLabel", background=COLOR_PANEL, foreground=COLOR_FG)

    def _build_controls(self):
        # --- Config Section ---
        config_frame = tk.LabelFrame(self.top_frame, text="Configuration", bg=COLOR_PANEL, fg=COLOR_FG, bd=0, font=('Segoe UI', 9, 'bold'))
        config_frame.pack(side='left', padx=10, pady=5, fill='y')
        
        # Model
        ttk.Label(config_frame, text='Threading Model:').pack(side='left', padx=(5,2))
        self.model_var = tk.StringVar(value='Many-to-Many')
        ttk.Combobox(config_frame, textvariable=self.model_var, values=['Many-to-One','One-to-Many','Many-to-Many'], state='readonly', width=14).pack(side='left', padx=5)
        
        # Cores
        ttk.Label(config_frame, text='Cores:').pack(side='left', padx=(10,2))
        self.cores_var = tk.IntVar(value=2)
        tk.Spinbox(config_frame, from_=1, to=16, textvariable=self.cores_var, width=3, bg=COLOR_BTN_BG, fg=COLOR_FG, buttonbackground=COLOR_BTN_BG).pack(side='left', padx=5)

        # Primitive
        ttk.Label(config_frame, text='Sync:').pack(side='left', padx=(10,2))
        self.prim_var = tk.StringVar(value='Semaphore')
        ttk.Combobox(config_frame, textvariable=self.prim_var, values=['Semaphore','Monitor'], state='readonly', width=10).pack(side='left', padx=5)

        # --- Actions Section ---
        action_frame = tk.LabelFrame(self.top_frame, text="Actions", bg=COLOR_PANEL, fg=COLOR_FG, bd=0, font=('Segoe UI', 9, 'bold'))
        action_frame.pack(side='right', padx=10, pady=5, fill='y')

        ttk.Button(action_frame, text='+ Add Threads', command=self._add_threads).pack(side='left', padx=5)
        ttk.Button(action_frame, text='Start', style="Accent.TButton", command=self._start_sim).pack(side='left', padx=5)
        ttk.Button(action_frame, text='Pause', command=self._pause_sim).pack(side='left', padx=5)
        
        # Reset Button
        self.reset_btn = ttk.Button(action_frame, text='Reset', command=self._reset_sim)
        self.reset_btn.pack(side='left', padx=5)

    def _build_thread_list(self):
        left_pane = tk.Frame(self.content_frame, bg=COLOR_PANEL, width=250)
        left_pane.pack(side='left', fill='y', padx=(0, 10))
        left_pane.pack_propagate(False) 
        
        lbl = tk.Label(left_pane, text="PROCESS TABLE", bg=COLOR_PANEL, fg="#aaaaaa", font=('Segoe UI', 9, 'bold'))
        lbl.pack(pady=10)

        self.thread_listbox = tk.Listbox(left_pane, bg=COLOR_BG, fg=COLOR_FG, bd=0, highlightthickness=0, selectbackground=COLOR_ACCENT, font=('Consolas', 10))
        self.thread_listbox.pack(fill='both', expand=True, padx=10, pady=10)

    def _build_visual(self):
        right_pane = tk.Frame(self.content_frame, bg=COLOR_PANEL)
        right_pane.pack(side='right', fill='both', expand=True)

        self.fig, self.ax = plt.subplots(figsize=(8,5))
        self.fig.patch.set_facecolor(COLOR_PANEL)
        self.ax.set_facecolor(COLOR_BG)           
        
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.ax.tick_params(colors='white')
        self.ax.yaxis.label.set_color('white')
        self.ax.xaxis.label.set_color('white')
        self.ax.title.set_color('white')

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_pane)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        self.ax.set_title('CPU Scheduling Timeline')
        self.ax.set_xlabel('Time Units')

    def _add_threads(self):
        start_id = len(self.scheduler.all_threads) + 1
        for i in range(5):
            tid = f'T{start_id+i:02d}'
            th = SimThread(tid)
            self.scheduler.add_thread(th)
        self._refresh_listbox()

    def _refresh_listbox(self):
        self.thread_listbox.delete(0, tk.END)
        for th in self.scheduler.all_threads:
            state = th.state if isinstance(th.state, str) else getattr(th.state, 'value', str(th.state))
            self.thread_listbox.insert(tk.END, f"{th.tid} : {state}")
            idx = self.thread_listbox.size() - 1
            color = STATE_COLOR_STR.get(state, 'white')
            self.thread_listbox.itemconfig(idx, foreground=color)

    def _start_sim(self):
        self.scheduler.cpu_cores = max(1,int(self.cores_var.get()))
        self.scheduler.model = self.model_var.get()
        if self.sim_thread and self.sim_thread.is_alive():
            if not self.scheduler.running_flag:
                self.sim_thread = threading.Thread(target=self.scheduler.run, kwargs={'speed':0.2}, daemon=True)
                self.sim_thread.start()
        else:
            self.sim_thread = threading.Thread(target=self.scheduler.run, kwargs={'speed':0.2}, daemon=True)
            self.sim_thread.start()

    def _pause_sim(self):
        self.scheduler.stop()

    def _reset_sim(self):
        self.scheduler.reset()
        self.thread_listbox.delete(0, tk.END)
        self.ax.clear()
        self.ax.set_title('CPU Scheduling Timeline')
        self.ax.set_xlabel('Time Units')
        
        self.ax.set_facecolor(COLOR_BG)
        self.ax.tick_params(colors='white')
        
        self.canvas.draw()
        self._refresh_listbox()

    def _start_ui_updater(self):
        def updater():
            try:
                while True:
                    time_, ev, data = self.scheduler.event_queue.get_nowait()
                    self._handle_event(time_, ev, data) 
            except queue.Empty:
                pass
            
            self._refresh_listbox()
            self._draw_timeline()
            self.ui_update_job = self.after(200, updater)
        updater()
    
    def _handle_event(self, time_, ev, data):
        if ev == 'finished':
            messagebox.showinfo("Simulation", "All processes completed successfully!")

    def _draw_timeline(self):
        if not self.scheduler.all_threads:
            return

        self.ax.clear()
        y = 0
        yticks = []
        ylabels = []
        
        for th in sorted(self.scheduler.all_threads, key=lambda x: x.tid):
            segs = []
            last_state = None
            last_time = 0
            
            for (t, s) in th.timeline:
                if last_state is None:
                    last_state = s
                    last_time = t
                elif s == last_state:
                    continue
                else:
                    segs.append((last_time, t-last_time, last_state))
                    last_state = s
                    last_time = t
            
            if last_state is not None:
                segs.append((last_time, self.scheduler.time - last_time + 1, last_state))
            
            for (start, length, s) in segs:
                color = STATE_COLOR_STR.get(s, '#666666')
                self.ax.broken_barh([(start, length)], (y, 0.6), facecolors=color, edgecolor=COLOR_BG, linewidth=0.5)
            
            yticks.append(y + 0.3)
            ylabels.append(th.tid)
            y += 1
        
        self.ax.set_yticks(yticks)
        self.ax.set_yticklabels(ylabels)
        self.ax.set_xlabel('Time (Ticks)')
        self.ax.set_title(f'Scheduling Timeline (t={self.scheduler.time})')
        
        self.ax.set_facecolor(COLOR_BG)
        self.ax.tick_params(colors='white')
        
        self.canvas.draw()

# ========================= main.py =========================

if __name__ == '__main__':
    try:
        app = SimulatorApp()
        app.mainloop()
    except Exception as e:
        print('Error launching the app:', e)
        raise